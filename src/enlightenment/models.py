"""Boundary models. Every request body is validated here and rejected on failure.

``extra="forbid"`` is the fail-closed rule made mechanical: an unknown key is a
rejected request, never a silently coerced or stored one. Every string field is
length-capped so a payload cannot grow the store without limit.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

#: Slug shape for a session id: lowercase alphanumeric with single internal hyphens.
SESSION_ID_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"


class SessionUpsert(BaseModel):
    """A training session submitted by a caller.

    ``scenario`` is deliberately an open, length-capped string: the controlled
    vocabulary for orbital warfare training scenarios is TBC, re-verify with the
    project owner. Inventing one here would put unverified domain terms into stored
    data, so the field stays open until the real vocabulary is supplied.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=64, pattern=SESSION_ID_PATTERN)
    title: str = Field(min_length=1, max_length=200)
    scenario: str = Field(min_length=1, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)


class SessionPatch(BaseModel):
    """A partial update to an existing session.

    Every field is optional, which is what makes the anti-shrink rule observable: a
    payload that mentions only ``title`` must never delete ``notes``. ``extra="forbid"``
    still rejects an unknown key, so "partial" never means "unvalidated".
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=200)
    scenario: str | None = Field(default=None, min_length=1, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)


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
