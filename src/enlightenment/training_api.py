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
from enlightenment.identifiers import MAX_CONTENT_STRING, served_identifier, utf8
from enlightenment.scoring import MAX_ANSWER_LENGTH
from enlightenment.training import (
    DEMONSTRATION_OPERATOR,
    MAX_SERVED_PROSE,
    DrillError,
    DrillLoop,
    bounded_reason,
    capped,
)

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
#: gate reached 2,497,065 bytes on a procedure and 342,884 on a product by stretching string
#: leaves, both anonymous, and the sweep that was supposed to cover these routes skipped them
#: because its discovery filter dropped every parameterised path.
MAX_SERVED_DOCUMENT_BYTES: Final = 64 * 1024

#: How many orbital regimes one index entry serves. The shipped tree's widest is five
#: (`PROC-LAUNCH`: LEO, MEO, GEO, HEO, XGEO), so this clears honest content twice over while
#: bounding the count as well as each entry's length.
MAX_SERVED_REGIMES: Final = 10

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
#:
#: **At the REPOSITORY ROOT, resolved through `_PACKAGE_ROOT`, exactly as `content/` is.** It sat
#: under the package until V0.27.8. The platform forces `sonar.sources=src`, so 1,322 lines of
#: JavaScript that no coverage report can ever describe were inside the analysed tree and counted
#: as uncovered: the gate scored 76.5% against a Python figure of 98.30%, and the arithmetic put
#: the CEILING at 77.83% even with perfect Python tests, so 80% was unreachable by testing.
#: `sonar.coverage.exclusions` was tried twice, with one pattern and then six, and the metric did
#: not move either time.
#:
#: The placement is right on its own merits and not only because of the gate. This is served
#: DATA, like the content tree beside it - markup and a browser script, not Python source - and
#: `content/` already sits at the root for that reason and resolves through the same constant.
#: Both are copied into `/app` by the Dockerfile and staged by the packaging allowlist, so the
#: path is identical from a checkout and from the container.
_UI_DIRECTORY: Final = _PACKAGE_ROOT / "ui"

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


