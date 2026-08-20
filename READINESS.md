# App Store readiness: Enlightenment

**Band: NOT YET.** Two blockers remain, both process rather than product. A third, a red
pipeline, was found by this check and is now cleared.

This is a pre-flight ESTIMATE, not the binding decision. The App Store's SonarQube quality
gate, its container policy scan, its continuous Authority to Operate score and its human review
are the real gate; the internal `deploy-gate` is the last internal word and has not run on this
lineage since V0.8.0.

Head at time of writing: `90da0fd`, V0.19.0, branch `claude/bluestaq-app-store-server-6scbm5`.

## Blockers (each caps the band at Not yet regardless of score)

**1. Continuous integration was RED for the last three completed runs, and nobody looked.**
Runs 11, 12 and 13 all concluded `failure`. The local loop was green throughout, so nothing
surfaced it here. Root cause: the Podman preference added in run 11's commit. Three tests prove
`build-image.sh` defers with exit 3 when no container engine is reachable, and they work by
putting a stub `docker` on PATH. Once the script preferred Podman - correctly, because that is
what the platform's containerize stage uses - the stub was bypassed on any runner that HAS
Podman. The GitHub runner has it; this authoring environment has neither engine.
● Fixed in `90da0fd`: both engine names stubbed, choice pinned with
  `ENLIGHTENMENT_CONTAINER_ENGINE`. Reproduced locally with a working fake `podman` on PATH
  before fixing, and confirmed both ways.
● **Run 14 concluded `success` at `90da0fd`. This blocker is CLEARED**, and the conclusion was
  read from the run rather than inferred from the fix looking right.
● Owner: `ci-cd`.

**2. Neither binding gate has run against the current head.** `engineering-reviewer` and
`security-reviewer` both last returned **FAIL**, on `98f0596`. Four commits have landed since.
Their findings are closed and the loop is green, so the work is believed complete and is
unverified at head. The earlier PASSes on older commits must not be read as covering this one.
● Owner: `working-with-ai`, and the gate agents themselves.

**3. `deploy-gate` has not run since V0.8.0**, eleven releases ago, where it returned FAIL on
three blockers. It is the binding internal word before an irreversible publish.
● Owner: `release-and-deploy`.

## Per-dimension score

| Dimension | Weight | Result | Evidence |
| --- | --- | --- | --- |
| Verification loop green | blocker | **PASS** | 544 passed, 1 skipped. Also green executed under `dash`, and green with a working Podman on PATH |
| Coverage at least 80% | heavy | **PASS** | 98.71% branch coverage; both physics modules 100% line and branch |
| No secret in source or history | blocker | **PASS** | Seven-pattern scan of tree and all refs. Five history matches were placeholder-shaped test fixtures; the two live ones are now composed from parts so the `NAME = "long-literal"` shape is gone |
| Server contract: PORT/8080, 0.0.0.0, `/` and health 200, non-root numeric, no `ENV PORT` | blocker | **PASS** | Six contract paths measured at 200 with redirects NOT followed; `USER 10001:10001`; `EXPOSE 8080`; no `ENV PORT` or `ENV DATA_DIR` |
| Container package flat at the root | blocker | **PASS** | Artefact carries exactly one `Dockerfile`, at the root. The Foundations baseline's six recipe templates do not ship |
| Runtime image hardened AND flattened | blocker | **PASS** | `FROM scratch` with exactly one `COPY`; suid/sgid sweep as the last mutation; no package manager; `ensurepip` purged. Verified by the CI image job, which is GREEN even in the failed runs |
| Coverage report at the path the gate reads | heavy | **PASS** | Cobertura at `coverage.xml` from `pytest --cov` run verbatim. Now machine-independent: `relative_files = true`, so `<sources>` is `src` not an absolute path from this machine |
| Reproducible install; no unaddressed High/Critical CVE | heavy | **PASS** | Three hash-locked files, `--require-hashes`, `pip-audit` clean over all three |
| Upload is a testable source tree; simulation green; emits coverage | blocker | **PASS** | Simulation adds the platform's own `.gitlab-ci.yml`, sets `GITLAB_CI=true`, masks absent tools: 541 passed |
| Per-commit static analysis at zero violations | heavy | **PASS** | Full ruff profile (22 rule families, not hand-picked); cyclomatic capped at 10 as a conservative proxy for Sonar's cognitive 15 |
| Test command tolerates the platform invocation | blocker | **PASS** | `pytest --cov` verbatim from a clean state writes `coverage.xml`; `addopts` owns the flags |
| Negative assertions classified per environment; no fail-open scanner | blocker | **PASS** | `ON_PLATFORM_RUNNER` covers five variables; `pip-audit` classification is structural (JSON parseability), not a log grep |
| CI mirrors the loop and its latest run is green | blocker | **PASS** | Run 14 at `90da0fd` concluded `success`. Red for runs 11 to 13; see blocker 1 for the cause and the fix |
| Version stamp, audit row, generic client errors, no secret in logs | medium | **PASS** | Version in health payload; one changelog row per release; `teamToken` reported as a boolean and a length bucket only |
| Accessibility, design tokens | medium | **n/a** | No user interface yet; Phase 1 step 9 |
| Surgical structure, no dead code | medium | **PASS** | Four gate rounds; every dead branch removed rather than defended |
| House voice | light | **PASS** | UK English, no em-dash, no `+` meaning "and" |

