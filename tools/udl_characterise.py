#!/usr/bin/env python3
"""Characterise real UDL observation noise, on the networked workstation, offline from the app.

Flight plan step 4. **This file never runs in the container and is never packaged into the upload.**
It runs once, on Ash's networked workstation, in Script mode per CONTEXT-001 Section 3. Its only
output that crosses the boundary is a parameter file of DISTRIBUTIONS: no records, no object
identifiers, no credentials. `--emit` refuses to write a file that fails that check.

Standard library only, one file, no third-party import. That is the Script-mode rule and it is also
what makes this runnable on a workstation with no build environment.

WHAT THIS TOOL DOES NOT KNOW, AND WILL NOT GUESS
------------------------------------------------
The UDL base address, its endpoint paths, and the names of its query parameters and record fields
are NOT in the flight plan and are not invented here. They live in an *endpoint profile*, an INI
file the operator writes once from the UDL API documentation. With no profile, every networked mode
refuses to run and names the exact keys it needs. `--print-profile-template` writes the blank.

Everything that does NOT depend on those facts is finished and provable today:

    python3 tools/udl_characterise.py --self-test
    python3 tools/udl_characterise.py --analyse-only records.json --emit noise-model.json

The first runs the analyser against synthetic records with known statistics and prints a JSON
assertion manifest. The second runs it against a saved dump. Both work with no network and no
profile, so the analysis half is verified BEFORE anything touches a live service.

THE LEARNED REGISTER, wired rather than described
-------------------------------------------------
● `Accept: */*` on the history list. A stricter Accept was measured being refused.
● `Accept: text/plain` on the count endpoint. It returns a bare integer, not JSON.
● Time ranges are formatted trailing-Z with microseconds.
● Above the 10,000 `firstResult` cap, TIME-SLICE. Offset pagination past the cap silently truncates,
  which is the failure mode that produces a confident answer from a third of the data. A slice whose
  own count still exceeds the cap is bisected until it fits, and a slice that cannot be bisected
  further is reported as a gap rather than silently sampled.
"""

from __future__ import annotations

import argparse
import configparser
import hashlib
import json
import math
import re
import secrets
import statistics
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any

#: A record as the service returns it: a JSON object whose shape is the API's, not ours. Named
#: rather than written as a bare `dict` so strict typing has something to check against.
Record = dict[str, Any]

TOOL_VERSION = "1.0.0"
PARAMETER_FILE_SCHEMA = "enlightenment.noise-model/1"

#: The window recorded when there is no window: an offline dump that carried none.
_EMPTY_WINDOW = {"from": "", "to": ""}

#: The platform's hard ceiling on offset pagination. Above it, slice time.
FIRST_RESULT_CAP = 10_000

#: Robust outlier bound: median plus or minus this many median-absolute-deviations. Robust rather
#: than standard-deviation based, because the thing being measured IS the outlier rate, and a
#: sigma bound computed from a contaminated sample moves to swallow its own contamination.
DEFAULT_MAD_K = 5.0

#: Recursion bound on slice bisection, and the floor below which a slice is not narrowed
#: further. Both are named so the fail-closed branch is a constant, not a literal in a branch.
MAX_SLICE_DEPTH = 24
MIN_SLICE = timedelta(seconds=1)

#: The minimum sample an outlier rate is computed from. Below it the rate is not reported at
#: all, because a rate over two points is a coin toss dressed as a measurement.
MIN_OUTLIER_SAMPLE = 3

#: The synthetic sample's mean, dragged by one planted outlier, sits above this. A floor rather
#: than an equality, so the assertion survives a change to the synthetic sample's size.
OUTLIER_DRAG_FLOOR = 80.0

#: A gap below this is a near-duplicate elset epoch rather than a real update. The plan calls for
#: near-duplicate epochs to be counted; the threshold is a parameter because the right value is a
#: property of the provider set, not of this tool.
DEFAULT_NEAR_DUPLICATE_SECONDS = 60.0

#: The shape of a satellite catalogue number. The emitted parameter file is checked against this
#: before it is written: a distribution file has no reason to contain one, and the check is cheaper
#: than the review that would otherwise have to catch it.
CATALOGUE_NUMBER_PATTERN = re.compile(
    r"(?<![0-9A-Za-z_-])(?<![0-9]\.)[0-9]{5,8}(?![0-9A-Za-z_-])(?!\.[0-9])"
)


class ProfileError(RuntimeError):
    """The endpoint profile is missing or incomplete. The message names the exact keys needed."""


class BoundaryError(RuntimeError):
    """Something that must not cross the boundary was found in the output."""


# --------------------------------------------------------------------------------------
# The endpoint profile: every fact this tool refuses to invent, in one file.
# --------------------------------------------------------------------------------------