async def interface_response() -> HTMLResponse:
    """The interface document, with the headers that keep it air-gapped.

    ONE responder for the two routes that serve it - `/ui` and, for a browser, `/`. The
    alternative was a second `HTMLResponse` built beside the root route, and the thing that must
    not diverge is `_UI_HEADERS`: serving this markup without its Content-Security-Policy would
    ship the interface with the air-gap posture silently removed, which is a security regression
    dressed as a convenience.
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


#: The spellings of a zero quality weight. `text/html;q=0` is a client stating it does NOT accept
#: HTML, so naming the type while ignoring the weight would serve it the one thing it refused.
ZERO_WEIGHTS: Final = frozenset({"0", "0.0", "0.00", "0.000"})


def wants_markup(accept: str | None) -> bool:
    """Whether this caller asked for HTML, by name.

    **The default is the machine-readable body, and that direction is the whole design.** `/` is
    part of the App Store health contract, so an unknown client, a client sending `*/*`, a client
    sending nothing at all, and every probe keep exactly the JSON they have always had. Only an
    `Accept` header that NAMES `text/html` gets the interface - which is what a browser sends and
    what a kubelet probe does not.

    Added at V0.27.9 because the App Store console's "Open App" button opens `/`, so every human
    who followed it landed on `{"name":"Enlightenment",...}` and reasonably concluded the deploy
    had failed. It had not: all ten pipeline stages passed and the interface was at `/ui` the
    whole time. A correct contract that sends people to the wrong place is still a product fault.
    """
    if not accept:
        return False
    #: Parsed on the media type only. A `q=0` on `text/html` is a client saying it does NOT want
    #: HTML, and honouring the name while ignoring the weight would serve the opposite.
    for part in accept.split(","):
        media, _, parameters = part.strip().partition(";")
        if media.strip().lower() != "text/html":
            continue
        weights = [p.strip() for p in parameters.split(";") if p.strip().startswith("q=")]
        refused = bool(weights) and weights[0][2:].strip() in ZERO_WEIGHTS
        return not refused
    return False


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
        """The operator interface, at its canonical path.

        `/` also serves it, but only to a client that asks for HTML: see `interface_response`
        and the root route in `app.py`. This path is the one to bookmark and the one the
        documentation names, because it means the interface whatever the caller's headers say.
        """
        return await interface_response()


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
            #: Serialised WITH the list. Capping the list and leaving the total in the method is
            #: the fault this file names two fields down: a field added to `manifest()` and not to
            #: the route is true one altitude below the surface an operator reaches.
            "items_without_a_resolvable_answer_total": served[
                "items_without_a_resolvable_answer_total"
            ],
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

    @app.get("/api/v1/content/procedures")
    async def procedure_index() -> dict[str, Any]:
        """The procedures an operator may read, as an index rather than in full.

        The library screen needs a LIST and no route served one, so it had nothing to render from.
        Deliberately not the documents: the per-procedure route below already serves those under
        the same document budget, and an index that inlined thirteen full procedures would be a
        content-sized body on an anonymous route, which is the class this project has closed
        eleven times.

        Every field is bounded on the way out, by the conventions the sibling routes already use:
        `served_identifier` for an id, because two ids differing past the cap would otherwise
        merge into one entry the interface then keys on, and `capped` for prose, because a name is
        operator-facing text and a silent cut reads as the name somebody chose.
        """
        if not content.result.ok:
            raise _content_unavailable(content.result.errors)
        index = _procedure_index(content)
        return _within_document_budget({"procedures": index, "count": len(index)}, "index")

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


def _content_shape_fault(procedure_id: str, field: str, value: Any) -> HTTPException:
    """503 naming the procedure and the field whose SHAPE is wrong, never a 500.

    The TYPE is the diagnosis and the value is not served: an authored value has no declared
    maximum, and this module already refuses to echo one unbounded. A type name is bounded by
    construction and is what an author needs to find the record.
    """
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "error": "content_unavailable",
            "message": (
                f"The procedure index cannot be served: {field} on"
                f" {served_identifier(procedure_id)} is a {type(value).__name__}, and the"
                " schema declares it otherwise. One malformed record is a content fault, not a"
                " server fault."
            ),
        },
    )


def _authored_text(value: Any, limit: int, *, procedure_id: str, field: str) -> str:
    """Authored prose, bounded - or a content fault if it is not prose at all.

    **This exists because `capped` stringifies whatever it is handed.** `capped(value: Any)` calls
    `str()`, which never fails, so a list-shaped `purpose` served
    `"['a purpose in two', 'parts']"` to an operator: correctly bounded, correctly escaped and
    correctly wrong. V0.27.1 fixed exactly that fault on `regime` and left it standing on
    `purpose` one line above, which is why this is a TYPE gate at the boundary rather than a
    third field-by-field repair. A number is accepted and rendered, because an authored numeric
    is a legitimate scalar; a container is not.
    """
    if value is None:
        return ""
    #: `str` ONLY. An earlier draft admitted `int` and `float` as "legitimate scalars", which let
    #: `purpose: 7` render as the text "7" on a library card. The schema declares every field
    #: this gate guards as a string, so a number here is a shape fault like any other container,
    #: and the gate is named for text.
    if isinstance(value, str):
        return capped(value, limit)
    raise _content_shape_fault(procedure_id, field, value)


def _authored_sequence(value: Any, *, procedure_id: str, field: str) -> list[Any]:
    """An authored list, or a content fault.

    A bare string is REFUSED rather than iterated: slicing a string yields characters, so a
    string-shaped `regime` rendered ten one-letter pills, and a mapping or a number raised
    `KeyError: slice(...)` or `TypeError` out of the slice and reached the caller as an
    undiagnosed 500 - one malformed record killing the index for every procedure.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    raise _content_shape_fault(procedure_id, field, value)


