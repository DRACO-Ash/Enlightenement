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
#
# HARD RULE: this script may use NOTHING but a POSIX shell and `python3`.
#
# A contract test EXECUTES this script, and the platform runs that suite in ITS environment,
# not ours. A stock `python:3.12-slim` image has no `zip` and no `unzip`. So every external
# tool here is a way for the platform's Test stage to fail with a diagnosis pointing at
# packaging instead of at an absent binary, which is exactly what happened: `zip` was removed
# and `unzip`, `tar` and `sha256sum` were left behind, and the upload failed at Test with
# Quality, Container Build and Container Scan all skipped. Fixing one instance of a class is
# not fixing the class. `test_the_packaging_script_shells_out_to_nothing_but_python` enforces
# this rule mechanically so it cannot rot back.
set -eu
cd "$(dirname "$0")/.."

VERSION="${1:?usage: package-appstore.sh <version>}"
OUT="dist/enlightenment-appstore-${VERSION}.zip"
STAGE="dist/stage"

rm -rf "$STAGE" "$OUT"
mkdir -p "$STAGE" dist

# Root-level files the platform needs. requirements.txt is the template marker.
for file in Dockerfile .dockerignore .gitignore .python-version .env.example \
            requirements.txt requirements-dev.txt requirements-runtime.txt \
            requirements.in requirements-dev.in requirements-runtime.in \
            pyproject.toml sonar-project.properties README.md CLAUDE.md; do
  cp "$file" "$STAGE/$file"
done

# Directories: source, the suite the platform runs, the loop scripts, the runbooks, and
# .github. The workflow is included because the SUITE READS IT: two contract tests assert
# that the binding image checks run as root and cover the package-manager class, and an
# assertion that cannot run on the machine gating the deploy is worse than no assertion.
# The platform generates and commits its own pipeline regardless and ignores this one.
for dir in src tests scripts docs .github; do
  python3 -c '
import pathlib, shutil, sys
source, stage = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
shutil.copytree(
    source,
    stage / source,
    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    dirs_exist_ok=True,
)
' "$dir" "$STAGE"
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

python3 -c '
import hashlib, pathlib, sys, zipfile
out = pathlib.Path(sys.argv[1])
print(f"\nPACKAGE: {out}")
print(f"SHA-256: {hashlib.sha256(out.read_bytes()).hexdigest()}")
print("\nContents (Dockerfile must be at the root, never nested):")
with zipfile.ZipFile(out) as archive:
    names = archive.namelist()
for name in names[:28]:
    print(f"  {name}")
if len(names) > 28:
    print(f"  ... and {len(names) - 28} more")
print(f"\n{len(names)} files")
' "$OUT"