PROFILE_TEMPLATE = """\
# UDL endpoint profile for tools/udl_characterise.py
#
# Fill every value from the UDL API documentation. This tool will not guess any of them.
# Keep this file OUT of the repository: it is workstation configuration, not content.
#
# Nothing here is a secret. Credentials live in ~/.config/phase_offset/credentials.ini.

[endpoints]
# Scheme and host only, no trailing slash.
base_url =
# Path returning a LIST of historical observations for a time range.
observation_history_path =
# Path returning a BARE INTEGER count for the same time range. Queried first, so the tool knows
# whether it must time-slice before it fetches anything.
observation_count_path =
# The same pair for element sets, used for the epoch-spacing measure.
elset_history_path =
elset_count_path =

[query]
# The query parameter carrying the observation time RANGE. The plan records this as obTime.
time_field = obTime
# The parameter names for offset pagination within one time slice.
first_result_param = firstResult
max_results_param = maxResults
# How many records to request per page. Must not exceed the platform maximum.
page_size = 1000
# The parameter naming which columns to return, and its separator, if the API supports projection.
# Leave columns_param blank if it does not; the tool then requests whole records.
columns_param =
columns_separator = ,

[fields]
# Record field names. Every one is read; NONE is emitted verbatim except the marking distribution.
# Leave a value blank and the measures depending on it are reported as unavailable rather
# than estimated. That is the fail-closed behaviour: an absent measure is honest, and an
# invented one is not.
sensor_id =
observation_time = obTime
azimuth_residual =
elevation_residual =
range_residual =
magnitude =
magnitude_uncertainty =
classification_marking =
correlation_quality =
elset_epoch =
# Read for GROUPING only, to compute per-object revisit and epoch spacing. Replaced by a per-run
# salted pseudonym before any statistic is computed, and never written to the output.
object_identifier =
"""

_PROFILE_REQUIRED: dict[str, tuple[str, ...]] = {
    "endpoints": (
        "base_url",
        "observation_history_path",
        "observation_count_path",
        "elset_history_path",
        "elset_count_path",
    ),
    "query": ("time_field", "first_result_param", "max_results_param", "page_size"),
    "fields": ("sensor_id", "observation_time", "object_identifier"),
}


@dataclass(frozen=True, slots=True)
class Profile:
    """The resolved endpoint profile. Constructed only when every required key is present."""

    endpoints: dict[str, str]
    query: dict[str, str]
    fields: dict[str, str]
    digest: str

    @classmethod
    def load(cls, path: Path) -> Profile:
        if not path.is_file():
            raise ProfileError(
                f"no endpoint profile at {path}. Write one with"
                " `--print-profile-template > udl-profile.ini` and fill it from the UDL API"
                " documentation. This tool does not guess an API shape"
            )
        raw = path.read_text(encoding="utf-8")
        parser = configparser.ConfigParser(interpolation=None)
        parser.read_string(raw)

        missing = [
            f"[{section}] {key}"
            for section, keys in _PROFILE_REQUIRED.items()
            for key in keys
            if not parser.get(section, key, fallback="").strip()
        ]
        if missing:
            raise ProfileError(
                f"{path} is incomplete. These keys are required and empty: "
                + ", ".join(missing)
                + ". Every one is a fact about the UDL API that this tool will not invent"
            )

        base = parser.get("endpoints", "base_url", fallback="").strip()
        scheme = urllib.parse.urlsplit(base).scheme.lower()
        if scheme != "https":
            # A REAL finding, raised by the pinned linter and fixed rather than suppressed:
            # `urlopen` honours `file:` and every other registered scheme, so an operator typo or
            # a copied-in path would turn a retrieval into a local file read against a header
            # carrying live credentials. Allowlisted to one scheme, refused rather than corrected,
            # because silently rewriting `http` to `https` hides a profile that is wrong.
            raise ProfileError(
                f"{path}: [endpoints] base_url must be an https:// address; found scheme"
                f" {scheme!r}. Only https is allowed, and it is not inferred from a bare host"
            )

        section_map = {
            name: {key: value.strip() for key, value in parser.items(name)}
            for name in ("endpoints", "query", "fields")
            if parser.has_section(name)
        }
        return cls(
            endpoints=section_map.get("endpoints", {}),
            query=section_map.get("query", {}),
            fields=section_map.get("fields", {}),
            # The profile is provenance: the parameter file records WHICH profile produced it, by
            # hash, so a later reader can tell whether two runs queried the same shape.
            digest=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        )

    def field(self, logical: str) -> str | None:
        """The record field name for a logical measure, or None when the operator left it blank."""
        value = self.fields.get(logical, "").strip()
        return value or None


# --------------------------------------------------------------------------------------
# Credentials. Read from disk, used for one header, never logged and never emitted.
# --------------------------------------------------------------------------------------

DEFAULT_CREDENTIALS = Path.home() / ".config" / "phase_offset" / "credentials.ini"


def load_credentials(path: Path) -> tuple[str, str]:
    """Read the UDL username and password. `interpolation=None` per CONTEXT-001.

    Interpolation is off deliberately and it is not cosmetic: a password containing a percent sign
    raises `InterpolationSyntaxError` under the default parser, so a correct credential file fails
    to load and the failure looks like a bad password.
    """
    if not path.is_file():
        raise RuntimeError(f"no credentials file at {path}")
    mode = path.stat().st_mode & 0o777
    if mode & 0o077:
        raise RuntimeError(
            f"{path} is mode {mode:o}, readable beyond its owner. Run `chmod 600 {path}` before"
            " using it. Refused rather than warned: a credential this tool can read, another"
            " local process can read too"
        )
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(path, encoding="utf-8")
    for section in ("udl", "UDL", "DEFAULT"):
        if parser.has_section(section) or section == "DEFAULT":
            user = parser.get(section, "username", fallback="")
            secret = parser.get(section, "password", fallback="")
            if user and secret:
                return user, secret
    raise RuntimeError(
        f"{path} has no section with both `username` and `password`. Looked in [udl], [UDL]"
        " and [DEFAULT]. The values are not echoed here"
    )


