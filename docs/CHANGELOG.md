# Changelog: Enlightenment

One audit row per change: what changed, why, and how it was verified.

## V0.14 (2026-08-20)

**What.** The physics core of the flight plan's Phase 0, and a defect in the verification loop
itself that was found while running it.

### The verification loop was running an unpinned toolchain

This one comes first because it changes the standing of earlier entries in this file.

`scripts/verify.sh` invoked `ruff`, `mypy`, `pytest` and `pip-audit` by bare name, so PATH
decided which versions ran. On this machine PATH held:

| tool | on PATH | pinned |
| --- | --- | --- |
| ruff | 0.15.8 | 0.16.3 |
| mypy | 1.19.1 | 2.3.1 |
| pytest | an isolated tool environment that cannot import the application's dependencies | 9.1.1 |
| pip-audit | absent | 2.10.1 |

It surfaced as a FALSE FAILURE: ruff 0.15.8 raised S310 on `healthcheck.py`, a finding the
pinned 0.16.3 does not raise. That is the lucky direction. The same gap produces a false PASS
just as readily, and every other claim in this repository rests on this loop's verdict. "The
loop is green" has to mean "green against the dependency set the container ships and the
platform installs", or it means nothing.

**Standing of the earlier rows.** Every "loop green" claim in V0.1 to V0.13 was made without a
control on which analyser ran. The code those rows describe is unchanged and re-verified at
this release under the pinned toolchain, so the conclusions hold; the METHOD behind them did
not have the guarantee the rows implied. Recorded rather than quietly corrected.

**Fixed.**

● Every leg now runs as `"$PY" -m <tool>`, where `$PY` is resolved once from
  `ENLIGHTENMENT_PYTHON`, then `.venv/bin/python`, then `$VIRTUAL_ENV/bin/python`, then
  `python3`. The interpreter is echoed at the top of every run.
● New leg one: `scripts/check-environment.py <interpreter> <lockfile>...` asserts that every
  `name==version` pin is installed at exactly that version, reporting every divergence rather
  than the first. First because a mismatch means every later leg measures the wrong thing.
● Six guards in `tests/test_appstore_contract.py`. Three assert the loop's shape: no bare tool
  name, every tool routed through `$PY`, the environment check ahead of the first analyser.
  Three EXECUTE the checker: a missing distribution fails, a wrong version fails, a matching
  pin passes. The last is the control, without which a script that always exited non-zero
  would satisfy both negative tests.
● The three shape guards were run against `git show HEAD:scripts/verify.sh` and all three
  fail on it: five bare invocations, no module routed through `$PY`, no environment check.
● The executed guards use a SYNTHETIC lock file, not the real `requirements.txt`. Pointing
  them at the real file would couple the platform's test stage to the platform's install
  fidelity, so a divergence would fail the suite instead of reporting a mismatch. A
  self-inflicted pipeline failure is the fault that broke the last upload.

`scripts/package-appstore.sh` also calls `python3`, and that stays: it uses the standard
library only (`shutil`, `zipfile`, `hashlib`), so no third-party version can drift under it.
`simulate-pipeline.sh` already used its own temporary environment's paths.

### A real defect in the angle wrappers, found by property testing on its first run

`normalise_degrees(-1.13e-78)` returned `360.0`, outside its documented `[0, 360)`. Floating
point is the cause: the exact answer is a hair under a full turn, an amount too small to
represent at that magnitude, so `%` rounds UP to the excluded end. `normalise_longitude` and
`wrap_to_pi` had the same defect one representable step below their low ends.

This is the module's own subject matter turned on itself. The operational form, measured not
argued: two samples of a near-antipodal GEO pair where the target moves 1.4e-14 degrees between
them. The naive arithmetic reports the separation as +180 then -180, so the drift between
consecutive frames reads as a full 360 degrees. That is the ASTRA 1M artefact class exactly, and
a trainer whose own maths manufactures it teaches the wrong lesson about competency axis five.

**Fixed** with one `_fold_into_turn(value, turn)` helper all three wrappers share, so the
guarantee lives in one place. **Verified** three ways: the three inputs are pinned as
`@example` cases as well as properties, because a property test only rediscovers a corner if
the search happens to reach it; a parametrised regression asserts each lands inside its
interval; and the naive expressions were run against all four new assertions, which reject
3 of 3 interval cases and the drift case.

One correction against myself: the first version of the drift test asserted in its docstring
that the naive path returned 180 degrees there. It returns 0.0. The docstring certified
something the measurement disproved, so the test was rewritten around numbers taken from the
measurement rather than from reasoning.

### SGP4 against Vallado's published output

`tests/test_physics_propagation.py` reads `SGP4-VER.TLE` and `tcppver.out` from inside the
pinned `sgp4` wheel, the AIAA 2006-6753 verification distribution. 32 element sets, 641
reference rows, 640 comparable. Worst deviation MEASURED, not chosen: 1.17e-7 km in position
(about 0.12 mm) and 8.53e-10 km/s in velocity. Tolerances sit two orders above that, loose
enough to survive a libm difference between platforms and tight enough to catch a regression.

Reading the reference rather than transcribing a handful of vectors is the point: the hard rule
against inventing a figure applies to test data first.

Two named traps get a witness from the published data rather than a synthetic one.

