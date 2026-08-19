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

Exit codes:

    0  the edit was applied and verified
    2  wrong number of arguments
    3  the anchor is absent, or ambiguous (more than one occurrence, so the edit would be
       arbitrary), or the named target is a symlink
    4  the anchor is still present after the edit
    5  the target cannot be read as UTF-8 text

The target file is only ever replaced ATOMICALLY, after the result has been verified: a
temporary sibling is written, checked, and renamed over the target. A refusal therefore always
leaves the original byte-identical, which matters because a caller treating a non-zero exit as
"nothing happened" would otherwise be wrong.

The named target must not be a symlink. `Path.write_text` follows one, so a symlinked target
would write outside the named directory; the same reasoning puts `O_NOFOLLOW` on every file
this project's own store opens.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

EXIT_OK = 0
EXIT_MISUSE = 2
EXIT_ANCHOR = 3
EXIT_UNVERIFIED = 4
EXIT_UNREADABLE = 5
EXPECTED_ARGS = 4


def _write_atomically(target: Path, content: str) -> None:
    """Write ``content`` over ``target`` via a verified temporary sibling."""
    handle, temp_name = tempfile.mkstemp(dir=str(target.parent), prefix=".verified-edit-")
    temp_path = Path(temp_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        # Preserve the target's mode. mkstemp creates 0600, so without this a scripted edit to
        # any of this repository's mode-755 scripts or hooks would strip the executable bit and
        # put an unrequested mode change in the diff.
        temp_path.chmod(target.stat().st_mode & 0o7777)
        temp_path.replace(target)
    except OSError:
        temp_path.unlink(missing_ok=True)
        raise


def apply_edit(target: Path, anchor: str, replacement: str) -> int:
    """Replace ``anchor`` with ``replacement`` in ``target``, verifying before writing."""
    if target.is_symlink():
        sys.stderr.write(f"REFUSING a symlinked target: {target}\n")
        return EXIT_ANCHOR
    try:
        original = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        sys.stderr.write(f"CANNOT READ {target}: {exc.__class__.__name__}\n")
        return EXIT_UNREADABLE

    occurrences = original.count(anchor)
    if occurrences == 0:
        sys.stderr.write(f"ANCHOR NOT FOUND in {target}:\n{anchor}\n")
        return EXIT_ANCHOR
    if occurrences > 1:
        sys.stderr.write(f"ANCHOR AMBIGUOUS in {target} ({occurrences} occurrences):\n{anchor}\n")
        return EXIT_ANCHOR

    edited = original.replace(anchor, replacement, 1)

    # Verified BEFORE the write, so a refusal cannot leave a half-edited file behind. The
    # earlier version wrote first and checked afterwards, which is the inverse of what this
    # tool exists to prevent.
    if anchor in edited and anchor not in replacement:
        sys.stderr.write(f"ANCHOR WOULD SURVIVE the edit to {target}; nothing written\n")
        return EXIT_UNVERIFIED

    _write_atomically(target, edited)
    sys.stdout.write(f"edited {target}\n")
    return EXIT_OK


def main(argv: list[str]) -> int:
    """Entry point. Anchor and replacement come from files, so neither is shell-mangled."""
    if len(argv) != EXPECTED_ARGS:
        sys.stderr.write(__doc__ or "")
        return EXIT_MISUSE
    target, anchor_file, replacement_file = (Path(argv[1]), Path(argv[2]), Path(argv[3]))
    try:
        anchor = anchor_file.read_text(encoding="utf-8")
        replacement = replacement_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        sys.stderr.write(f"CANNOT READ an argument file: {exc.__class__.__name__}\n")
        return EXIT_UNREADABLE
    return apply_edit(target, anchor, replacement)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
