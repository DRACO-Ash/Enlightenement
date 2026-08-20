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
# ONLY requirements.txt, because that is ONLY what the platform's generated pipeline installs
# before it runs pytest. Installing the dev file here too is what made this simulation more
# generous than the platform: it went green while the real Test stage failed with
# `pytest: command not found`, exit 127. A simulation that helps the code along proves nothing.
"$SIM/.venv/bin/pip" install --quiet --require-hashes --no-deps -r "$SIM/requirements.txt"

# Mask the tools a stock `python:3.12-slim` image does NOT ship, so the suite runs here the way
# it runs there. This leg exists because a real upload failed at the Test stage on `unzip`: the
# local loop was green, this simulation was green, and neither reproduced the one thing that
# mattered, which is the platform's TOOL INVENTORY. Debian slim does carry coreutils (mktemp,
# sha256sum, tar, find), so only the genuinely absent tools are masked. Masking is done here,
# after the artefact has been unpacked, so the simulation's own use of unzip is unaffected.
MASK="$SIM/masked-bin"
mkdir -p "$MASK"
for absent in zip unzip git curl wget jq docker; do
  printf '#!/bin/sh\necho "%s: not found (masked: absent from a stock python image)" >&2\nexit 127\n' \
    "$absent" > "$MASK/$absent"
  chmod +x "$MASK/$absent"
done
echo "== masked as absent for the test stage: zip unzip git curl wget jq docker =="

echo "== simulated test stage (the platform's environment, not yours) =="
( cd "$SIM" && PATH="$MASK:$PATH" GITLAB_CI=true ./.venv/bin/python -m pytest )

echo "== the artefact the quality gate reads =="
test -s "$SIM/coverage.xml" || { echo "FAIL: coverage.xml absent in the checkout" >&2; exit 1; }
grep -q '<coverage' "$SIM/coverage.xml" || { echo "FAIL: coverage.xml is not Cobertura" >&2; exit 1; }

rm -rf "$SIM"
printf '\nPIPELINE SIMULATION: PASS\n'