● **The unchecked error code.** Satellite 33334 in the official set returns SGP4 code 3,
  instantaneous eccentricity out of range. A wrapper that ignores the code returns floats that
  read as a position; this one raises. Vallado shipped the trap, which is stronger than an
  element set I would have built to fail.
● **TEME is not J2000.** The frame is carried in `StateVector` and asserted. The failure is
  silent and grows with epoch separation, so the only defence is that it is never implicit.

A guard test recounts all 641 rows independently and asserts 640 comparisons actually happened,
because a per-satellite loop that swallows exceptions is a green suite that compared nothing.

**Verified.** Loop green under the pinned toolchain: 420 passed, 1 skipped, coverage 98.61%
against a 80% floor, all three lock files audited clean. Both physics modules at 100% line and
branch coverage.

**Still open, and needing your decision before Phase 1** (unchanged from V0.13): SQLite on the
storage volume versus the current JSON snapshot store; the `IdentityProvider` adapter versus
the shared team token; and a signed Data Protection Impact Assessment (DPIA) before any
named-individual performance record is written.

## V0.13 (2026-08-19)

**What.** The real cause of the upload failure, read from the platform log rather than inferred,
plus the first increment of the ENLIGHTENMENT flight plan V1.0.

### The upload failure: `pytest: command not found`, exit 127

The platform's generated test stage runs exactly this:

```
pip install -r requirements.txt
pytest --cov --cov-report=xml:coverage.xml
```

It installs ONE file and knows nothing about a dev file, and the pipeline is GENERATED so it
cannot be edited to add a second install line. `requirements.txt` held runtime dependencies
only, so pytest was not there. Four of eight stages passed; Code Quality, Container Build and
Container Scan were all skipped.

**Two failures of mine, stated plainly.**

1. **The previous release fixed the wrong thing.** `unzip` in an executed script was a real
   latent defect and it is still worth having fixed, but it was NOT this failure. I diagnosed
   from the symptom instead of waiting for the log, having said in the same breath that the log
   should decide. Inference substituted for evidence and cost a cycle.
2. **The answer was in the document I had just read.** The flight plan states the contract at
   line 132: "two requirements files (`requirements.txt` carries all test tooling,
   `requirements-runtime.txt` stays lean)". I read it, noted it was the inverse of the layout in
   place, and deferred it as a separate concern. It was the fix.

**The three-file contract, now honoured:**

| File | Installed by | Contents |
|---|---|---|
| `requirements-runtime.txt` | the container image | lean runtime only |
| `requirements.txt` | the platform's test stage, and the local loop | runtime plus the test runner |
| `requirements-dev.txt` | local only | lint, types, vulnerability scan |

**And the reason the simulation missed it, which matters more than the fix.** The simulation
installed BOTH requirements files, so it was more generous than the platform: it went green while
the real stage failed. It now installs exactly what the platform installs and nothing more.
Proved by reverting the defect into a copy: the corrected simulation fails, and so does the local
loop. A simulation that helps the code along proves nothing about the platform.

Six new tests pin the contract in both directions: the test runner is present in the file the
platform installs, the image installs the LEAN file with hashes, no test tooling reaches the
image (asserted per tool), the simulation never installs the dev file, all three lock files are
audited, and all three are packaged into the artefact.

### Flight plan V1.0, Phase 0 step 2: the physics core

The flight plan is a materially different and much larger application than what is built: an
orbital warfare trainer with a physics core, a procedure library, a drill engine, a scoring
engine, a debrief engine, SQLite on the storage volume and a single-file SPA. What ships today is
a session recorder, roughly five per cent of that, and the `scenario` field is free text. So
there is no simulation-data generation to alter yet; this is new construction, and it follows the
plan's own ordering, which puts the physics first because everything scores against it.

● **`physics/angles.py`.** The plus-or-minus-180 seam isolated in one module, because the plan
  names angle wrapping as a regression trap and the LEARNED register records an ASTRA 1M case
  where a millisecond epoch gap produced a drift rate of about minus 22,900,000 degrees per day.
  `shortest_separation_degrees` is the only permitted way to difference two angles here.
● **`physics/propagation.py`.** SGP4 wrapped so nothing else touches the library. Two of the
  plan's named traps are closed by construction: the output frame is carried in the type, so TEME
  cannot be silently treated as J2000; and every non-zero SGP4 return code becomes an exception,
  because an unchecked code is a fabricated state vector and scoring an operator against one is
  worse than refusing to run.

`sgp4` is pinned with a recorded reason. `numpy` and `skyfield` are deliberately NOT added yet,
with reasons recorded in `requirements.in`: propagation and the determinism harness are scalar, and
skyfield's ephemeris dependency needs a deliberate vendoring decision under the air-gap posture.

**How verified.** Loop green, ruff and mypy strict clean over 15 modules, `pip-audit` clean over
all three lock files. Masked simulation green with the platform's exact install. The mypy override
for the untyped `sgp4` surface is narrowed to that one module, so no untyped value escapes the
wrapper.

**Not yet done, and deliberately not started:** the Vallado golden vectors (the data ships inside
the `sgp4` package as `SGP4-VER.TLE` and `tcppver.out`, so the tests will read the published
reference output rather than invented numbers), the determinism harness, and everything in Phase 1.

## V0.12 (2026-08-19)

**What.** The first real upload FAILED at the platform's Test stage: four of eight stages passed,
and Code Quality, Container Build and Container Scan were all skipped. The reported message was
"Tests failed", which points at the tests. The cause was not a test.