# --------------------------------------------------------------------------------------
# Retrieval. Count first, then slice, then page inside a slice.
# --------------------------------------------------------------------------------------


def _utc_stamp(moment: datetime) -> str:
    """Trailing-Z with microseconds, which is the form the service was measured accepting."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass(slots=True)
class Fetcher:
    """Retrieves records for a time window, honouring the LEARNED register."""

    profile: Profile
    credentials: tuple[str, str]
    timeout: float = 120.0
    verbose: bool = False
    gaps: list[dict[str, str]] = field(default_factory=list)

    def _request(self, url: str, accept: str) -> str:
        user, secret = self.credentials
        # The scheme is allowlisted to https in `Profile.load`, which runs before any request
        # is built, so the audit this rule raises is answered at the only place a scheme can
        # enter: the operator-written profile.
        request = urllib.request.Request(url, method="GET")  # noqa: S310
        request.add_header("Accept", accept)
        token = f"{user}:{secret}".encode()
        import base64  # noqa: PLC0415 - stdlib, imported at use so the header is the only user

        request.add_header("Authorization", "Basic " + base64.b64encode(token).decode("ascii"))
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                body: bytes = response.read()
            return body.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            # The URL is echoed WITHOUT its query string. A query carries the time window, which is
            # harmless, but this is the one place a credential could reach a log if the profile ever
            # grew a token parameter, and a rule that holds only for today's profile is not a rule.
            raise RuntimeError(
                f"HTTP {exc.code} from {urllib.parse.urlsplit(url).path}: {exc.reason}"
            ) from None
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"cannot reach {urllib.parse.urlsplit(url).netloc}: {exc.reason}"
            ) from None

    def _url(self, path: str, params: dict[str, str]) -> str:
        base = self.profile.endpoints["base_url"].rstrip("/")
        return f"{base}/{path.lstrip('/')}?{urllib.parse.urlencode(params)}"

    def _range(self, start: datetime, end: datetime) -> dict[str, str]:
        time_field = self.profile.query["time_field"]
        return {time_field: f"{_utc_stamp(start)}..{_utc_stamp(end)}"}

    def count(self, count_path: str, start: datetime, end: datetime) -> int:
        """The count endpoint returns a BARE INTEGER under `Accept: text/plain`, not JSON."""
        body = self._request(self._url(count_path, self._range(start, end)), "text/plain").strip()
        try:
            return int(body)
        except ValueError:
            raise RuntimeError(
                f"the count endpoint returned {len(body)} characters that are not an integer."
                " Check [endpoints] observation_count_path in the profile"
            ) from None

    def _page(self, history_path: str, start: datetime, end: datetime, offset: int) -> list[Record]:
        params = self._range(start, end)
        params[self.profile.query["first_result_param"]] = str(offset)
        params[self.profile.query["max_results_param"]] = self.profile.query.get(
            "page_size", "1000"
        )
        body = self._request(self._url(history_path, params), "*/*")
        payload = json.loads(body)
        if isinstance(payload, dict):
            for key in ("data", "results", "items"):
                if isinstance(payload.get(key), list):
                    return [row for row in payload[key] if isinstance(row, dict)]
            raise RuntimeError(
                "the history endpoint returned an object with no list under data, results or"
                " items. Record the real key in the profile rather than letting this tool guess"
            )
        if not isinstance(payload, list):
            raise TypeError(
                f"the history endpoint returned {type(payload).__name__}, expected a list"
            )
        return [row for row in payload if isinstance(row, dict)]

    def fetch(
        self, history_path: str, count_path: str, start: datetime, end: datetime, depth: int = 0
    ) -> list[Record]:
        """Every record in the window, time-sliced whenever the count exceeds the offset cap."""
        total = self.count(count_path, start, end)
        if self.verbose:
            print(f"  {_utc_stamp(start)} to {_utc_stamp(end)}: {total} records", file=sys.stderr)
        if total == 0:
            return []
        if total > FIRST_RESULT_CAP:
            span = end - start
            if span <= MIN_SLICE or depth > MAX_SLICE_DEPTH:
                # Reported, never silently sampled. A truncated slice would make every statistic
                # below it a statement about an unknown subset.
                self.gaps.append(
                    {
                        "from": _utc_stamp(start),
                        "to": _utc_stamp(end),
                        "count": str(total),
                        "reason": "count exceeds the offset cap and the slice cannot be narrowed"
                        " further; this window is NOT represented in the measures",
                    }
                )
                return []
            middle = start + span / 2
            return self.fetch(history_path, count_path, start, middle, depth + 1) + self.fetch(
                history_path, count_path, middle, end, depth + 1
            )

        page_size = max(1, int(self.profile.query.get("page_size") or "1000"))
        rows: list[Record] = []
        offset = 0
        while offset < total and offset < FIRST_RESULT_CAP:
            page = self._page(history_path, start, end, offset)
            if not page:
                break
            rows.extend(page)
            offset += page_size
        return rows


# --------------------------------------------------------------------------------------
# The analyser. Pure functions over records; no network, no credentials, no profile needed
# beyond the field map.
# --------------------------------------------------------------------------------------


def _numbers(values: list[Any]) -> list[float]:
    out: list[float] = []
    for value in values:
        if isinstance(value, bool) or value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            out.append(number)
    return out


def summarise(values: list[float]) -> dict[str, float] | None:
    """The distribution a scenario generator can sample from. None when there is nothing to say.

    Percentiles are computed by nearest-rank on the sorted sample rather than by interpolation,
    because the consumer samples from this and an interpolated percentile can name a value that
    never occurred.
    """
    sample = sorted(values)
    if not sample:
        return None
    size = len(sample)

    def rank(fraction: float) -> float:
        index = min(size - 1, max(0, round(fraction * (size - 1))))
        return sample[index]

    result = {
        "n": float(size),
        "min": sample[0],
        "p05": rank(0.05),
        "p25": rank(0.25),
        "median": rank(0.50),
        "p75": rank(0.75),
        "p95": rank(0.95),
        "max": sample[-1],
        "mean": statistics.fmean(sample),
        "mad": statistics.median([abs(value - rank(0.50)) for value in sample]),
    }
    result["stdev"] = statistics.stdev(sample) if size > 1 else 0.0
    return result


def outlier_rate(values: list[float], mad_k: float) -> dict[str, float] | None:
    """Fraction of the sample beyond median plus or minus `mad_k` median-absolute-deviations."""
    sample = sorted(values)
    if len(sample) < MIN_OUTLIER_SAMPLE:
        return None
    median = statistics.median(sample)
    mad = statistics.median([abs(value - median) for value in sample])
    if mad == 0.0:
        return {"rate": 0.0, "n": float(len(sample)), "bound": 0.0, "undetermined": 1.0}
    bound = mad_k * mad
    beyond = sum(1 for value in sample if abs(value - median) > bound)
    return {
        "rate": beyond / len(sample),
        "n": float(len(sample)),
        "bound": bound,
        "undetermined": 0.0,
    }


def _gaps_seconds(times: list[datetime]) -> list[float]:
    ordered = sorted(times)
    return [(later - earlier).total_seconds() for earlier, later in pairwise(ordered)]


def parse_time(value: Any) -> datetime | None:
    """Parse a UDL timestamp. Trailing Z is normalised; anything unparsable is None, not a guess."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


