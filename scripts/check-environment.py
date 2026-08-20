#!/usr/bin/env python3
"""Assert that what is INSTALLED equals what the lock files PIN, and refuse to run otherwise.

Why this exists, recorded plainly because it invalidated earlier work rather than merely
improving on it: `scripts/verify.sh` used to invoke bare `ruff`, `mypy`, `pytest` and
`pip-audit`, so the loop ran whatever those names resolved to on PATH. On this machine PATH
held ruff 0.15.8 against a pinned 0.16.3, mypy 1.19.1 against a pinned 2.3.1, and a `pytest`
inside an isolated tool environment that could not import the application's own dependencies
at all. The drift surfaced as a FALSE FAILURE, which is the lucky direction. The same gap
produces a false PASS just as easily, and the loop is the thing every other claim rests on:
"the verification loop is green" has to mean "green against the dependency set the container
ships and the platform installs", or it means nothing.

Usage:

    python3 scripts/check-environment.py <interpreter> <lockfile> [<lockfile> ...]

Every `name==version` pin in each lock file must be installed in `<interpreter>`'s
environment at exactly that version. A missing distribution and a mismatched one are both
failures; neither is a warning. Exit 0 when every pin matches, 1 otherwise, with every
divergence listed rather than only the first, because fixing them one round-trip at a time
is how a re-lock turns into an afternoon.

Hash lines and continuations are skipped: this reads the pins, not the hashes. `pip install
--require-hashes` already enforces the hashes at install time, and duplicating that check
here would be a second implementation of it to keep in step.

**The check is one-directional, and that is a decision rather than an omission.** Every pin
must be installed at its pinned version; an EXTRA distribution present but not pinned is not
reported. Asserting the reverse would fail on every runner, because `pip`, `setuptools` and
`wheel` are provided by the interpreter's own environment and are not all pinned here. A leg
that fails on a correct environment is a leg people learn to skip, which costs more than the
latent hole it closes. If an unpinned distribution ever matters, `pip-audit` scans the lock
files in leg six and the container installs only `requirements-runtime.txt`.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

from packaging.markers import Marker
from packaging.version import InvalidVersion, Version

EXIT_OK = 0
EXIT_MISMATCH = 1
EXIT_MISUSE = 2

#: Hard bound on the version probe. Generous for the work (listing installed distributions)
#: and short enough that a wedged interpreter fails the leg instead of hanging it.
PROBE_TIMEOUT_SECONDS = 60

#: The script name, an interpreter, and at least one lock file.
MINIMUM_ARGUMENTS = 3

#: A pin line: distribution name, optional extras in brackets, `==`, version, then optionally
#: an environment marker after `;` and a trailing ` \` introducing the hash block.
#:
#: The extras group is not decoration. Without it, `uvicorn[standard]==9.9.9` did not match,
#: `read_pins` skipped the line in silence, and the checker printed "1 pins checked, all match"
#: with an unmet pin sitting in the file. A control that silently ignores what it cannot parse
#: is fail-OPEN, in the one leg the rest of the loop's meaning now rests on. The extras form is
#: also the ordinary way to pin uvicorn, so this was not a hypothetical.
PIN = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)"
    r"(?:\[[^\]]*\])?"
    r"==(?P<version>[^\s;\\]+)"
    r"\s*(?:;\s*(?P<marker>[^\\]*?))?\s*\\?$"
)


class UnparsedLine(NamedTuple):
    """A requirement line the pin pattern rejected, kept so it can be reported not dropped."""

    lockfile: str
    number: int
    text: str


def read_pins(lockfile: Path) -> dict[str, str]:
    """Return `{canonical name: version}` for every applicable pin in ``lockfile``.

    A pin whose environment marker does not apply to the running interpreter is skipped
    deliberately: `pywin32==306 ; sys_platform == "win32"` is not expected to be installed on
    Linux, and reporting it as missing would be a false failure that teaches people to ignore
    this leg.
    """
    pins: dict[str, str] = {}
    for raw in lockfile.read_text().splitlines():
        line = raw.strip()
        if not _is_requirement_line(line):
            continue
        match = PIN.match(line)
        if match is None:
            continue
        if not _marker_applies(match.group("marker")):
            continue
        pins[canonicalise(match.group("name"))] = match.group("version")
    return pins


def read_unparsed(lockfile: Path) -> list[UnparsedLine]:
    """Return every requirement line the pin pattern could not read.

    Reported rather than ignored. `read_pins` returning fewer entries than the file holds is
    indistinguishable, from the caller's side, from a file that holds fewer pins - which is
    exactly how the extras form went unnoticed.
    """
    unparsed: list[UnparsedLine] = []
    for number, raw in enumerate(lockfile.read_text().splitlines(), start=1):
        line = raw.strip()
        if not _is_requirement_line(line):
            continue
        if PIN.match(line) is None:
            unparsed.append(UnparsedLine(lockfile.name, number, line))
    return unparsed


def _is_requirement_line(line: str) -> bool:
    """True for a line that should name a pinned requirement.

    Blank lines, comments, pip options, `-r` includes and the `--hash=...` continuation lines
    are all legitimately not pins. Everything else is, and must parse.
    """
    # One test, not two: `--hash=...` already starts with `-`, so a separate check for it could
    # never return False. The earlier version had one, under a docstring implying it did work.
    return bool(line) and not line.startswith(("#", "-"))


def _marker_applies(marker: str | None) -> bool:
    """Whether an environment marker holds for the interpreter running this script.

    A marker that cannot be evaluated is treated as APPLYING, so an unreadable marker becomes
    a reported mismatch rather than a silent skip. Fail closed, as everywhere else.
    """
    if not marker:
        return True
    try:
        return bool(Marker(marker).evaluate())
    except Exception:  # deliberately broad; the reason is below
        # Deliberately broad, and `InvalidMarker` alone was not enough. Measured escapes from
        # the narrower version: `python_full_version ~= "banana"` raises `UndefinedComparison`,
        # and `python_version >= "3." + "9" * 100000` raises `ValueError` from CPython's
        # 4300-digit integer conversion limit. Both left this function as an uncaught traceback,
        # fail-closed only by the coincidence that Python exits 1 and EXIT_MISMATCH is 1.
        #
        # `packaging` parses and evaluates a mini-language over file content, so its failure
        # surface is not enumerable from the outside. Attacked with eighteen hostile markers it
        # executes nothing (`__import__("os").system("id")` raises `InvalidMarker`) and does not
        # backtrack pathologically (5,000 conjunctions in 0.08s), but "no code execution" and
        # "only ever raises these three types" are different claims and only the first is tested.
        #
        # Named on the way past, redacted, because the exit code alone leaves an operator
        # looking at "NOT INSTALLED" with no way to tell a real mismatch from a marker that
        # could not be evaluated. Fail closed AND say why.
        sys.stderr.write(
            f"  note: could not evaluate marker, treating as applicable: {redact(marker)}\n"
        )
        return True


#: Credentials embedded in a URL, as `scheme://userinfo@host`. A PEP 440 direct reference
#: (`pkg @ https://token@host/pkg.whl`) is a requirement line, so it reaches the reports below
#: and would otherwise be echoed to a log verbatim. Option lines such as `--index-url` are
#: already skipped, being prefixed with a dash, so requirement lines are the remaining path.
#:
#: **No colon is required, and the first version demanded one.** That version matched only
#: `user:password@`, so `https://ghp_...@github.com/org/repo.git` - a bare token with no
#: password, and the ordinary shape of a pip direct reference against a private repository -
#: was never matched at all. The most likely real credential to reach this path was the one
#: form the control could not see. It also leaked the tail of any password containing a raw
#: `@`, since userinfo runs to the LAST `@` before the authority.
#:
#: Greedy `[^/\s]+` anchors on that last `@` and cannot cross a `/`, so a plain URL with an
#: `@` in its path (`https://host/path@x`) and an ordinary index URL are left alone.
URL_CREDENTIALS = re.compile(r"(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*://)[^/\s]+@")


def redact(text: str) -> str:
    """Return ``text`` with any URL userinfo replaced by a marker.

    This function exists because the fix for a fail-open branch introduced an echo. Reporting
    the lines it cannot parse is what stopped `check-environment.py` silently skipping them, and
    a private-index setup can legitimately hold a token in a direct reference. The report is
    written to stderr, which lands in a CI log, so it is a disclosure path.

    Rendered as the house redaction marker rather than removed, so a reader can see that
    something was withheld rather than wondering whether the line was truncated.
    """
    return URL_CREDENTIALS.sub(r"\g<scheme>[REDACTED:credential]@", text)


def canonicalise(name: str) -> str:
    """PEP 503 name normalisation, so `pip_audit` and `pip-audit` compare equal."""
    return re.sub(r"[-_.]+", "-", name).lower()


def versions_equal(pinned: str, installed: str) -> bool:
    """Compare two versions by PEP 440 semantics, not as strings.

    `pytest==9.1.1.0` and an installed `9.1.1` are the same release and a string comparison
    calls them different. That failed in the safe direction, but a leg that cries wolf on a
    correct environment is a leg people learn to skip.
    """
    try:
        return Version(pinned) == Version(installed)
    except InvalidVersion:
        return pinned == installed


def installed_versions(interpreter: str) -> dict[str, str]:
    """Ask ``interpreter`` what it actually has, rather than assuming it is this process.

    Run out of process on purpose: the loop's interpreter is the one that must satisfy the
    pins, and it is not necessarily the one running this script.
    """
    probe = (
        "import json\n"
        "from importlib.metadata import distributions\n"
        "print(json.dumps({d.metadata['Name']: d.version for d in distributions()"
        " if d.metadata['Name']}))\n"
    )
    # Why S603 is suppressed below: a list argv with shell=False, and a probe that is a
    # constant string literal with no interpolation. `interpreter` is a path from argv, and
    # argv is trusted in all three contexts this runs in - the local loop, GitHub CI, and
    # the platform - because anyone able to set it could already set PATH or execute code
    # directly. The timeout is the real control here: a wedged interpreter would otherwise
    # hang the whole loop until the CI job timed out, and a loop that hangs reports nothing.
    try:
        result = subprocess.run(  # noqa: S603
            [interpreter, "-c", probe],
            capture_output=True,
            text=True,
            check=False,
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        # A timeout is a failure to CHECK, and a failure to check is never a pass. Reported
        # as a mismatch rather than raised, so the loop's exit code stays the whole story.
        sys.stderr.write(f"FAIL: {interpreter} did not answer within {PROBE_TIMEOUT_SECONDS}s\n")
        raise SystemExit(EXIT_MISMATCH) from None
    if result.returncode != 0:
        sys.stderr.write(f"FAIL: could not query {interpreter}: {result.stderr.strip()}\n")
        raise SystemExit(EXIT_MISMATCH)

    raw: dict[str, str] = json.loads(result.stdout)
    return {canonicalise(name): version for name, version in raw.items()}


class Divergences(NamedTuple):
    """What a scan of the lock files found. Split out so `main` stays inside the complexity cap."""

    checked: int
    missing: list[str]
    wrong: list[str]
    unreadable: list[UnparsedLine]


def scan(lockfiles: list[str], installed: dict[str, str]) -> Divergences:
    """Compare every applicable pin in ``lockfiles`` against ``installed``.

    Raises :class:`FileNotFoundError` for a lock file that does not exist, because a named
    file that is absent is a caller error rather than a mismatch to report alongside others.
    """
    missing: list[str] = []
    wrong: list[str] = []
    unreadable: list[UnparsedLine] = []
    checked = 0
    for name in lockfiles:
        lockfile = Path(name)
        if not lockfile.is_file():
            raise FileNotFoundError(name)
        unreadable.extend(read_unparsed(lockfile))
        for pinned_name, pinned_version in read_pins(lockfile).items():
            checked += 1
            actual = installed.get(pinned_name)
            # Redacted where the line is COMPOSED, not at one echo site. The first version
            # redacted only the unreadable-line report, and this is the other place a URL
            # reaches stderr: the version group is `[^\s;\\]+`, which swallows a whole URL, so
            # `pkg==https://user:token@host/x` - a one-character typo of the direct-reference
            # form the redaction was written for - printed the credential in full.
            if actual is None:
                missing.append(f"  {pinned_name}: pinned {redact(pinned_version)}, NOT INSTALLED")
            elif not versions_equal(pinned_version, actual):
                wrong.append(
                    f"  {pinned_name}: pinned {redact(pinned_version)}, installed {redact(actual)}"
                )
    return Divergences(checked, missing, wrong, unreadable)


def main(argv: list[str]) -> int:
    if len(argv) < MINIMUM_ARGUMENTS:
        sys.stderr.write(f"{__doc__}\n")
        return EXIT_MISUSE

    interpreter = argv[1]
    try:
        found = scan(argv[2:], installed_versions(interpreter))
    except FileNotFoundError as absent:
        sys.stderr.write(f"FAIL: lock file {absent.args[0]} does not exist\n")
        return EXIT_MISMATCH

    if found.unreadable:
        # Reported BEFORE the empty-file case, because it is the more specific diagnosis: a
        # file of nothing but unreadable lines would otherwise be blamed on holding no pins.
        #
        # A line this script cannot parse must NEVER read as a match. The extras form
        # (`uvicorn[standard]==1.2.3`) was silently skipped once, and the run printed
        # "all match" with an unmet pin sitting in the file.
        sys.stderr.write("FAIL: lines that should name a pin could not be read\n")
        for entry in found.unreadable:
            sys.stderr.write(f"  {entry.lockfile}:{entry.number}: {redact(entry.text)}\n")
        return EXIT_MISMATCH

    if not found.checked:
        sys.stderr.write("FAIL: the lock files named contained no pins at all\n")
        return EXIT_MISMATCH

    if found.missing or found.wrong:
        sys.stderr.write(f"FAIL: the environment does not match the lock files ({interpreter})\n")
        # Deduplicated: a distribution pinned in both lock files would otherwise be reported
        # twice, and a wall of repeats reads as a bigger problem than it is.
        for line in dict.fromkeys(found.wrong + found.missing):
            sys.stderr.write(f"{line}\n")
        sys.stderr.write(
            "\nRe-install before trusting any verdict from this loop:\n"
            "  .venv/bin/pip install --require-hashes --no-deps "
            "-r requirements.txt -r requirements-dev.txt\n"
        )
        return EXIT_MISMATCH

    sys.stdout.write(f"  {found.checked} pins checked, all match ({interpreter})\n")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv))