**`scripts/package-appstore.sh` shelled out to `unzip`, which a stock `python:3.12-slim` image
does not ship.** A contract test EXECUTES that script, so on the platform's runner it exited 127
and the test asserting a clean exit failed. Locally green, in CI green, and neither environment
reproduced the one thing that mattered: the platform's TOOL INVENTORY.

**This is a class I had already been told about and fixed one instance of.** A reviewer raised
exactly this in the previous round, naming `zip`. I removed `zip` and left `unzip`, `tar` and
`sha256sum` in the same file. Fixing the instance is not fixing the class, and this cost a real
upload cycle to learn.

**Three fixes, at three different rungs:**

1. **The script now uses nothing but a POSIX shell and `python3`.** `shutil.copytree` for the
   copy, `zipfile` for the archive and the listing, `hashlib` for the digest. The rule is stated
   at the top of the file so the next person does not reintroduce it.
2. **Two tests assert the RULE**, parametrised over the tools a stock python image lacks
   (`zip`, `unzip`, `git`, `curl`, `wget`, `jq`, `docker`), with a word-boundary match so
   `zipfile` does not read as `zip`. So the local loop now catches this class at the cheapest rung.
3. **The pipeline simulation MASKS those tools** during its test stage, replacing each with a
   stub that exits 127. The simulation previously reproduced the platform's added file and its
   environment variable, but not its tool inventory, which is why it passed while the upload
   failed.

Proved rather than assumed: reintroducing `unzip -l` into the packaging script makes the local
loop go red AND the masked simulation go red. Two independent nets, both verified against the
actual defect.

**Also widened: the platform-runner gate.** `ON_PLATFORM_RUNNER` tested `GITLAB_CI == "true"`
exactly, betting the deploy on one variable having one exact value. A negative assertion about a
file the PLATFORM ITSELF adds must never be guaranteed-false on the machine that gates the
deploy, so any credible runner signal now counts (`GITLAB_CI`, `CI`, `CI_PIPELINE_ID`,
`CI_JOB_ID`, `GITHUB_ACTIONS`).

**How verified.** Loop green, 334 tests collected (333 passed, 1 skipped locally; 332 passed and 2
skipped under the masked simulation), branch coverage 98.50%,
`pip-audit` clean over both lockfiles. Masked pipeline simulation green against the artefact on
the pinned interpreter. The masking leg proved load-bearing by reintroducing the defect.

**Caveat on the diagnosis.** The platform's own log for the failed run has not been read. `unzip`
in an executed script is a defect that produces exactly this symptom and it is fixed, but if the
new upload fails again, get "More Details" from the console: the specific assertion will name the
cause, and inference should not substitute for it twice.

## V0.11 (2026-08-19)

**What.** Both gates FAILED the V0.10 head with five MAJORs. Two were claims I had recorded as
closed and had not been, which is the third time that has been the failing finding.

● **The unparsable `If-Match` 500 was not closed.** `isascii() and isdecimal()` still lets `int()`
  raise: CPython caps integer string conversion at 4300 digits, so a 4301-digit validator returned
  500 on a real socket. A reviewer found it AFTER I recorded the class as closed. The guard is now
  three-layered: character class, a 19-digit length bound, and a guarded conversion. The third
  layer exists because a documented fail-safe should not depend on having enumerated every hostile
  input, which two rounds of this same bug proved I cannot.
● **The "binding patch-level check" checked no patch level.** Counting `Package:` lines proves the
  scanner can ENUMERATE what ships, not that anything is patched, while three places said
  otherwise. `apt-get upgrade` is deliberately fail-open, so the honest position is that patch
  assurance rests on the digest-pinned base plus the platform's own container scan, which is the
  only thing with a real CVE database. The claim is narrowed to what the check does; the check
  stays, because a well-meant cleanup of `/var/lib/dpkg` would silently blind the scanner.

● **Three CI assertions were satisfied by any mention of their marker**, so each check could be
  deleted with the suite green: the OS-package step replaced by an `echo` naming the marker, the
  bundled-wheel scan likewise, and `dpkg` in the tool list satisfied by the unrelated
  `/var/lib/dpkg/status` line. Instances sixteen to eighteen of the assert-the-prose class in one
  file. Each marker is now bound to the `docker run` step that must carry it, and the tool list is
  parsed rather than matched.
● **The artefact-building test shelled out to `zip`.** The platform runs this suite in ITS
  environment, and `zip` is not part of a stock Python image, so an absent binary would fail the
  test stage and skip quality, container build and deploy, with the diagnosis pointing at
  packaging. Packaging now builds the archive with `zipfile`, so the release path needs only the
  interpreter that is already running the suite.
● **V0.10 shipped with no audit row.** Written above, retrospectively, and a test now fails when
  the version being shipped has none.

Also: the edit helper preserved no file mode, so a scripted edit to any mode-755 script stripped
its executable bit; the security policy cited a test for the real-write control that does not kill
an existence-check mutant, because the case it covers never reaches the write; the narrowness of
the `app.state` seam was unasserted, so re-publishing the whole runtime and its plaintext token
left the suite green; and the deployment record carried a hand-copied test count that had already
been wrong twice, now removed rather than corrected again.

**How verified.** Loop green, ruff and mypy strict clean, 326 tests collected (325 passed, 1
skipped) with branch coverage at 98.50% against an 80% floor, `pip-audit` clean over both lockfiles, pipeline simulation green against the
artefact, CI green across all three jobs including the binding image leg.

