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
