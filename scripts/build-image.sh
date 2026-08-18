#!/bin/sh
# Step 10 of the deploy sequence: build the container image.
#
# A leg that cannot run is NOT a pass. With no Docker daemon reachable this script exits
# 3 with an unmissable banner, so a partial loop can never read as a green one, and
# continuous integration stays the binding source of truth for this leg.
set -eu
cd "$(dirname "$0")/.."
TAG="${1:-enlightenment:local}"

if ! docker info >/dev/null 2>&1; then
  cat >&2 <<'BANNER'
################################################################################
# IMAGE BUILD DEFERRED TO CI - THIS IS NOT A PASS                              #
#                                                                              #
# No Docker daemon is reachable, so the container build and the image policy    #
# posture could not be verified here. The `image` job in the CI workflow is the #
# binding check. Do not treat this run as green, and do not submit to the App   #
# Store until that job has passed.                                             #
################################################################################
BANNER
  exit 3
fi

log=$(mktemp)
# Redirect, never pipe. In POSIX sh a pipeline's status is the LAST command's status, so
# `docker build | tee` reports tee's success and a failed build reads as a pass. That is a
# fail-open, and this is the exact line where it would live.
if docker build -t "$TAG" . >"$log" 2>&1; then
  cat "$log"
  rm -f "$log"
  echo "IMAGE BUILD: PASS ($TAG)"
  exit 0
fi
cat "$log" >&2

# A build that could not REACH the registry is a failure to check, not a failure of the
# Dockerfile, and neither is a pass. Distinguish them so the banner tells the truth.
if grep -qiE 'forbidden|failed to resolve source metadata|failed to do request|connection refused|no such host' "$log"; then
  cat >&2 <<'BANNER'
################################################################################
# IMAGE BUILD DEFERRED TO CI - THIS IS NOT A PASS                              #
#                                                                              #
# The build could not reach the container registry, so the Dockerfile itself is #
# unverified: neither proved nor disproved. The `image` job in the CI workflow  #
# is the binding check. Do not treat this run as green.                        #
################################################################################
BANNER
  rm -f "$log"
  exit 3
fi

rm -f "$log"
echo "IMAGE BUILD: FAIL - the Dockerfile was reached and rejected. Fix it." >&2
exit 1