## V0.10 (2026-08-19)

**What.** The container was built for the first time, and the build immediately found a defect no
local check could have.

`ensurepip` vendors a complete pip wheel, `pip-25.0.1-py3-none-any.whl`. It is not a binary, so
`command -v pip` reported nothing and the package-manager check passed, while a filesystem CVE
scanner reports pip as a shipped package. The claim "the runtime ships no package manager" was
therefore FALSE for three releases of documentation. A reviewer had hypothesised exactly this and
said plainly it could not be settled without a build; fixing the CI trigger in V0.9 is what let
the hypothesis be tested. `ensurepip` is purged in the prep stage and asserted locally and in CI.

**The lesson is not about pip.** A `PATH` check answers "what can the entrypoint run". A scanner
asks "what is in the image". Those are different questions, and the documentation asserted the
second while only ever testing the first.

**What the first build proved**, against the built filesystem rather than the Dockerfile text:
`Config.User = 10001:10001`; zero setuid or setgid paths, swept as root with stderr surfaced;
no package-manager binary on `PATH`; the dpkg database retained so the platform scanner can still
enumerate; and, after the fix, zero bundled wheels. The container also ran and answered every
platform probe on 8080.

**`/readyz` returned 503 in that run, and that is correct.** No file-storage add-on is mounted in
CI, so the non-root user cannot write the image's own default directory. The application starts,
serves every liveness path, publishes a complete diagnosis with `errno 13 EACCES` and the resolved
directory, and reports itself unready. Deliberately not softened: a writable in-image directory
would let a pod whose volume failed to mount run on ephemeral storage and lose every training
session at the next restart. A loud unready state beats silent data loss.

**How verified.** Loop green, 312 tests collected, branch coverage 98.72%, `pip-audit` clean over
both lockfiles, pipeline simulation green, and all three CI jobs green including the binding image
leg.

**This row was missing when V0.10 shipped**, and is written here retrospectively. A test now fails
if the version being shipped has no audit row, because the deploy gate reads this document and
V0.10 left it describing a three-commit-stale state.

## V0.9 (2026-08-18)

**What.** `deploy-gate` returned FAIL on V0.8.0 with three blockers. None was a defect in the
application: two were owner decisions I must not invent, and the third was a hole in my own
verification chain.

**The hole, and it is the important one.** The CI `image` job is the only thing that can build
this container, because the authoring environment's network policy denies the registry blob
endpoint. Three documents, including `docs/SECURITY.md`, name it as the binding check for
container hardening. The gate checked whether it had ever run instead of taking that on trust:
zero workflows registered on the repository, zero pull requests ever opened, `origin/main`
holding a single file, and a trigger set to `pull_request` into `main` and `push` to `main` only.
So on a release branch it had never fired once, and **the container had never been built by
anything, anywhere**, while three documents called its verification binding. A binding check that
cannot fire is not a check. The trigger now covers release branches and manual dispatch, and a
test fails if that regresses.

**Two checks only a built image can settle, added while the job was being fixed.** The
package-manager check tested binaries on `PATH`, so a vendored wheel under `ensurepip` would pass
it while a filesystem CVE scanner reports it. And nothing at all asserted the base patch level,
because the Dockerfile's `apt-get upgrade` is deliberately fail-open for runners behind a mirror.
Both now have a binding check reading the retained dpkg database, which is the reason keeping that
database was the right call rather than a tidiness loss.

**Owner decisions, recorded as decisions with their date.** Category Training / Simulation.
Visibility private to the Bluestaq Ltd team. Resource budget 1Gi request and 2Gi limit, 1 CPU
request and 2 CPU limit. The scenario vocabulary stays an open, length-capped field rather than
invented terms.

**A consequence of private-to-team worth stating loudly.** It requires the team token, and setting
the token makes `ALLOWED_ORIGIN` mandatory, so the environment tab is no longer empty for this
deployment. Two variables are set and every other row stays `[delete]`. The failure mode of
forgetting the token is a read-only service, never an open one, which is the whole point of the
fail-closed write posture.

**The withdrawal path for a first deployment, which was missing.** There is no previous version to
roll back to, and the record said so honestly but documented only the rollback that applies to
later releases. So an operator had nothing to follow if THIS deployment had to come out. Written
now: take the app out of service through the lifecycle action, do not delete the record as a first
move, and never delete-and-recreate under the same slug, because app-record residue is a known
platform failure that recovers only with a fresh slug and therefore a changed URL. Deleting is the
step that is hard to undo, not the deploy.

**How verified.** Loop green: ruff format and check, mypy strict over 12 modules, 311 tests
collected (310 passed, 1 skipped) with branch coverage at 98.72% against an 80% floor, Cobertura
written, `pip-audit` clean over both lockfiles. Three mutants this round, all three killed, with
the control run FIRST and confirmed green on a COMPLETE tree either side of them.

**Still not verified, and now actually reachable.** The container image build. Unchanged in this
environment, but the CI job that can do it is no longer unable to fire.

## V0.8 (2026-08-18)

**What.** Both gates PASSED at round 7 on V0.7. This closes the eleven MINORs they raised
alongside those passes, including one real bug in shipped code.

