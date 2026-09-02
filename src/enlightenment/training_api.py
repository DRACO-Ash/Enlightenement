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
import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from fastapi import HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from enlightenment.audit import log_event
from enlightenment.content import CONTENT_DIR_VARIABLE, ContentPackage
from enlightenment.scoring import MAX_ANSWER_LENGTH
from enlightenment.training import (
    DEMONSTRATION_OPERATOR,
    DrillError,
    DrillLoop,
    bounded_reason,
)
from enlightenment.training.drill import _bounded as bounded_identifier

#: How many content errors either anonymous route serves. A NAMED constant across both, because
#: the two literals drifted apart once already and the count cap is half of the bound: per-entry
#: length and entry count are different limits and neither substitutes for the other.
MAX_SERVED_ERRORS: Final = 20

#: Largest serialised library document either reference route will serve. The library is a
#: reference and the flight plan makes it anonymous, so its fields are NOT individually bounded -
#: a per-field cap would mutilate the reference. The control is the document size, and it FAILS
#: CLOSED: an oversized document is refused with a 503 naming it, rather than served truncated,
#: because a silently shortened reference is worse than an absent one.
#:
#: 64 kB is measured against the shipped library: the largest procedure serialises to 13,888 bytes
#: and the largest product - PRD-COCO, document plus layout - to 5,616, so this clears honest
#: content 4.7 times over. The 2,304 in an earlier draft of this comment was the product document
#: alone, measured without the layout the route serves beside it. The
#: gate reached 2,497,065 bytes on a procedure and 342,786 on a product by stretching string
#: leaves, both anonymous, and the sweep that was supposed to cover these routes skipped them
#: because its discovery filter dropped every parameterised path.
MAX_SERVED_DOCUMENT_BYTES: Final = 64 * 1024

if TYPE_CHECKING:  # pragma: no cover - imported for typing only
    from fastapi import FastAPI

#: Where the content tree sits. Resolved from the package rather than the working directory, so it
#: is the same path whether the app is run from a checkout or from `/app` in the container, and
#: overridable by environment for an operator who mounts content elsewhere. `CONTENT_DIR` is read
#: here and never set in the Dockerfile, which is the platform-injection rule this project holds
#: for `PORT` and `DATA_DIR` applied to one more variable.
_PACKAGE_ROOT: Final = Path(__file__).resolve().parents[2]


def resolve_content_root() -> Path:
    """One environment name for the content tree, and the loader owns it.

    This read `CONTENT_DIR` while `ContentPackage`'s own resolver read
    `ENLIGHTENMENT_CONTENT_DIR`. An operator who set the second got the baked-in tree served over
    HTTP while the validator checked a different one, so verification leg 2 could pass green
    against content the server never loads.
    """
    override = os.environ.get(CONTENT_DIR_VARIABLE, "").strip()
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
            #: Each error BOUNDED, not only the list. Measured on a hostile tree: twenty errors,
            #: the longest 4,253 characters, an 85,151-byte anonymous response - because a content
            #: error quotes the value that failed validation and `content/models.py` sets no
            #: maximum on any of them. Twenty entries of unbounded length is not a bound, which is
            #: the same fault the withhold reason carried on the manifest one route along.
            "content_errors": [bounded_reason(str(error)) for error in errors[:MAX_SERVED_ERRORS]],
        },
    )


def register_training_routes(
    app: FastAPI,
    *,
    content: ContentPackage,
    loop: DrillLoop,
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
    _register_library(app, content=content, loop=loop)
    _register_drill(app, loop=loop, content=content, guard_write=guard_write)


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


def _register_library(app: FastAPI, *, content: ContentPackage, loop: DrillLoop) -> None:
    """What is loaded, and the procedures an operator may read. Never gated, never scored."""

    @app.get("/api/v1/content/manifest")
    async def manifest() -> dict[str, Any]:
        """Loaded versions, the content hash and what the package will not let us serve yet.

        The hash is the important field. Every run record carries it, so a result from last week
        stays interpretable against content that has since changed.
        """
        result = content.result
        served = loop.manifest()
        return {
            "ok": result.ok,
            "content_hash": result.content_hash,
            "counts": dict(result.counts),
            #: Bounded per entry AND capped in count, like the 503 below. Bounding only that exit
            #: left this one at 86,317 bytes on the same hostile tree - LARGER than the response
            #: V0.26.6 cites as the defect it closed, in this file, 110 lines away. There were four
            #: surfaces carrying the class, not three, and this codebase's own sentence for it is
            #: "a bound applied at one of two exits is a bound at neither".
            "errors": [bounded_reason(str(error)) for error in result.errors[:MAX_SERVED_ERRORS]],
            "thresholds_source": content.thresholds.source,
            "scored_scenarios_ready": content.scored_scenarios_ready,
            #: What is NOT wired, disclosed on a surface an operator can actually reach. These
            #: counts were honest in the commit message, the changelog and three docstrings, and
            #: absent from the product, which is the one place a supervisor would look.
            "rubric_rules_implemented": served["rubric_rules_implemented"],
            "rubric_rules_unwired": served["rubric_rules_unwired"],
            "stimulus_params_unread": served["stimulus_params_unread"],
            #: Served, not merely computed. `manifest()` carried this and the route did not, so
            #: the claim "named on the manifest" was true one altitude below the surface an
            #: operator can reach - which is the fault this codebase names at `ScoredDrill`.
            "items_without_a_resolvable_answer": served["items_without_a_resolvable_answer"],
            #: Serialised in the same edit that adds it to `manifest()`. Adding a field to the
            #: method and forgetting the route is the exact fault the security gate raised one
            #: commit ago, and I repeated it within the hour writing this fix.
            "withheld_reasons": served["withheld_reasons"],
            "why_not_ready": (
                ""
                if content.scored_scenarios_ready
                else "Thresholds carry placeholders. A scored scenario is refused until"
                " thresholds.local.json is populated, because an operator seeing a placeholder"
                " value in the interface is a bug."
            ),
        }

    @app.get("/api/v1/content/procedure/{procedure_id}")
    async def procedure_detail(procedure_id: str) -> dict[str, Any]:
        """One procedure, in full. The library is a reference, so nothing here is withheld."""
        if not content.result.ok:
            raise _content_unavailable(content.result.errors)
        found = next((p for p in content.procedures if p.id == procedure_id), None)
        if found is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "not_found", "message": "No such procedure."},
            )
        return _within_document_budget({"procedure": found.model_dump(mode="json")}, procedure_id)

    @app.get("/api/v1/content/product/{product_id}")
    async def product_detail(product_id: str) -> dict[str, Any]:
        """A product definition and its observed layout, so the interface can say how it reads."""
        if not content.result.ok:
            raise _content_unavailable(content.result.errors)
        found = content.product(product_id)
        if found is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "not_found", "message": "No such product."},
            )
        return _within_document_budget(
            {"product": found.model_dump(mode="json"), "layout": content.layout(product_id)},
            product_id,
        )