@dataclass(slots=True)
class Analyser:
    """Turns records into distributions. Holds a per-run salt so no object identifier is emitted."""

    fields: dict[str, str | None]
    mad_k: float = DEFAULT_MAD_K
    near_duplicate_seconds: float = DEFAULT_NEAR_DUPLICATE_SECONDS
    pseudonymise_sensors: bool = True
    _salt: str = field(default_factory=lambda: secrets.token_hex(16))

    def _pseudonym(self, value: Any) -> str:
        digest = hashlib.sha256(f"{self._salt}:{value}".encode()).hexdigest()
        return digest[:12]

    def _sensor_label(self, value: Any) -> str:
        if value is None:
            return "unattributed"
        return self._pseudonym(value) if self.pseudonymise_sensors else str(value)

    def _get(self, row: Record, logical: str) -> Any:
        name = self.fields.get(logical)
        return row.get(name) if name else None

    _RESIDUAL_FIELDS = (
        "azimuth_residual",
        "elevation_residual",
        "range_residual",
        "magnitude",
        "magnitude_uncertainty",
    )

    def _accumulate(self, observations: list[Record]) -> dict[str, Any]:
        """One pass over the observations, gathering everything the per-sensor measures need."""
        per_sensor: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        revisit: dict[str, dict[str, list[datetime]]] = defaultdict(lambda: defaultdict(list))
        markings: Counter[str] = Counter()
        correlation: list[float] = []
        present: Counter[str] = Counter()

        for row in observations:
            sensor = self._sensor_label(self._get(row, "sensor_id"))
            for logical in self._RESIDUAL_FIELDS:
                value = _numbers([self._get(row, logical)])
                if value:
                    per_sensor[sensor][logical].append(value[0])
            moment = parse_time(self._get(row, "observation_time"))
            if moment is not None:
                revisit[sensor][self._pseudonym(self._get(row, "object_identifier"))].append(moment)
            marking = self._get(row, "classification_marking")
            if isinstance(marking, str) and marking.strip():
                markings[marking.strip()] += 1
            correlation.extend(_numbers([self._get(row, "correlation_quality")]))
            present.update(self._present_fields(row))

        return {
            "per_sensor": per_sensor,
            "revisit": revisit,
            "markings": markings,
            "correlation": correlation,
            "present": present,
        }

    def _present_fields(self, row: Record) -> list[str]:
        """Which mapped fields this record actually carries. Drives the missing-field rate."""
        logicals = (
            "sensor_id",
            "observation_time",
            *self._RESIDUAL_FIELDS,
            "classification_marking",
            "correlation_quality",
        )
        return [
            logical
            for logical in logicals
            if self.fields.get(logical) and self._get(row, logical) not in (None, "")
        ]

    def _sensor_measures(
        self,
        per_sensor: dict[str, dict[str, list[float]]],
        revisit: dict[str, dict[str, list[datetime]]],
    ) -> dict[str, Any]:
        """Per sensor: a distribution and outlier rate per residual, plus revisit spacing."""
        sensors: dict[str, Any] = {}
        for sensor, measures in sorted(per_sensor.items()):
            entry: dict[str, Any] = {
                logical: {
                    "distribution": summarise(values),
                    "outliers": outlier_rate(values, self.mad_k),
                }
                for logical, values in sorted(measures.items())
            }
            gaps: list[float] = []
            for times in revisit[sensor].values():
                gaps.extend(_gaps_seconds(times))
            entry["revisit_seconds"] = summarise(gaps)
            entry["observation_count"] = (
                len([value for values in measures.values() for value in values]) or None
            )
            sensors[sensor] = entry
        return sensors

    def _elset_measures(self, elsets: list[Record]) -> dict[str, Any]:
        """Epoch spacing per object, and how many of those gaps are near-duplicates."""
        by_object: dict[str, list[datetime]] = defaultdict(list)
        for row in elsets:
            moment = parse_time(self._get(row, "elset_epoch"))
            if moment is not None:
                by_object[self._pseudonym(self._get(row, "object_identifier"))].append(moment)

        epoch_gaps: list[float] = []
        near_duplicates = 0
        for times in by_object.values():
            for gap in _gaps_seconds(times):
                epoch_gaps.append(gap)
                if gap <= self.near_duplicate_seconds:
                    near_duplicates += 1

        return {
            "elset_epoch_spacing_seconds": summarise(epoch_gaps),
            "elset_near_duplicate_epochs": {
                "count": near_duplicates,
                "of_gaps": len(epoch_gaps),
                "threshold_seconds": self.near_duplicate_seconds,
            },
        }

    def _missing_rates(self, present: Counter[str], total: int) -> dict[str, float]:
        """Fraction of records lacking each MAPPED field. An unmapped field is not a rate at all.

        The denominator is the total record count, not the count that carried the field, which is
        the whole point: a rate over its own numerator is always zero.
        """
        if not total:
            return {}
        return {
            logical: round(1.0 - (present[logical] / total), 6)
            for logical in sorted(name for name, value in self.fields.items() if value)
            if logical in present or logical in self._RESIDUAL_FIELDS
        }

    def analyse(self, observations: list[Record], elsets: list[Record]) -> dict[str, Any]:
        """The whole measurement, assembled from the passes above."""
        gathered = self._accumulate(observations)
        total = len(observations)
        return {
            "record_counts": {"observations": total, "elsets": len(elsets)},
            "sensors": self._sensor_measures(gathered["per_sensor"], gathered["revisit"]),
            **self._elset_measures(elsets),
            "missing_field_rate": self._missing_rates(gathered["present"], total),
            "classification_marking_distribution": dict(sorted(gathered["markings"].items())),
            "correlation_quality": summarise(gathered["correlation"]),
            "measures_unavailable": sorted(
                name for name, value in self.fields.items() if not value
            ),
            "sensor_labels": "pseudonymised" if self.pseudonymise_sensors else "verbatim",
        }