**The bug.** `If-Match: "\u00b2"` returned 500 from a path documented to IGNORE an unparsable
validator, because `isdigit()` accepts characters `int()` rejects. Reached by a reviewer on a raw
socket: uvicorn latin-1 decodes header bytes, so byte 0xB2 arrives as that character. Graded
MINOR because the route sits behind authentication, no state is written and both limiter tiers
bound it, but it is a 500 in shipped code and this project had already found and fixed the same
class in `healthcheck.resolve_port` two releases earlier. Found there, missed here. The guard is
now `isascii() and isdecimal()` in both places, and the parser is tested directly across eleven
hostile spellings plus the wire case, because a client library refuses to encode the bytes.

**Two claims corrected by measurement rather than reasoning.** The packaging test asserted that
commenting out the `rm -rf` purge would ship `.git`, `.venv`, `var/` and `dist/` in the App Store
zip. A reviewer built the artefact with the purge removed and found it clean: the real control is
the ALLOWLIST copy loop, and the purge is a defensive re-check behind it. So the test now BUILDS
the artefact and inspects the zip, and the claim says what the layers actually do. Removing either
layer alone still gives a clean artefact; removing both is what the test catches.

**Four demonstrated escapes in my own test instruments.** A trailing `#` comment on a live shell
line could delete the packaging purge with the suite green. A four-line `pytest.ini` outranks
`[tool.pytest.ini_options]`, so the coverage-flag assertion stayed green while a bare `pytest`
wrote no Cobertura, which is the exact 0%-coverage gate failure it exists to prevent. The
documentation sweep exempted elided citations, leaving 12 of 63 names unchecked. And the version
lived in two files with no parity test, which is the class the sweep was added to close.

**The edit helper reviewed as shipped code, and it needed it.** `Path.write_text` follows a
symlink, so a symlinked target wrote OUTSIDE the named directory: the same reasoning that puts
`O_NOFOLLOW` on every file this project's store opens. It also wrote before verifying, so its
`EXIT_UNVERIFIED` refusal left a half-edited file, which is the inverse of what the tool exists
to prevent. It now refuses a symlink, verifies BEFORE writing, writes atomically through a
temporary sibling, and reports an unreadable target with a documented code instead of a
traceback. Nine tests drive it.

**A process note worth recording.** The first run of this round's mutation battery reported eight
kills that were not real: my mutant copy omitted two root files, so the packaging test failed in
every run including the control, and eight mutants appeared "killed" by a test that was failing
for an unrelated reason. The control run is what caught it. Running the control FIRST, not last,
is the cheap habit that turns a mutation battery from theatre into evidence.

**How verified.** Loop green: ruff format and check, mypy strict over 12 modules, 307 tests
collected (306 passed, 1 skipped) with branch coverage at 98.72% against an 80% floor,
Cobertura written, `pip-audit` clean over both lockfiles. Pipeline simulation green. Ten mutants
this round on a COMPLETE copy with the control verified first: eight killed by the intended test,
one shown to be neutralised by a second layer rather than undetected, and that layered case then
proved detectable by removing both layers at once.

**Still not verified.** The container image build, for the same reason as every prior release: the
registry blob endpoint is denied by this environment's network policy. The CI `image` job binds.

## V0.7 (2026-08-18)

**What.** Round 6 returned two MAJORs, and the more important one is a class rather than a bug:
**four contract assertions read their target file raw, so a comment satisfied them.** Each was
measured surviving as a commented-out line, and each protects something that matters:

| Commented out | What the suite still said | What would have happened |
|---|---|---|
| `sonar.python.coverage.reportPaths` | green | SonarQube reads no report, scores 0%, quality gate fails on upload |
| `--cov-report=xml:coverage.xml` in `addopts` | green | a bare platform `pytest` writes no Cobertura, and `verify.sh` is satisfied by a stale file |
| `.env` in `.gitignore` | green | a developer's real `.env` becomes committable |
| the packaging purge | green | `.git`, `.venv`, `var/` and `dist/` ship inside the App Store zip |

That last one is the same defect this project's own ledger already recorded once, reproduced
verbatim on a different line of the same file, in a test file that already contained two
comment-stripping readers written to prevent exactly this. Every one of these now goes through a
real parser: `tomllib` for the manifest, a `.properties` parser, and an executable-lines reader.

**The second MAJOR.** The lifespan docstring still said the pool is "created on FIRST PROBE
rather than at construction", three lines above the code that builds it eagerly, in the very
function the previous round edited. The field comment 460 lines away was rewritten at length
while this one was missed.

**A guard so the documentation cannot rot silently.** `test_every_test_named_in_the_security_policy_exists`
sweeps every backticked test name in this document and fails if one does not resolve. It found a
dangling citation the moment it was written, from a rename two commits earlier. It states its own
blind spot: it cannot see a row whose named test exists but no longer asserts the control it is
cited for, which is what the mutation ledger is for.

**Three controls that needed a better instrument, not just a test.** The single-worker pool is now
asserted as SERIALISATION, by submitting two blocking callables and proving the second cannot
start until the first returns, rather than by reading a private CPython attribute. A probe after
lifespan shutdown now fails closed instead of silently falling back to the shared default
executor, which is the starvation the dedicated pool exists to prevent. And the inspection seam
was narrowed: publishing the whole runtime put the plaintext team token within reach of any
handler through `request.app.state`, so only the pool is published.

