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
from typing import Any, Final

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
#: two distinct ids collapse to one served name at about 29,173 candidates - ONE TRIAL, and a
#: draw well below the median: a 32-bit digest's median first collision is about 77,000 by the
#: birthday bound, and an independent trial reached 94,696. The single draw is quoted because it
#: is the one that was observed, and its basis is given because a bare figure reads as a
#: threshold. It errs on the conservative side, against a residual
#: declared when the prefix was four times longer. The actor is the trusted content author and the
#: consequence is merged run history rather than a disclosure, so the digest is not widened -
#: but the figure is recorded here, because the sentence above was written about a different
#: prefix and a reader would otherwise take it at face value.
DIGEST_CHARACTERS: Final = 8
DIGEST_MARKER: Final = "~"


def utf8(text: str) -> bytes:
    """UTF-8 for a content-supplied string, which is not guaranteed to be valid Unicode TEXT.

    **A lone surrogate is legal JSON and legal in a Python `str`, and `str.encode("utf-8")` raises
    on it.** `json.loads('"\\ud800"')` returns `'\ud800'`, so a content author can put one in an
    id with an escape sequence and no invalid byte anywhere in the file. Measured before this
    existed: three drills with `"DRL-\\ud800\\ud800-x"` as their id produced a **500 on the
    anonymous `/api/v1/me`**, because `served_identifier` encodes to measure the length.

    That is a fail-OPEN crash on an unauthenticated route from authored data, which this project's
    rules forbid twice over: a control that cannot be verified is treated as failed, and an
    anonymous route must not be sized or steered by content. `errors="replace"` turns the
    unencodable character into `?`, which is one byte of valid UTF-8: shorter, visible, and never
    a traceback.

    **The digest changes for surrogate-bearing input and for nothing else**, so the persisted
    shortened-identifier format is unaffected by this: the shipped tree contains exactly one
    non-ASCII string, a degree sign in a detection pattern, which no cap touches.
    """
    return text.encode("utf-8", errors="replace")


#: How deep a value may nest before this project refuses to serve it. **A serialiser limit, not a
#: taste limit.** `pydantic_core` raises `Circular reference detected (depth exceeded)` at about
#: 250, and that raise happens while the RESPONSE IS RENDERING - outside every route's try/except -
#: so it reaches an anonymous caller as a 500 while `/healthz` stays 200. Measured: a stored
#: session row carrying a 252-deep dict produced exactly that on `GET /api/v1/sessions`; 250 was
#: fine, 252 was not, and a nested list does the same.
#:
#: 32 is four times the deepest thing this project actually ships - the two procedure libraries
#: reach 8, every other content file and every session row is shallower - and an order of
#: magnitude below where the serialiser gives way. Refusing at the LOAD boundary rather than at
#: the wire is the same rule as the surrogate check beside it: one boundary in one place beats two
#: copies that drift.
MAX_NESTING_DEPTH: Final = 32


def _encodable(text: str) -> bool:
    """Whether `text` survives UTF-8 encoding. False for a string carrying a lone surrogate."""
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def unservable_pointer(node: Any) -> tuple[str, int, str] | None:
    """A JSON pointer to ONE value in `node` that cannot be SERVED, how many, and which kind.

    Two kinds, one traversal: a string carrying a lone surrogate, which cannot be encoded as UTF-8,
    and a value nested past `MAX_NESTING_DEPTH`, which pydantic's serialiser refuses. They are
    checked together because they fail identically - inside the serialiser, while the response
    renders, outside every route's try/except, as a 500 on an anonymous route with `/healthz`
    still 200 - and because a second traversal is a second thing to keep in step.

    Shared by the two boundaries that read JSON somebody else wrote: `content/loader._read_json`
    and `storage.TrainingStore.load`. It lived in the loader first, and the security gate found the
    consequence of that: a lone surrogate in the stored snapshot produced a **500 on the
    unauthenticated `GET /api/v1/sessions`**, because the store had no equivalent check. One
    boundary rule in one place beats two copies that diverge, which is this project's rule for
    every other shared control.

    **Keys as well as values, at every depth, through lists as well as dicts.** The first version
    walked values only and nothing crashed - by downstream accident in two separate layers, not by
    design - so the walk is complete rather than relying on either.

    "One" rather than "the first": this walks with an explicit stack, so the pointer is the first
    the traversal REACHES and not the first in document order. Stated because the message is what
    an author acts on, and an ordering claim the code does not make is false precision.

    **Scalars are tested inline and never pushed, and a pointer is built only on a failure.** The
    first version pushed a tuple and an eagerly formatted pointer string for every node including
    integers: measured on a 6.0 MB document of `{"a": [1] * 2_000_000}`, `json.loads` peaked at
    17.1 MB and the walk then peaked at **230.0 MB transient**, thirteen times the parse. Only
    containers are pushed now. The load path runs at startup with one worker, so an exhaustion
    there is "the container never started and no health path answered" - the failure this project
    forbids by name, and not one a check added for safety should introduce.

    Non-recursive on purpose: `[` nested 200,000 deep dies in `json.loads` with the `RecursionError`
    the loader already catches, and never here.
    """
    first: str | None = None
    total = 0
    stack: list[tuple[Any, str, int]] = [(node, "", 1)]
    while stack:
        current, where, depth = stack.pop()
        #: DEPTH is checked before the children are pushed, so the refusal names the node that
        #: crossed the bound rather than one of its descendants. Returned immediately rather than
        #: counted: a document too deep to serve is refused whole, and walking the rest of it to
        #: total up strings nobody will ever see is work for no diagnosis.
        if depth > MAX_NESTING_DEPTH:
            return (where or "/", 1, "depth")
        containers, unencodable = _entries(current, where)
        stack.extend((value, at, depth + 1) for value, at in containers)
        for at in unencodable:
            total += 1
            if first is None:
                first = at
    return (first, total, "surrogate") if first is not None else None