# --------------------------------------------------------------------------------------
# The boundary. Only a parameter file of distributions crosses it.
# --------------------------------------------------------------------------------------


def assert_crossable(payload: Any, path: str = "$") -> None:
    """Refuse to emit anything that looks like an identifier rather than a distribution.

    Walks the whole structure. Numbers are fine: a distribution is numbers. STRINGS are where an
    identifier would hide, so every string is checked against the catalogue-number shape and against
    the URL shape. The classification-marking keys are the one class of verbatim string that is
    meant to cross, and they are checked like everything else rather than exempted, because a
    marking is a short token and has no reason to look like either.
    """
    if isinstance(payload, dict):
        for key, value in payload.items():
            assert_crossable(key, f"{path}.{key}")
            assert_crossable(value, f"{path}.{key}")
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            assert_crossable(value, f"{path}[{index}]")
    elif isinstance(payload, str):
        if CATALOGUE_NUMBER_PATTERN.search(payload):
            raise BoundaryError(
                f"{path} holds a bare 5-to-8 digit run, which is the shape of a catalogue number."
                " A parameter file of distributions has no reason to contain one. The value is"
                " deliberately not echoed"
            )
        if re.search(r"\b[a-z][a-z0-9+.-]*://", payload):
            raise BoundaryError(f"{path} holds a URL. Only distributions cross the boundary")


def build_parameter_file(
    measures: dict[str, Any],
    *,
    window: dict[str, str],
    profile_digest: str | None,
    gaps: list[dict[str, str]],
) -> dict[str, Any]:
    """The one artefact that crosses: distributions plus the provenance to judge them by."""
    return {
        "schema": PARAMETER_FILE_SCHEMA,
        "tool_version": TOOL_VERSION,
        "provenance": {
            "window": window,
            "endpoint_profile_sha256": profile_digest,
            "unrepresented_windows": gaps,
            "note": "Distributions only. No records, no object identifiers, no credentials."
            " Review on the same cycle as the procedure library, and re-run on any known change"
            " to the UDL provider set.",
        },
        "measures": measures,
    }