**The edit helper is now executed, not asserted.** Five tests drive `scripts/verified-edit.py`
through its outcomes, and the unreachable third refusal it advertised is deleted rather than
claimed, on the same reasoning that removed the inert drain guard.

**How verified.** Loop green: ruff format and check, mypy strict over 12 modules, 286 tests
collected (285 passed, 1 skipped) with branch coverage at 98.71% against an 80% floor,
Cobertura written, `pip-audit` clean over both lockfiles. Pipeline simulation green. Nine mutants
this round, eight killed first time; the ninth, a post-shutdown probe silently using the shared
executor, was closed and re-proved killed.

**Still not verified.** The container image build, for the same reason as every prior release: the
registry blob endpoint is denied by this environment's network policy. The CI `image` job binds.

## V0.6 (2026-08-18)

**What.** The security gate PASSED again on the current tree. The engineering gate FAILED on one
MAJOR, and it was the same fault line as the two rounds before it: my record certified a
mutation proof that a five-line experiment disproved.

**The disproved claim.** I said lazy probe-pool creation was closed and mutation-proved, and
gave a mechanism: "a ThreadPoolExecutor is held by a module-level registry, so building an app
and never probing it left an idle thread alive; 40 threads for 40 apps". Both reviewers measured
otherwise. A `ThreadPoolExecutor` starts NO worker until work is submitted, so 40 constructed
pools hold 0 threads, and my test counting threads passed whether the pool was built lazily or
eagerly. It asserted nothing.

Investigating properly turned up a second wrong half: a dereferenced executor's worker also
exits when the executor is collected, so creating a new pool per probe leaks nothing observable
either. Laziness was therefore unassertable in both directions. **The branch is removed, not
defended.** The pool is built eagerly, and the control that does matter, the lifespan release,
is the one that kills its mutant.

**A control the removal exposed.** Raising the pool from one worker to eight was a surviving
mutant, and single-worker serialisation is one of the two invariants `_probe_storage` names as
what keeps publication ordered. Thread counts cannot catch it, because single-flight means only
one probe runs at a time either way. It is now asserted through an explicit in-process
inspection seam (`app.state.runtime`), so the wiring is checked rather than the source grepped.

**Two more unasserted controls, both mine.** The drain bound that SHIPS was asserted by nothing,
because both drain tests injected the timeout: setting the constant to 86 400 seconds left every
test green while the deployed drain was effectively unbounded again. And the budget being TOTAL
rather than per-message was unasserted: moving the deadline inside the loop left the suite green,
and on a real socket that mutant left a client dripping one byte every 10 seconds unanswered
after 46 seconds against 15.0 for the shipped code.

**A test that hung instead of failing.** The per-message mutant made my own drain test wait
forever, because the test relied on the bound it was testing to terminate. A hanging test is not
a failing test: continuous integration reports a job timeout, which reads as infrastructure
trouble rather than as a defect. Every drain test now bounds itself as well as the code.

**Dead weight removed rather than kept.** The `remaining <= 0` guard in the drain was inert,
because `asyncio.wait_for` raises on a non-positive timeout itself, and the prose grep for the
image script's deferral is deleted now that four tests execute it.

**The process claim is now checkable.** The verified-edit helper is landed at
`scripts/verified-edit.py` instead of living only in an authoring session. It refuses a missing
anchor, an AMBIGUOUS anchor, and a replacement that is not present afterwards. A reader of this
record can run it.

**Honest residual recorded, not omitted.** The body drain is bounded, measured at 120 of 120
parked connections answered 408 with descriptors returning to baseline. A connection that stops
before the blank line ending the headers never reaches the ASGI application, so neither the
drain bound nor the rate limiter can see it: 200 such connections took a worker from 10 to 210
descriptors. That is not fixable inside an ASGI application without a custom protocol, so it is
recorded as an accepted residual with the platform ingress named as its bound.

**How verified.** Loop green: ruff format and check, mypy strict over 12 modules, 279 tests
collected (278 passed, 1 skipped) with branch coverage at 98.71% against an 80% floor,
Cobertura written, `pip-audit` clean over both lockfiles. Pipeline simulation green. Ten mutants
this round: seven killed first time, three survived and were closed by removing the unassertable
branch and asserting the two real controls, then re-proved killed.

**Still not verified.** The container image build, for the same reason as every prior release:
the registry blob endpoint is denied by this environment's network policy. The CI `image` job
binds, and its own assertions are mutation-proved.

## V0.5 (2026-08-18)

**What.** The security gate PASSED at round 4 with four MINORs. The engineering gate FAILED,
and not on the request path: on the RELEASE RECORD. The V0.4 audit row stated in the past tense
that the single-flight docstring's two false claims had been corrected. They had not. The edit
was a string replacement whose anchor did not match, so it silently did nothing, and I wrote the
entry as though it had landed.

That is worse than the prose it failed to fix, and worse than a code defect, because a record
that certifies work not done makes every other claim in it worth less. It happened in the same
commit that added a ledger about claims running ahead of evidence.

**The process fix, not just the text fix.** Every edit now goes through a helper that reads the
file back and fails loudly on a missed anchor or an absent replacement. The first thing it did
was refuse the docstring edit and print the anchor, which is how the correction finally landed.

