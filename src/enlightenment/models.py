"""Boundary models. Every request body is validated here and rejected on failure.

``extra="forbid"`` is the fail-closed rule made mechanical: an unknown key is a
rejected request, never a silently coerced or stored one. Every string field is
length-capped so a payload cannot grow the store without limit.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

#: Slug shape for a session id: lowercase alphanumeric with single internal hyphens.
SESSION_ID_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"

#: The control characters an operator legitimately types into free text. Everything else
#: non-printable is refused.
FREE_TEXT_CONTROLS = frozenset("\n\r\t")


def _no_stray_control(value: str) -> str:
    """Free text with no control character in it beyond a line break or a tab.

    **A SIZE control as much as a hygiene one, and that is why it lives at the boundary rather
    than at the wire.** `json.dumps` escapes a C0 control as `\\u00XX` even with
    `ensure_ascii=False`, so one code point renders as SIX bytes where an astral character renders
    as four and a newline as two. The field caps count CODE POINTS, so the worst case was set by
    the most expensive character the boundary accepted, and it accepted `U+0000`.

    Measured: twenty writes at the declared caps, filled with NUL and every one accepted with 201,
    rendered to 281,353 bytes against the 262,144 ceiling on `GET /api/v1/sessions`; twenty-five
    rows reach 351,327, or 134% of it. So an anonymous route fail-closed to 503 on twenty
    legitimate authenticated writes, while the refusal told the operator "a row was not written
    through this API" - **provably false, and it sends them hunting an out-of-band volume write
    that never happened.**

    The rule is `str.isprintable()`, which this project already applies in `audit.py`,
    `healthcheck.py` and `config.py`, so it is an existing convention rather than a new one. The
    boundary was already inconsistent with itself: `U+2028` was refused, but only incidentally -
    `str_strip_whitespace` strips it to empty and `min_length` rejects that - while `U+0000` sailed
    through. `\n`, `\r` and `\t` are allowed because a note with line breaks is legitimate free
    text and each renders as two bytes, so keeping them costs nothing.

    With those refused, the most expensive accepted character is an astral one at four rendered
    bytes per code point, which makes the astral worst case the genuine one.

    The offending character is NOT named, per the boundary rule this project holds everywhere: the
    message gives the shape and pydantic supplies the field.
    """
    if any(
        not character.isprintable() and character not in FREE_TEXT_CONTROLS for character in value
    ):
        raise ValueError("carries a control character other than a line break or a tab")
    return value


#: Free text at the boundary: length-capped and control-free.
FreeText = Annotated[str, AfterValidator(_no_stray_control)]


class SessionUpsert(BaseModel):
    """A training session submitted by a caller.

    ``scenario`` is deliberately an open, length-capped string: the controlled
    vocabulary for orbital warfare training scenarios is TBC, re-verify with the
    project owner. Inventing one here would put unverified domain terms into stored
    data, so the field stays open until the real vocabulary is supplied.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=64, pattern=SESSION_ID_PATTERN)
    title: FreeText = Field(min_length=1, max_length=200)
    scenario: FreeText = Field(min_length=1, max_length=120)
    notes: FreeText | None = Field(default=None, max_length=2000)


class SessionPatch(BaseModel):
    """A partial update to an existing session.

    Every field is optional, which is what makes the anti-shrink rule observable: a
    payload that mentions only ``title`` must never delete ``notes``. ``extra="forbid"``
    still rejects an unknown key, so "partial" never means "unvalidated".
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: FreeText | None = Field(default=None, min_length=1, max_length=200)
    scenario: FreeText | None = Field(default=None, min_length=1, max_length=120)
    notes: FreeText | None = Field(default=None, max_length=2000)


class DrillAnswer(BaseModel):
    """One produced drill answer.

    Both answer fields are free text and that is the product's central design choice, not an
    oversight: the plan requires production rather than recognition, so there is no option id to
    validate against a list. What IS validated is shape and size, because a free-text field that
    reaches a store read whole on every request is a denial of service with a keyboard.

    ``confidence`` is an integer step rather than a percentage. Five steps are answerable in under
    a second, which the 100ms cue-to-feedback budget needs, and a discrete scale stops an operator
    hedging at 50% on everything to game a proper scoring rule.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    item_id: str = Field(min_length=1, max_length=64, pattern=SESSION_ID_PATTERN)
    classification: str = Field(min_length=1, max_length=300)
    first_action: str = Field(min_length=1, max_length=300)
    confidence: int = Field(ge=1, le=5)