# --------------------------------------------------------------------------------------
# --self-test: the analyser proved against synthetic records with known statistics.
# --------------------------------------------------------------------------------------

_SELF_TEST_FIELDS = {
    "sensor_id": "sensorId",
    "observation_time": "obTime",
    "azimuth_residual": "azResid",
    "elevation_residual": "elResid",
    "range_residual": None,
    "magnitude": "mag",
    "magnitude_uncertainty": "magUnc",
    "classification_marking": "classificationMarking",
    "correlation_quality": "corrQuality",
    "elset_epoch": "epoch",
    "object_identifier": "idOnOrbit",
}


def _synthetic() -> tuple[list[Record], list[Record]]:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    # Sensor A: eleven observations of one object at exactly 60-second spacing, residuals 0..10,
    # so median, percentiles and revisit are all known by construction.
    observations: list[Record] = [
        {
            "sensorId": "SENSOR-A",
            "obTime": _utc_stamp(base + timedelta(seconds=60 * index)),
            "azResid": float(index),
            "elResid": float(index),
            "mag": 7.0,
            "magUnc": 0.1,
            "classificationMarking": "UNCLASSIFIED",
            "corrQuality": 0.9,
            "idOnOrbit": "SYNTHETIC-OBJECT-ONE",
        }
        for index in range(11)
    ]
    # One gross outlier, so the MAD-based rate is exactly 1 in 12.
    observations.append(
        {
            "sensorId": "SENSOR-A",
            "obTime": _utc_stamp(base + timedelta(seconds=660)),
            "azResid": 1000.0,
            "elResid": 5.0,
            "classificationMarking": "UNCLASSIFIED",
            "corrQuality": 0.9,
            "idOnOrbit": "SYNTHETIC-OBJECT-ONE",
        }
    )
    # Sensor B: one observation with a MISSING magnitude, so the missing-field rate is non-zero.
    observations.append(
        {
            "sensorId": "SENSOR-B",
            "obTime": _utc_stamp(base + timedelta(seconds=30)),
            "azResid": 2.0,
            "elResid": 2.0,
            "classificationMarking": "SYNTHETIC-MARKING",
            "corrQuality": 0.4,
            "idOnOrbit": "SYNTHETIC-OBJECT-TWO",
        }
    )
    elsets = [
        {"epoch": _utc_stamp(base), "idOnOrbit": "SYNTHETIC-OBJECT-ONE"},
        # Ten seconds later: a near-duplicate epoch, under the 60-second threshold.
        {"epoch": _utc_stamp(base + timedelta(seconds=10)), "idOnOrbit": "SYNTHETIC-OBJECT-ONE"},
        {"epoch": _utc_stamp(base + timedelta(hours=6)), "idOnOrbit": "SYNTHETIC-OBJECT-ONE"},
    ]
    return observations, elsets


