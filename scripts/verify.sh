#!/bin/sh
# The verification loop. Ordered cheapest-first so a cheap failure never pays for an
# expensive leg. Every leg is the Python cell of the canonical step in toolchain-adapters.
#
# Legs: format, lint (the local mirror of the Sonar profile), types, tests with coverage,
# dependency vulnerability scan. The container image build is NOT here: it is step 10 of
# the deploy sequence and lives in scripts/build-image.sh.
set -eu
cd "$(dirname "$0")/.."

# The label is bound to a name before use. SonarQube flags a positional parameter read
# directly inside a function body, and it is a fair point in shell: `$1` inside a function
# means the function's argument, which is easy to misread as the script's.
green() {
  leg_label="$1"
  printf '\n== %s ==\n' "$leg_label"
}

# Every leg runs through ONE interpreter, resolved here, and never through a bare tool name.
#
# This is not tidiness. The loop used to call `ruff`, `mypy`, `pytest` and `pip-audit` by
# name, so it ran whatever PATH happened to hold. On the machine where this was found PATH
# had ruff 0.15.8 against a pinned 0.16.3, mypy 1.19.1 against a pinned 2.3.1, and a `pytest`
# in an isolated tool environment that could not import the application's dependencies at
# all. It surfaced as a false FAILURE. The same gap yields a false PASS just as readily, and
# every other claim in this repository rests on this loop's verdict.
#
# `python -m <tool>` guarantees the analyser and the code under analysis share one
# environment. ENLIGHTENMENT_PYTHON overrides the choice for a runner that installs into the
# system environment instead of a virtual environment, which is what the platform does.
if [ -n "${ENLIGHTENMENT_PYTHON:-}" ]; then
  PY="$ENLIGHTENMENT_PYTHON"
elif [ -x .venv/bin/python ]; then
  PY=.venv/bin/python
