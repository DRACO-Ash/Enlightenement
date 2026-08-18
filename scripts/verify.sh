#!/bin/sh
# The verification loop. Ordered cheapest-first so a cheap failure never pays for an
# expensive leg. Every leg is the Python cell of the canonical step in toolchain-adapters.
#
# Legs: format, lint (the local mirror of the Sonar profile), types, tests with coverage,
# dependency vulnerability scan. The container image build is NOT here: it is step 10 of
# the deploy sequence and lives in scripts/build-image.sh.
set -eu
cd "$(dirname "$0")/.."

green() { printf '\n== %s ==\n' "$1"; }

green "1/5 format (ruff format --check)"
ruff format --check .

green "2/5 lint (ruff check)"
ruff check .

green "3/5 types (mypy strict)"
mypy

green "4/5 tests with coverage (pytest, Cobertura to coverage.xml)"
pytest
if [ ! -s coverage.xml ]; then
  echo "FAIL: coverage.xml is missing or empty; the SonarQube gate would score 0%." >&2
  exit 1
fi

green "5/5 dependency vulnerability scan (pip-audit)"
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
  if pip-audit --require-hashes --disable-pip --format json -r "$lockfile" >"$audit_json" 2>/dev/null; then
    python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print("  packages audited:", len(d.get("dependencies", [])))' "$audit_json"
    echo "  no known vulnerabilities found"
    rm -f "$audit_json"
    return 0
  fi
  if python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$audit_json" 2>/dev/null; then
    # Parsable JSON with a non-zero exit means the scan RAN and found something real.
    python3 -m json.tool "$audit_json" > "$audit_json.pretty"
    head -40 "$audit_json.pretty"
    rm -f "$audit_json" "$audit_json.pretty"
    echo "FAIL: pip-audit reported an advisory in $lockfile. Upgrade and re-lock, or" >&2
    echo "record the suppression with a written justification." >&2
    return 1
  fi
  # No parsable report: the scan did not run. Show whatever it did say. Redirected, not
  # piped: the class guard in tests/test_appstore_contract.py takes no exemptions.
  audit_text=$(mktemp)
  pip-audit --require-hashes --disable-pip -r "$lockfile" >"$audit_text" 2>&1 || true
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

audit_lockfile requirements.txt || exit 1
audit_lockfile requirements-dev.txt || exit 1

# The banner names a skipped leg explicitly. A partial loop reported as an unqualified
# PASS is how a leg that never ran reads as covered.
if [ "$skipped" -eq 1 ]; then
  printf '\nVERIFICATION LOOP: PASS (1 leg SKIPPED, see above)\n'
else
  printf '\nVERIFICATION LOOP: PASS\n'
fi
