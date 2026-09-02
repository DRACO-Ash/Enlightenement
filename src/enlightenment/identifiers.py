"""Shortening a content identifier for a wire, a log line or a storage row.

**One function, in one place, importable by every layer.** Seven instances of one fault reached
seven consecutive releases, each outside the scope of the sweep before it, because the rule lived
inside `training/drill.py` and was applied by hand everywhere else. `content/` cannot import from
`training/`, so the seventh instance - a loader error composing a raw id and then cutting the whole
composite - could not have used it even if somebody had remembered. A rule that a layer is unable to
obey is not a rule, so it moved here.
"""

from __future__ import annotations

import hashlib
from typing import Final

#: Longest content-supplied string stored on a run row or served as an identity: the version, the
#: item id, the procedure id, the competency axis. `content/models.py` declares no maximum length on
#: any of them.
MAX_CONTENT_STRING: Final = 64

#: How many hex characters of the digest a shortened identifier carries, and the character that
#: introduces it. Thirty-two bits: collision-free by a wide margin inside the served caps, and
#: grindable by a determined content author. `~` is not reserved, so an author could write a
#: 63-character id ending in a tilde and eight hex digits that reads as shortened. Both are recorded
#: rather than defended, because neither matters at these stakes.
DIGEST_CHARACTERS: Final = 8
DIGEST_MARKER: Final = "~"


def served_identifier(item_id: str) -> str:
    """A content id shortened WITHOUT two distinct ids collapsing into one.

    A plain truncation cuts silently, so any two ids sharing a prefix longer than the cap become one
    string: measured, 140 distinct authored ids served ONE entry under a name matching nothing an
    author wrote, while the gap was 94 items wide. Two rules broken at once - never invent a name in
    operator-facing data, and never let a shortened disclosure read as a complete one - plus every
    comparison against that key silently failing.

    A cut id keeps a digest of the whole string. The digest is not a secret and nothing verifies it:
    it exists so two shortened ids differ, and so a reader can see the id was shortened rather than
    mistake it for what the author typed.
    """
    if len(item_id) <= MAX_CONTENT_STRING:
        return item_id
    digest = hashlib.sha256(item_id.encode("utf-8")).hexdigest()[:DIGEST_CHARACTERS]
    keep = MAX_CONTENT_STRING - len(digest) - len(DIGEST_MARKER)
    return f"{item_id[:keep]}{DIGEST_MARKER}{digest}"
