# The dependency vulnerability gate

What leg six of the verification loop is, why it is built the way it is, and what to do when it
fires. Written from the shipped implementation in `scripts/verify.sh`,
`scripts/check-environment.py`, `scripts/lock-requirements.sh` and the guards in
`tests/test_appstore_contract.py`, so every claim below is checkable against a file.

**The one-line version.** A dependency scan is only worth the confidence it earns, and it earns
none unless three separate things are true at once: the scan actually ran, it ran against the
dependency set that ships, and a failure to check is reported as a failure rather than a clean
tree. Leg six is arranged around those three, and each one has a test holding it in place.

## Where it sits, and why last

`sh scripts/verify.sh` runs six legs, cheapest first:

| Leg | What it proves |
|---|---|
| 1 | `scripts/check-environment.py` - installed versions equal the lock-file pins |
| 2 | `ruff format --check` |
| 3 | `ruff check` |
| 4 | `mypy` strict |
| 5 | `pytest` with Cobertura coverage to `coverage.xml`, 80% floor |
| 6 | `pip-audit` against all three lock files |

Leg six is last because it is the only leg that needs the network, and a leg that needs the
network is the leg most likely to be slow or unavailable. Leg one is first for the opposite
reason: it is the cheapest, and it is the leg that gives every other leg its meaning. If what is
installed does not equal what is pinned, then leg six scanned a set of versions that is not the
set the container ships, and its clean verdict describes a machine nobody deploys.

That ordering is asserted, not merely intended:
`test_the_environment_check_is_the_first_leg_of_the_loop` pins the environment check ahead of the
first analyser, and does it by position relative to the analyser rather than by line number, so
reordering the analysers stays free while moving the check after one of them does not.

## The three lock files, and why all three are scanned

```
requirements-runtime.in    fastapi, uvicorn, gunicorn, sgp4
requirements.in            the above, plus pytest, pytest-cov, coverage, httpx, hypothesis
requirements-dev.in        ruff, mypy, pip-audit
```

Each `.in` compiles to a hash-locked `.txt` via `sh scripts/lock-requirements.sh`, which runs
`uv pip compile --python-version 3.12 --generate-hashes`. The container installs
**`requirements-runtime.txt` only**, with `pip install --require-hashes --no-deps`: the lean file
exists so the image does not carry the test tooling or the analysers.

All three are scanned, and the reasoning differs per file.

● **`requirements-runtime.txt`** is the shipped attack surface. Obvious.
● **`requirements.txt`** is what the analysed environment holds, so an advisory here is a version
  the loop's own verdict was computed against.
● **`requirements-dev.txt`** is the one people argue about, and the argument is wrong. The
  platform installs the dev lock file and executes it in its own test stage, so an advisory there
  is code running on the runner, not just local tooling. "It is only a dev dependency" describes
  where it is declared, not where it executes.

Leg one covers all three for a related reason recorded in `verify.sh` itself: the runtime pins are
currently a version-identical subset of `requirements.txt`, so checking the lean file is
*incidentally* satisfied today. Incidental is exactly the false confidence the leg exists to
remove. If a shared pin ever diverged, the image would ship a version the analysed environment
never contained.

## The four rules the implementation encodes

### 1. A failure to check is never a pass

`pip-audit` exits non-zero for a real advisory **and** for an unreachable advisory endpoint. Those
are not the same result, and collapsing them is how a scan that never ran reads as covered.

The classification is **structural, not textual**. The scan is asked for JSON:

● Exit zero: clean. The package count is printed from the JSON, so the log says how much was
  actually examined rather than just "no vulnerabilities".
● Non-zero **with parsable JSON**: the endpoint answered and the verdict is real. Fail the leg,
  print the report.
● **Unparsable output**: the scan did not run. Fail the leg, with a message that says so in those
  words: "This is a failure to check, not a clean tree."

The alternative, grepping the log for words like "connection" or "resolve", was rejected for a
specific reason: a genuine advisory whose package name or fix-version string happens to contain
one of those words would be misread as a network problem, turning a real finding into an
honest-looking skip. The most dangerous failure of a security control is the one that produces a
reassuring log line.

### 2. An offline runner must say so, out loud, in the banner

`OFFLINE=1` converts the unreachable-endpoint case into an explicit skip, and only that case. It
prints `SKIPPED (honest)`, names continuous integration as the authoritative networked runner for
the leg, and then changes the final banner to `VERIFICATION LOOP: PASS (1 leg SKIPPED, see
above)`.

The banner change is the point. A partial loop reported as an unqualified PASS is how a leg that
never ran ends up cited as evidence. The flag also cannot be used to wave away a real advisory,
because a real advisory produces parsable JSON and never reaches the offline branch.