elif [ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/bin/python" ]; then
  PY="$VIRTUAL_ENV/bin/python"
else
  PY=python3
fi
echo "interpreter: $PY ($("$PY" --version 2>&1))"

green "1/8 environment matches the lock files"
# First, and deliberately so: a mismatch here means every leg below is measuring something
# other than what ships. Cheapest leg and the one that gives the rest their meaning.
# All THREE lock files, including the lean one the image installs. Its pins are currently a
# version-identical subset of requirements.txt, so checking it is incidentally satisfied
# today - but incidental is exactly the false confidence this leg exists to remove. If a
# shared pin ever diverged, the image would ship a version the analysed environment never
# contained, which is this commit's own defect one level up.
"$PY" scripts/check-environment.py "$PY" \
  requirements-runtime.txt requirements.txt requirements-dev.txt

green "2/8 content package validates"
# Second, and before any analyser touches the code: the content IS the asset, and the
# application is a delivery mechanism for it. Seventeen assertions, ten seconds, and two of them
# exist specifically to protect the handover: `generators_canonical` fails if any drill
# references a generator outside the canonical twelve, and `response_formats_declared` fails if a
# drill uses a response format the schema does not declare. Both caught real defects during the
# package's own final review, as did `detection_patterns_compile`.
#
# Standard library only and owned by the content author, so it is run rather than reimplemented.
#
# THIS LEG IS REPOSITORY-ONLY. `tools/` is deliberately excluded from the upload artefact, because
# `tools/udl_characterise.py` reads real UDL credentials and the flight plan says it never ships,
# so this loop cannot be run from an unpacked zip and is not meant to be. The platform runs pytest
# against the artefact, not this script. Recorded here after the engineering gate unpacked the
# upload, hit the missing file, and proposed shipping `tools/` - which would have put the
# credential-reading script into the artefact to fix a convenience.
"$PY" tools/validate_content.py --content-dir content --self-test \
  | "$PY" -c 'import json,sys; r=json.load(sys.stdin); print("content", r["counts"], "errors", len(r["errors"]), "warnings", len(r["warnings"])); sys.exit(1 if r["errors"] else 0)'

green "3/8 format (ruff format --check)"
"$PY" -m ruff format --check .

green "4/8 lint (ruff check)"
"$PY" -m ruff check .

green "5/8 types (mypy strict)"
"$PY" -m mypy

green "6/8 tests with coverage (pytest, Cobertura to coverage.xml)"
"$PY" -m pytest
if [ ! -s coverage.xml ]; then
  echo "FAIL: coverage.xml is missing or empty; the SonarQube gate would score 0%." >&2
  exit 1
fi

green "7/8 interface tests with coverage (node --test over ui/)"
# The interface is 1,300 lines of JavaScript and it used to have no direct test at all: the
# Python suite asserts the served BYTES - the contrast floor, the absence of invented figures,
# the verdict-colour reservation - which is the right level for "what reaches the operator" and
# cannot reach a function's branches. Both halves now exist.
#
# The runner is Node's own, with no dependency added: `node --test` and V8's coverage. The
# harness evaluates `ui/app.js` in a `vm` context so the file stays loadable by a plain
# `<script>` tag under `script-src 'self'` and gains no module exports it does not ship with.
# Node's built-in coverage reporter does not attribute a vm-run script - it reported 97.96%
# while listing only the test files - so the figure comes from V8's raw byte ranges instead,
# by the method written out at the top of ui/tests/coverage.mjs.
#
# THIS LEG IS REPOSITORY-ONLY, like leg 2. The platform's generated pipeline runs `pip install`
# and `pytest` and nothing else, so it never runs this and the interface's coverage never
# reaches the quality gate. That is also why `ui/` sits outside `src/`: see
# sonar-project.properties.
if [ -n "${ENLIGHTENMENT_NODE:-}" ]; then
  NODE="$ENLIGHTENMENT_NODE"
elif command -v node >/dev/null 2>&1; then
  NODE=node
elif [ -x /opt/node22/bin/node ]; then
  NODE=/opt/node22/bin/node
else
  echo "FAIL: node is not installed, so the interface tests cannot run. This leg is not" >&2
  echo "      optional and it does not skip: an untested interface is what it exists to stop." >&2
  echo "      Set ENLIGHTENMENT_NODE, or install Node 22 (see environment-setup)." >&2
  exit 1
fi
echo "node: $NODE ($("$NODE" --version 2>&1))"
UI_COVERAGE="${TMPDIR:-/tmp}/enlightenment-ui-coverage-$$"
rm -rf "$UI_COVERAGE"
mkdir -p "$UI_COVERAGE"
NODE_V8_COVERAGE="$UI_COVERAGE" "$NODE" --test "ui/tests/*.test.mjs"
"$NODE" ui/tests/coverage.mjs "$UI_COVERAGE" coverage-ui.info
rm -rf "$UI_COVERAGE"

green "8/8 dependency vulnerability scan (pip-audit)"
# pip-audit exits non-zero both for a real advisory AND for an unreachable advisory
# endpoint. Those are not the same result: a failure to CHECK is never a pass.
#
# The classification is STRUCTURAL, not a grep over the log text. Grepping for words like
# "connection" or "resolve" misreads a genuine advisory whose package or fix-version string
# happens to contain one, turning a real finding into an honest-looking skip. Instead the
# scan is asked for JSON: valid JSON means the endpoint answered and the verdict is real,
# whatever it says; unparsable output means the scan never ran.
#
# BOTH lockfiles are scanned. The platform installs the dev lockfile and executes it in its
# own test stage, so an advisory there is shipped code on the runner, not just local tooling.
skipped=0

audit_lockfile() {
  lockfile="$1"
  echo "-- auditing $lockfile"
  audit_json=$(mktemp)
  if "$PY" -m pip_audit --require-hashes --disable-pip --format json -r "$lockfile" >"$audit_json" 2>/dev/null; then
    "$PY" -c 'import json,sys; d=json.load(open(sys.argv[1])); print("  packages audited:", len(d.get("dependencies", [])))' "$audit_json"
    echo "  no known vulnerabilities found"
    rm -f "$audit_json"
    return 0
  fi
  if "$PY" -c 'import json,sys; json.load(open(sys.argv[1]))' "$audit_json" 2>/dev/null; then
    # Parsable JSON with a non-zero exit means the scan RAN and found something real.
    "$PY" -m json.tool "$audit_json" > "$audit_json.pretty"
    head -40 "$audit_json.pretty"
    rm -f "$audit_json" "$audit_json.pretty"
    echo "FAIL: pip-audit reported an advisory in $lockfile. Upgrade and re-lock, or" >&2
    echo "record the suppression with a written justification." >&2
    return 1
  fi
  # No parsable report: the scan did not run. Show whatever it did say. Redirected, not
  # piped: the class guard in tests/test_appstore_contract.py takes no exemptions.
  audit_text=$(mktemp)
  "$PY" -m pip_audit --require-hashes --disable-pip -r "$lockfile" >"$audit_text" 2>&1 || true
  tail -5 "$audit_text"
  rm -f "$audit_text" "$audit_json"
  if [ "${OFFLINE:-0}" = "1" ]; then
    echo "  SKIPPED (honest): the advisory endpoint could not be reached and OFFLINE=1 is set."
    echo "  Continuous integration is the authoritative networked runner for this leg."
    skipped=1
    return 0
  fi
  echo "FAIL: could not reach the advisory endpoint, so $lockfile was not scanned." >&2
  echo "This is a failure to check, not a clean tree. Set OFFLINE=1 only on a runner" >&2
  echo "that is deliberately offline." >&2
  return 1
}

audit_lockfile requirements-runtime.txt || exit 1
audit_lockfile requirements.txt || exit 1
audit_lockfile requirements-dev.txt || exit 1

# The banner names a skipped leg explicitly. A partial loop reported as an unqualified
# PASS is how a leg that never ran reads as covered.
if [ "$skipped" -eq 1 ]; then
  printf '\nVERIFICATION LOOP: PASS (1 leg SKIPPED, see above)\n'
else
  printf '\nVERIFICATION LOOP: PASS\n'
fi
