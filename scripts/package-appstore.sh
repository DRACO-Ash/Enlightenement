#!/bin/sh
# Produce the App Store upload artefact: a FLAT source zip.
#
# The platform copies this zip into a GitLab project it owns, adds its own generated
# .gitlab-ci.yml, and runs install, test, quality, container build, and deploy. So the
# zip must be a self-sufficient, testable SOURCE tree with the Dockerfile at the root:
# not a build artefact, and never with the tests removed (that failure killed a pipeline
# in eight seconds).
#
# This allowlist shapes the UPLOAD. .dockerignore shapes the IMAGE. Two separate contracts.
set -eu
cd "$(dirname "$0")/.."

VERSION="${1:?usage: package-appstore.sh <version>}"
OUT="dist/enlightenment-appstore-${VERSION}.zip"
STAGE="dist/stage"

rm -rf "$STAGE" "$OUT"
mkdir -p "$STAGE" dist

# Root-level files the platform needs. requirements.txt is the template marker.
for file in Dockerfile .dockerignore .gitignore .python-version .env.example \
            requirements.txt requirements-dev.txt requirements.in requirements-dev.in \
            pyproject.toml sonar-project.properties README.md CLAUDE.md; do
  cp "$file" "$STAGE/$file"
done

# Directories: source, the suite the platform runs, the loop scripts, the runbooks, and
# .github. The workflow is included because the SUITE READS IT: two contract tests assert
# that the binding image checks run as root and cover the package-manager class, and an
# assertion that cannot run on the machine gating the deploy is worse than no assertion.
# The platform generates and commits its own pipeline regardless and ignores this one.
for dir in src tests scripts docs .github; do
  mkdir -p "$STAGE/$dir"
  tar -cf - --exclude='__pycache__' --exclude='*.pyc' "$dir" | tar -xf - -C "$STAGE"
done

# Banned from the upload, defensively re-checked rather than assumed.
find "$STAGE" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$STAGE" \( -name '*.pyc' -o -name '.coverage' -o -name 'coverage.xml' \
     -o -name '.env' -o -name '.env.*' ! -name '.env.example' \) -delete 2>/dev/null || true
rm -rf "$STAGE/.git" "$STAGE/.venv" "$STAGE/var" "$STAGE/dist"

# Archived with the interpreter, not the `zip` binary. `zip` is not part of a stock Python
# image, and the platform runs this project's own suite against the uploaded tree in ITS
# environment: a contract test that shells out to a missing tool fails the test stage and skips
# quality, container build and deploy, with the diagnosis pointing at packaging rather than at
# an absent binary. The interpreter is guaranteed present, because it is what runs the suite.
( cd "$STAGE" && python3 -c '
import pathlib, sys, zipfile
root = pathlib.Path(".")
out = pathlib.Path(sys.argv[1])
with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(root.rglob("*")):
        if path.name == ".DS_Store":
            continue
        archive.write(path, path.relative_to(root).as_posix())
' "../$(basename "$OUT")" )
rm -rf "$STAGE"

printf '\nPACKAGE: %s\n' "$OUT"
printf 'SHA-256: %s\n' "$(sha256sum "$OUT" | cut -d' ' -f1)"
printf '\nContents (Dockerfile must be at the root, never nested):\n'
unzip -l "$OUT" | head -30
