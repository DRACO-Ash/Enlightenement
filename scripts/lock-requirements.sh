#!/bin/sh
# Regenerate the hash-locked requirement files from the .in inputs.
# Run this deliberately when a dependency changes, then commit both lock files.
# The image installs with `pip install --require-hashes`, so an unhashed or drifted
# lock file fails the container build rather than installing something unexpected.
set -eu
cd "$(dirname "$0")/.."
uv pip compile requirements-runtime.in --python-version 3.12 --generate-hashes \
  --no-annotate --output-file requirements-runtime.txt
uv pip compile requirements.in --python-version 3.12 --generate-hashes \
  --no-annotate --output-file requirements.txt
uv pip compile requirements-dev.in --python-version 3.12 --generate-hashes \
  --no-annotate --output-file requirements-dev.txt
echo "locked: requirements-runtime.txt requirements.txt requirements-dev.txt"