Corrected for real this time: `_probe_storage`'s docstring counts two properties rather than
three, and states the invariants the code actually relies on (only the caller that started a
probe publishes it, and the pool has one worker) instead of claiming single-flight makes a
publication race impossible. Two independent reviewers reproduced two coexisting probe tasks, so
the impossibility claim was simply false. A test docstring repeating the same overstatement is
corrected too. A second false mechanism claim in the V0.4 entry is corrected in place: a probe
after lifespan shutdown does NOT raise, because the lifespan sets the pool to `None` and
`_run_probe` silently builds a new one.

**Four controls that were claimed closed and were asserted by nothing**, each found by an
independent run rather than by me:

● The image script's deferral behaviour was tested by grepping for the strings
  `THIS IS NOT A PASS` and `exit 3` anywhere in the file, so rewriting the no-daemon leg to
  `echo PASS; exit 0` stayed green. That is the leg that matters most, because it is the one
  that currently cannot run for real. It is now EXECUTED against a stub `docker`, four ways: no
  daemon defers with exit 3, an unreachable registry defers, a Dockerfile the builder reached
  and refused fails hard with exit 1, and a successful build reports a pass.
● The lazy probe-pool creation and the lifespan release. Both mutants survived; both are now
  asserted by counting probe threads by IDENTITY, since every pool names its worker `probe_0`
  and a set of names silently deduplicated across apps.

**Two latent defects closed on the way.** The body cap read `scope["method"]` un-normalised, so
a lowercase `post` skipped the cap entirely: not exploitable today, because Starlette's route
match is case sensitive, but this is the third time this cap has declined to run on a scope value
the layers behind it normalise differently and the first two shipped as exploitable. And the
drain had no time bound: 200 unauthenticated requests declaring a body and sending one byte took
a listener from 8 to 207 file descriptors with none ever answering. The drain is now bounded at
15 seconds and answers 408.

**How verified.** Loop green: ruff format and check, mypy strict over 12 modules, 275 tests
collected (274 passed, 1 skipped) with branch coverage at 98.37% against an 80% floor,
Cobertura written, `pip-audit` clean over both lockfiles. Pipeline simulation green. Six fresh
mutants, all six killed first time. Re-measured on a real uvicorn socket: the round-3 header
order, a lowercase method token and mixed-case header names all return 413 with peak resident
set flat at 46 MB, and 120 parked undrained connections were all answered by the drain bound,
with the listener's file descriptors falling from 110 back to 83 and liveness answering 200
throughout.

**Still not verified.** The container image build, for the same reason as every prior release:
the registry blob endpoint is denied by this environment's network policy. The CI `image` job
binds, and its own assertions are now themselves mutation-proved.

## V0.4 (2026-08-18)

**What.** Closed the third round. Both gates independently found the same bypass, and it was
one I introduced in the round-two fix.

● **The body cap was bypassable by header ORDER.** `_body_framed` returned from inside its
  header loop on whichever framing header appeared first, and treated `Content-Length: 0` as
  "no body". RFC 7230 section 3.3.3 makes `Transfer-Encoding` win, and h11 agrees, so
  `Content-Length: 0` sent BEFORE `Transfer-Encoding: chunked` read as no body while the
  server delivered the whole thing. Measured unauthenticated on a raw socket: 128 MB accepted,
  resident set 45 MB to 326 MB, answering 422 rather than 413. Swapping the two headers gave a
  correct 413, and that order dependence was the entire defect. So the round-two
  pre-authentication denial of service was live again, one commit after I declared it closed.
  Every header is now examined before deciding, and a declared length is ignored when a
  transfer-encoding is present, because the framing header wins and the length is then not the
  body's size. Re-measured on a real socket across four header orders: 413 every time,
  resident set flat at 46 MB.
● **My own fix had broken a control's only assertion.** Seeding the boot verdict into the probe
  cache meant the fail-closed test was served from the boot-time result, so the async handler
  never ran: inverting it to `ok=True` left all 244 tests green. The test now pins
  `cache_seconds=0.0` so the handler is actually reached. (An earlier version of this entry
  justified the fix by claiming that a probe after lifespan shutdown raises. It does not: the
  lifespan sets the pool to `None` and `_run_probe` silently builds a new one. The reason the
  fix matters is simply that a fail-open readiness handler answers `200 ready` on a pod whose
  storage was never proved, and nothing was asserting otherwise.)

Also fixed: a POST on a probe path could be parked indefinitely at zero cost, because the drain
awaits with no timeout and those paths are rate-limit exempt by design, so the cap now skips
them entirely; the snapshot was read following symlinks while the lock guarding it was opened
`O_NOFOLLOW`, so a principal with write access to the volume could have its own file served
through the API and copied into a backup; the probe pool is created on first probe rather than
at construction. (Retracted in V0.6: the stated mechanism was false. A `ThreadPoolExecutor`
starts no worker until work is submitted, so 40 constructed pools hold 0 threads, and a
dereferenced executor's worker exits on collection. The change to lazy creation was real; the
reason given for it was not, and the branch was later removed as unassertable.)

**Two claims that this entry originally recorded as corrected, and were not.** The
single-flight docstring said "two probes racing to publish is impossible" and announced three
properties while listing two. Both were left untouched: the edit was a string replacement whose
anchor did not match, so it silently did nothing, and this entry was written as though it had
landed. The fourth engineering review caught the release record asserting a source change the
diff did not contain, which is a worse defect than the prose it failed to fix. Corrected for
real in V0.5, and every edit is now applied through a helper that fails loudly on a missed
anchor.