Applicable dimensions: 16. Passing: 16. Every mechanical and contract dimension measurable here
passes, and that is **irrelevant while a blocker stands**: the two remaining blockers are that
the binding reviewers have not seen this head.

## What the two unloaded skills found

`appstore-gate-compliance` and `deploy-recipes` were in the original skill set and had not been
used. Checking against both:

● Everything in their checklists already complied, **verified rather than assumed** for the
  first time: the flatten, the sweep ordering, the coverage path and format, the pinned digest,
  `exec` in the CMD, `--require-hashes`, the simulation's added CI file.
● Newly verified: every shipped script is syntax-clean under `dash` AND the loop executes under
  it, so the platform's minimal shell cannot produce `sh: bash: not found` at build time.
● One pitfall closed: `deploy-recipes` names a framework redirect on `GET /` as one of three
  failures that bite every stack. FastAPI ships `redirect_slashes=True`, so `/healthz/` answers
  307. Benign (the platform probes canonical paths) but the canonical paths' no-redirect property
  was unpinned. Now asserted with redirects not followed.
● The cost of not loading them earlier was real: the `pytest: command not found` upload failure
  and the machine-dependent coverage path were both discovered the expensive way.

## Structural risk that no release can close

`appstore-gate-compliance`: **ship often, so the new-code window stays small.** Nothing has ever
shipped. SonarQube scores NEW code against a zero-violations bar, so with no shipped baseline the
entire codebase is new code, judged at once. The skill's own mitigation for stacked work is to run
the local analyser over the WHOLE accumulated range rather than the latest diff, and this loop
already does that - `ruff` runs over the full tree every time, never a diff. That is the right
mitigation and it is in place. The residual is any Sonar rule class the local profile cannot
express, which is recorded rather than claimed closed.

**Implication for sequencing:** the smallest shippable increment is worth more than another
feature. Every release that stacks unshipped widens the blast radius of one missed rule.

## Deployment actions that are yours, not code

● **`securityContext.fsGroup`** must be set by an operations request, or the root-owned
  file-storage volume refuses every write from the non-root container and `/readyz` returns 503
  with `EACCES`. This is why the CI container's `/readyz` is 503 and correct.
● **The environment tab holds exactly two rows:** `ENLIGHTENMENT_TEAM_TOKEN` and
  `ALLOWED_ORIGIN`. Every other row `[delete]`. Never paste guidance prose as a value - a known
  platform failure. Generate the token yourself; it must never appear in a commit or a transcript.
● **Slug `enlightenment`**, single word, no hyphen. Confirm uniqueness before first upload.
● **Never delete-and-recreate under the same slug.** App-record residue fails a pipeline with
  ZERO stages run and recovers only with a fresh slug and a changed URL.

## Skills to download from Launchpad

None. Every skill this report names is already present in `.claude/skills/`. The gap was that
three of them had not been READ, not that they were missing:
`appstore-gate-compliance` and `deploy-recipes` (now used), and `release-and-deploy`
(needed for the ship runbook when you decide to deploy).

## What would raise the band

1. ~~Run 14 of CI green.~~ **Done**: `success` at `90da0fd`.
2. `engineering-reviewer` and `security-reviewer` PASS at head. → clears blocker 2.
3. `deploy-gate` PASS. → clears blocker 3, and moves the band to **Ready**.

Nothing on that list is a product defect. The application meets every mechanical and contract
dimension that can be measured here.
