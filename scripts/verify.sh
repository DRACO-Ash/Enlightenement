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
# endpoint. Those are not the same result: a failure to CHECK is never a pass. An
# explicitly offline run records an honest skip; anywhere else it is a hard failure.
audit_log=$(mktemp)
if pip-audit --require-hashes --disable-pip -r requirements.txt >"$audit_log" 2>&1; then
  cat "$audit_log"
elif grep -qiE 'connection|network|temporary failure|timed out|resolve' "$audit_log"; then
  cat "$audit_log"
  if [ "${OFFLINE:-0}" = "1" ]; then
    echo "SKIPPED (honest): the advisory endpoint was unreachable and OFFLINE=1 is set."
    echo "Continuous integration is the authoritative networked runner for this leg."
  else
    echo "FAIL: could not reach the advisory endpoint, so the scan did not run." >&2
    echo "This is a failure to check, not a clean tree. Set OFFLINE=1 only on a runner" >&2
    echo "that is deliberately offline." >&2
    rm -f "$audit_log"
    exit 1
  fi
else
  cat "$audit_log"
  echo "FAIL: pip-audit reported an advisory. Upgrade and re-lock, or record the" >&2
  echo "suppression with a written justification." >&2
  rm -f "$audit_log"
  exit 1
fi
rm -f "$audit_log"

printf '\nVERIFICATION LOOP: PASS\n'