def _entries(current: Any, where: str) -> tuple[list[tuple[Any, str]], list[str]]:
    """Containers under `current` to push, and pointers to its directly-held bad strings.

    Split out of `unservable_pointer` because ruff's complexity limit is a real bound and a
    `noqa` would be a suppression. The split is also the honest shape: one function decides what
    is worth pushing, the other only counts.
    """
    if isinstance(current, dict):
        return _dict_entries(current, where)
    if isinstance(current, list):
        return _list_entries(current, where)
    if isinstance(current, str) and not _encodable(current):
        return [], [where or "/"]
    return [], []


def _dict_entries(current: dict[Any, Any], where: str) -> tuple[list[tuple[Any, str]], list[str]]:
    """A dict's pushable children and bad strings. KEYS are checked as well as values."""
    containers: list[tuple[Any, str]] = []
    unencodable: list[str] = []
    for key, value in current.items():
        at = f"{where}/{key}"
        if isinstance(key, str) and not _encodable(key):
            unencodable.append(at)
        if isinstance(value, dict | list):
            containers.append((value, at))
        elif isinstance(value, str) and not _encodable(value):
            unencodable.append(at)
    return containers, unencodable


def _list_entries(current: list[Any], where: str) -> tuple[list[tuple[Any, str]], list[str]]:
    """A list's pushable children and bad strings. Scalars are never pushed."""
    containers: list[tuple[Any, str]] = []
    unencodable: list[str] = []
    for index, value in enumerate(current):
        if isinstance(value, dict | list):
            containers.append((value, f"{where}/{index}"))
        elif isinstance(value, str) and not _encodable(value):
            unencodable.append(f"{where}/{index}")
    return containers, unencodable


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
    character. The result is a code-point PREFIX of the input, proved over 400,000 random strings
    spanning all four byte widths, combining marks and zero-width joiners - so a cut shortens a
    value and never changes its meaning. The one exception is an input carrying a lone surrogate,
    which `utf8` replaces with `?` before the cut: unencodable input has no prefix to preserve.

    A shortened identifier already carries a digest of the whole string, so losing up
    to three bytes of the prefix cannot make two ids collide.
    """
    encoded = utf8(text)
    #: `encoded.decode(...)`, not `text`. For valid Unicode text this is the identity - proved by
    #: differential over the shipped tree and 400,000 random strings - and for text carrying a
    #: lone surrogate it returns the `?` form rather than handing back a value that cannot be
    #: serialised. Returning `text` here left the 500 in place and merely moved it: pydantic's own
    #: serialiser raised on the unencodable string a few frames later.
    if len(encoded) <= limit:
        return encoded.decode("utf-8", errors="ignore")
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
    if len(utf8(item_id)) <= MAX_CONTENT_STRING:
        return cut_to_bytes(item_id, MAX_CONTENT_STRING)
    digest = hashlib.sha256(utf8(item_id)).hexdigest()[:DIGEST_CHARACTERS]
    keep = MAX_CONTENT_STRING - len(digest) - len(DIGEST_MARKER)
    return f"{cut_to_bytes(item_id, keep)}{DIGEST_MARKER}{digest}"
