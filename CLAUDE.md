# CLAUDE.md

Always-true conventions for this project. Procedures live in `.claude/skills/`. The house voice is in `.claude/output-styles/house-voice.md`. When a rule here and a skill disagree, this file wins for conventions and the skill wins for procedure.

## What this project is

Enlightenment is an orbital warfare training application. Archetype: `server` (a container running an HTTP API). Deployment target: the Bluestaq App Store at `enlightenment.apps.bluestaq.com`, detected template `python` (a root `requirements.txt` with a root `Dockerfile`), so the SonarQube quality gate is binding.

Stack: Python 3.12, FastAPI on gunicorn with the uvicorn worker. Source under `src/enlightenment/`, built by the `create_app(...)` factory. The training scenario vocabulary is `TBC, re-verify` with the project owner; the boundary model keeps that field open rather than inventing terms.

## Hard rules (never violate)

**Both archetypes**
- **No secrets in any shippable file**, in source or in history. Read secrets from the environment; render any value in docs as `[REDACTED:type]`. The pre-write hook blocks a credential before it lands.
- **No client-side access gate.** A hardcoded Personal Identification Number (PIN), flag, or hidden field in the browser is a User Experience gate, never security. Real gates are server-side.
- **Surgical edits only.** Change the smallest region that satisfies the request. Do not reformat, re-indent, or reconstruct regions you were not asked to touch.
- **Never invent a name, title, date, organisation, or figure** in user-facing content or data. If a fact is not verifiable, mark it with the explicit unknown marker (`TBC, re-verify`); do not assert it.
- **Every untrusted value is escaped or validated at the boundary**, and a control that cannot be verified is treated as failed (fail closed).

**Static archetype**
- Not applicable: this project is `server`. The static rules stay in the baseline at
  `.claude/skills/security-hardening/SKILL.md` should the archetype ever change.

**Server archetype**
- **The container is the whole build.** A single `Dockerfile` installs from the lockfile and runs the server; no separate bundler output. Runs as a non-root numeric user, no setuid/setgid binaries.
- **Listen on `os.environ["PORT"]`, default 8080, bound to `0.0.0.0`.** Never add `ENV PORT=` or
  `ENV DATA_DIR=` to the Dockerfile; code defaults carry those values and platform injection wins.
  Answer `/`, `/healthz`, `/readyz`, `/livez`, `/ping` with HTTP 200, unauthenticated.
  **Liveness and readiness are split, deliberately.** `/livez`, `/ping`, `/health` are
  dependency-free and always 200: a downstream outage must never restart a healthy
  container. `/healthz` and `/readyz` prove storage with a REAL write (an existence check
  passes on a read-only or root-owned mount and then fails the first write), race a hard
  timeout shorter than the platform probe, and return 503 with the resolved data directory
  and the exact errno when storage is unusable. The healthy case is 200 on all five paths;
  the 503 is the fail-closed branch the App Store contract requires, so a screenshot of an
  unhealthy pod is a complete diagnosis.
- **Secrets are server-side only.** Compare the team token in constant time. Validate every request body and every LLM output before storing or returning it; the dataset merge never silently shrinks.

## Commands

```
python3.12 -m venv .venv                                    create the environment
.venv/bin/pip install --require-hashes --no-deps \
  -r requirements.txt -r requirements-dev.txt               install, reproducibly
sh scripts/verify.sh                                        THE VERIFICATION LOOP
python3 scripts/check-environment.py <python> <lockfile>...  assert installed == pinned
python -m enlightenment                                     run locally (loopback, auth off)
sh scripts/simulate-pipeline.sh <version>                   simulate the platform pipeline
sh scripts/package-appstore.sh <version>                    build the upload artefact
sh scripts/build-image.sh enlightenment:<version>           build the container image
sh scripts/lock-requirements.sh                             re-lock after a dependency change
```

The loop runs cheapest-first, six legs: `scripts/check-environment.py` (installed versions
must equal the lock-file pins), `ruff format --check`, `ruff check`, `mypy` strict, `pytest`
with Cobertura coverage to `coverage.xml` at 80% or more, then `pip-audit`. A leg that
cannot run locally exits non-zero with a "deferred to CI" banner; it is never a green pass.

**Every leg runs through one resolved interpreter, never a bare tool name.** `verify.sh`
resolves `$PY` (`ENLIGHTENMENT_PYTHON`, then `.venv/bin/python`, then `$VIRTUAL_ENV`, then
`python3`) and calls `"$PY" -m ruff`, `"$PY" -m mypy`, and so on. Bare names let PATH choose
the analyser: the loop was once found running ruff 0.15.8 against a pinned 0.16.3 and mypy
1.19.1 against a pinned 2.3.1, which produced a finding the pinned toolchain does not raise.
A loop whose own inputs are unpinned cannot certify anything, so the environment check is
leg one, before any analyser.

Every change runs the verification loop, then passes the `engineering-reviewer` and `security-reviewer` gates before it is done. Anything that deploys, publishes, or mutates external state requires the `deploy-gate` verdict and an explicit human confirmation.

## Directory layout

```
src/enlightenment/physics/  the physics core: angles, SGP4 propagation, time and Earth rotation,
                            Clohessy-Wiltshire relative motion. Pure functions, no input or
                            output, no state. Flight plan Phase 0 step 2.
src/enlightenment/scenario/ the determinism substrate: seeded randomness, an integer-tick clock,
                            an append-only run log. Flight plan Phase 0 step 3, and a gate: the
                            same seed must yield an identical event log twice.
src/enlightenment/          the application source. Sources live under src/ deliberately:
                            the platform forces sonar.sources=src, so this placement and the
                            committed sonar-project.properties agree instead of racing.
tests/                      the suite the platform runs against the uploaded zip
scripts/                    the verification loop, packaging, and pipeline simulation
docs/                       deployment parameters, security policy, changelog
Dockerfile                  the whole build. Flat at the root, never nested.
sonar-project.properties    quality-gate scoping and the coverage report path
requirements*.txt           hash-locked dependencies (the python template marker)
.claude/                    the Foundations baseline (skills, agents, output style, hooks)
```

## Naming and versioning

- Releases are `V0.1` style. The version lives in `src/enlightenment/__init__.py` and
  `pyproject.toml`; bump both by path, never by a repo-wide search-and-replace, and add one
  audit row in `docs/CHANGELOG.md` on every change.
- The App Store slug is `enlightenment`: lowercase, alphanumeric, no hyphen at all, so it
  cannot trip the double-hyphen naming fault that fails a pipeline with zero stages run.

## House voice (applies to all prose, UI copy, comments, commits)

A guide, not a leash. Held everywhere: never fabricate data; avoid the long em-dash (a single dash is fine); no `+` meaning "and" in prose. The Bluestaq default, which is your call on your own project: UK English, the `£`/`$`/`%` symbols, expand an uncommon acronym on first use, lead with the decision then the reasoning. Anything publish-facing or Bluestaq-brand-facing follows the brand in full. Full voice: `.claude/output-styles/house-voice.md`.
