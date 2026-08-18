#!/usr/bin/env python3
"""Apply a text replacement to a file and FAIL LOUDLY if the anchor did not match.

Why this exists, stated plainly because it is a real project control and not a nicety:
a plain `str.replace` is a silent no-op when its anchor does not match. One such no-op let a
docstring correction be recorded in `docs/CHANGELOG.md` as done while the source file was
untouched, and a binding review caught the release record certifying work the diff did not
contain. That is worse than the defect it failed to fix, because a record which certifies
work not done devalues every other claim in it.

Use this for any scripted edit to a tracked file:

    python3 scripts/verified-edit.py <file> <anchor-file> <replacement-file>

It exits non-zero, with the anchor printed, when the anchor is absent, when the anchor is
ambiguous (more than one occurrence, so the edit would be arbitrary), or when the
replacement is not present in the file afterwards.
"""

from __future__ import annotations

import sys
from pathlib import Path

EXIT_OK = 0
EXIT_MISUSE = 2
EXIT_ANCHOR = 3
EXIT_UNVERIFIED = 4
EXPECTED_ARGS = 4


def apply_edit(target: Path, anchor: str, replacement: str) -> int:
    """Replace ``anchor`` with ``replacement`` in ``target``, verifying the result."""
    original = target.read_text(encoding="utf-8")
    occurrences = original.count(anchor)
    if occurrences == 0:
        sys.stderr.write(f"ANCHOR NOT FOUND in {target}:\n{anchor}\n")
        return EXIT_ANCHOR
    if occurrences > 1:
        sys.stderr.write(f"ANCHOR AMBIGUOUS in {target} ({occurrences} occurrences):\n{anchor}\n")
        return EXIT_ANCHOR

    target.write_text(original.replace(anchor, replacement, 1), encoding="utf-8")

    after = target.read_text(encoding="utf-8")
    if replacement and replacement not in after:
        sys.stderr.write(f"REPLACEMENT NOT PRESENT after writing {target}\n")
        return EXIT_UNVERIFIED
    if anchor in after and anchor not in replacement:
        sys.stderr.write(f"ANCHOR STILL PRESENT after writing {target}\n")
        return EXIT_UNVERIFIED
    sys.stdout.write(f"edited {target}\n")
    return EXIT_OK


def main(argv: list[str]) -> int:
    """Entry point. Reads the anchor and replacement from files, so neither is shell-mangled."""
    if len(argv) != EXPECTED_ARGS:
        sys.stderr.write(__doc__ or "")
        return EXIT_MISUSE
    return apply_edit(
        Path(argv[1]),
        Path(argv[2]).read_text(encoding="utf-8"),
        Path(argv[3]).read_text(encoding="utf-8"),
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv))