**Three controls this release claimed were mutation-proved and were not**, each found by an
independent run rather than by me: the dedicated probe pool, the quoted bind address in the
launch command, and the dev-lockfile audit leg. All three now have tests that die under
mutation. The mutation ledger in `docs/SECURITY.md` now carries a per-round table of what was
claimed against what an independent run found, because three rounds have now shown my own
counts running ahead of the evidence.

**Two of my own tests were asserting prose, not behaviour.** The lockfile-audit test matched
the words in `verify.sh` including comments, so commenting the leg out stayed green. The
probe-path exemption test built its own middleware rather than the application's, so removing
the exemption from the real wiring stayed green. Both now exercise what executes.

**How verified.** Loop green: ruff format and check, mypy strict over 12 modules, 262 tests
collected (261 passed, 1 skipped) with branch coverage at 98.68% against an 80% floor,
Cobertura written, `pip-audit` clean over both lockfiles. Pipeline simulation green against the
artefact on the pinned interpreter with `GITLAB_CI=true`. Ten fresh mutants this round: eight
killed first time, two survived, were closed, then re-proved killed. The header-order bypass
was additionally re-measured on a real uvicorn socket rather than only in tests.

**Still not verified.** The container image build, for the same reason as every prior release:
the registry blob endpoint is denied by this environment's network policy. The CI `image` job
binds.

## V0.3 (2026-08-18)

**What.** Closed the second round of gate findings. Both gates independently found the same
two MAJORs, which is the strongest possible signal that they were real.

● **The probe cache bounded nothing under concurrency.** The cache was read, awaited, then
  written, so every request arriving while a probe ran started its own. Measured at 500
  concurrent requests producing 500 real probes, and 17 400 concurrent requests producing
  228. Worse than wasted work: on a slow volume the queued probes exceeded their own 2s
  timeout, so a majority of responses were 503 against storage that was fine, and those
  paths are unauthenticated and rate-limit exempt by design, so any caller could take a
  healthy pod out of rotation. Probes are now single-flight: a caller arriving while one runs
  awaits that one. The probe also moved to its own single-thread executor, because sharing the
  default pool with the store took a legitimate listing from 1.4ms to 109ms at the median.
● **The body cap sat outside the coarse rate limiter, not inside it as documented.** Twelve
  oversize requests left the limiter's key table empty, so an unauthenticated caller could
  send unlimited 64KB-body requests without ever spending budget. Registration order is
  corrected and now asserted. The same middleware had also made every path drainable: `GET
  /livez` with a declared length and no bytes went from answering in 0.01s to parking with no
  response at all. It now reads a body only for POST, PUT and PATCH, and only when one is
  framed.
● **Two controls the code and the security policy both claimed were mutation-proved were
  asserted by nothing.** Deleting the `asyncio.to_thread` offload left all 216 tests green,
  while the reviewer measured the event-loop stall going from 4ms to 792ms; with one worker a
  stalled loop stalls the platform's own liveness probe. Replacing `hmac.compare_digest` with
  `==` also left the suite green. The first is now proved directly by asserting no running
  event loop is visible inside a store call; the second by a source assertion that the
  primitive is present and no token is compared with plain equality.

Also fixed: the PATCH existence check ran outside the store lock, so a concurrent write that
tripped the session cap between check and write turned an intended merge into an append of a
partial record; `str.isdigit()` accepted characters `int()` rejects, so a hostile PORT raised
an uncaught ValueError out of a function documented to return None, and non-ASCII decimals
would silently resolve to a different port than they look like; pre-write backups were written
0644 while the snapshot is 0600; the lock path is opened `O_NOFOLLOW`, so it cannot be planted
as a symlink to de-serialise every writer; `verify.sh` now audits the dev lockfile too, since
the platform installs and executes it on its own test stage; the limiter's dead window-reset
branch is gone; the interpolated `PORT` in the launch command is quoted; the deprecated
`on_event` shutdown hook is a lifespan handler.

**Corrections to my own record**, which matter more than the code fixes. An independent
32-mutant run found four surviving mutants where I had recorded one. `docs/SECURITY.md` cited a
test name that does not exist. The data-loss figure was out by a factor of two: reproduced
three times at 81, 83 and 84 records surviving of 160, not 40 of 80. The README claimed either
access variable alone refuses to start, when only a token without an origin does. The stated
middleware order was inverted. The deployment table still sized memory for two workers. All
corrected, and the mutation ledger in `docs/SECURITY.md` now lists every survivor with the
reason each is or is not load-bearing.

**Removed rather than left untestable.** The probe's publication-ordering guard is gone. Once
probes are single-flight only the caller that started one publishes it, so two verdicts cannot
race, and the guard became unreachable. A mutation proved no test could kill it. Unreachable
code inside a security control invites a wrong mental model, which is the same reason the
limiter's dead branch came out.

**How verified.** Loop green: ruff format and check, mypy strict over 12 modules, 245 tests
collected (244 passed, 1 skipped) with branch coverage at 98.04% against an 80% floor,
Cobertura written, `pip-audit` clean over BOTH lockfiles. Pipeline simulation green against the
artefact on the pinned interpreter with `GITLAB_CI=true`. Eleven fresh mutants run this round:
eight killed first time, three survived and were closed, then re-proved killed.

**Still not verified.** The container image build, for the same reason as V0.1 and V0.2: the
registry blob endpoint is denied by this environment's network policy. The CI `image` job binds.

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
