#!/bin/sh
# Step 10 of the deploy sequence: build the container image.
#
# A leg that cannot run is NOT a pass. With no Docker daemon reachable this script exits
# 3 with an unmissable banner, so a partial loop can never read as a green one, and
# continuous integration stays the binding source of truth for this leg.
set -eu
cd "$(dirname "$0")/.."
TAG="${1:-enlightenment:local}"

# PODMAN FIRST, because that is what the platform's containerize stage uses. Building locally
# with a different engine than the one that will build the submission is a difference the local
# loop cannot see: the two disagree on default build backends, on how they resolve unqualified
# image names, and on rootless UID mapping. Docker remains the fallback so a developer with only
# Docker is not blocked, and the engine actually used is echoed so a build log is never
# ambiguous about which one ran.
# An EXPLICIT override that does not work is an error, not a hint. Falling through to PATH
# discovery would silently build with an engine the caller did not ask for, and a silent
# fallback on this exact seam is how three tests drifted from the runner they ran on.
if [ -n "${ENLIGHTENMENT_CONTAINER_ENGINE:-}" ]; then
  if command -v "$ENLIGHTENMENT_CONTAINER_ENGINE" >/dev/null 2>&1 \
    && "$ENLIGHTENMENT_CONTAINER_ENGINE" info >/dev/null 2>&1; then
    ENGINE="$ENLIGHTENMENT_CONTAINER_ENGINE"
  else
    echo "FAIL: ENLIGHTENMENT_CONTAINER_ENGINE is set to" \
      "'$ENLIGHTENMENT_CONTAINER_ENGINE', which is not runnable." >&2
    echo "An explicit override that silently falls back to PATH would build with an engine" >&2
    echo "you did not ask for. Unset it to use discovery, or point it at a working engine." >&2
    exit 2
  fi
else
  ENGINE=""
  for candidate in podman docker; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" info >/dev/null 2>&1; then
      ENGINE="$candidate"
      break
    fi
  done
fi

if [ -z "$ENGINE" ]; then
  cat >&2 <<'BANNER'
################################################################################
# IMAGE BUILD DEFERRED TO CI - THIS IS NOT A PASS                              #
#                                                                              #
# Neither Podman nor Docker is reachable, so the container build and the image  #
# policy posture could not be verified here. The platform builds with PODMAN;   #
# the `image` job in the CI workflow is the binding check. Do not treat this    #
# run as green, and do not submit to the App Store until that job has passed.   #
################################################################################
BANNER
  exit 3
fi
echo "container engine: $ENGINE ($("$ENGINE" --version 2>&1 | head -1))"

log=$(mktemp)
# Redirect, never pipe. In POSIX sh a pipeline's status is the LAST command's status, so
# `<engine> build | tee` reports tee's success and a failed build reads as a pass. That is a
# fail-open, and this is the exact line where it would live.
if "$ENGINE" build -t "$TAG" . >"$log" 2>&1; then
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
