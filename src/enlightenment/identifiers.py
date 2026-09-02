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

#: Longest content-supplied string, in BYTES of UTF-8, stored on a run row or served as an
#: identity: the item id, the
#: cue id, the procedure id, the competency axis. `content/models.py` declares no maximum length on
#: any of them. NOT the version - that is cut silently by `_bounded` and nothing reads it for
#: meaning, so listing it here overstated what this module governs.
MAX_CONTENT_STRING: Final = 64

#: How many hex characters of the digest a shortened identifier carries, and the character that
#: introduces it. Thirty-two bits: collision-free by a wide margin inside the served caps, and
#: grindable by a determined content author. `~` is not reserved, so an author could write a
#: 63-character id ending in a tilde and eight hex digits that reads as shortened. Both are recorded
#: rather than defended, because neither matters at these stakes.
#:
#: **The prefix carries far less of the distinctness for a multi-byte id than it used to, and that
#: changes what "grindable" means here.** The cut became BYTES at V0.26.24, so an astral id keeps
#: 13 code points of prefix where an ASCII one keeps 55. Measured over prefix-sharing astral ids,
#: two distinct ids collapse to one served name at about 29,173 candidates, against a residual
#: declared when the prefix was four times longer. The actor is the trusted content author and the
#: consequence is merged run history rather than a disclosure, so the digest is not widened -
#: but the figure is recorded here, because the sentence above was written about a different
#: prefix and a reader would otherwise take it at face value.
DIGEST_CHARACTERS: Final = 8
DIGEST_MARKER: Final = "~"


def cut_to_bytes(text: str, limit: int) -> str:
    """``text`` shortened to at most ``limit`` BYTES of UTF-8, never splitting a code point.

    **The unit is bytes because every ceiling this project asserts is in bytes.** The caps were
    declared in CODE POINTS and the anonymous-response ceilings in bytes, and one `U+1F600` is one
    code point and four bytes - so a 64-code-point cap admitted 256 bytes, and the sweep that
    certified those ceilings poisoned its tree with ASCII. Measured by the security gate: with
    astral identifiers, `GET /api/v1/me` served 17,407 bytes against a 16,384-byte ceiling that
    the suite reported as held. Two units for one bound is not a tight bound, it is an unmeasured
    one.

    For ASCII the two units are identical, so no shipped identifier and no persisted value changes
    shape: the golden-value test that pins the shortened form is unaffected. What changes is that
    a multi-byte identifier is now cut where the ceiling is actually drawn.

    Cutting UTF-8 at an arbitrary byte can split a code point, so the tail is decoded with
    `errors="ignore"`, which drops the incomplete sequence rather than emitting a replacement
    character. A shortened identifier already carries a digest of the whole string, so losing up
    to three bytes of the prefix cannot make two ids collide.
    """
    encoded = text.encode("utf-8")
    if len(encoded) <= limit:
        return text
    return encoded[:limit].decode("utf-8", errors="ignore")


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

    **THE OUTPUT FORM IS A PERSISTED FORMAT, and it changed at V0.26.15.** `RunRecord.item_id` is
    written through this function into `progress.json` on the platform volume and compared against a
    freshly computed value, so the exact string matters across an upgrade. Moving the function here
    also corrected an off-by-one - the old arithmetic reserved two characters for a one-character
    marker, so a shortened id was 63 characters where it is now exactly 64. The corrected form is
    kept, because reserving a byte nothing uses is a bug rather than a convention, and the change is
    recorded here and pinned by a golden-value test rather than left to be discovered on an upgrade.
    Nothing is deployed, so it costs nothing today; on an existing volume it would reset one item's
    attempt count once before self-healing.
    """
    if len(item_id.encode("utf-8")) <= MAX_CONTENT_STRING:
        return item_id
    digest = hashlib.sha256(item_id.encode("utf-8")).hexdigest()[:DIGEST_CHARACTERS]
    keep = MAX_CONTENT_STRING - len(digest) - len(DIGEST_MARKER)
    return f"{cut_to_bytes(item_id, keep)}{DIGEST_MARKER}{digest}"