def _within_document_budget(document: dict[str, Any], identifier: str) -> dict[str, Any]:
    """A reference document, or a 503 saying it is too large to serve. Never a truncated one."""
    size = len(json.dumps(document, default=str).encode("utf-8"))
    if size > MAX_SERVED_DOCUMENT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "document_too_large",
                "message": (
                    f"The library document {bounded_identifier(identifier)!r} serialises"
                    f" to {size} bytes,"
                    f" over the {MAX_SERVED_DOCUMENT_BYTES}-byte budget for an anonymous"
                    " reference response. This is a content fault, not a request fault."
                ),
            },
        )
    return document


class DrillAnswer(BaseModel):
    """One submitted answer. Validated at the boundary, and nothing here is optional by accident."""

    model_config = ConfigDict(extra="forbid")

    drill_run_id: str = Field(min_length=1, max_length=64)
    response: str = Field(min_length=1, max_length=MAX_ANSWER_LENGTH)
    confidence: int = Field(ge=1, le=5)
    #: Validated and then NOT forwarded. The client's own timer cannot decide a score, so the
    #: field is bounded here as a wire contract - a client that sends nonsense still gets a 422 -
    #: and the elapsed time the scorer uses is measured from the server's own `served_at`.
    elapsed_ms: int = Field(ge=0, le=3_600_000)


def _register_drill(
    app: FastAPI, *, loop: DrillLoop, content: ContentPackage, guard_write: Any
) -> None:
    """The drill loop. The one place the production-format rule can be defeated, so it is here."""

    @app.get("/api/v1/drill/next")
    async def next_drill(response: Response) -> dict[str, Any]:
        """Serve the next item. **No accept value, no reject value, no explanation, no answer.**

        `no-store`, because a cached drill payload is a drill an operator can re-read after
        seeing the reveal, and the spacing model assumes retrieval rather than recognition.
        """
        if not content.result.ok:
            raise _content_unavailable(content.result.errors)
        try:
            served = await asyncio.to_thread(loop.serve, operator_id=DEMONSTRATION_OPERATOR)
        except DrillError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"error": "no_drill", "message": str(exc)},
            ) from None
        response.headers["cache-control"] = "no-store"
        return served.as_dict()

    @app.post("/api/v1/drill/answer")
    async def answer_drill(payload: DrillAnswer, request: Request) -> dict[str, Any]:
        """Score one answer and return the full decomposition.

        A write: it moves a rating, schedules the cue and appends a run record. So it passes a
        strict-tier limiter, and specifically its own `DRILL_LIMIT` bucket rather than the gated
        writes' one, because an open route must not be able to spend a gated route's allowance.

        Idempotent on the run id: a second submission returns the first result rather than
        rescoring, so a double-click cannot move a rating twice.
        """
        guard_write(request)
        try:
            scored = await asyncio.to_thread(
                loop.score,
                run_id=payload.drill_run_id,
                response=payload.response,
                confidence=payload.confidence,
                operator_id=DEMONSTRATION_OPERATOR,
            )
        except DrillError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "unscorable", "message": str(exc)},
            ) from None
        # The item and the actor, and neither the submitted answer nor any score. The plan forbids
        # a personal performance figure in a log line, and an operator's own words are
        # performance data.
        log_event(
            "drill.answered",
            actor=DEMONSTRATION_OPERATOR,
            itemId=scored.item_id,
        )
        return scored.as_dict()

    @app.get("/api/v1/me")
    async def me(response: Response) -> dict[str, Any]:
        """Where the operator stands.

        **Never a bare competency estimate.** The interval is part of the value: a figure with no
        interval invites a claim the data cannot support, and this is the number a supervisor
        would read.
        """
        if not content.result.ok:
            raise _content_unavailable(content.result.errors)
        response.headers["cache-control"] = "no-store"
        return await asyncio.to_thread(loop.dashboard, operator_id=DEMONSTRATION_OPERATOR)