def _procedure_index(content: ContentPackage) -> list[dict[str, Any]]:
    """The library list: identifiers, a bounded purpose, and a step COUNT.

    A module-level helper rather than a loop inside the registrar, because the registrar was at
    ruff's complexity cap and one more route tipped it. Extracting the body is the fix; raising
    the cap would be the suppression.

    `purpose` and `regime` are AUTHORED prose and an authored term, so both are bounded on the
    way out - prose on the prose cap, the term on the string cap - for the reason the sibling
    routes give: an anonymous route that echoes an authored string echoes whatever length the
    author gave it, and `content/models.py` sets no maximum on any of them.
    """
    index: list[dict[str, Any]] = []
    for procedure in content.procedures:
        extra = procedure.model_extra or {}
        identifier = procedure.id
        regimes = _authored_sequence(extra.get("regime"), procedure_id=identifier, field="regime")
        #: A COUNT, not the steps: the document route serves those, and inlining thirteen step
        #: lists here is the content-sized body this index exists to avoid. It is a count OF A
        #: LIST, checked: `len()` over a mapping counted its keys and over a string counted its
        #: characters, and both answered 200 with a plausible number in place of a step count.
        steps = _authored_sequence(extra.get("steps"), procedure_id=identifier, field="steps")
        index.append(
            {
                "id": served_identifier(identifier),
                "name": _authored_text(
                    procedure.name, MAX_CONTENT_STRING, procedure_id=identifier, field="name"
                ),
                "status": _authored_text(
                    procedure.status, MAX_CONTENT_STRING, procedure_id=identifier, field="status"
                ),
                "purpose": _authored_text(
                    extra.get("purpose"),
                    MAX_SERVED_PROSE,
                    procedure_id=identifier,
                    field="purpose",
                ),
                #: Each regime bounded individually and the count capped, because per-entry
                #: length and entry count are different limits and neither substitutes for the
                #: other. Each ENTRY goes through the text gate too: a list of lists would
                #: otherwise put a repr inside a pill.
                "regime": [
                    _authored_text(
                        entry, MAX_CONTENT_STRING, procedure_id=identifier, field="regime"
                    )
                    for entry in regimes[:MAX_SERVED_REGIMES]
                ],
                "steps": len(steps),
            }
        )
    return index


def _within_document_budget(document: dict[str, Any], identifier: str) -> dict[str, Any]:
    """A reference document, or a 503 saying it is too large to serve. Never a truncated one."""
    size = len(utf8(json.dumps(document, default=str)))
    if size > MAX_SERVED_DOCUMENT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "document_too_large",
                "message": (
                    f"The library document {served_identifier(identifier)!r} serialises"
                    f" to {size} bytes,"
                    f" over the {MAX_SERVED_DOCUMENT_BYTES}-byte budget for an anonymous"
                    " reference response. This is a content fault, not a request fault."
                ),
            },
        )
    return document


class DrillAnswer(BaseModel):
    """One submitted answer. Validated at the boundary, and nothing here is optional by accident.

    A SECOND `DrillAnswer` sat in `models.py` until V0.26.36, unreferenced, carrying an earlier
    field set (`item_id`, `classification`, `first_action`). It read as load-bearing beside two
    models that had just been hardened, so wiring it up would have re-opened the escaped-control
    size class in silence. Deleted; this is the boundary model, and the reasoning it carried is
    kept here where it applies.

    `response` is free text and that is the product's central design choice, not an oversight: the
    plan requires production rather than recognition, so there is no option id to validate against
    a list. What is validated is shape and size.

    **`response` is deliberately NOT `FreeText`.** That rule is a SIZE control for the served
    session ceiling, where an escaped control costs six rendered bytes against an astral
    character's four. This field reaches neither a served surface nor the store: the matcher
    returns only a verdict and the authored `note`/`why_wrong`, and the run row records
    `classification=outcome.matched` with `first_action=""`, so the operator's own words are never
    echoed and never persisted. That property is what makes the exemption correct rather than
    convenient, so it is bound by a test rather than left as a reading of the code.

    `confidence` is an integer step rather than a percentage. Five steps are answerable in under a
    second, which the 100ms cue-to-feedback budget needs, and a discrete scale stops an operator
    hedging at 50% on everything to game a proper scoring rule.
    """

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
            #: SHORTENED. `audit.py` cuts a log value at 256 with no marker and no digest, so two
            #: ids differing only past 256 characters produced byte-identical log lines. This
            #: module's own comment says a log line is a wire too, and this was the one identifier
            #: sink that did not use the function at all.
            itemId=served_identifier(scored.item_id),
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
