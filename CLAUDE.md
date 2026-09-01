# CLAUDE.md

Always-true conventions for this project. Procedures live in `.claude/skills/`. The house voice is in `.claude/output-styles/house-voice.md`. When a rule here and a skill disagree, this file wins for conventions and the skill wins for procedure.

## What this project is

Enlightenment is an orbital warfare training application. Archetype: `server` (a container running an HTTP API). Deployment target: the Bluestaq App Store at `enlightenment.apps.bluestaq.com`, detected template `python` (a root `requirements.txt` with a root `Dockerfile`), so the SonarQube quality gate is binding.

Stack: Python 3.12, FastAPI on gunicorn with the uvicorn worker. Source under `src/enlightenment/`, built by the `create_app(...)` factory.

**`docs/FLIGHT-PLAN.md` is the authority on what this product is and what order it is built in.** Read it before proposing any feature, sequence or interface. It carries the vision, the six competency axes, the thirteen-step build plan, the measured palette contrast figures, the performance budget, the out-of-scope list, and the definition of done. Where this file and the flight plan disagree on WHAT to build, the flight plan wins; this file governs HOW to build it.

The `scenario` FIELD on a stored session is still free text and validated only for shape, because a session record is not the procedure library. The training vocabulary itself is NOT open: the flight plan names the fifteen procedures, the three wired for v1 (Manoeuvre, RPO, Separation versus Breakup), and the six competency axes.

## Hard rules (never violate)

**Both archetypes**
- **No secrets in any shippable file**, in source or in history. Read secrets from the environment; render any value in docs as `[REDACTED:type]`. The pre-write hook blocks a credential before it lands.
- **No client-side access gate.** A hardcoded Personal Identification Number (PIN), flag, or hidden field in the browser is a User Experience gate, never security. Real gates are server-side.
- **Surgical edits only.** Change the smallest region that satisfies the request. Do not reformat, re-indent, or reconstruct regions you were not asked to touch.
- **Never invent a name, title, date, organisation, or figure** in user-facing content or data. If a fact is not verifiable, mark it with the explicit unknown marker (`TBC, re-verify`); do not assert it.
- **ASK for a missing document; never infer around it.** Owner instruction, after a plan was built by inference from the code and the DPIA while `docs/FLIGHT-PLAN.md` existed but was not in the repository. Noting an absence in a footer is not asking. If a governing document, figure or decision cannot be found, stop and request it by name - the cost of one question is always lower than the cost of a plan built on a guess.
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

## The two environments, and which one a command is for

**The owner's workstation is Windows, running PowerShell.** Recorded here because it was established
in conversation, never written down, and then lost to a context compaction - after which the step 4
runbook told the operator to run `chmod 600` and the tool refused every Windows credentials file on
synthetic POSIX permission bits. A fact that lives only in a transcript is a fact that will be
guessed again.

Two environments, and every operator-facing instruction states which one it is for:

● **The build and CI environment is Linux.** `scripts/*.sh`, the verification loop, the container,
  the pipeline. POSIX shell is correct here and needs no apology.
● **The owner's workstation is Windows and PowerShell.** Anything in `docs/RUNBOOK-*.md` or `tools/`
  runs there. So: no line-continuation backslash (PowerShell uses a backtick), no `chmod`, no `less`,
  and `python` as well as `python3` because the Windows launcher installs both. Give the PowerShell
  form first, and the POSIX form second where both are useful.

Code that runs in both places branches on the platform and checks something real on each side. It
never SKIPS a control because the usual mechanism is meaningless on one platform: Windows reports
synthetic `st_mode` bits, so the credentials check verifies the file sits inside the user profile,
where Windows access control restricts it. "The bits mean nothing here" is a reason to check
something else, never nothing.

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
- **Bump the version on EVERY change, not only on a release.** Owner decision, taken after three
  distinct artefacts shipped as `0.22.0` in one day and the App Store recorded an upload against
  one of them. A version that identifies more than one build cannot answer "which one is
  deployed", and the SHA-256 is not a substitute: nobody quotes a digest in a conversation. Six
  tests bind the version across both stamps, `docs/CHANGELOG.md`, the deploy checklist, the
  submission manifest and the artefact, so a missed site fails the loop rather than shipping.
  **This was not true of the changelog until V0.26.6**, and the correction belongs here rather
  than only in the entry: the binding asserted `## V{major}.{minor} ` and so was satisfied by any
  older heading in the same minor series. A patch release with no audit row shipped green, which
  is every release this project makes. Not a shortcut but a mistake about what varies - the patch
  is the component that identifies a build here, so major.minor was precisely the wrong half to
  assert. A binding test that binds less than it claims is worse than no test, because the claim
  is what stops anyone looking.
- The App Store slug is `enlightenment`: lowercase, alphanumeric, no hyphen at all, so it
  cannot trip the double-hyphen naming fault that fails a pipeline with zero stages run.

## House voice (applies to all prose, UI copy, comments, commits)

A guide, not a leash. Held everywhere: never fabricate data; avoid the long em-dash (a single dash is fine); no `+` meaning "and" in prose. The Bluestaq default, which is your call on your own project: UK English, the `£`/`$`/`%` symbols, expand an uncommon acronym on first use, lead with the decision then the reasoning. Anything publish-facing or Bluestaq-brand-facing follows the brand in full. Full voice: `.claude/output-styles/house-voice.md`.