def self_test() -> tuple[bool, dict[str, Any]]:
    """Run the analyser over synthetic records and assert what must hold. Returns the manifest."""
    observations, elsets = _synthetic()
    analyser = Analyser(fields=dict(_SELF_TEST_FIELDS), pseudonymise_sensors=False)
    measures = analyser.analyse(observations, elsets)

    sensor_a = measures["sensors"]["SENSOR-A"]
    sensor_b = measures["sensors"]["SENSOR-B"]
    near = measures["elset_near_duplicate_epochs"]

    assertions: list[dict[str, Any]] = [
        {
            "assertion": "both synthetic sensors are reported separately",
            "expected": ["SENSOR-A", "SENSOR-B"],
            "actual": sorted(measures["sensors"]),
            "why": "a per-sensor noise model that merges sensors is not a per-sensor noise model",
        },
        {
            # 12 values: 0..10 plus a 1000. Nearest-rank NEVER invents a value, so the median is an
            # observed 6 rather than the interpolated 5.5, and on an even sample it takes the upper
            # of the two central ranks. Written out because the first version of this assertion
            # expected 5.0 and the self-test caught it - which is the whole point of having one.
            "assertion": "the median of residuals 0..10 with one gross outlier is an observed 6",
            "expected": 6.0,
            "actual": sensor_a["azimuth_residual"]["distribution"]["median"],
            "why": "the median must resist the outlier; the mean of this sample is over 87",
        },
        {
            "assertion": "the mean, unlike the median, IS dragged by the outlier",
            "expected": True,
            "actual": sensor_a["azimuth_residual"]["distribution"]["mean"] > OUTLIER_DRAG_FLOOR,
            "why": "shows the median assertion above is measuring resistance, not coincidence",
        },
        {
            "assertion": "the MAD outlier rate finds exactly the one planted outlier in 12",
            "expected": round(1 / 12, 6),
            "actual": round(sensor_a["azimuth_residual"]["outliers"]["rate"], 6),
            "why": "the plan asks for an outlier rate; a robust bound must not swallow its own"
            " contamination",
        },
        {
            "assertion": "revisit spacing of 60-second observations has a 60-second median",
            "expected": 60.0,
            "actual": sensor_a["revisit_seconds"]["median"],
            "why": "revisit is the gap between consecutive observations of the SAME object",
        },
        {
            "assertion": "a field absent from a record raises the missing-field rate above zero",
            "expected": True,
            "actual": measures["missing_field_rate"]["magnitude"] > 0.0,
            "why": "an absent value must be counted, never imputed",
        },
        {
            "assertion": "a field left blank in the profile is reported UNAVAILABLE, not estimated",
            "expected": ["range_residual"],
            "actual": measures["measures_unavailable"],
            "why": "an absent measure is honest; an invented one is not",
        },
        {
            "assertion": "the near-duplicate epoch is counted, and the six-hour gap is not",
            "expected": 1,
            "actual": near["count"],
            "why": "the plan calls for near-duplicate epochs specifically",
        },
        {
            "assertion": "both synthetic markings appear in the distribution",
            "expected": {"SYNTHETIC-MARKING": 1, "UNCLASSIFIED": 12},
            "actual": measures["classification_marking_distribution"],
            "why": "the marking mix drives what a scenario is allowed to show",
        },
        {
            "assertion": "correlation quality is summarised across every record that carries it",
            "expected": 13.0,
            "actual": measures["correlation_quality"]["n"],
            "why": "a partial denominator understates or overstates every rate built on it",
        },
        {
            "assertion": "sensor B is present and distinct",
            "expected": 2.0,
            "actual": sensor_b["azimuth_residual"]["distribution"]["median"],
            "why": "guards against every record landing in one bucket",
        },
    ]

    # The boundary guard, proved in both directions.
    parameter_file = build_parameter_file(
        measures, window={"from": "synthetic", "to": "synthetic"}, profile_digest=None, gaps=[]
    )
    try:
        assert_crossable(parameter_file)
        boundary_clean = True
    except BoundaryError:
        boundary_clean = False
    assertions.append(
        {
            "assertion": "the synthetic parameter file passes the boundary guard",
            "expected": True,
            "actual": boundary_clean,
            "why": "only a parameter file of distributions crosses the boundary",
        }
    )
    try:
        assert_crossable({"planted": "object 25544 must not cross"})
        caught = False
    except BoundaryError:
        caught = True
    assertions.append(
        {
            "assertion": "the boundary guard REFUSES a planted catalogue-number shape",
            "expected": True,
            "actual": caught,
            "why": "a guard that has never refused anything is not known to work",
        }
    )
    # Pseudonymisation, proved rather than asserted in prose.
    pseudo = Analyser(fields=dict(_SELF_TEST_FIELDS), pseudonymise_sensors=True)
    pseudo_measures = pseudo.analyse(observations, elsets)
    assertions.append(
        {
            "assertion": "pseudonymised mode emits no verbatim sensor name",
            "expected": True,
            "actual": "SENSOR-A" not in json.dumps(pseudo_measures),
            "why": "the default must not leak the sensor set through the noise model",
        }
    )

    for item in assertions:
        item["pass"] = bool(item["expected"] == item["actual"])
    passed = all(item["pass"] for item in assertions)
    return passed, {
        "tool_version": TOOL_VERSION,
        "manifest": "enlightenment.udl-characterise.self-test/1",
        "passed": passed,
        "count": len(assertions),
        "failed": [item["assertion"] for item in assertions if not item["pass"]],
        "assertions": assertions,
    }


# --------------------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------------------


