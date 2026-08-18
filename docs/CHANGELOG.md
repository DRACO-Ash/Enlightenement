# Changelog: Enlightenment

One audit row per change: what changed, why, and how it was verified.

## V0.2 (2026-08-18)

**What.** Closed every finding from the first engineering and security gate reviews: one
engineering BLOCKER, three security BLOCKERs, nine MAJORs, and the MINORs worth acting on.

The three that mattered most, each measured rather than argued:

● **Writes were open by default.** `require_token` returned a local actor before the token
  compare ran, so with no token configured, which is the container default with an empty
  operator environment tab, an unauthenticated caller could POST and PATCH. The loopback
  binding that was supposed to mitigate it is read only by the local runner; the container
  binds every interface from its launch command. Writes now fail closed and anonymous writes
  need an explicit `ENLIGHTENMENT_ALLOW_ANONYMOUS` opt-in that cannot combine with a token.
  Reads, health, and diagnostics stay open so the posture is recoverable.
● **The body cap trusted the declared content-length.** A chunked request declares none, so
  the check was skipped and the body was buffered in full before any handler or dependency:
  one unauthenticated 256 MB POST took the worker from 52 MB to 821 MB resident and returned
  422. The cap now counts bytes actually received, in a pure ASGI middleware that drains up
  to the cap and never further, ahead of authentication.
● **Two workers destroyed the dataset.** The launch command ran `--workers 2` against a
  file-backed read-modify-write store that called itself the single writer. Two processes,
  80 writes each, every one acknowledged with a 201 and an audit line: 40 records present
  afterwards. The atomic rename is exactly why the loss left no torn file. Now one worker, an
  exclusive `fcntl.flock` across load, merge, and rename, and a monotonic revision with
  `If-Match` returning 409 instead of overwriting.

Also fixed: `seed()` escaped the boot guard, so a corrupt or root-owned snapshot made the
worker unstartable rather than unready; `PATCH` was missing from the cross-origin method list
while being a shipped route, making the anti-shrink merge unreachable from a browser; the
readiness paths performed an unbounded real write per request, so an unauthenticated flood
could exhaust volume IOPS and then trip the probe's own timeout into a restart loop, now
bounded by a five-second cache; the HEALTHCHECK interpolated `PORT` raw, so
`PORT=8080@evil.example` made it probe an attacker-controlled host and report HEALTHY; `apt`
and `dpkg` shipped in the runtime image; the rate-limit key table evicted a tracked caller on
overflow, resetting its count, and now refuses the new key instead; the diagnostics read-out
published the token's exact length and now reports a coarse band with a 24-character minimum
enforced at boot; a wildcard origin now refuses to start unconditionally rather than only
alongside a token; store input and output moved off the event loop; the image HEALTHCHECK
moved to `/livez`; the audit sanitiser now covers every reflected log value structurally; the
`pip-audit` network classifier is structural rather than a grep over log text.

Two of the binding CI image checks were themselves unsound and are corrected: the suid sweep
ran as the image's non-root user, where `find` cannot descend into an unreadable directory
and returns zero while bits still ship, and the package-manager check tested for pip alone.

**Why.** A gate FAIL is the cheapest place to learn any of this. Every one of these defects
would have surfaced as a live incident or an App Store pipeline failure instead.

**How verified.** Loop green: ruff format and check across 23 rule families, mypy strict over
12 modules, 217 tests collected (216 passed, 1 skipped) with branch coverage at 97.63% against
an 80% floor, Cobertura written to `coverage.xml`, `pip-audit` clean. Pipeline simulation green
against the actual artefact on the pinned interpreter with `GITLAB_CI=true`. Twenty-one mutants
killed across two rounds; one recorded as surviving (the constant-time compare, whose property
no functional test can assert). Two mutants were killed only after fixing a TEST that matched
explanatory prose rather than the instruction it described.

**Still not verified.** The container image build, for the same reason as V0.1: the registry
blob endpoint is denied by this environment's network policy. The CI `image` job is binding.

**Deliberately NOT done.** `/var/lib/dpkg` is kept. It is the package database, not a tool,
and it is what the platform's policy scan reads to enumerate OS packages. Deleting it would
remove the scanner's evidence rather than the risk, which is suppressing a finding. The tools
come out; the truth about what ships stays in. A test asserts it is still there.

## V0.1 (2026-08-18)

**What.** First commit. The gate-compliant Python server skeleton: the `create_app(...)`
factory, env-only validated configuration, constant-time shared-token authentication,
two-tier rate limiting, fail-closed CORS, split liveness and readiness paths with a
real-write storage probe behind a hard timeout, a secret-free diagnostics read-out, one
structured JSON audit line per privileged action, an atomic anti-shrink JSON store with
schema version and pre-write backups, hash-locked dependencies, a flattened hardened
Dockerfile pinned by digest, quality-gate scoping, and the verification loop, packaging,
and pipeline-simulation scripts.

**Why.** The Foundations baseline ships standards, not a starter application, and the App
Store contract is cheapest to satisfy at scaffold time. Retrofitting it costs one upload
cycle per pipeline stage, because the platform reveals its requirements one gate at a time.

**How verified.** `ruff format --check` and `ruff check` clean across 23 selected rule
families (`python3 -c "import tomllib,pathlib;print(len(tomllib.loads(pathlib.Path('pyproject.toml').read_text())['tool']['ruff']['lint']['select']))"`);
`mypy` strict clean over 11 source files; 126 tests collected (125 passed, 1 skipped) with branch coverage at
97.60% against an 80% floor, Cobertura written to `coverage.xml`; `pip-audit` against the hash-locked
runtime requirements; the pipeline simulation green against the actual upload artefact in
the platform's environment (`GITLAB_CI=true`, its generated pipeline file present). Eight
mutants across the security controls were each confirmed to turn a named test red.

**Not verified here.** The container image build and the image policy posture. A Docker
daemon was started successfully, but the registry's blob endpoint is denied by the authoring
environment's network policy, so no base-image layer can be pulled and the Dockerfile is
neither proved nor disproved. `scripts/build-image.sh` distinguishes an unreachable registry
from a rejected Dockerfile and exits 3 with a "deferred to CI" banner rather than reporting a
pass; the CI `image` job is the binding check. One finding did come out of the attempt: the
`# syntax=docker/dockerfile:1` frontend directive was removed, because it makes the builder
fetch an external frontend image before reading any instruction, and the App Store runner sits
behind a registry mirror with no guaranteed public route. Every feature used is in BuildKit's
built-in frontend.

**Open with the project owner.** The training scenario vocabulary (`scenario` is an open,
length-capped string rather than an invented enumeration), the App Store category and
visibility, and the resource budget.
