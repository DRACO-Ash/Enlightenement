"""HTTP surface for the training layer, and the single-page app that drives it.

Kept out of `app.py` because the factory there is already the whole container contract, and a
route group with its own content store and its own failure modes reads better beside those failure
modes than inside the health-probe wiring.

**Three rules this module exists to hold:**

● **The answer key never crosses the wire before the operator commits.** `GET /api/v1/drill/next`
  serialises a :class:`~enlightenment.training.ServedDrill`, which has no answer field to leak.
  The reveal is the response to `POST /api/v1/drill/answer`, after an answer has been stored.
● **Writes are rate limited and validated at the boundary.** Answering is a write: it moves a
  rating, schedules a cue and appends a run record. It goes through the strict tier the plan asks
  for on the scoring endpoint by name, but through its OWN bucket (`DRILL_LIMIT`) rather than the
  one the gated session writes share. This route is unauthenticated until operator identity
  exists, so anyone can spend its budget; while the two shared a limiter, anyone could spend the
  gated routes' budget too, and twenty unauthenticated answers left a token-authenticated session
  write answering 429.
● **Content failures are author-facing and never fatal.** A malformed content tree yields a 503
  from the drill endpoints naming the files at fault, while the health paths stay green: the
  container is fine, the content is not, and those are different incidents.

**Authentication is deliberately NOT on these routes yet, and that is a stated gap, not an
oversight.** The plan makes sign-in a real boundary because it gates personal performance records,
and it puts identity behind an `IdentityProvider` adapter at step 10. Until that lands every
request is served as :data:`~enlightenment.training.DEMONSTRATION_OPERATOR`, a synthetic id, so no
named-individual record can be written before the DPIA is signed. The interface says so on screen.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from fastapi import HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse

from enlightenment import __version__
from enlightenment.audit import log_event
from enlightenment.content import ContentStore, Procedure
from enlightenment.models import DrillAnswer
from enlightenment.training import (
    CONFIDENCE_STEPS,
    DEMONSTRATION_OPERATOR,
    DrillEngine,
    DrillError,
)

if TYPE_CHECKING:  # pragma: no cover - imported for typing only
    from fastapi import FastAPI

#: Where the content tree sits. Resolved from the package rather than the working directory, so it
#: is the same path whether the app is run from a checkout or from `/app` in the container, and
#: overridable by environment for an operator who mounts content elsewhere. `CONTENT_DIR` is read
#: here and never set in the Dockerfile, which is the platform-injection rule this project holds
#: for `PORT` and `DATA_DIR` applied to one more variable.
_PACKAGE_ROOT: Final = Path(__file__).resolve().parents[2]


def resolve_content_root() -> Path:
    override = os.environ.get("CONTENT_DIR", "").strip()
    return Path(override) if override else _PACKAGE_ROOT / "content"


#: The interface directory. Two files: the document and its script. The script is a sibling rather
#: than inline because the response sets `script-src 'self'`, and the alternatives to a separate
#: file are a maintained CSP hash or `'unsafe-inline'`. One extra file is cheaper than either, and
#: `'unsafe-inline'` on script is not available to this project at any price.
_UI_DIRECTORY: Final = Path(__file__).resolve().parent / "ui"

#: What may be served out of the interface directory, by exact name. An allowlist rather than a
#: path join with a traversal check: a two-entry allowlist cannot be traversed, and every
#: path-normalisation bug in this class comes from believing the check was right.
_UI_FILES: Final[dict[str, str]] = {
    "app.js": "text/javascript; charset=utf-8",
}


def resolve_ui_file() -> Path:
    """The single-file SPA. Read from disk per request rather than cached in memory.

    Per-request read, deliberately: the file is small, the platform serves ten concurrent
    operators, and hot-editing the interface without a restart is worth more here than saving a
    few microseconds. If that ever stops being true it becomes a cached read with an mtime check,
    not a build step.
    """
    return _UI_DIRECTORY / "index.html"


def _content_unavailable(errors: Sequence[str]) -> HTTPException:
    """503 naming the files at fault. Author-facing detail, because the author is the audience.

    503 rather than 500: the service is healthy and the content is not, and a 500 would send
    someone looking at the container. The errors are content paths and validation messages, which
    carry no secret and no personal data, so echoing them costs nothing and saves a log dive.
    """
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "error": "content_unavailable",
            "message": (
                "The training content tree did not load. No drill can be served until it does."
            ),
            "content_errors": list(errors[:20]),
        },
    )


def register_training_routes(
    app: FastAPI,
    *,
    content: ContentStore,
    engine: DrillEngine,
    guard_write: Any,
) -> None:
    """Mount the interface and the training API.

    `guard_write` is passed in rather than imported so the rate limiter stays owned by the
    factory, which is what lets the factory hand THIS route a different bucket from the gated
    session writes. It is `_guard_drill_rate`, not `_guard_write_rate`: an open route must not be
    able to spend a gated route's allowance and shut it.

    Split into three registrations rather than one, because each closure counts towards the
    enclosing function's cognitive complexity and the cap (Sonar S3776, fifteen per function in
    this project) is an ally here: interface, library and drill are three separable concerns with
    three different failure modes.
    """
    _register_interface(app)
    _register_library(app, content=content)
    _register_drill(app, engine=engine, content=content, guard_write=guard_write)


#: Headers on every interface response. Named once so the document and its script cannot drift
#: apart: a strict policy on the page and a lax one on the script it loads is no policy.
_UI_HEADERS: Final[dict[str, str]] = {
    # The plan's air-gap posture, enforced rather than trusted: no CDN, no external call, no
    # inline handler. `'unsafe-inline'` appears for STYLE only, because the stylesheet is inline
    # in the document; `script-src` stays strict, so an injected string cannot execute.
    "content-security-policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';"
        " img-src 'self' data:; connect-src 'self'; font-src 'self';"
        " base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
    "referrer-policy": "no-referrer",
    "cache-control": "no-store",
}


def _register_interface(app: FastAPI) -> None:
    """The interface document and its script, and the headers that keep both air-gapped."""

    @app.get("/ui/{filename}")
    async def interface_asset(filename: str) -> Response:
        """Serve one allowlisted interface file.

        The name is looked up in `_UI_FILES` and never joined onto a path, so there is no traversal
        to defend against: an unknown name is a 404 before any filesystem call. `index.html` is not
        in the allowlist because it has its own route above with its own content type.
        """
        media_type = _UI_FILES.get(filename)
        if media_type is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "not_found", "message": "No such interface file."},
            )
        try:
            body = await asyncio.to_thread((_UI_DIRECTORY / filename).read_text, encoding="utf-8")
        except OSError as exc:
            log_event("ui.asset_unavailable", filename=filename, errno=exc.errno)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"error": "ui_unavailable", "message": "An interface file is missing."},
            ) from None
        return Response(content=body, media_type=media_type, headers=_UI_HEADERS)

    @app.get("/ui", response_class=HTMLResponse)
    @app.get("/ui/", response_class=HTMLResponse)
    async def interface() -> HTMLResponse:
        """The operator interface.

        Served at `/ui` and not at `/`, on purpose: `/` is part of the App Store health contract
        and answers 200 with a machine-readable body that the platform router and this project's
        own contract tests both depend on. Moving the interface there would make one route serve
        two audiences and put the health contract at the mercy of a front-end change.
        """
        path = resolve_ui_file()
        try:
            markup = await asyncio.to_thread(path.read_text, encoding="utf-8")
        except OSError as exc:
            log_event("ui.unavailable", path=str(path), errno=exc.errno)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"error": "ui_unavailable", "message": "The interface file is missing."},
            ) from None
        return HTMLResponse(content=markup, headers=_UI_HEADERS)


def _register_library(app: FastAPI, *, content: ContentStore) -> None:
    """Content status and the procedure library. Both read-only, neither scored."""

    @app.get("/api/v1/content")
    async def content_status() -> dict[str, Any]:
        """What content is loaded, what failed, and who authored it.

        The provenance fields are here because the current content set is ILLUSTRATIVE and the
        interface has to be able to say so on screen. A trainer that cannot tell an operator whether
        the procedure they just learned is authoritative is worse than no trainer.
        """
        result = await asyncio.to_thread(content.reload)
        procedures = [
            {
                "id": item.meta.id,
                "version": item.meta.version,
                "title": item.meta.title,
                "status": item.meta.status.value,
                "authored_by": item.meta.authored_by,
                "authored_on": item.meta.authored_on.isoformat(),
                "steps": len(item.steps),
            }
            for item in content.all_of("procedures").values()
            if isinstance(item, Procedure)
        ]
        return {
            "ok": result.ok,
            "version": __version__,
            "counts": {kind: len(items) for kind, items in result.items.items()},
            "errors": list(result.errors[:20]),
            "procedures": sorted(procedures, key=lambda row: row["id"]),
            "confidence_steps": {str(step): value for step, value in CONFIDENCE_STEPS.items()},
            "operator_id": DEMONSTRATION_OPERATOR,
            "identity": (
                "Synthetic operator. Sign-in and the supervisor audit trail are flight plan step"
                " 10, and no named-individual record is written before the DPIA is signed."
            ),
            "content_provenance": (
                "ILLUSTRATIVE content, authored to exercise the interface end to end. Derived from"
                " public open-source material only. NOT a JCO procedure and not validated by a"
                " subject-matter expert."
            ),
        }

    @app.get("/api/v1/library/{procedure_id}")
    async def procedure_detail(procedure_id: str) -> dict[str, Any]:
        """One procedure in full, for the library view and for reading after a drill.

        Reading a procedure is not scored and is deliberately always available: the plan's tone
        rule is that errors are learning events, and locking the reference behind a completed drill
        would make looking it up feel like cheating rather than like learning.
        """
        found = content.get("procedures", f"{procedure_id}@v1")
        if not isinstance(found, Procedure):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "not_found", "message": "No such procedure version is loaded."},
            )
        return {
            "id": found.meta.id,
            "version": found.meta.version,
            "title": found.meta.title,
            "status": found.meta.status.value,
            "authored_by": found.meta.authored_by,
            "authored_on": found.meta.authored_on.isoformat(),
            "change_reason": found.meta.change_reason,
            "purpose": found.purpose,
            "entry_conditions": list(found.entry_conditions),
            "roles": list(found.roles),
            "steps": [
                {
                    "ordinal": step.ordinal,
                    "action": step.action,
                    "responsible_role": step.responsible_role,
                    "note": step.note,
                    "warning": step.warning,
                }
                for step in found.steps
            ],
            "threshold_criteria": [
                {"name": item.name, "condition": item.condition}
                for item in found.threshold_criteria
            ],
            "reporting_requirements": list(found.reporting_requirements),
            "transition_rules": [
                {"when": rule.when, "to_procedure_id": rule.to_procedure_id}
                for rule in found.transition_rules
            ],
            "closure_criteria": list(found.closure_criteria),
        }


def _register_drill(
    app: FastAPI, *, engine: DrillEngine, content: ContentStore, guard_write: Any
) -> None:
    """The drill loop itself: serve without the answer, score what comes back."""

    @app.get("/api/v1/drill/next")
    async def next_drill(response: Response) -> dict[str, Any]:
        """The next unanswered drill. Carries no answer key, by construction."""
        if not content.all_of("drills"):
            result = await asyncio.to_thread(content.reload)
            if not result.ok:
                raise _content_unavailable(result.errors)
        try:
            served = await asyncio.to_thread(engine.serve, operator_id=DEMONSTRATION_OPERATOR)
        except DrillError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"error": "no_drill", "message": str(exc)},
            ) from None
        # Never cached. A cached drill is the same instantiation twice, which defeats the
        # template-versus-instance split, and a cached answer page would be a stale reveal.
        response.headers["cache-control"] = "no-store"
        return served.as_dict()

    @app.post("/api/v1/drill/answer")
    async def answer_drill(payload: DrillAnswer, request: Request) -> dict[str, Any]:
        """Score one produced answer and return the full decomposition.

        A write: it moves a rating, schedules the cue and appends a run record. So it passes a
        strict-tier limiter, which is what the plan asks for on the scoring endpoint by name, and
        specifically its own `DRILL_LIMIT` bucket rather than the gated writes' one.
        """
        guard_write(request)
        try:
            scored = await asyncio.to_thread(
                engine.score,
                operator_id=DEMONSTRATION_OPERATOR,
                item_id=payload.item_id,
                classification=payload.classification,
                first_action=payload.first_action,
                confidence=payload.confidence,
            )
        except DrillError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "unscorable", "message": str(exc)},
            ) from None
        # Audited without the answer text and without the score. The plan forbids a personal
        # performance figure in any log line, and the operator's own words are performance data;
        # the item and the content hash are what an incident actually needs.
        log_event(
            "drill.answered",
            actor=DEMONSTRATION_OPERATOR,
            itemId=scored.item_id,
            procedureId=scored.procedure_id,
        )
        return scored.as_dict()

    @app.get("/api/v1/dashboard")
    async def dashboard(response: Response) -> dict[str, Any]:
        """Where the operator stands, what has decayed, and what is due."""
        payload = await asyncio.to_thread(engine.dashboard, operator_id=DEMONSTRATION_OPERATOR)
        response.headers["cache-control"] = "no-store"
        return payload