def _parse_window(text: str) -> datetime:
    moment = parse_time(text)
    if moment is None:
        raise argparse.ArgumentTypeError(
            f"{text!r} is not an ISO-8601 instant, for example 2026-08-01T00:00:00Z"
        )
    return moment


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="udl_characterise.py",
        description="Characterise UDL observation noise into a parameter file of distributions."
        " Runs on the networked workstation, never in the container.",
    )
    parser.add_argument("--profile", type=Path, help="endpoint profile INI (required to fetch)")
    parser.add_argument(
        "--print-profile-template",
        action="store_true",
        help="write the blank endpoint profile to stdout and exit",
    )
    parser.add_argument("--credentials", type=Path, default=DEFAULT_CREDENTIALS)
    parser.add_argument("--start", type=_parse_window, help="window start, ISO-8601")
    parser.add_argument("--end", type=_parse_window, help="window end, ISO-8601")
    parser.add_argument(
        "--analyse-only",
        type=Path,
        help="analyse a saved JSON dump; no network, no credentials, no profile",
    )
    parser.add_argument(
        "--raw-out",
        type=Path,
        help="save the fetched records so the analysis is reproducible offline. STAYS ON THIS"
        " WORKSTATION: raw records do not cross the boundary",
    )
    parser.add_argument("--emit", type=Path, help="write the parameter file here")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="prove the analyser against synthetic records; prints the assertion manifest",
    )
    parser.add_argument("--mad-k", type=float, default=DEFAULT_MAD_K)
    parser.add_argument(
        "--near-duplicate-seconds", type=float, default=DEFAULT_NEAR_DUPLICATE_SECONDS
    )
    parser.add_argument(
        "--sensor-labels",
        choices=("pseudonymise", "verbatim"),
        default="pseudonymise",
        help="pseudonymise (default) replaces each sensor name with a per-run hash. Choose"
        " verbatim only once the sensor set is agreed as shareable",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser


@dataclass(slots=True)
class Inputs:
    """Records to analyse, the field map to read them with, and the provenance of both."""

    observations: list[Record]
    elsets: list[Record]
    fields: dict[str, str]
    window: dict[str, str]
    profile_digest: str | None = None
    gaps: list[dict[str, str]] = field(default_factory=list)


def _offline_inputs(args: argparse.Namespace) -> Inputs:
    """Read a saved dump. No network, no credentials, and no profile unless the dump lacks one."""
    payload = json.loads(args.analyse_only.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        observations, elsets, fields, window = payload, [], None, _EMPTY_WINDOW
    else:
        observations = payload.get("observations", [])
        elsets = payload.get("elsets", [])
        fields = payload.get("fields")
        window = payload.get("window", _EMPTY_WINDOW)
    if fields is None and args.profile:
        fields = Profile.load(args.profile).fields
    if fields is None:
        raise RuntimeError(
            "the dump carries no `fields` map and no --profile was given. The analyser needs to"
            " know which record key is the sensor and which is the time; it will not guess"
        )
    return Inputs(observations=observations, elsets=elsets, fields=fields, window=window)


def _live_inputs(args: argparse.Namespace) -> Inputs:
    """Fetch from the service. Requires a complete profile and readable credentials."""
    if not args.profile:
        raise RuntimeError(
            "--profile is required to fetch. Write one with"
            " `--print-profile-template > udl-profile.ini` and fill it from the UDL API"
            " documentation. This tool does not guess an API shape.\n"
            "Nothing else is blocked: --self-test and --analyse-only need no profile"
        )
    if not (args.start and args.end):
        raise RuntimeError("--start and --end are required to fetch")

    profile = Profile.load(args.profile)
    fetcher = Fetcher(
        profile=profile,
        credentials=load_credentials(args.credentials),
        verbose=args.verbose,
    )
    print("fetching observations", file=sys.stderr)
    observations = fetcher.fetch(
        profile.endpoints["observation_history_path"],
        profile.endpoints["observation_count_path"],
        args.start,
        args.end,
    )
    print("fetching element sets", file=sys.stderr)
    elsets = fetcher.fetch(
        profile.endpoints["elset_history_path"],
        profile.endpoints["elset_count_path"],
        args.start,
        args.end,
    )
    window = {"from": _utc_stamp(args.start), "to": _utc_stamp(args.end)}
    if args.raw_out:
        args.raw_out.write_text(
            json.dumps(
                {
                    "observations": observations,
                    "elsets": elsets,
                    "fields": profile.fields,
                    "window": window,
                },
                indent=1,
            ),
            encoding="utf-8",
        )
        args.raw_out.chmod(0o600)
        print(f"raw records saved to {args.raw_out} (stays on this workstation)", file=sys.stderr)
    return Inputs(
        observations=observations,
        elsets=elsets,
        fields=profile.fields,
        window=window,
        profile_digest=profile.digest,
        gaps=fetcher.gaps,
    )


def _cmd_self_test() -> int:
    passed, manifest = self_test()
    json.dump(manifest, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    print(
        f"SELF-TEST: {'PASS' if passed else 'FAIL'} "
        f"({manifest['count'] - len(manifest['failed'])}/{manifest['count']})",
        file=sys.stderr,
    )
    return 0 if passed else 1


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.print_profile_template:
        sys.stdout.write(PROFILE_TEMPLATE)
        return 0
    if args.self_test:
        return _cmd_self_test()

    try:
        inputs = _offline_inputs(args) if args.analyse_only else _live_inputs(args)
    except (ProfileError, RuntimeError, TypeError, OSError, json.JSONDecodeError) as exc:
        print(f"{exc}", file=sys.stderr)
        return 2

    fields: dict[str, str | None] = {
        logical: (inputs.fields.get(logical) or None) for logical in _SELF_TEST_FIELDS
    }
    measures = Analyser(
        fields=fields,
        mad_k=args.mad_k,
        near_duplicate_seconds=args.near_duplicate_seconds,
        pseudonymise_sensors=args.sensor_labels == "pseudonymise",
    ).analyse(inputs.observations, inputs.elsets)

    parameter_file = build_parameter_file(
        measures,
        window=inputs.window,
        profile_digest=inputs.profile_digest,
        gaps=inputs.gaps,
    )
    try:
        assert_crossable(parameter_file)
    except BoundaryError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 3

    rendered = json.dumps(parameter_file, indent=2, sort_keys=True) + "\n"
    if args.emit:
        args.emit.write_text(rendered, encoding="utf-8")
        args.emit.chmod(0o644)
        print(f"parameter file written to {args.emit}", file=sys.stderr)
        print(f"SHA-256: {hashlib.sha256(rendered.encode()).hexdigest()}", file=sys.stderr)
    else:
        sys.stdout.write(rendered)
    if inputs.gaps:
        print(
            f"WARNING: {len(inputs.gaps)} window(s) are NOT represented in these measures; see"
            " provenance.unrepresented_windows",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
