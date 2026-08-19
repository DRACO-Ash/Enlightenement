# Changelog: Enlightenment

One audit row per change: what changed, why, and how it was verified.

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
