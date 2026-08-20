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
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_MISMATCH = 1
EXIT_MISUSE = 2

#: A pin line: distribution name, `==`, version, optionally trailing ` \` for the hash block.
PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s\;]+)")


def read_pins(lockfile: Path) -> dict[str, str]:
    """Return `{canonical name: version}` for every pin in ``lockfile``."""
    pins: dict[str, str] = {}
    for raw in lockfile.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "--", "-r")):
            continue
        match = PIN.match(line)
        if match:
            pins[canonicalise(match.group(1))] = match.group(2)
    return pins


def canonicalise(name: str) -> str:
    """PEP 503 name normalisation, so `pip_audit` and `pip-audit` compare equal."""
    return re.sub(r"[-_.]+", "-", name).lower()


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
    result = subprocess.run(  # noqa: S603
        [interpreter, "-c", probe], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        sys.stderr.write(f"FAIL: could not query {interpreter}: {result.stderr.strip()}\n")
        raise SystemExit(EXIT_MISMATCH)

    raw: dict[str, str] = json.loads(result.stdout)
    return {canonicalise(name): version for name, version in raw.items()}


def main(argv: list[str]) -> int:
    if len(argv) < 3:  # noqa: PLR2004
        sys.stderr.write(f"{__doc__}\n")
        return EXIT_MISUSE

    interpreter = argv[1]
    installed = installed_versions(interpreter)

    missing: list[str] = []
    wrong: list[str] = []
    checked = 0
    for name in argv[2:]:
        lockfile = Path(name)
        if not lockfile.is_file():
            sys.stderr.write(f"FAIL: lock file {name} does not exist\n")
            return EXIT_MISMATCH
        for pinned_name, pinned_version in read_pins(lockfile).items():
            checked += 1
            actual = installed.get(pinned_name)
            if actual is None:
                missing.append(f"  {pinned_name}: pinned {pinned_version}, NOT INSTALLED")
            elif actual != pinned_version:
                wrong.append(f"  {pinned_name}: pinned {pinned_version}, installed {actual}")

    if not checked:
        sys.stderr.write("FAIL: the lock files named contained no pins at all\n")
        return EXIT_MISMATCH

    if missing or wrong:
        sys.stderr.write(f"FAIL: the environment does not match the lock files ({interpreter})\n")
        # Deduplicated: a distribution pinned in both lock files would otherwise be reported
        # twice, and a wall of repeats reads as a bigger problem than it is.
        for line in dict.fromkeys(wrong + missing):
            sys.stderr.write(f"{line}\n")
        sys.stderr.write(
            "\nRe-install before trusting any verdict from this loop:\n"
            "  .venv/bin/pip install --require-hashes --no-deps "
            "-r requirements.txt -r requirements-dev.txt\n"
        )
        return EXIT_MISMATCH

    sys.stdout.write(f"  {checked} pins checked, all match ({interpreter})\n")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv))
