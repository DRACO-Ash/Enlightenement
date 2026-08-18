#!/bin/sh
# Simulate the platform pipeline against the ARTEFACT, not the repository.
#
# Reproduces the platform's checkout state and environment, not merely its command: the
# generated .gitlab-ci.yml it adds to the checkout, GITLAB_CI=true, and a check that the
# coverage artefact the SonarQube gate reads actually exists. If this is not green, the
# upload will fail regardless of what the repository's own CI says.
#
# Two gates this cannot reproduce, both server-side: the SonarQube ruleset and the image
# policy scan. They are mitigated by the local analyser in scripts/verify.sh keeping the
# violation count at zero, and by the flattened hardened runtime image.
set -eu
cd "$(dirname "$0")/.."

VERSION="${1:-0.1.0}"
SIM="${TMPDIR:-/tmp}/enlightenment-sim-$$"

sh scripts/package-appstore.sh "$VERSION" >/dev/null
ZIP="dist/enlightenment-appstore-${VERSION}.zip"

rm -rf "$SIM"; mkdir -p "$SIM"
unzip -q "$ZIP" -d "$SIM"

# The platform commits its own pipeline file into the checkout.
printf 'stages: [test]\n' > "$SIM/.gitlab-ci.yml"

# Use the PINNED interpreter, not whatever `python3` happens to be. A simulation on the
# wrong runtime proves nothing about the platform's build.
PINNED="python$(cat .python-version)"
if ! command -v "$PINNED" >/dev/null 2>&1; then
  echo "FAIL: the pinned interpreter $PINNED is not installed; see environment-setup." >&2
  exit 1
fi

echo "== simulated install stage ($PINNED) =="
"$PINNED" -m venv "$SIM/.venv"
"$SIM/.venv/bin/pip" install --quiet --require-hashes --no-deps -r "$SIM/requirements.txt"
"$SIM/.venv/bin/pip" install --quiet --require-hashes --no-deps -r "$SIM/requirements-dev.txt"

echo "== simulated test stage (the platform's environment, not yours) =="
( cd "$SIM" && GITLAB_CI=true ./.venv/bin/python -m pytest )

echo "== the artefact the quality gate reads =="
test -s "$SIM/coverage.xml" || { echo "FAIL: coverage.xml absent in the checkout" >&2; exit 1; }
grep -q '<coverage' "$SIM/coverage.xml" || { echo "FAIL: coverage.xml is not Cobertura" >&2; exit 1; }

rm -rf "$SIM"
printf '\nPIPELINE SIMULATION: PASS\n'
