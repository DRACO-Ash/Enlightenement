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

from packaging.markers import InvalidMarker, Marker
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
    if not line or line.startswith(("#", "-")):
        return False
    return not line.startswith("--hash")


def _marker_applies(marker: str | None) -> bool:
    """Whether an environment marker holds for the interpreter running this script.

    A marker that cannot be evaluated is treated as APPLYING, so an unreadable marker becomes
    a reported mismatch rather than a silent skip. Fail closed, as everywhere else.
    """
    if not marker:
        return True
    try:
        return bool(Marker(marker).evaluate())
    except InvalidMarker:
        return True


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
            if actual is None:
                missing.append(f"  {pinned_name}: pinned {pinned_version}, NOT INSTALLED")
            elif not versions_equal(pinned_version, actual):
                wrong.append(f"  {pinned_name}: pinned {pinned_version}, installed {actual}")
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
            sys.stderr.write(f"  {entry.lockfile}:{entry.number}: {entry.text}\n")
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
