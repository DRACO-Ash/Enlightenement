# Changelog: Enlightenment

One audit row per change: what changed, why, and how it was verified.

## V0.17 (2026-08-20)

**What.** Both gates returned FAIL on V0.16. Two MAJORs in the credential redaction that V0.16
introduced, and five in the record: docstrings and changelog lines making claims the repository
itself disproves.

**The diagnosis, in the engineering gate's own words, because it is right and it is about my
method rather than my prose:** *every one of these is a claim that could have been checked by
running something that already exists in this repository. The habit to build is not more careful
prose, it is running the assertion before writing the sentence about it.*

Three rounds running, the code has held up under attack and the record has not. So every figure
in this entry was measured immediately before it was written, and where a claim is a list rather
than a number it is now pinned in a test, because a list in a docstring cannot be checked by the
loop.

### MAJOR: the redaction missed the commonest credential form

V0.16 added `redact()` for URL userinfo. Its pattern required a colon, matching only
`user:password@`. So `https://ghp_...@github.com/org/repo.git` - a bare token with no password,
and the ordinary shape of a pip direct reference against a private repository - was never
matched at all. **The most likely real credential to reach that path was the one form the
control could not see.** Also bypassed: `https://:token@host`, percent-encoded userinfo (which
pip's own documentation recommends), and the tail of any password containing a raw `@`, since
userinfo runs to the LAST `@` before the authority.

Fixed by dropping the colon requirement: `(?P<scheme>...://)[^/\s]+@`. Greedy, and `[^/\s]+`
cannot cross a `/`, so an ordinary index URL and a URL with an `@` in its path are untouched -
asserted, because over-redaction is not harmless: the unreadable-line report exists to tell an
operator which line to fix.

### MAJOR: the redaction was installed at one echo site of two

`redact()` guarded the unreadable-line report only. A line the pin pattern DOES match, whose
version group is a URL, went out through the missing-and-wrong report in clear:
`pkg==https://alice:token@host/x.whl` printed `pkg: pinned https://alice:token@host/x.whl, NOT
INSTALLED`. That is a one-character typo (`==` for `@`) of exactly the form the redaction was
written for. The comment beside the pattern asserted this was "the one remaining path"; a
two-line lock file refuted it.

Fixed by redacting where the line is COMPOSED rather than where it is printed. Both remaining
reports were audited: they carry only an interpreter path, a lock file name, or constant text.

**Verified**, and this is the shape the earlier rounds were missing: five credential forms are
parametrised named cases, three no-credential URLs are the control against over-redaction, and
both fixes are mutation-proved. Restoring the colon-requiring pattern turns four cases red;
removing `redact()` from the composed line turns the fifth red.

### MAJOR, five times over: the record contradicted the repository

Each of these was checkable by running something already present.

● **The V0.15 antisymmetry claim, wrong twice in opposite directions.** The first draft named
  range, whole-turn and antisymmetry as the old implementation's failures. The correction said
  antisymmetry was NOT among them and that three tests catch it. Measured by reverting the
  implementation and running the suite: **five** tests go red, and antisymmetry IS one of them -
  at `math.nextafter(-180.0, 0.0)`, forward gives `-179.99999999999997` and backward `-180.0`.
  Range is genuinely not violated. The entry now lists the five test names.
● **The checksum-failure breakdown.** "Both lines of satellite 33333 and line 1 of 33334 and
  33335" enumerates four while claiming five, and mis-assigns 33335. Measured: both lines of
  33333 AND 33335, and line 1 of 33334. The total was right and the breakdown invented, in the
  docstring justifying the most important opt-out in the module. **Now pinned as
  `CHECKSUM_FAILURES` and asserted**, so it cannot be prose again.
● **The opt-out count said one in the source, three in the test, three in the changelog.** The
  function was telling a maintainer the wrong thing about itself.
● **Three live docstrings asserted the design V0.16 replaced**, in the file V0.16 edited: that
  the checksum "is not a gate in `load_elements`" and "belongs in the scenario engine's
  solvability check". One was inside a live assertion message. A stale docstring beside a
  passing test is worse than none, because the test passing is what makes the reader trust it.
● **The checksum residual quoted a rate and a characterisation that contradict each other:**
  "roughly one line in ten" beside "517 of 50,000", which is one in 97. I copied both from a
  gate report instead of running it. Measured over 200,000 samples of each shape: **1.05 per
  cent** for fully random printable-ASCII lines (about one in 94, because column 69 must happen
  to be a digit before it can be the right digit) and **9.79 per cent** for lines whose column
  69 is already a digit - the shape a mistyped field produces, and so the realistic authoring
  error. Both rates are now pinned by a seeded test with deliberately loose bounds, asserting
  the order-of-magnitude gap rather than a figure that would flake.

### A surplus opt-out, removed rather than documented

One of the three `verify_checksum=False` sites had no written reason. Removing it, its test still
passed - which is what proved it surplus, and what the count test should have caught: its own
failure message demands a written reason for each one. It also meant that test was not exercising
the default path a real caller takes. Now two opt-outs, both with reasons, and the census
**walks every Python file in the repository** rather than only its own, which is what a guard
against something spreading has to do.

### Smaller corrections

● `if verify_checksum:` was a truthiness test on a parameter documented as strict fail-closed:
  `None`, `0`, `""` and empty containers all disabled it. Now `is not False`. Keyword-only, so
  it cannot be switched off positionally.
● The broad `except` in `_marker_applies` fails closed but said nothing, leaving an operator
  looking at "NOT INSTALLED" with no way to tell a real mismatch from an unevaluable marker. It
  now names the marker, through `redact()`.
● `TemporaryDirectory` instead of `mkdtemp`: the timeout test created a directory and wrote an
  executable stub into it outside the `try`, so a write failure would have left both behind.
● An unused `import runpy` inside an inline `-c` script, where ruff cannot see it.
● Stale timing figures. Measured: this file is 3.4s at 2,000 examples against 1.1s at the
  default 100, so the budget costs about 2.3s, on a full suite of 15.4s without coverage and
  22.2s under the loop. The earlier note said "a fraction of a second on a suite that runs in
  thirteen", which was neither figure.

### What the gates confirmed, recorded because they were my claims

● The seam fix holds: one gate ran 40 clean-Hypothesis-database sweeps, the other 15 plus 6 of
  the full suite, all green - and one proved the sweep is SENSITIVE by restoring the
  `pytest.approx`-gated branch while keeping the new `@example`, which failed 10 of 10 on the
  first run. That is the part that matters: the sweep detects the defect it exists to detect.
● Nine and eleven mutants respectively, across both changed source files, all killed.
● `verify_checksum` cannot be disabled positionally: `load_elements(a, b, False)` is a
  `TypeError`.
● 200,000 fuzz lines through `load_elements`: every rejection is `PropagationError`, no escapes.
  The `# pragma: no cover` branch justified on 60,000 lines in V0.16 held at 200,000.
● The temp stub leaves nothing: directory diffed before and after, `find /` for the stub name
  returns nothing.

**Verified.** Loop green under the pinned toolchain: **508 passed, 1 skipped**, coverage 98.71%
against a 80% floor, all three lock files audited clean, both physics modules at 100% line and
branch. Pipeline simulation green: **507 passed, 2 skipped**. Repo-wide opt-out census: exactly
two call sites. Clean-Hypothesis-database sweep of the full suite: 0 failures in 12 runs, which
is a sample and is quoted as one.

## V0.16 (2026-08-20)

**What.** Both gates returned FAIL on V0.15. The security gate found a BLOCKER: the verification
loop was RED at the commit I had pushed and reported green. The engineering gate found three
MAJORs, two of them false statements in the V0.15 changelog itself.

### BLOCKER: I reported the loop green from a run that was luck

`test_reversing_a_separation_negates_it` fails deterministically from a clean Hypothesis
database in about one run in five. My runs passed; the reviewer's did not. Measured: 1 failure
in 5 clean-database runs, then reproduced 4 in 12 before the fix.

**The test was the defect, not the implementation.** Its seam branch read
`if forward == pytest.approx(-180.0)`, and `pytest.approx` defaults to a RELATIVE tolerance of
1e-6, so it claimed the exact-seam special case for a band about 1.8e-4 degrees wide and then
demanded the reverse separation also be -180. At `second = -179.99999999999997` the two
separations are exactly antisymmetric, and the general rule applies. A tolerance on a BRANCH
CONDITION is not a tolerance on a comparison: it widened an exact special case into a band where
it does not hold. Gated on exact equality; `angles.py` needed no change.

**Why it surfaced now, and the lesson that outlives it.** V0.15 widened `LONGITUDES` to the last
representable value below 180, which is what made the near-seam band reachable. The widened
domain immediately found a defect in the test that guarded it.

The lesson is about my own claim, not the test. **A property test's verdict is only as strong as
its search, and "green once" is weak evidence for a boundary this narrow.** I asserted a green
loop from a single run and pushed it. The seam properties now run 2,000 examples instead of the
default 100, the falsifying value is pinned as an explicit `@example` so the regression is
deterministic rather than one-run-in-five, and the fix was confirmed over 12 clean-database
runs. Twelve is still a sample; it is quoted as one.

### MAJOR: two false statements in the V0.15 changelog

Both are corrected in place in the V0.15 entry above, with the correction visible rather than
edited away.

● It claimed V0.14's record said the output finiteness guard was "removed as dead code,
  measured over sixteen extreme values". **V0.14's record claimed no such thing** - the guard
  did not exist in V0.14 and its removal was never recorded anywhere. I fabricated an entry in
  this project's own audit trail, in the release whose entire subject is audit-trail integrity.
  The measurement was real and happened in development; the attribution was invented.
● It claimed the pipeline simulation's extra skip is "the leg that needs the dev toolchain".
  **Nothing in the suite skips on that.** The real cause is `scripts/simulate-pipeline.sh`
  setting `GITLAB_CI=true`, which makes `ON_PLATFORM_RUNNER` true and skips the
  `.gitlab-ci.yml` assertion. Measured with `GITLAB_CI=true pytest -rs`, which names both skips.

The figures in both cases were right and the explanations were invented. That is a specific
habit worth naming: reaching for a plausible cause rather than the one the tool would have told
me, in a record whose only value is that its explanations can be trusted.

### MAJOR: a validator that raised on the input it exists to reject

`element_line_checksum_ok("")` raised `IndexError` and a non-string raised `TypeError`. **Both
binding gates found it independently** - the same defect class fixed in `load_elements` in the
very commit that introduced this, in the function beside it. A predicate that raises is not a
predicate. Guarded at entry, returning False for anything that is not a 69-column string, with
eight rejection cases and a positive control pinned.

### MAJOR: a control described in the present tense with no call site

`element_line_checksum_ok` had zero callers while its docstring said the scenario engine calls
it in the solvability check. The measured hazard was live: for a well-shaped but meaningless
element set the public wrapper returns a finite, plausible fabricated state in a majority of
cold processes, and nothing rejected it.

**Wired.** `load_elements(..., verify_checksum=True)` by default. Exactly three call sites opt
out: `_reference_propagator`, because five of the sixty-six lines in Vallado's verification file
fail the checksum and a default that refused the reference data would be a control refusing its
own authority, plus two tests that deliberately exercise the layer beneath the gate. The count of
opt-out call sites is asserted **by parsing the file, not searching its text**: the first version
counted the string and found six, because docstrings discussing the opt-out matched too. A guard
that counts mentions instead of calls measures prose.

### Controls that survived inversion, now pinned

Four mutations left the previous suite green. Each is now killed:

● `_marker_applies` inverted to fail open. Skipping an unevaluable marker is the same silent
  fail-open the extras defect demonstrated.
● `timeout=PROBE_TIMEOUT_SECONDS` deleted. Exercised against a stub interpreter that sleeps.
● The extras group deleted from the pin pattern. The old test asserted only that "uvicorn" and
  "9.9.9" appeared in stderr, which the unreadable-line report satisfies by echoing the raw
  line, so it asserted less than its docstring claimed.
● The input finiteness guard deleted. `match="finite"` was satisfied by the output guard's
  "non-finite state" too: two controls, one assertion, the weaker propping up the stronger.

### Smaller corrections

● **`InvalidMarker` was not the only failure mode.** `python_full_version ~= "banana"` raises
  `UndefinedComparison` and a 100,000-digit version literal raises `ValueError` from CPython's
  4300-digit conversion limit. Both escaped as uncaught tracebacks, fail-closed only by the
  coincidence that Python exits 1 and `EXIT_MISMATCH` is 1. Now caught broadly, with the reason
  written: `packaging` evaluates a mini-language over file content, so its failure surface is
  not enumerable from outside.
● **The fix for the fail-open branch introduced a disclosure path.** Echoing unreadable
  requirement lines is what stopped them being skipped, and a PEP 440 direct reference can
  legitimately carry a token (`pkg @ https://user:token@host/pkg.whl`). URL userinfo is now
  rendered as `[REDACTED:credential]` before anything reaches stderr and thence a CI log.
● **`SGP4_ERRORS[6]` said "mean radius".** The library's `mrt` is the instantaneous geocentric
  radius in Earth radii, not a mean. Corrected, since the entry above it promises the phrasing
  is expanded for readability but never for meaning.
● **A dead condition** in `_is_requirement_line`: a separate `--hash` check could never return
  False, because the preceding test already excludes every line starting with a dash.
● **The width check is stricter than the library**, and the docstring now says so: the 33 line-2
  records in `SGP4-VER.TLE` are 103 or 104 columns as they appear in the file, so a caller
  reading raw records must truncate to 69 first.

### What the gates confirmed independently

Recorded because these were my claims and they are load-bearing:

● **The `sgp4` non-determinism is real.** Both gates reproduced it. One measured four of six
  cold processes returning a finite plausible state and two refusing, then consistently all-NaN
  once warm, with `epochyr=0`, `epochdays=0.0`, `bstar=0.0` after the parse: the line-1 fields
  are never assigned and the accelerated propagator runs on uninitialised memory. As an
  information-disclosure primitive it is very weak - the bytes are consumed as orbital elements
  and pushed through trig and Kepler iteration - and unreachable, since nothing outside the
  physics package imports it. The determinism breach and the fabricated plausible state are the
  live risks, and both now have a wired control.
● **5 of 66 reference lines fail the checksum**, verified against an independent implementation
  and a published ISS element set.
● **The `# pragma: no cover` on the library-refusal branch** was justified on six samples; a
  gate fuzzed 60,000 well-shaped printable-ASCII lines and `twoline2rv` raised for none. The
  justification stands on better evidence than I gave it.

**Verified.** Loop green under the pinned toolchain: **498 passed, 1 skipped**, coverage 98.71%
against a 80% floor, all three lock files audited clean, both physics modules at 100% line and
branch coverage. Pipeline simulation green: **497 passed, 2 skipped**. Four mutation tests
confirm the newly pinned controls fail when inverted.

## V0.15 (2026-08-20)

**What.** Closing the engineering gate's FAIL on V0.14 and the security gate's five MINORs.
Five MAJORs, and three of them were claims V0.14 certified as true that were not.

**The pattern across all three, because it is the same mistake.** In each case I measured one
axis, found nothing, and wrote the conclusion down as if I had measured the space. Property
testing found the angle defect and I fixed the end it reported. The reference file has two
identifying columns and I keyed on one. A measurement over `minutes` on a good element set
found no non-finite result, so I called the guard dead code. The fix is not "measure more"; it
is to state which axis was measured, in the record, so the gap is visible to the next reader.

### MAJOR: the angle fix closed one end of the interval and opened the other

V0.14 certified the plus-or-minus-180 seam as closed. It was closed at the low end only.

`normalise_longitude` added half a turn, folded, and subtracted it back. The ADDITION loses the
precision before the shared helper ever sees it: `179.99999999999997 + 180.0` rounds to
`360.0`, the fold correctly maps that to `0.0`, and subtracting half a turn returns `-180.0`
for an input that was already in range. Two frames one representable step apart then reported a
drift of **-359.99999999999994** degrees for 2.8e-14 degrees of real motion. `wrap_to_pi` had
the twin at plus pi, and `shortest_separation_degrees` inherited both.

So the fix for the artefact reintroduced the artefact, at the other end, and the changelog said
otherwise. Worse, the suite could not see it: the `LONGITUDES` strategy capped at `179.999`, so
the entire failing band sat outside the domain of the idempotence, separation and antisymmetry
properties. A property test is only as good as its domain, and a domain that stops short of the
boundary agrees with you about the interior.

**Fixed** by folding into `[0, 360)` FIRST and subtracting a whole turn from the upper half, so
no lossy arithmetic touches the input. Verified over 600,000 random samples plus 4,000
exhaustive representable steps either side of both ends: zero range violations, whole-turn
property holds, antisymmetry holds over the widened range.

Precisely what the old implementation fails, **measured by reverting it and running the suite**
rather than reasoned about. Five tests go red:

```
test_a_value_already_inside_the_interval_is_returned_unchanged[longitude]
test_a_value_already_inside_the_interval_is_returned_unchanged[radians]
test_two_frames_one_step_apart_near_the_high_end_report_no_drift
test_a_drift_is_the_separation_of_two_samples_never_the_difference_of_two_separations
test_reversing_a_separation_negates_it
```

It does not violate the range property, and over 2,000 representable steps either side of both
ends it returns a different value on exactly 500. It DOES violate antisymmetry, at
`math.nextafter(-180.0, 0.0)`: forward gives `-179.99999999999997` and backward `-180.0`.

Two earlier drafts of this paragraph got it wrong in opposite directions - the first named
range, whole-turn and antisymmetry as the failures, the second said antisymmetry was NOT among
them and counted three tests. Both were written from reasoning. The correct answer took one
`git stash`, one revert and three seconds of pytest.

**Also fixed:** `LONGITUDES` now runs to the last representable value below 180, and the high
ends are pinned as explicit examples. And a new test asserts the value is returned UNCHANGED,
not merely in range - the half-fix satisfied "in range" and that is how it passed.

**One thing that is not a defect, now stated as a rule.** Any half-open interval has a
discontinuity at its seam, so subtracting two normalised values across it gives about a whole
turn no matter how correct the normalisation. Chasing that is what produced the half-fix. A
drift must be computed as `shortest_separation_degrees(first_sample, second_sample)` on the raw
values, never as the difference of two separations measured against a third point. Both the
right and the wrong calculation are now asserted, because a rule without its counter-example is
a rule nobody follows.

### MAJOR: 26 published reference rows were never compared

Satellite 20413 appears TWICE in `SGP4-VER.TLE`: identical elements, two time spans of 26 and
70 rows. Both parsers keyed by satellite number, so the second occurrence overwrote the first
and 26 rows of an e=0.786 deep-space case were silently dropped. `EXPECTED_ELEMENT_SETS = 32`
and `EXPECTED_REFERENCE_ROWS = 641` then enshrined the loss, under a docstring reading "the
counts the pinned wheel actually ships" and a test named for catching a shrinking set. The
guard was measuring the shrunk total.

**Fixed** with occurrence-ordered lists instead of dicts. A dict keyed by a value the source
does not guarantee unique is a silent drop by construction. Now 33 blocks, 667 rows, 666
comparisons. **Verified**: a new test counts the file's data lines independently of the parser,
so a constant can no longer be updated to match a bug; another asserts the repeated number is
still present twice; another asserts the two files stay in the same order, since the golden
comparison pairs them by position. Worst deviations over all 666 rows are unchanged, so both
tolerances still hold.

### MAJOR: an invented cause in a diagnostic

`SGP4_ERRORS[5]` read "epoch element set was a sub-orbital trajectory". The pinned library says
"(error 5 no longer in use; it meant the satellite was underground)". I wrote a plausible cause
instead of reading the one that shipped, under a comment claiming the table came from the
library's own documentation. That is the hard rule against inventing a fact, broken inside a
diagnostic, in a trainer whose purpose is teaching diagnosis. Entry 3 also used my word
("instantaneous") where the library says "perturbed".

The existing test asserted only that each cause was non-empty and echoed in the message, so it
certified the invented text against itself.

**Fixed:** all six entries are now faithful renderings, expanded for readability (`nm` to "mean
motion") but never for meaning. A parity test asserts the key sets match the library's, so a
dependency bump that adds or retires a code fails the suite instead of leaving the table quietly
wrong. A second test pins code 5 specifically, since "no longer in use" reads oddly enough that
a future reader might tidy it into something that sounds like an orbital fault.

### MAJOR: a fail-open branch in the control everything else now rests on

`check-environment.py` required `==` immediately after the distribution name, so
`uvicorn[standard]==9.9.9` did not match, was skipped in silence, and the run printed "1 pins
checked, all match" with an unmet pin sitting in the file. The extras form is the ordinary way
to pin uvicorn. A control that silently ignores what it cannot parse is fail-open, and this is
the leg the rest of the loop's meaning depends on.

**Fixed:** the pattern accepts extras and markers; every requirement line the pattern rejects
is reported by file and line rather than dropped; a pin whose environment marker does not apply
is skipped deliberately, so a Windows-only pin is not a false failure on Linux; and versions
compare by PEP 440, so `9.1.1.0` and `9.1.1` are one release rather than a mismatch that
teaches people to skip the leg.

**Declined, with the reason recorded:** the check stays one-directional. Asserting that nothing
is installed BEYOND the lock files would fail on every runner, because `pip`, `setuptools` and
`wheel` come from the interpreter's own environment and are not all pinned here. A leg that
fails on a correct environment costs more than the latent hole it closes.

### MAJOR: the submission manifest named the wrong version

The V0.14 diff set both code files to 0.14.0 and, in the same diff, left
`docs/DEPLOYMENT.md` reading "0.13.0, matching `pyproject.toml` and
`src/enlightenment/__init__.py`". False as written, in the row a human copies into the App Store
console. The checklist still certified 307 tests and 98.72% coverage, and a simulation of
0.13.0.

Two code files were guarded by a test and the document a human actually reads was not, which is
the wrong way round: a mismatch between two code files fails a test, a mismatch between the code
and the manifest ships. **Fixed**, and two new guards now assert the manifest's Version row and
the checklist's simulation command both name the version in `pyproject.toml`.

### The security gate's five MINORs, and one finding underneath them

None were reachable from the HTTP edge; the physics core is imported nowhere outside itself and
its tests.

● **A non-finite time produced a fabricated state vector.** `sgp4_tsince(float("inf"))` returns
  code **0** with an all-NaN state, so the exact thing the wrapper exists to prevent arrived
  THROUGH the code check rather than around it. Input now guarded.
● **Three third-party exception types escaped the module's stated contract:** `ValueError` for
  an embedded NUL, `UnicodeEncodeError` for a lone surrogate, `TypeError` for a non-string. A
  caller cannot fail closed on an exception it was never told about. Element-set lines are now
  validated for width and charset at the boundary, and everything arrives as
  `PropagationError`. Nine hostile inputs are pinned, with a control test proving the library
  does not refuse them all by itself.
● **Leg one omitted `requirements-runtime.txt`,** the only lock file that ships. Now checked,
  plus an invariant asserting the lean file is a version-identical subset of the tested one,
  since the loop only catches divergence when both files' pins happen to be installed together.
● **A bare suppression and an unbounded subprocess** in `check-environment.py`: justification
  written, `timeout=60` added, and a timeout reported as a mismatch rather than raised, because
  a failure to check is never a pass.

**And the finding that came out of investigating them, which is the most serious thing in this
release.** The pinned `sgp4` extension is **not dependably deterministic** for a well-shaped but
meaningless element set. Three identical consecutive calls in one process returned an all-NaN
state, then a finite and entirely plausible one, then all-NaN again: `twoline2rv` leaves the
object partially initialised and the propagated values come from whatever was in memory. This
trainer's determinism requirement is that the same seed yields an identical event log twice, so
such an element set cannot be allowed near a scenario.

Two layers, neither claimed sufficient alone. The output finiteness guard catches the NaN
outcome. The plausible outcome is invisible at that layer - a finite wrong number looks like a
finite right one - so `element_line_checksum_ok` implements the published TLE checksum for the
scenario engine's authoring-time solvability check. Every meaningless line tried fails it.

It is deliberately **not** a gate inside `load_elements`: five of the sixty-six element-set
lines in Vallado's own verification file fail the checksum, including the deliberate error case
at 33334. They are synthetic vectors, not real element sets, and a control that refuses the
reference data is not a control. A test pins that count, so if a future wheel ships a corrected
file the checksum can be promoted.

**On the output guard, stated accurately this time.** V0.14 shipped without it and recorded no
reason. The removal happened in development during this release: I added the guard, measured it
over sixteen extreme values of `minutes` on a good element set, found the branch unreachable,
and took it out. That measurement held the element set fixed. Varying the element set instead
reaches the branch immediately, so the guard is back and the docstring names the axis the
measurement covered.

An earlier draft of this entry attributed the "removed as dead code" claim to V0.14's record.
V0.14 made no such claim. Fabricating an entry in this project's own audit trail, in the release
whose subject is audit-trail integrity, is worse than the defect it was describing.

**Verified.** Loop green under the pinned toolchain: **498 passed, 1 skipped**, coverage 98.71%
against a 80% floor, all three lock files audited clean. Pipeline simulation green: **497
passed, 2 skipped**, same coverage.

Both figures are quoted because V0.14 quoted one that came from neither run. The two differ by
exactly one skip, and the cause is `scripts/simulate-pipeline.sh` setting `GITLAB_CI=true`,
which makes `ON_PLATFORM_RUNNER` true and skips
`test_the_platform_generates_its_own_pipeline_and_we_never_commit_one` - the platform commits
its own pipeline, so its absence is not assertable on a platform runner. An earlier draft
attributed the skip to a missing dev toolchain. Nothing in the suite skips on that. Measured
with `GITLAB_CI=true pytest -rs`, which names both skips directly.

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
pinned `sgp4` wheel, the AIAA 2006-6753 verification distribution. Worst deviation MEASURED,
not chosen: 1.17e-7 km in position (about 0.12 mm) and 8.53e-10 km/s in velocity.

**Superseded by V0.15.** This entry said "32 element sets, 641 reference rows, 640 comparable".
The published file holds 33 blocks and 667 rows; keying the parser by satellite number dropped
26 of them. It also said the tolerances sit "two orders above" the measurement, which is true
of position (85 times) and not of velocity (12 times). Left in place with the correction rather
than edited away, because a record that quietly repairs itself is worth less than one that shows
where it was wrong.

Reading the reference rather than transcribing a handful of vectors is the point: the hard rule
against inventing a figure applies to test data first.

Two named traps get a witness from the published data rather than a synthetic one.

● **The unchecked error code.** Satellite 33334 in the official set returns SGP4 code 3,
  perturbed eccentricity out of range. A wrapper that ignores the code returns floats that
  read as a position; this one raises. Vallado shipped the trap, which is stronger than an
  element set I would have built to fail.
● **TEME is not J2000.** The frame is carried in `StateVector` and asserted. The failure is
  silent and grows with epoch separation, so the only defence is that it is never implicit.

A guard test recounts the rows independently and asserts the comparisons actually happened,
because a per-block loop that swallows exceptions is a green suite that compared nothing. The
counts it asserted were wrong; see V0.15.

**Verified.** Loop green under the pinned toolchain. The figure recorded here was "420 passed,
1 skipped, coverage 98.61%"; the loop's own output at the time was 421 passed and 1 skipped,
and 420 passed with 2 skipped was the PIPELINE SIMULATION. The certified number mixed two runs.
Corrected here rather than silently: a release record whose headline figure came from neither
run is the kind of small inaccuracy that makes the rest of it worth less.

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