### 3. The scan runs through one resolved interpreter, never a bare name

Every leg is invoked as `"$PY" -m <module>`, where `$PY` resolves in order:
`ENLIGHTENMENT_PYTHON`, then `.venv/bin/python`, then `$VIRTUAL_ENV/bin/python`, then `python3`.

This is not tidiness. The loop was found calling `ruff`, `mypy`, `pytest` and `pip-audit` by bare
name, so PATH chose the versions: ruff 0.15.8 against a pinned 0.16.3, mypy 1.19.1 against a
pinned 2.3.1, and a `pytest` inside an isolated tool environment that could not import the
application's dependencies at all. It surfaced as a false failure, which is the lucky direction.
The same gap yields a false pass just as readily.

For `pip-audit` specifically the consequence is sharper than a version mismatch: a `pip-audit`
from somewhere else on PATH may resolve a different environment entirely, so it can report clean
on a dependency set that is not the one under test.

Two tests hold this: `test_the_loop_never_invokes_a_tool_by_bare_name` and
`test_the_loop_routes_every_tool_through_one_resolved_interpreter`.

### 4. A gating command is never piped into anything

`test_no_verification_script_pipes_a_gating_command_into_another` greps every `scripts/*.sh` for a
gating command (`docker build`, `pytest`, `ruff check`, `mypy`, `pip-audit`) piped into another
command. In POSIX `sh` a pipeline's exit status is the **last** command's status, so
`pip-audit ... | tee log` reports the status of `tee`, which is to say success, always. Inside leg
six the scan output is redirected to a file rather than piped, deliberately, so the guard needs no
exemption for the script that is most tempting to exempt.

The test's own docstring records what it cannot see: a fail-open expressed some other way, such as
a bare `|| true` on a mandatory step or a status captured into a variable and never checked. Those
are reviewed by eye at the gates. A guard that states its blind spot is more useful than one that
implies it has none.

## When an advisory fires

The failure message names two routes, and the order matters.

1. **Upgrade and re-lock.** Change the version in the relevant `.in` file, run
   `sh scripts/lock-requirements.sh`, commit all three `.txt` files, and re-run the loop. Leg one
   will catch a lock file that was regenerated but not installed, which is the usual next mistake.
2. **Record the suppression with a written justification.** Only when there is no fix version, and
   the reasoning belongs in the repository rather than in a terminal. An undocumented suppression
   is indistinguishable from an oversight six months later.

Never edit a `.txt` lock file by hand. The hashes are what make
`pip install --require-hashes --no-deps` meaningful, and a hand-edited pin with a stale hash fails
the container build rather than installing something unexpected, which is the correct behaviour
and an expensive way to discover a typo.

## What this gate does not cover

Stated because a control's boundary is part of its specification.

● **The platform runs its own pipeline, and this loop is a rehearsal of it, not a substitute.**
  The SonarQube quality gate is binding for this project (detected template `python`) and is a
  separate mechanism with a separate verdict. `sh scripts/simulate-pipeline.sh <version>` exists
  for that rehearsal.
● **Leg one is one-directional by decision.** Every pin must be installed at its pinned version;
  an extra distribution that is present but unpinned is not reported. Asserting the reverse would
  fail on every runner, because `pip`, `setuptools` and `wheel` come from the interpreter's own
  environment. A leg that fails on a correct environment is a leg people learn to skip, which
  costs more than the latent hole it closes.
● **`tools/` is outside the coverage gate and outside `sonar.sources=src`.** The workstation-only
  UDL characterisation tool is standard library only, so it adds nothing for `pip-audit` to scan,
  but no coverage signal exists for it either. Mutation testing at the review gates is the only
  check on that file, which is why the binding reviewers mutation-test it by hand.
● **An advisory database is a snapshot, not a proof.** A clean scan means nothing is *known* today
  about these versions. It is not a statement about tomorrow, which is why the leg runs on every
  change rather than once per release.

## Verification ledger, honestly

● **Observed in this repository:** the clean path, repeatedly. Latest run: 15 packages audited in
  `requirements-runtime.txt`, 27 in `requirements.txt`, 35 in `requirements-dev.txt`, no known
  vulnerabilities in any of the three, 77 pins matched at leg one.
● **Not observed, and read from the script rather than exercised:** the real-advisory branch and
  the unreachable-endpoint branch. Neither has fired here. The structural JSON classification, the
  `OFFLINE=1` skip and the banner change are described above from the implementation, not from a
  run that took those paths. Treat the advisory-handling procedure as designed and reviewed rather
  than as field-tested.
● **Not covered here:** the platform's own pipeline verdict, which only the platform can give.
