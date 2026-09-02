"""Mechanised App Store upload-gate contract checks.

These assert the CLASS, not one named instance, so a regression cannot reappear quietly.
Every negative assertion below is classified per environment: it is either true in every
checkout, or explicitly gated on the platform runner. No assertion here may be
guaranteed-false on the machine that gates the deploy.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import tomllib
import unittest.mock
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from importlib.metadata import version as installed_version
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")


def _instructions(text: str) -> str:
    """Strip comment and blank lines.

    The assertions below are about what the builder EXECUTES. Matching the file's own
    prose (which names the very patterns it forbids, so the rule is documented where it
    is enforced) would make them false for the right reasons, which is the worst kind of
    failing test.
    """
    return "\n".join(
        line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")
    )


DOCKER_INSTRUCTIONS = _instructions(DOCKERFILE)


#: Files this repository commits that the PLATFORM CHECKOUT does not carry. The App Store
#: generates and owns its own pipeline configuration, and its test job runs against a checkout
#: with `sonar-project.properties` absent - measured, in the `python-test` job of MR 5: five tests
#: and the packaging script died on `FileNotFoundError` for a file that is tracked here and ships
#: in the artefact. Same classification as `.gitlab-ci.yml`, which the platform also adds and this
#: suite already refuses to assert about: a check that cannot run in an environment must SKIP with
#: a written reason, never fail. The local run still asserts every one of them.
PLATFORM_MANAGED_ABSENCES = ("sonar-project.properties",)


def _require_local_file(name: str) -> Path:
    """Return the path, or skip when the platform checkout does not carry the file."""
    path = ROOT / name
    if not path.is_file():
        if name in PLATFORM_MANAGED_ABSENCES:
            pytest.skip(
                f"{name} is absent: the platform manages its own copy and its test job runs"
                " without one, so this assertion is not answerable here. It runs locally and in"
                " the pipeline simulation."
            )
        raise AssertionError(f"{name} is missing from the repository root")
    return path


def _git_or_skip() -> str:
    """The `git` binary, or skip. It is NOT present in the platform's test container.

    Measured in MR 5: two tests died on `FileNotFoundError: 'git'`. Note that `check=False` does
    not protect against this - `subprocess.run` raises before there is any exit code to inspect,
    so the fallback branch those tests already had was unreachable. The guard has to be the
    binary's presence, not the command's result.
    """
    binary = shutil.which("git")
    if binary is None:
        pytest.skip(
            "git is absent, which is the platform test container. The assertion this guards is"
            " answered by the artefact-walking branch or by the local run."
        )
    return binary


def _properties(path: Path) -> dict[str, str]:
    """Parse a `.properties` file into live key-value pairs, ignoring comments.

    Reading the raw text let `# DISABLED: sonar.python.coverage.reportPaths=coverage.xml`
    satisfy the assertion that the coverage path is configured, while SonarQube read no report
    and scored 0%. A settings file is parsed, never grepped.
    """
    settings: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "!")) or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        settings[key.strip()] = value.strip()
    return settings


def _live_lines(path: Path, comment: str = "#") -> list[str]:
    """The lines of a file that actually execute: no blanks, no comments."""
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith(comment)
    ]


def _pyproject() -> dict[str, Any]:
    """The parsed manifest. `tomllib` cannot be fooled by a commented-out setting."""
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


#: True when running on the platform's GitLab runner, which adds files to the checkout.
#:
#: Deliberately broad. Gating on `GITLAB_CI == "true"` alone bets the deploy on one variable
#: having one exact value: if the platform ever sets `CI` but not `GITLAB_CI`, or sets
#: `GITLAB_CI=1`, a negative assertion about a file the PLATFORM ITSELF adds becomes
#: guaranteed-false on the machine that gates the deploy. That is the one thing this file's
#: own docstring forbids, so any credible runner signal counts.
ON_PLATFORM_RUNNER = any(
    os.environ.get(name) not in (None, "", "false", "0")
    for name in ("GITLAB_CI", "CI", "CI_PIPELINE_ID", "CI_JOB_ID", "GITHUB_ACTIONS")
)


# --- the runtime contract -----------------------------------------------------------


def test_dockerfile_sits_at_the_repository_root() -> None:
    """A nested Dockerfile fails the build with `context must be a directory`."""
    assert (ROOT / "Dockerfile").is_file()


@pytest.mark.parametrize("banned", ["ENV PORT=", "ENV DATA_DIR="])
def test_no_baked_environment_default_can_defeat_the_injected_value(banned: str) -> None:
    """True in every checkout: a baked default overrides what the platform injects."""
    assert banned not in DOCKER_INSTRUCTIONS


def test_the_launch_command_binds_every_interface_on_the_platform_port() -> None:
    """gunicorn and uvicorn default to 127.0.0.1, which the platform probe cannot reach.

    The bind address must be QUOTED. Unquoted, `${PORT}` word-splits inside `sh -c`, so an
    operator-pasted value injects extra gunicorn arguments instead of failing loudly, and
    guidance prose pasted into the environment tab is a catalogued platform failure. The
    earlier assertion matched a substring present either way, so removing the quotes stayed
    green.
    """
    # The CMD is a JSON array, so the shell quotes appear escaped in the file itself.
    assert r"-b \"0.0.0.0:${PORT:-8080}\"" in DOCKER_INSTRUCTIONS


def test_the_launch_command_execs_so_sigterm_reaches_the_server() -> None:
    assert re.search(r'CMD \["sh", "-c", "exec gunicorn', DOCKER_INSTRUCTIONS)


def test_the_container_runs_as_a_numeric_non_root_user() -> None:
    users = re.findall(r"^USER\s+(\S+)", DOCKER_INSTRUCTIONS, re.MULTILINE)
    assert users, "no USER instruction found"
    for user in users:
        uid = user.split(":")[0]
        assert uid.isdigit(), f"USER must be numeric, got {user!r}"
        assert int(uid) != 0, "the container must not run as root"


def test_the_shipped_stage_is_flattened_to_one_layer() -> None:
    """The scanner reads layer history; a single clean layer is the only construction
    with none."""
    assert "FROM scratch" in DOCKER_INSTRUCTIONS
    assert DOCKER_INSTRUCTIONS.count("COPY --from=prep / /") == 1


def test_the_base_image_is_pinned_by_digest() -> None:
    bases = re.findall(r"^FROM\s+(\S+)", DOCKER_INSTRUCTIONS, re.MULTILINE)
    for base in bases:
        if base == "scratch":
            continue
        assert "@sha256:" in base, f"base image must be digest-pinned, got {base!r}"


def test_the_suid_sweep_covers_files_and_directories_and_fails_closed() -> None:
    """Matched by the COMMAND, not by the instruction it sits in.

    The earlier pattern was anchored to `^RUN find / -xdev`, which asserted the sweep was its own
    standalone `RUN`. That is a shape, not the property. The platform's Dockerfile linter flags
    consecutive `RUN` instructions, so the sweep is now the last command of the purge `RUN` - the
    invariant it protects is unchanged and its sibling below still enforces it, but this assertion
    had to stop caring where the command lives.
    """
    sweep = re.search(r"^.*find / -xdev -perm /6000 .*$", DOCKER_INSTRUCTIONS, re.MULTILINE)
    assert sweep, "the suid/sgid sweep is missing"
    line = sweep.group(0)
    assert "-type f" in line
    assert "-type d" in line
    assert "|| true" not in line, "the sweep is a mandatory step and must fail closed"


def test_nothing_follows_the_suid_sweep_in_its_stage() -> None:
    """A later instruction can re-introduce the class the sweep just cleared."""
    prep = DOCKER_INSTRUCTIONS.split("FROM scratch")[0]
    sweep_index = prep.index("find / -xdev -perm /6000")
    remainder = prep[sweep_index:].split("\n", 1)[1]
    mutating = [
        line for line in remainder.splitlines() if re.match(r"^(RUN|COPY|ADD|USER)\b", line.strip())
    ]
    assert mutating == [], f"instructions follow the sweep: {mutating}"


def test_the_healthcheck_runs_the_projects_own_validated_probe() -> None:
    assert "HEALTHCHECK" in DOCKER_INSTRUCTIONS
    assert "enlightenment.healthcheck" in DOCKER_INSTRUCTIONS


def test_the_container_runs_a_single_worker() -> None:
    """The training snapshot is a file-backed read-modify-write store. Two workers were
    measured losing half of all acknowledged writes; the store now serialises with an
    exclusive lock, and one worker keeps it safe even where advisory locking does not hold.
    """
    assert "--workers 1" in DOCKER_INSTRUCTIONS
    assert "--workers 2" not in DOCKER_INSTRUCTIONS


@pytest.mark.parametrize(
    "family",
    [r"/usr/bin/apt\S*", r"/usr/bin/dpkg\S*", r"/opt/venv/bin/pip\S*", r"/etc/apt\b"],
)
def test_no_package_manager_family_survives_into_the_shipped_image(family: str) -> None:
    """The scanner judges what is IN the image, not what the entrypoint runs.

    Matched by FAMILY (a glob-shaped pattern), not by a fixed list of binary names, because
    the first version removed pip alone and the second enumerated eight names.

    What this CANNOT see: a package-manager binary the base image ships under a path none of
    these patterns covers. The image cannot be built in the authoring environment (the
    registry blob endpoint is denied), so nothing here can enumerate the base image's real
    contents. The CI `image` job is the check that can, and it runs the equivalent test
    against the built filesystem.
    """
    sweep = DOCKER_INSTRUCTIONS.split("FROM scratch")[0]
    assert re.search(family, sweep), f"no path matching {family} is removed from the runtime"


def test_the_package_database_is_deliberately_kept() -> None:
    """/var/lib/dpkg is the package DATABASE, not a tool, and it is what the platform's
    policy scan reads to enumerate OS packages. Deleting it would remove the scanner's
    evidence rather than the risk, which is suppressing a finding.
    """
    assert "/var/lib/dpkg " not in DOCKER_INSTRUCTIONS
    assert "/var/lib/dpkg\\" not in DOCKER_INSTRUCTIONS


def _ci_instructions() -> list[str]:
    """The workflow's executable lines, with comments and blanks removed.

    Comment lines are stripped for the same reason they are in `_instructions`: an earlier
    version of this test matched `--user 0` inside the COMMENT explaining why the flag is
    needed, so removing the flag from the actual command left the test green. A mutation
    proved it. Assertions are about what runs, never about the prose beside it.
    """
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    return [
        line for line in workflow.splitlines() if line.strip() and not line.lstrip().startswith("#")
    ]


def test_the_binding_suid_sweep_in_ci_runs_as_root() -> None:
    """A non-root `find` cannot descend into a directory it cannot read: the error goes to
    stderr and the count comes back zero while bits still ship. This check stands in for
    the platform's own policy scan, so it must not be able to pass blind.
    """
    lines = _ci_instructions()
    sweep = next(index for index, line in enumerate(lines) if "-perm /6000" in line)
    # The docker run invocation is the line (or two) immediately before the find.
    command = " ".join(lines[max(0, sweep - 2) : sweep + 1])
    assert "docker run" in command, f"the sweep is not run against the image: {command}"
    assert "--user 0" in command, f"the suid sweep does not run as root: {command}"
    assert "2>/dev/null" not in command, "the sweep discards the errors that reveal a blind pass"


def test_the_package_manager_check_in_ci_covers_the_class() -> None:
    """Superseded in substance by the per-tool test further down, which binds each name to the
    loop's own step. Kept because it asserts the loop EXISTS at all, which the per-tool test
    depends on.
    """
    step = _ci_step_containing("for tool in")
    assert step, "the image job has no package-manager loop"
    assert "command -v" in step, "the loop does not actually test for the tools"


# --- the quality gate ---------------------------------------------------------------


def test_sonar_configuration_scopes_sources_tests_and_the_coverage_report() -> None:
    settings = _properties(_require_local_file("sonar-project.properties"))
    assert settings.get("sonar.sources") == "src"
    assert settings.get("sonar.tests") == "tests"
    assert settings.get("sonar.python.coverage.reportPaths") == "coverage.xml"


def test_a_bare_pytest_run_still_emits_the_cobertura_report_the_gate_reads() -> None:
    """Only the xml report writes the file Sonar consumes; a bare run would score 0%.

    Read from the PARSED manifest: mentioning the flag in a comment while dropping it from
    `addopts` used to satisfy this, and a bare platform `pytest` would then write no Cobertura
    while `verify.sh` was satisfied by a stale file from a previous run.
    """
    addopts = _pyproject()["tool"]["pytest"]["ini_options"]["addopts"]
    assert "--cov-report=xml:coverage.xml" in addopts
    assert "--cov-fail-under=80" in addopts


def test_no_configuration_file_shadows_the_manifests_pytest_settings() -> None:
    """pytest prefers `pytest.ini`, `tox.ini` and `setup.cfg` over the manifest.

    Adding a four-line `pytest.ini` therefore left the assertion above green while a bare
    `pytest` wrote NO coverage.xml, which is the exact 0%-coverage gate failure that assertion
    exists to prevent. Asserting the manifest is only meaningful if nothing outranks it.
    """
    for shadow in ("pytest.ini", "tox.ini"):
        assert not (ROOT / shadow).exists(), f"{shadow} outranks the manifest's pytest settings"
    setup_cfg = ROOT / "setup.cfg"
    if setup_cfg.exists():
        assert "[tool:pytest]" not in setup_cfg.read_text(encoding="utf-8")


def test_the_release_version_matches_across_the_manifest_and_the_package() -> None:
    """The version lives in two files and the deploy checklist asks a human to compare them.

    That is the class the documentation sweep was added to close, so it is mechanised here
    too: a bump that touches one and not the other fails before a reviewer has to notice.
    """
    manifest = _pyproject()["project"]["version"]
    package = re.search(
        r'__version__ = "([^"]+)"',
        (ROOT / "src" / "enlightenment" / "__init__.py").read_text(encoding="utf-8"),
    )
    assert package is not None, "the package declares no __version__"
    assert manifest == package.group(1), (
        f"pyproject says {manifest}, the package says {package.group(1)}"
    )


def test_the_udl_runbook_names_the_version_of_the_tool_it_documents() -> None:
    """A seventh version site, hand-bumped every release since V0.23.6 and bound by nothing.

    `docs/RUNBOOK-UDL-CHARACTERISATION.md` carries a readiness row naming the tool version the
    operator is about to run on a live UDL endpoint with real credentials. Six tests bind the
    other sites; this row had only discipline holding it, which the engineering gate pointed
    out is not a control. A runbook that names the wrong version tells an operator they are
    running something they are not.
    """
    row = re.search(
        r"`tools/udl_characterise\.py` \| this repository, `V([0-9.]+)`",
        (ROOT / "docs" / "RUNBOOK-UDL-CHARACTERISATION.md").read_text(encoding="utf-8"),
    )
    assert row is not None, "the runbook's tool-version row moved or lost its shape"
    manifest = _pyproject()["project"]["version"]
    assert row.group(1) == manifest, (
        f"the UDL runbook says V{row.group(1)}, pyproject says {manifest}"
    )


def test_the_submission_manifest_names_the_version_being_shipped() -> None:
    """THE row a human copies into the App Store console, so a stale value is a wrong upload.

    This guard was missing and the omission bit immediately: the release that bumped both code
    files to 0.14.0 left `docs/DEPLOYMENT.md` reading "0.14.0, matching pyproject.toml" while
    the file still said 0.13.0. The claim was false in the same diff that made it.

    Two code files were guarded and the document a human actually reads was not, which is the
    wrong way round: a mismatch between two code files fails a test, a mismatch between the
    code and the manifest ships.
    """
    version = _pyproject()["project"]["version"]
    row = next(
        (
            line
            for line in _live_lines(ROOT / "docs" / "DEPLOYMENT.md")
            if line.startswith("| Version")
        ),
        None,
    )
    assert row is not None, "the submission manifest has no Version row"
    assert version in row, f"the manifest says {row.strip()}, pyproject says {version}"


def test_the_deploy_checklist_names_the_version_it_simulates() -> None:
    """`simulate-pipeline.sh` with no argument defaults to 0.1.0 and simulates the wrong zip.

    The checklist spells the version out for that reason, so it is the other place a stale
    number does real damage.
    """
    version = _pyproject()["project"]["version"]
    lines = [
        line
        for line in _live_lines(ROOT / "docs" / "DEPLOYMENT.md")
        if "simulate-pipeline.sh" in line and "checklist" not in line.lower()
    ]
    assert lines, "the checklist no longer names the simulation command"
    assert any(f"simulate-pipeline.sh {version}" in line for line in lines), (
        f"the checklist simulates a version other than {version}: {lines}"
    )


def test_the_local_complexity_cap_is_tighter_than_the_platform_cap() -> None:
    """Sonar S3776 caps cognitive complexity at 15; a looser local cap is a future
    upload failure."""
    cap = _pyproject()["tool"]["ruff"]["lint"]["mccabe"]["max-complexity"]
    assert cap <= 15


# --- dependency hygiene -------------------------------------------------------------


@pytest.mark.parametrize("lockfile", ["requirements.txt", "requirements-dev.txt"])
def test_every_locked_requirement_is_exact_and_hash_pinned(lockfile: str) -> None:
    # Comment lines stripped first: a lockfile's own header is a comment, and a requirement
    # commented out must not count as pinned.
    text = "\n".join(_live_lines(ROOT / lockfile))
    requirements = re.findall(r"^([A-Za-z0-9._-]+)==(\S+)", text, re.MULTILINE)
    assert requirements, f"{lockfile} declares no requirements"
    for name, _version in requirements:
        assert f"{name}==" in text
    assert "--hash=sha256:" in text
    assert text.count("--hash=sha256:") >= len(requirements)


def test_no_version_range_operator_appears_in_a_lockfile() -> None:
    for lockfile in ("requirements.txt", "requirements-dev.txt"):
        text = (ROOT / lockfile).read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue
            assert not re.match(r"^[A-Za-z0-9._-]+\s*[~>^<]=", stripped), stripped


# --- secrets ------------------------------------------------------------------------


def test_the_environment_template_names_every_variable_without_a_value() -> None:
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    for name in (
        "PORT",
        "DATA_DIR",
        "STORAGE_MOUNT_PATH",
        "ENLIGHTENMENT_TEAM_TOKEN",
        "ALLOWED_ORIGIN",
        "BUILD_ID",
    ):
        assert name in example, f"{name} is missing from .env.example"
    for line in example.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        assert stripped.endswith("=") or "apps.bluestaq.com" in stripped, stripped


def test_gitignore_blocks_secrets_data_and_coverage_from_day_one() -> None:
    """Live patterns only. Splitting the raw text made `# .env` two tokens, so commenting the
    rule out kept this green while a developer's real `.env` became committable.
    """
    ignored = set(_live_lines(ROOT / ".gitignore"))
    for pattern in (".env", ".env.local", ".env.*.local", "coverage.xml", "var/"):
        assert pattern in ignored, f"{pattern} is not git-ignored"


def test_no_dotenv_file_is_present_in_the_source_tree() -> None:
    """True in every checkout, including the platform's: the packaging allowlist and
    .gitignore both exclude .env, so its presence would mean a real leak.
    """
    assert not (ROOT / ".env").exists()


# --- environment classification -----------------------------------------------------


def test_the_platform_generates_its_own_pipeline_and_we_never_commit_one() -> None:
    """Classified: the platform ADDS its own .gitlab-ci.yml to the checkout, so asserting
    its absence is guaranteed-false on the runner that gates the deploy. Enforced only
    off the platform, and recorded as an explicit honest pass on it.
    """
    if ON_PLATFORM_RUNNER:
        pytest.skip("the platform commits its own .gitlab-ci.yml; absence is not assertable here")
    assert not (ROOT / ".gitlab-ci.yml").exists()


def test_no_build_output_can_reach_the_platform_checkout() -> None:
    """The platform runs the suite against the uploaded zip with no build step of its own,
    so nothing there may depend on a build output.

    Classified: asserting that `dist/` is ABSENT would be guaranteed-false in any checkout
    where packaging has been run, which is every checkout about to be uploaded. The invariant
    that holds everywhere is that `dist/` is git-ignored and cannot reach the artefact.

    Asserted by BUILDING the artefact and looking inside it, not by matching a line of the
    script. Two reasons. A substring match over comment-stripped lines could still be
    satisfied by a trailing `# TODO restore: rm -rf ...` on a live line, which deletes the
    purge. And the counterfactual an earlier version of this docstring asserted was wrong: the
    real control is the ALLOWLIST copy loop, which never copies `.git`, `.venv`, `var/` or
    `dist/` in the first place. The `rm -rf` is a defensive re-check behind it. Reviewers
    measured that with the purge removed the zip is still clean, so the claim is corrected
    here rather than repeated.
    """
    assert "dist/" in set(_live_lines(ROOT / ".gitignore"))

    # The DECLARED version, not a synthetic one. `package-appstore.sh` now refuses a version
    # that disagrees with `pyproject.toml`, because this repository once built an 0.18.0 archive
    # from a tree declaring 0.17.0, and an inspection keyed on the declared version then examined
    # a different file from the one just written and called it clean. The synthetic
    # `0.0.0-contract-test` this test used to pass is exactly the mismatch that guard refuses.
    #
    # The archive is left in place rather than deleted: it is the real artefact, correctly built,
    # and the rejection-criteria tests read it instead of skipping.
    with zipfile.ZipFile(_latest_artefact()) as package:
        names = package.namelist()

    banned = ("/.git/", "/.venv/", "/var/", "/dist/", "__pycache__", ".coverage")
    offenders = [
        name
        for name in names
        if any(marker in f"/{name}" for marker in banned)
        or (name.endswith((".pyc", ".env")) and not name.endswith(".env.example"))
    ]
    assert offenders == [], f"the artefact carries files it must not: {offenders[:10]}"
    # The Dockerfile must be at the ROOT of the zip, never nested.
    assert "Dockerfile" in names, "the artefact has no root-level Dockerfile"
    assert any(name.startswith("tests/") for name in names), "the suite is missing from the zip"


# --- the loop scripts must not fail open --------------------------------------------


def test_no_verification_script_pipes_a_gating_command_into_another() -> None:
    """A pipeline's exit status in POSIX sh is the LAST command's status, so piping a
    gating command into `tee` or `head` turns a failure into a pass.

    This is a grep over the class, not a test of one named instance. What it CANNOT see: a
    fail-open expressed some other way (a bare `|| true` on a mandatory step, a status
    discarded into a variable and never checked). Those are reviewed by eye at the gates.
    """
    gating = ("docker build", "pytest", "ruff check", "mypy", "pip-audit")
    # A single `|` is a pipe; `||` is a logical OR and loses nothing. Matching bare "|"
    # flagged every `|| true` in the tree, which is a false positive, and a guard that
    # cries wolf gets exempted rather than obeyed.
    pipe = re.compile(r"(?<!\|)\|(?!\|)")
    offenders: list[str] = []
    for script in sorted((ROOT / "scripts").glob("*.sh")):
        for number, line in enumerate(script.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or not pipe.search(stripped):
                continue
            if any(command in stripped for command in gating):
                offenders.append(f"{script.name}:{number}: {stripped}")
    assert offenders == [], "a gating command is piped, so its exit status is lost:\n" + "\n".join(
        offenders
    )


# The prose grep that used to live here is deleted, not weakened. It asserted only that the
# strings "THIS IS NOT A PASS" and "exit 3" appeared SOMEWHERE in the script, so rewriting the
# no-daemon leg to `echo PASS; exit 0` left it green while carrying the most reassuring name
# in the file. The four executing tests below replaced it.


def test_the_loop_audits_every_lockfile_it_installs() -> None:
    """The platform installs the dev lockfile and executes it in its own test stage, so an
    advisory there is shipped code on the runner, not just local tooling. Removing the
    second leg used to leave the suite green.
    """
    verify = "\n".join(_live_lines(ROOT / "scripts" / "verify.sh"))
    for lockfile in ("requirements.txt", "requirements-dev.txt"):
        assert f"audit_lockfile {lockfile}" in verify, f"{lockfile} is never audited"
    # Two CALLS, counted over executable lines only. Matching the raw file let the leg be
    # commented out with the suite still green, which is the third time a test here has
    # asserted prose rather than the instruction beside it.
    assert sum(1 for line in verify.splitlines() if line.strip().startswith("audit_lockfile ")) >= 2


# --- the image script is EXECUTED, not grepped ----------------------------------------


def _run_build_image(tmp_path: Path, stub: str) -> subprocess.CompletedProcess[str]:
    """Run scripts/build-image.sh against a stub container engine.

    Stubs BOTH names and pins the choice with `ENLIGHTENMENT_CONTAINER_ENGINE`, because
    stubbing `docker` alone stopped working the moment the script learned to prefer Podman -
    which is what the platform's containerize stage uses. On a runner with a working Podman the
    script found the real one, built the real image, and returned 0, so three tests asserting a
    deferral exit code failed. **They failed in CI and not locally**, because this authoring
    environment has neither engine while the GitHub runner has Podman.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("podman", "docker"):
        fake = bin_dir / name
        fake.write_text(stub, encoding="utf-8")
        fake.chmod(0o755)
    # PATH stubs only, and no explicit override. Stubbing both names is what makes the deferral
    # reachable: the discovery loop tries `podman` then `docker` BY NAME, and PATH resolves both
    # to these stubs, so no real engine is consulted whatever the runner has installed.
    #
    # The override is deliberately NOT set here. It now fails loudly (exit 2) when it names an
    # unusable engine, which is correct - an explicit choice that silently falls back to
    # discovery would build with something the caller did not ask for - but it is a different
    # exit code from the deferral this helper's callers assert. Its own behaviour is covered by
    # `test_the_build_script_honours_an_explicit_engine_override` and
    # `test_an_unusable_explicit_engine_fails_rather_than_falling_back`.
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    shell = shutil.which("sh")
    assert shell, "no POSIX shell on PATH"
    return subprocess.run(  # noqa: S603 - a resolved shell and a fixed, in-repo script path
        [shell, str(ROOT / "scripts" / "build-image.sh"), "enlightenment:test"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
        timeout=120,
        check=False,
    )


def test_no_reachable_daemon_defers_with_a_banner_and_a_non_zero_exit(tmp_path: Path) -> None:
    """EXECUTED, not grepped. The earlier version asserted only that the strings
    "THIS IS NOT A PASS" and "exit 3" appeared somewhere in the file, so rewriting the
    no-daemon leg to `echo PASS; exit 0` left the suite green. That is the one leg that
    matters most, because it is the leg that currently cannot run for real.
    """
    result = _run_build_image(tmp_path, "#!/bin/sh\nexit 1\n")
    assert result.returncode == 3, f"expected the deferral exit code, got {result.returncode}"
    assert "THIS IS NOT A PASS" in result.stderr
    assert "PASS (" not in result.stdout


def test_an_unreachable_registry_defers_rather_than_passing(tmp_path: Path) -> None:
    stub = (
        "#!/bin/sh\n"
        'case "$1" in\n'
        "  info) exit 0 ;;\n"
        "  build) echo 'ERROR: failed to resolve source metadata: Forbidden' >&2; exit 1 ;;\n"
        "esac\n"
        "exit 0\n"
    )
    result = _run_build_image(tmp_path, stub)
    assert result.returncode == 3, f"expected the deferral exit code, got {result.returncode}"
    assert "THIS IS NOT A PASS" in result.stderr


def test_a_rejected_dockerfile_fails_rather_than_deferring(tmp_path: Path) -> None:
    """A Dockerfile the builder REACHED and refused is a real failure, exit 1, not a deferral.
    Conflating the two would let a broken Dockerfile read as an environment problem.
    """
    stub = (
        "#!/bin/sh\n"
        'case "$1" in\n'
        "  info) exit 0 ;;\n"
        "  build) echo 'ERROR: unknown instruction: FRM' >&2; exit 1 ;;\n"
        "esac\n"
        "exit 0\n"
    )
    result = _run_build_image(tmp_path, stub)
    assert result.returncode == 1, f"expected a hard failure, got {result.returncode}"
    assert "THIS IS NOT A PASS" not in result.stderr


def test_a_successful_build_reports_a_pass(tmp_path: Path) -> None:
    result = _run_build_image(tmp_path, "#!/bin/sh\nexit 0\n")
    assert result.returncode == 0
    assert "IMAGE BUILD: PASS" in result.stdout


# --- the documentation cannot rot silently --------------------------------------------


def _test_names_in(path: Path) -> set[str]:
    """Every test name in ``path``, at any nesting depth, both `def` and `async def`.

    An AST walk rather than a line scan. The line scan missed `async def` entirely, and would also
    have missed a decorated definition split across lines, or one reflowed by the formatter. The
    parser knows what a function is; a prefix match guesses.

    **`ast.walk`, not `tree.body`, and that distinction was itself a survivor.** The first AST
    version read module level only while its docstring claimed the walk survived class nesting.
    Both gates planted `class TestNested:` with a test inside, pytest collected it under the
    default `Test*` prefix, and the sweep passed. Measured at the time: `ast.walk` and `tree.body`
    yielded the identical 435 names, so nothing was hidden that day - the hole was open, not
    occupied, which is the only reason this is the third recorded instance of the same fault
    rather than a live gap.

    Walking everything also picks up a `test_`-prefixed function nested inside another function.
    Nothing does that here, and if something ever does it fails SAFE: the name arrives needing a
    citation or an exemption, which is a decision, not a silence.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    }


def _all_test_names() -> set[str]:
    """Every test name in the suite, for checking that a list of names still names something."""
    names: set[str] = set()
    for suite in sorted((ROOT / "tests").glob("test_*.py")):
        names |= _test_names_in(suite)
    return names


def _suite_of(name: str) -> str | None:
    """Which suite defines ``name``, or ``None`` if nothing does."""
    for suite in sorted((ROOT / "tests").glob("test_*.py")):
        if name in _test_names_in(suite):
            return suite.name
    return None


#: The heading that opens the control table. Sliced on, rather than pattern-matched around, because
#: `startswith("|")` over the whole document is not "the control table" - it is every markdown table
#: in `docs/SECURITY.md`, and the mutant ledger is one of those. Proved by the engineering gate: it
#: deleted a control row, added a ledger row naming that row's test, and all three sweep checks went
#: green. A control carrying no register promise read as cited, which is the same fault as scanning
#: the prose, one table along.
CONTROL_TABLE_HEADING = "## Controls, each with a test that fails if it regresses"


def _control_table_rows(policy: str) -> str:
    """The lines of the control table, and of nothing else.

    Asserts the heading exists. A renamed heading must fail loudly: an empty slice would make every
    citation vanish, and the sweep would then report every security test as uncited - noisy rather
    than silent, but a rename should say so rather than be diagnosed from a wall of names.

    **Slicing to the next heading was not narrow enough**, and the first attempt at this fix was
    measured as insufficient before it was believed: the mutant LEDGER lives under this same
    heading, further down the section, so cutting a control row and adding a ledger row naming its
    test still read as cited. The table is the FIRST contiguous run of pipe-prefixed lines after
    the heading, and that is what this returns - the ledger is a later run, separated by prose, and
    is therefore outside it whatever it says.
    """
    assert CONTROL_TABLE_HEADING in policy, (
        f"docs/SECURITY.md has no {CONTROL_TABLE_HEADING!r} heading, so the citation slice cannot"
        " be anchored; if the heading was renamed, update CONTROL_TABLE_HEADING with it"
    )
    after = policy.split(CONTROL_TABLE_HEADING, 1)[1]
    rows: list[str] = []
    for line in after.splitlines():
        if line.lstrip().startswith("|"):
            rows.append(line)
        elif rows:
            break
    assert rows, "the control table under the heading holds no rows, so no citation can resolve"
    return "\n".join(rows)


#: An elided citation - the `test_a_thing...` form the table uses to stay narrow - is resolved by
#: PREFIX, and an unbounded prefix re-opens the sweep for a whole family. Measured by the security
#: gate: shortening `test_the_coarse_tier...` to `test_the...` made an uncited control read as
#: cited, because a short prefix matches a large fraction of the swept suite. So both ends are
#: bounded. The literals are absolute, not derived from the register, because a bound asserted
#: against itself is no bound - this project has shipped that mistake twice.
#:
#: **No counts here on purpose.** This comment carried "matches 32 of the 182 swept tests and
#: `test_a...` would match 91" and went stale in three consecutive commits, because any commit that
#: adds a swept test changes both. A figure in a comment has no mechanism keeping it true. The
#: assertion below reports the live numbers when it fires, which is when anybody needs them.
MIN_ELIDED_PREFIX = 20
MAX_ELIDED_RESOLUTION = 3

#: How a citation is spelled, in one place, because three checks read them and they drifted apart
#: once already. `(?![A-Za-z0-9_])` ends the token so a name cannot match inside a longer one, and
#: `(?!\.py\b)` drops file stems so `tests/test_auth.py` contributes no bare `test_auth`.
#:
#: **Case-insensitive, and the reason is drift, not a live miss.** It was written as a lowercase
#: class, while the sibling regex in `test_every_test_named_in_the_security_policy_exists` already
#: used `[A-Za-z0-9_]`. Two spellings of one idea is how they diverged last time. The trigger was a
#: test briefly named `..._TARGET_...`: the lowercase class truncated it at the capital, matched the
#: useless stem `test_a_symlinked_backup_`, and a real cited control read as UNCITED. Lint then
#: required the lowercase name (N802), so on the register as it stands the two classes return the
#: identical set. That equivalence is ASSERTED below rather than stated here, because the earlier
#: version of this comment quoted a count, was true when taken, and went stale the moment the test
#: was renamed. What widening actually buys: a capitalised citation becomes a LOUD dangling-name
#: failure instead of a silent truncation, and the two sibling regexes stop drifting.
CITATION_TOKEN = r"\btest_[A-Za-z0-9_]+(?![A-Za-z0-9_])(?!\.py\b)"


#: Every suite holding a security property the register carries. `test_http.py`, `test_storage.py`
#: and `test_audit.py` were missing while the sweep read only four: the register cites the
#: 500-header test, the middleware-order test, the symlink refusals, the atomic write, the
#: anti-shrink merge and the log-injection block, all of which live there, so a new uncited control
#: in any of them was exactly as invisible as nosniff was.
SWEPT_SECURITY_SUITES: tuple[str, ...] = (
    "test_audit.py",
    "test_auth.py",
    "test_config.py",
    "test_content_package.py",
    "test_drill_loop.py",
    "test_generators.py",
    "test_healthcheck.py",
    "test_http.py",
    "test_middleware.py",
    # The progress store, which will hold personal performance data the moment identity exists.
    # Swept because it carries three register rows: the file's mode, the capped history, and the
    # degrade-to-defaults path on a damaged file. Its tests lived in the retired `test_training.py`
    # and were restored here in V0.24.0, because deleting a suite for a module that still exists
    # takes its controls with it and the register goes on citing them.
    "test_progress.py",
    "test_ratelimit.py",
    "test_storage.py",
    # The training layer. Swept because it carries four classes of control the register names:
    # the answer key never crossing the wire before a commit (a disclosure control on the thing
    # the product is FOR), the interface's Content Security Policy and its markup-sink discipline,
    # the strict limiter on the scoring endpoint, and the redaction gate re-asserted at the edge
    # rather than only at load.
    #
    # V0.24.0 replaced the illustrative engine with the real content package, and the suites moved
    # with it: `test_content.py` and `test_training.py` are gone, and `test_content_package.py`,
    # `test_generators.py`, `test_drill_loop.py` and `test_scoring.py` carry the same four classes
    # of control over the new modules. The answer-key boundary in particular is now asserted on
    # the raw response BODY of a real 140-item library rather than on a placeholder one.
    "test_scoring.py",
    "test_training_api.py",
    # Elo, calibration and spacing. Restored in V0.24.1 after both gates found the module live,
    # at 87% coverage, and named by NO test: three mutants passed the full suite. Swept because
    # the register now carries the rating band, the proper scoring rule and the off-scale
    # confidence refusal, and an uncited control here would be exactly as invisible as those were.
    "test_training_scoring.py",
)

#: Suites holding no security property, so nothing in them needs a register row. Recorded rather
#: than left implicit, because `SWEPT_SECURITY_SUITES` on its own is only closed against suites
#: that already exist: a NEW suite holding an uncited control was invisible until somebody happened
#: to cite it. Every file matching `tests/test_*.py` must appear in exactly one of these three
#: sets, so adding a suite forces the same decision that adding a test does.
NON_SECURITY_SUITES: frozenset[str] = frozenset(
    {
        # The physics core and the determinism substrate: pure functions over numbers, no input or
        # output, no state, no untrusted value. Their boundary guards are correctness bounds, not
        # access controls, and `docs/SECURITY.md` carries no row for them by design.
        #
        # `test_entrypoint.py` is here for a DIFFERENT reason, spelled out because the reason above
        # does not cover it and this list is the only thing between an unswept suite and the sweep.
        # It does read the environment and assert the resolved bind address, which looks like an
        # access-control assertion and is not: `config.py:158-167` records that loopback binding is
        # deliberately NOT relied on as a control, because the container binds `0.0.0.0` from its
        # launch command and the write routes fail closed on their own. So it asserts wiring - that
        # the documented default is what actually gets bound - and the control it might look like
        # lives in the `writes_open` rows instead. A security test added HERE would need this set
        # amended on purpose, which is the decision this comment exists to force.
        "test_entrypoint.py",
        "test_physics_angles.py",
        "test_physics_propagation.py",
        "test_physics_relative.py",
        "test_physics_times.py",
        "test_scenario_determinism.py",
    }
)

#: Suites the register cites at FILE granularity and this sweep deliberately does NOT walk.
#: `docs/SECURITY.md` cites `tests/test_appstore_contract.py` for the Dockerfile row, because that
#: control is asserted by several Dockerfile-text tests rather than one. Walking this suite would
#: put 104 of its 113 tests into the sweep, nearly all of them packaging, pipeline-naming and image
#: shape assertions carried by `docs/DEPLOYMENT.md` at contract granularity rather than by the
#: security register. A 104-entry exemption list is a list nobody maintains, and an unmaintained
#: exemption list is the exact failure this check exists to catch, so the scope is narrowed here in
#: writing instead of being quietly widened.
UNSWEPT_CITED_SUITES: frozenset[str] = frozenset({"test_appstore_contract.py"})

#: Security-property tests that are deliberately NOT cited in the register, each because the
#: property it guards is already carried by a cited row rather than being a control of its own.
#: A curated list with a written reason, in the same idiom as the checksum opt-out census: a NEW
#: security test must either be cited or be added here on purpose.
#:
#: The list grew from 32 names to 100 when the sweep started walking the AST across all seven
#: control suites instead of `def`-prefixed lines across four: 2 dead entries removed and 70 added.
#: That growth is the point. The previous 32 were not a smaller true answer, they were all the
#: sweep could see - 62 tests across four suites, of which it recognised 45, against 168 across
#: seven now. Triaging the 74 newly visible names also found four register rows claiming more than
#: they cited - the `==` census, the 413 half of the cross-origin row, the `app.state` exposure
#: surface and the backup symlink refusal - and those four are now cited rather than exempted.
UNCITED_SECURITY_TESTS: frozenset[str] = frozenset(
    {
        # --- PRESENTATION. The axis-label refit keeps timestamps inside the plot box at every
        # width; a clipped label is a legibility fault and a wrong reading, not an access control,
        # and `docs/SECURITY.md` is not where a reader should look for it.
        "test_the_plot_refits_its_text_after_layout_rather_than_reserving_a_fixed_gutter",
        # --- test_training_scoring.py. TRAINING CORRECTNESS, the first kind described below.
        # Restored in V0.24.1 after both gates found `training/scoring.py` live and named by no
        # test at all. Three of its assertions DO carry register rows - the rating band, the
        # proper scoring rule, the off-scale confidence refusal - because each is a bound on a
        # value that reaches a person. These five are the measurement itself: an Elo exchange that
        # neither creates nor destroys rating, a draw at parity, the direction of a wrong answer,
        # the spacing ladder's monotonicity, and the wording of the calibration verdict. Real
        # properties, and the reason the product works, but "the Elo exchange is symmetric" in a
        # document that promises controls would dilute the document.
        # `serve(item_id=...)` bypasses selection for a debrief and for tests. Its refusal of an
        # unknown id is a correctness guard - it must not substitute a different drill - and not
        # an access control: the route does not expose the parameter.
        "test_an_unknown_item_id_is_refused_rather_than_substituted",
        "test_two_equally_rated_players_expect_a_draw",
        "test_the_exchange_is_symmetric_so_ratings_are_not_created_or_destroyed",
        "test_a_wrong_answer_lowers_the_operator_and_raises_the_item",
        "test_a_miss_returns_the_cue_to_the_front_of_the_spacing_ladder",
        "test_the_spacing_ladder_only_ever_grows_and_is_bounded",
        "test_the_calibration_verdict_names_the_costly_case_in_words",
        # --- test_training.py and test_training_api.py. Both suites ARE swept: the answer-key
        # boundary, the interface policy, the markup sinks, the scoring limiter, the progress
        # file's mode and the edge redaction check all carry register rows. The names below are
        # the remainder, and they fall into three kinds, none of which is an access control:
        #
        # * TRAINING CORRECTNESS. Elo symmetry and bounds, the Brier score, the spacing reset on a
        #   miss, interval width on a small sample, plot determinism, the bounded-versus-unbounded
        #   relative track. Real properties, and the reason the product works, but a register row
        #   for "the Elo exchange is symmetric" would dilute a document whose promise is
        #   "controls, each with a test that fails if it regresses".
        # * FAIL-SOFT BEHAVIOUR ON DATA THIS PROCESS WROTE ITSELF. A missing progress file, a run
        #   row of an unknown shape, a cue with no due date. Each degrades rather than raising, and
        #   the DAMAGED-file case that does carry a disclosure argument is cited separately.
        # * PRESENTATION AND ACCESSIBILITY. The palette rules, reduced motion, the status glyphs,
        #   the interval rendering. These are code standards in this project and they are enforced
        #   by these tests, but they are not security controls and `docs/SECURITY.md` is not where
        #   a reader should look for them.
        "test_a_drill_response_is_never_cached",
        "test_a_procedure_is_served_in_full_and_an_unknown_one_is_a_404",
        "test_an_unknown_run_is_a_400_naming_the_problem_not_a_500",
        # Renamed and rescoped in V0.24.0: status-by-shape became the verdict-glyph half of the
        # red reservation, which IS cited because it is a transfer-of-training decision.
        "test_the_interface_honours_an_inverted_axis",
        "test_the_interface_sizes_plot_text_against_the_measured_scale",
        "test_a_product_is_served_with_its_observed_layout",
        "test_normalisation_folds_the_variants_an_operator_actually_types",
        "test_selection_prefers_a_due_item_over_a_better_matched_one",
        "test_the_bounded_relative_track_closes_and_the_unbounded_one_does_not",
        "test_the_manifest_states_its_own_provenance",
        "test_the_dashboard_reports_intervals_and_never_a_bare_competency_number",
        "test_the_interface_honours_reduced_motion",
        "test_the_reveal_arrives_only_as_the_answer_response",
        # --- test_content.py. The suite IS swept, because the redaction gate is a disclosure
        # control and the fail-closed load is an integrity one, and both carry register rows. These
        # thirteen are content-CORRECTNESS: does a version resolve, is a hash canonical, is an
        # ordinal contiguous, is the schema artefact emitted. Each is a real property and none is an
        # access control, so a register row for it would dilute a document whose promise is
        # "controls, each with a test that fails if it regresses".
        #
        # Two are close enough to the line to say why they are BELOW it.
        # `test_a_draft_is_loaded_but_never_counted_as_active` reads like an authorisation check and
        # is not: `status` governs which content SCORES a run, and nothing about it decides who may
        # read or write. `test_a_reference_to_content_that_is_not_loaded_is_refused` is referential
        # integrity at load, so its failure mode is an unscoreable run, not a disclosure or a
        # bypass. The version-pinning case in the same area IS cited, because a rubric floating to a
        # newer procedure silently rescores history, which is a record-integrity property.
        #
        # Listed individually rather than exempted by file, deliberately: a new SECURITY test in
        # this suite still fails the sweep until somebody decides about it, which is the whole
        # reason this set exists per-test.
        # A unit-level half of the nosniff rows, which cite the integration tests.
        "test_a_non_http_scope_passes_through_untouched",
        # Unit-level cases of controls the register cites at SOURCE granularity - the
        # `config.py` rows for start-up refusals and binding, and the `ratelimit.py` rows for
        # the two-tier limiter. Each is a positive-or-negative case of a cited control rather
        # than a control of its own, and demanding a register row per case would produce a
        # register nobody reads. Listed individually rather than exempted by file, so a NEW
        # security test in either suite still fails this check until somebody decides.
        "test_a_configured_token_requires_authentication_and_keeps_writes_closed",
        "test_a_finished_window_is_dropped_from_the_table",
        "test_a_nonsensical_window_is_refused",
        "test_a_real_origin_still_starts",
        "test_a_tracked_caller_is_still_counted_when_the_table_is_full",
        "test_a_value_at_the_cap_is_accepted",
        "test_allows_exactly_the_limit_then_refuses",
        "test_anything_other_than_an_affirmative_leaves_writes_closed",
        "test_data_dir_resolution_prefers_explicit_then_platform_then_default",
        "test_explicit_host_overrides_the_default",
        "test_host_binds_every_interface_when_a_token_is_set",
        "test_host_binds_loopback_when_authentication_is_off",
        "test_keys_are_independent",
        "test_one_call_below_the_limit_still_passes",
        "test_window_resets_only_after_it_elapses",
        # Ten more that a LOOSE matcher had masked: the first version of the check
        # shrank a name to `test_an` and found it inside an unrelated citation, so
        # these read as cited when nothing cited them. Same reason as the rest - unit
        # cases of controls the register carries at source granularity.
        "test_a_token_at_the_minimum_is_accepted",
        "test_auth_required_tracks_the_token",
        "test_build_id_falls_back_to_the_package_version",
        "test_the_key_table_never_exceeds_its_bound_under_a_flood",
        "test_the_limit_is_reported",
        "test_the_token_band_never_exposes_an_exact_length",
        "test_writes_are_closed_by_default_with_no_token_and_no_opt_in",
        # --- test_audit.py: cases of the two `audit.py` sanitiser rows, the log-injection block
        # and "EVERY reflected log value sanitised, lines emitted as JSON". Actor defaulting and
        # the JSON line shape are each one behaviour of that one sanitiser. The two LENGTH-cap
        # tests were exempted under this reason and no longer are: the security gate deleted
        # `[:limit]` from `audit.py` and raised both bounds, and every cited test stayed green,
        # which disproved the reason rather than the control. The cap has its own row now.
        "test_an_empty_reflected_value_stays_empty_rather_than_becoming_anonymous",
        "test_an_event_line_leaves_non_string_fields_intact",
        "test_audit_emits_one_parsable_json_line_with_the_given_fields",
        "test_no_control_character_survives_a_reflected_value",
        # --- test_auth.py: the four behaviour cases of the constant-time compare, whose row
        # cites the primitive and the `==` census. Match, mismatch, wrong-same-length and a
        # missing header are the compare's own truth table, not four separate controls.
        "test_exact_match_passes",
        "test_length_mismatch_fails_without_comparing",
        "test_missing_header_fails",
        "test_wrong_value_of_the_same_length_fails",
        # --- test_healthcheck.py: the positive and default cases of the five `healthcheck.py`
        # rows. Every FAIL-CLOSED branch in that module is now cited by name, because the security
        # gate mutated all three and found them killed only by tests this sweep could not even see
        # - the suite was outside it, because the guard derived cited suites from file references
        # and the register cites this one by test name. What is left here is the other half of each
        # truth table: a good port resolves, a padded one normalises rather than being refused, an
        # absent one takes the documented 8080 default, and a 200 reads healthy.
        "test_a_200_liveness_response_is_healthy",
        "test_a_port_padded_by_the_operator_console_is_normalised_not_refused",
        "test_a_valid_port_is_accepted",
        "test_an_absent_port_falls_back_to_the_documented_default",
        "test_the_probe_defaults_to_8080_when_no_port_is_injected",
        "test_the_probe_reads_the_injected_port",
        # --- test_http.py: HTTP-level cases of rows the register carries at source
        # granularity - the body cap, the `If-Match` parse, the must-exist merge, the
        # `extra="forbid"` rejection, the probe cache and pool, the CORS echo, the public
        # health paths, the closed-by-default write posture and the nosniff header.
        "test_a_body_within_the_cap_is_accepted_when_sent_chunked",
        "test_a_latin1_if_match_byte_on_the_wire_is_ignored_rather_than_raising",
        "test_a_matching_if_match_is_accepted",
        "test_a_patch_to_an_unknown_session_is_a_404_not_a_silent_create",
        "test_a_post_still_requires_every_mandatory_field",
        "test_a_probe_path_declaring_a_body_answers_even_for_a_body_method",
        "test_a_stale_probe_verdict_is_refreshed_once_the_window_passes",
        "test_a_well_formed_if_match_still_parses",
        "test_a_write_with_a_wrong_token_of_the_same_length_is_refused",
        "test_a_write_with_the_right_token_succeeds",
        "test_an_error_response_carries_nosniff_too",
        "test_an_oversize_body_with_a_declared_length_is_refused",
        "test_an_unparsable_if_match_is_ignored_rather_than_failing_the_request",
        "test_liveness_paths_return_200_unauthenticated",
        "test_no_cors_header_is_emitted_when_no_origin_is_configured",
        "test_readiness_paths_return_200_unauthenticated_when_storage_is_writable",
        "test_readiness_returns_503_with_the_resolved_dir_and_errno",
        "test_reads_and_probes_stay_open_in_the_closed_default",
        "test_repeated_probes_hold_exactly_one_probe_thread",
        "test_the_allowed_origin_is_echoed_and_another_origin_is_not",
        "test_the_published_pool_reference_is_cleared_with_the_pool",
        "test_the_readiness_probe_uses_the_validated_config_not_a_fresh_environment_read",
        "test_the_revision_digit_bound_stays_well_below_the_interpreter_limit",
        # --- test_http.py, not security controls at all. Conditional GET is a caching
        # behaviour, the diagnostics content assertions are completeness checks on an
        # operator page whose ONE security property (no token, no exact length) is cited,
        # and the root-path assertion is an App Store health contract carried by
        # `docs/DEPLOYMENT.md`. Kept in the sweep's suite list rather than exempted by file,
        # so a real control added beside them still fails this check.
        "test_a_listing_carries_an_etag_and_answers_304_when_unchanged",
        "test_diagnostics_answers_every_plausible_deploy_question_at_once",
        "test_diagnostics_reports_the_anonymous_write_posture",
        "test_root_returns_200_and_never_a_redirect",
        "test_the_etag_changes_after_a_write",
        # --- test_middleware.py: the body cap's and the drain budget's own boundary and scope
        # cases. The register carries the cap on bytes read, the header order, the method case,
        # the probe exemption and the total budget; these are the at-the-cap, one-over,
        # zero-budget, within-budget, disconnect, replay and method-scope cases of those rows.
        # The non-HTTP scope branch is behaviourally inert by construction, which is recorded
        # in `middleware.py` and in accepted risk 10.
        "test_a_body_arriving_within_the_budget_is_not_timed_out",
        "test_a_body_at_the_cap_is_passed_through_intact",
        "test_a_body_method_declaring_no_body_is_not_drained_either",
        "test_a_disconnect_mid_body_reaches_the_app_and_is_not_refused",
        "test_a_method_that_carries_no_body_is_never_drained",
        "test_a_non_http_scope_is_passed_through_untouched",
        "test_a_receive_after_the_replay_falls_through_to_the_real_transport",
        "test_a_zero_budget_times_out_immediately",
        "test_an_unknown_method_is_passed_through_rather_than_drained",
        "test_one_byte_over_the_cap_is_refused_and_the_app_never_runs",
        # --- test_storage.py: cases of the anti-shrink merge, the revision guard, the
        # must-exist-inside-the-lock check, the snapshot validation behind the corrupt-snapshot
        # row, and the real-write probe. The two SESSION-cap tests were exempted here as cases of
        # "the retention cap", which is the BACKUP retention row and a different control
        # altogether; disabling `_enforce_cap` leaves the backup test green. The session cap has
        # its own row now. `test_probe_reports_an_existing_path
        # _that_is_a_file_not_a_directory` is exempted DELIBERATELY and not by oversight: the
        # register's own NOTE records that citing it for the real-write control was wrong,
        # because it never reaches the write and so kills no existence-check mutant.
        "test_a_matching_expected_revision_is_accepted",
        "test_a_must_exist_write_is_refused_when_the_id_is_absent",
        "test_a_must_exist_write_merges_when_the_id_is_present",
        "test_a_partial_update_never_deletes_an_unsent_field",
        "test_every_write_advances_the_revision",
        "test_load_returns_an_empty_snapshot_when_absent",
        "test_malformed_json_is_rejected_not_coerced",
        "test_merge_session_keeps_existing_values_absent_from_the_update",
        "test_migrate_preserves_unrecognised_fields",
        "test_probe_reports_an_existing_path_that_is_a_file_not_a_directory",
        "test_probe_writable_proves_a_usable_directory_with_a_real_write",
        "test_seed_creates_the_snapshot_and_is_idempotent",
        "test_the_write_result_counts_are_measured_inside_the_lock",
        # --- test_content_package.py. Swept, and three properties carry register rows: the
        # partial-library refusal, the malformed-file report and the frozen models. The names
        # below are correctness and provenance rather than boundary controls. Counts, hash
        # stability, the rated band and the canonical-generator guard protect the TRAINING; the
        # threshold refusal is a content decision from the flight plan, and its harm is an
        # operator shown a placeholder figure rather than a disclosure.
        "test_a_generator_outside_the_canonical_twelve_is_refused",
        "test_a_populated_local_threshold_file_unlocks_scored_scenarios",
        "test_a_scored_scenario_is_refused_while_thresholds_are_placeholders",
        "test_an_item_authored_outside_the_rated_band_is_refused",
        "test_every_shipped_drill_uses_a_canonical_generator",
        "test_the_content_hash_is_stable_and_changes_with_the_content",
        "test_the_drill_rubric_is_present_and_its_rules_carry_operator_facing_reasons",
        "test_the_package_carries_the_counts_the_handover_declares",
        "test_the_shipped_package_loads_with_no_errors",
        # --- test_generators.py. Swept, and one property carries a register row: the wire form
        # never carrying the derived expected value, which is half the answer-key boundary. The
        # rest are contract tests on the RENDERERS, read out of product-layouts.json. They
        # decide whether the trainer is as hard as the job and hold no boundary property: an
        # inverted magnitude axis is a correctness question, not a disclosure one.
        "test_a_different_seed_draws_a_different_surface",
        "test_an_unresolvable_generator_fails_closed",
        "test_every_product_the_content_references_has_a_registered_renderer",
        "test_every_shipped_drill_renders",
        "test_every_surface_carries_a_text_equivalent_of_how_it_reads",
        "test_every_surface_declares_its_axes_with_units",
        "test_the_composite_mode_renders_every_product_on_the_board",
        "test_the_contract_block_still_states_the_requirements_these_tests_check",
        "test_the_determination_table_column_order_is_initial_final_delta",
        "test_the_determination_table_marks_the_row_that_is_natural_regression",
        "test_the_neighbourhood_carries_every_observed_column",
        "test_the_neighbourhood_header_shows_the_threshold_block_and_the_filters",
        "test_the_photometry_magnitude_axis_is_inverted",
        "test_the_probe_mode_resolves_the_product_from_the_stimulus",
        "test_the_provisional_noise_figures_are_marked_as_provisional",
        "test_the_relative_motion_panels_use_independent_scales",
        "test_the_relative_motion_surface_marks_state_changes_distinctly_from_the_track",
        "test_the_residual_departs_in_the_series_the_params_name",
        "test_the_residual_scale_is_tight_and_labels_the_time_and_beta_series",
        "test_the_right_ascension_panel_is_drawn_as_a_staircase",
        "test_the_same_params_and_seed_draw_the_same_surface_every_time",
        "test_the_waterfall_is_observation_level_scatter_with_gaps",
        "test_the_waterfall_time_axis_runs_newest_at_the_bottom",
        # --- test_drill_loop.py. Swept, and two properties carry register rows: the served
        # payload carrying no answer key and no derived value, and the run record carrying its
        # content hash. The rest is loop behaviour protecting the training rather than the
        # boundary. The idempotency one is the closest call and sits here rather than in the
        # register because its harm is a rating moved twice, not a disclosure.
        "test_a_second_submission_returns_the_first_result_rather_than_rescoring",
        "test_an_unknown_run_id_is_refused",
        "test_an_unloaded_package_refuses_to_serve_rather_than_inventing_an_item",
        "test_selection_targets_the_band_just_above_the_operator",
        "test_the_dashboard_never_reports_a_bare_competency_estimate",
        "test_the_dashboard_says_identity_does_not_exist_yet",
        "test_the_manifest_reports_what_is_loaded_and_what_is_not_wired",
        "test_the_reveal_carries_everything_the_service_withheld",
        "test_the_same_operator_and_item_draw_the_same_stimulus_until_they_answer",
        "test_two_operators_on_one_item_get_different_stimuli",
        # --- test_scoring.py. Swept, and one property carries a register row: the bounded
        # answer length, which is the denial-of-service surface on a caller-controlled string.
        # The rest is scoring correctness - exact matching, tolerance, the sentinel refusal, the
        # fail-closed report of an unwired rule. All protect the SCORE rather than the system,
        # and a wrong score is a training failure rather than a security one.
        "test_a_computed_answer_with_no_generator_value_is_refused_not_guessed",
        "test_a_near_miss_is_refused_rather_than_guessed_in_the_operator_s_favour",
        "test_a_numeric_answer_is_judged_against_the_tolerance_the_content_states",
        "test_a_partial_answer_earns_the_credit_the_item_states",
        "test_a_registered_predicate_makes_a_previously_unimplemented_rule_score",
        "test_a_rule_cap_is_honoured_from_the_content",
        "test_a_rule_with_no_predicate_is_reported_rather_than_silently_scoring_zero",
        "test_an_unrecognised_answer_is_none_and_not_a_reject",
        "test_every_score_names_the_rule_and_its_award_comes_from_the_content",
        "test_normalisation_strips_at_most_two_fillers_so_it_cannot_be_made_to_loop",
        "test_the_drill_rubric_is_fully_implemented",
        "test_the_reject_list_returns_its_reason_so_a_miss_becomes_a_teachable_moment",
        "test_the_sentinel_is_never_matched_as_a_literal_string",
        "test_the_speed_bonus_needs_both_correct_and_inside_the_target",
        # --- test_progress.py. Swept, and three properties carry register rows: the file mode,
        # the capped history and the degrade-to-defaults path. The names below are the store's
        # ordinary behaviour around them: a missing file on first run, multi-operator isolation,
        # and the spacing and interval arithmetic. The interval one matters a great deal and is
        # not a security control: it stops a supervisor reading three answers as proof.
        "test_a_cue_with_no_recorded_due_date_is_due",
        "test_a_miss_returns_the_spacing_interval_to_the_front",
        "test_a_missing_progress_file_is_not_an_error",
        "test_a_perfect_small_sample_still_reports_a_non_zero_interval",
        "test_an_axis_with_no_attempts_reports_nothing_rather_than_zero",
        "test_saving_one_operator_preserves_every_other_operator",
    }
)


def test_every_exempted_security_test_still_exists() -> None:
    """An exemption naming nothing carries a written reason for nothing.

    `UNCITED_SECURITY_TESTS` had two entries matching no test anywhere -
    `test_a_token_at_the_minimum_is_` and `test_data_dir_resolution_prefers_explicit_the`, both
    truncation residue from the shrinking-prefix matcher that produced the list. They sat beside
    their real full-length names, so nothing was hidden, and nothing would have caught it either.
    The same silence would let a renamed test drift out of scope and take its exemption with it, or
    let a truncated stem exempt a future name by prefix accident.

    This mirrors `test_every_test_named_in_the_security_policy_exists`, which does exactly this job
    for the register's citations. Two lists of names, both needing a liveness check, and only one
    of them had one.
    """
    live = _all_test_names()
    dead = UNCITED_SECURITY_TESTS - live
    assert not dead, (
        "these names are exempted from the citation sweep and match no test, so their written"
        f" reasons guard nothing: {sorted(dead)}"
    )

    # An exemption for a test that EXISTS but sits outside the swept suites is never consulted, so
    # it reads as a decision while guarding nothing - the same silence in a different position.
    # Subtracting `dead` keeps the two disjoint: without it every fabricated name trips both, and
    # this second message would only ever be reachable in theory.
    swept = set()
    for suite in SWEPT_SECURITY_SUITES:
        swept |= _test_names_in(ROOT / "tests" / suite)
    stray = sorted((UNCITED_SECURITY_TESTS & live) - swept)
    assert not stray, (
        "these names are exempted but live outside the swept suites, so the exemption is never"
        f" read: {stray}"
    )

    # An exemption that has since been CITED is stale: the register now carries the control, and
    # leaving the name here would keep exempting it if the citation were ever removed.
    policy = (ROOT / "docs" / "SECURITY.md").read_text(encoding="utf-8")
    cited = set(re.findall(CITATION_TOKEN, _control_table_rows(policy)))
    redundant = sorted(UNCITED_SECURITY_TESTS & cited)
    assert not redundant, (
        "these names are BOTH cited in docs/SECURITY.md and exempted from needing a citation;"
        f" drop the exemption: {redundant}"
    )

    # And the file-granularity opt-out must still name a real, still-cited suite.
    for suite in sorted(UNSWEPT_CITED_SUITES):
        assert (ROOT / "tests" / suite).is_file(), (
            f"{suite} is exempted from the sweep but no such suite exists"
        )
        assert f"tests/{suite}" in policy, (
            f"{suite} is exempted as a file-granularity citation, but docs/SECURITY.md no longer"
            " cites it, so the opt-out narrows the sweep for no reason"
        )


def test_every_security_test_is_cited_by_the_policy() -> None:
    """The REVERSE direction, which is the gap that hid a control for several rounds.

    Its sibling below catches a register row naming a test that does not exist. Nothing caught the
    other direction, and that was not hypothetical: `X-Content-Type-Options: nosniff` was added,
    tested five ways, and left out of the register's control table entirely. The sweep is
    citation-driven, so an UNCITED control is invisible to it by construction. It took a reviewer
    reading the document to find it.

    **This check has now been defeated twice, both times by verifying less than it reported.** The
    first version matched a shrinking prefix, reduced a name to `test_an`, found that inside
    `test_anonymous_writes_require_the_explicit_opt_in`, and passed every `test_an...` as cited.
    The second matched `line.startswith("def test_")` - and 17 of the 20 tests in
    `test_middleware.py` are `async def`, so the suite whose omission motivated the whole check was
    the suite it could not see. Both gates planted an uncited async test and both watched it pass.
    My own verification had held only because I wrote the plant as `def`.

    So it walks the AST now, which sees both function kinds and survives decorators, reflowing and
    class nesting - none of which a line-prefix scan does. A completeness check is worth exactly
    what it can see, and the two things that hid from this one were a keyword and a substring.
    """
    policy = (ROOT / "docs" / "SECURITY.md").read_text(encoding="utf-8")

    # The policy's citation TOKENS, extracted once, rather than a substring search over the whole
    # document. A bare `in policy` test was the first version's other flaw: it would match a name
    # mentioned anywhere, including in the survivor prose and the mutant ledger, so one future
    # sentence naming a suite would silently exempt every test in it.
    # ONLY the control table's rows count as citations. A document-wide scan let a name in the
    # surviving-mutant prose read as a register row, and one did:
    # `test_an_honest_oversize_declaration_is_refused_without_reading_the_body` was cited nowhere
    # but a sentence about mutants. Filtering on `|` alone then let the MUTANT LEDGER's rows count,
    # which is the same hole one table along. The register's promise is "each with a test that fails
    # if it regresses", and only a row under that heading makes it.
    rows = _control_table_rows(policy)
    # The trailing lookaheads matter. `[A-Za-z0-9_]` ends the token so a name cannot match a
    # longer one's prefix, and `(?!\.py\b)` drops the FILE stems: `tests/test_auth.py` would
    # otherwise contribute a bare `test_auth` citation, and a future test named exactly `test_auth`
    # would then read as cited by a filename. The elided `test_x...` form still matches, because
    # only `.py` is excluded and not every dot.
    cited_names = set(re.findall(CITATION_TOKEN, rows))
    cited_prefixes = {name for name in cited_names if f"{name}..." in rows}

    # The claim beside CITATION_TOKEN - that widening to include capitals changes nothing on the
    # register as it stands - checked rather than asserted in prose. If a capitalised citation is
    # ever added this fails, which is the loud failure the widening exists to produce. Two were
    # briefly added in V0.24.1 and renamed instead: the project lints test names lowercase
    # (N802), and an exemption plus a second allowlist to keep two shouted words was more
    # machinery than the emphasis was worth.
    lowercase_only = set(re.findall(r"\btest_[a-z0-9_]+(?![a-z0-9_])(?!\.py\b)", rows))
    assert lowercase_only == cited_names, (
        "a citation in the control table contains a capital letter. That is now handled rather"
        " than silently truncated, but the comment beside CITATION_TOKEN says the two classes"
        f" agree on this register, and they no longer do: {sorted(cited_names - lowercase_only)}"
    )

    # Both bounds asserted against absolute literals first, so raising one cannot quietly widen
    # what the sweep accepts.
    assert MIN_ELIDED_PREFIX == 20, "the minimum elided-prefix length changed; re-measure the risk"
    assert MAX_ELIDED_RESOLUTION == 3, "the elided-prefix resolution bound changed; re-measure"
    live = _all_test_names()
    for prefix in sorted(cited_prefixes):
        assert len(prefix) >= MIN_ELIDED_PREFIX, (
            f"the elided citation {prefix!r} is {len(prefix)} characters, under the"
            f" {MIN_ELIDED_PREFIX}-character floor; a short prefix admits a whole family of tests"
            " as cited"
        )
        resolved = sorted(name for name in live if name.startswith(prefix))
        assert resolved, f"the elided citation {prefix!r} resolves to no test at all"
        assert len(resolved) <= MAX_ELIDED_RESOLUTION, (
            f"the elided citation {prefix!r} resolves to {len(resolved)} of the {len(live)} tests"
            f" in the suite, over the bound of {MAX_ELIDED_RESOLUTION}; write the names out or"
            f" narrow the prefix: {resolved}"
        )

    # A row whose control cell is empty carries a citation and promises nothing. The register's
    # heading is "Controls, each with a test that fails if it regresses"; a blank control is not
    # one.
    #
    # DECLARED LIMIT, measured not assumed: a cell holding `<!-- retired -->` passes this, and
    # so does a row whose text no longer describes what its test asserts. Both need somebody to
    # judge
    # whether prose describes a real control, which no matcher does. Stated here rather than
    # implied away, because every defeat of this sweep so far came from a comment claiming ground
    # the code did not hold.
    for row in rows.splitlines():
        cells = row.split("|")
        if len(cells) < 4:
            continue  # not a three-column row
        control = cells[1].strip()
        # The markdown separator is dashes and colons, and it is recognised by EVERY cell being
        # separator-shaped, not just the first. Two earlier versions of this guard were measured as
        # survivors: one tested `set(control) <= {"-", " "}`, and `set("")` is a subset of
        # everything, so the separator branch swallowed the empty cell it was written to catch; the
        # next skipped any row whose first cell was `---`, so a real data row could keep its
        # citation with its control gutted to a dash.
        if all(cell.strip() and set(cell.strip()) <= {"-", ":"} for cell in cells[1:-1]):
            continue
        assert control, f"a control row has an empty control cell: {row!r}"
        assert set(control) - {"-", ":"}, (
            f"a control row's control cell is separator punctuation, not a control: {row!r}"
        )

    # Every suite matching the glob is accounted for, in exactly one of three sets. The previous
    # guard derived the cited suites from `tests/(test_\w+\.py)` FILE references only, so a suite
    # the register cited by TEST NAME was neither swept nor flagged - `test_healthcheck.py` was
    # cited for the port-validation row and its twelve tests were invisible, three of them the only
    # thing killing a fail-closed branch in `healthcheck.py`. Partitioning the glob closes both
    # that and the engineering gate's separate case: a brand-new suite, cited by nothing at all.
    on_disk = {path.name for path in (ROOT / "tests").glob("test_*.py")}
    accounted = set(SWEPT_SECURITY_SUITES) | UNSWEPT_CITED_SUITES | NON_SECURITY_SUITES
    assert on_disk == accounted, (
        "every tests/test_*.py must be swept, opted out in writing, or declared to hold no"
        f" security property; unaccounted on disk: {sorted(on_disk - accounted)};"
        f" named but absent: {sorted(accounted - on_disk)}"
    )

    # And a suite declared to hold no security property must not be where a cited control lives,
    # or the declaration is simply false.
    misdeclared = sorted(
        f"{name} in {suite}"
        for name in cited_names
        if (suite := _suite_of(name)) is not None and suite in NON_SECURITY_SUITES
    )
    assert not misdeclared, (
        "docs/SECURITY.md cites a control living in a suite declared to hold no security property:"
        f" {misdeclared}"
    )

    uncited: list[str] = []
    for suite in SWEPT_SECURITY_SUITES:
        for name in _test_names_in(ROOT / "tests" / suite):
            if name in UNCITED_SECURITY_TESTS or name in cited_names:
                continue
            # The elided `test_a_thing...` form the table uses to stay narrow, matched as a real
            # prefix of a real citation rather than as any old substring.
            if any(name.startswith(prefix) for prefix in cited_prefixes):
                continue
            uncited.append(f"{suite}::{name}")

    assert not uncited, (
        "these security-property tests are cited nowhere in docs/SECURITY.md, so the register"
        " omits a control it claims to carry; cite them or name them in UNCITED_SECURITY_TESTS"
        f" with a reason: {uncited}"
    )


def test_every_test_named_in_the_security_policy_exists() -> None:
    """`docs/SECURITY.md` promises "each with a test that fails if it regresses", so a row
    pointing at a test that no longer exists cannot keep that promise.

    A rename in one commit left exactly one dangling name, found by a reviewer's sweep rather
    than by anything in the suite. This is that sweep, mechanised. Names written with a
    trailing ellipsis are deliberate abbreviations and are skipped.

    What this CANNOT see: a row whose named test exists but no longer asserts the control it
    is cited for. Mutation testing is the instrument for that, and its ledger is in the same
    document.
    """
    policy = (ROOT / "docs" / "SECURITY.md").read_text(encoding="utf-8")
    cited = {
        name
        for name in re.findall(r"`(test_[A-Za-z0-9_]+)(?:\.\.\.)?`", policy)
        if not name.endswith("_")
    }
    # An elided citation is RESOLVED BY PREFIX, not exempted. Skipping them left 12 of 63
    # cited names unchecked, so renaming one of those left the policy citing a test that no
    # longer exists with the sweep still green.
    elided = set(re.findall(r"`(test_[A-Za-z0-9_]+)\.\.\.`", policy))
    # `_all_test_names()` rather than a line scan of `^(?:async )?def test_`, which is the exact
    # technique the sibling check above withdrew. It carried the same class-nesting blind spot,
    # failing SAFE here (a cited class-nested test would read as dangling) but still measuring
    # something other than what it reported.
    defined = _all_test_names()
    dangling = sorted(
        name
        for name in cited
        if name not in defined
        and not (name in elided and any(known.startswith(name) for known in defined))
    )
    assert dangling == [], f"docs/SECURITY.md cites tests that do not exist: {dangling}"
    assert cited, "the sweep found no cited test names, so it is asserting nothing"


def test_content_is_read_through_one_boundary_and_nothing_else() -> None:
    """`_read_json` is the only place content enters the process, enforced rather than described.

    The surrogate rejection, the shape check and the JSON-pointer diagnosis all live in
    `_read_json`, and the claim that it is the ONE entry point is what makes that placement
    sufficient. Nothing enforced it: **twelve of the twenty-three files in `content/` are read by
    no code at all today**, and a future flight-plan step wiring one of them with a bare
    `json.loads` would reintroduce the whole class with the suite green.

    So this asserts the boundary structurally, the same technique as the route-table enumeration
    that holds the anonymous-body sweep: no module under `src/enlightenment/content/` may call
    `json.loads` or `Path.read_text` except inside `_read_json` itself.

    **`read_bytes` is exempt, and the reason is the property rather than convenience.** The check
    forbids the two calls that turn a content file into a Python `str` - `json.loads` and
    `read_text` - because a lone surrogate can only exist in a `str`. `ContentPackage._hash` reads
    raw BYTES for a digest and never decodes them, so no string is produced and nothing can carry
    a surrogate; the first version of this test forbade `read_bytes` too and found that reader
    immediately, which is the check working and the exemption being reasoned rather than assumed.

    DECLARED LIMIT: this holds the content package's own modules. A reader elsewhere in the source
    could still open a content file directly, and no matcher catches that without hard-coding a
    list of paths nobody maintains. The check is scoped in writing rather than quietly, because
    every defeat of a sweep in this project has come from a claim wider than the code.
    """
    boundary = ROOT / "src" / "enlightenment" / "content"
    offenders: list[str] = []
    for path in sorted(boundary.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name == "_read_json":
                continue
            for inner in ast.walk(node):
                if not isinstance(inner, ast.Call):
                    continue
                target = inner.func
                name = (
                    target.attr
                    if isinstance(target, ast.Attribute)
                    else target.id
                    if isinstance(target, ast.Name)
                    else ""
                )
                if name in {"loads", "read_text"}:
                    offenders.append(f"{path.name}::{node.name} calls {name}()")
    assert offenders == [], (
        "content is read outside `_read_json`, so the surrogate rejection and the shape check no"
        f" longer sit on the one boundary they claim to: {offenders}"
    )


def test_every_control_row_splits_into_the_header_s_columns() -> None:
    """A stray `|` in a control's prose splits its row into more cells than the header declares,
    and every check that reads the table by cell INDEX then reads the wrong cell.

    Measured: the shortened-identifier row carried five pipes against a three-column header from
    `4045e52` to `9db2c42`, six consecutive commits, and nothing failed. The sibling row-shape
    guard skips on `len(cells) < 4`, a floor rather than an equality, so a row with an EXTRA
    column passes it. The cost is not hypothetical: the stray pipe cut that row's control cell in
    half, so measuring the cell by index returned 1,126 characters for a 4,872-character row.

    The header's own width is read from the table and also asserted against a literal, so
    widening the register is a deliberate two-line edit rather than something a stray character
    can do.
    """
    policy = (ROOT / "docs" / "SECURITY.md").read_text(encoding="utf-8")
    rows = _control_table_rows(policy).splitlines()
    cells_per_row = len(rows[0].split("|"))
    assert cells_per_row == 5, (
        "the control table header no longer declares exactly three columns, so the checks that"
        f" index its cells need re-reading before this literal is raised: {rows[0]!r}"
    )
    misshapen = [row for row in rows if len(row.split("|")) != cells_per_row]
    assert misshapen == [], (
        f"these control-table rows do not split into the header's {cells_per_row - 2} columns, so"
        " a check reading a cell by index reads the wrong cell there; a literal pipe inside a"
        f" control's prose has to be escaped: {[row[:120] for row in misshapen]}"
    )


# --- the verified-edit helper is itself executed --------------------------------------


def _run_verified_edit(tmp_path: Path, body: str, anchor: str, replacement: str) -> int:
    target = tmp_path / "target.txt"
    target.write_text(body, encoding="utf-8")
    anchor_file = tmp_path / "anchor.txt"
    anchor_file.write_text(anchor, encoding="utf-8")
    replacement_file = tmp_path / "replacement.txt"
    replacement_file.write_text(replacement, encoding="utf-8")
    result = subprocess.run(  # noqa: S603 - a resolved interpreter and a fixed, in-repo script
        [
            sys.executable,
            str(ROOT / "scripts" / "verified-edit.py"),
            str(target),
            str(anchor_file),
            str(replacement_file),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return result.returncode


def test_the_edit_helper_applies_a_matching_anchor(tmp_path: Path) -> None:
    assert _run_verified_edit(tmp_path, "alpha bravo charlie", "bravo", "delta") == 0
    assert (tmp_path / "target.txt").read_text(encoding="utf-8") == "alpha delta charlie"


def test_the_edit_helper_refuses_a_missing_anchor(tmp_path: Path) -> None:
    """The exact failure that let a changelog certify a docstring correction never applied."""
    assert _run_verified_edit(tmp_path, "alpha bravo", "not-here", "delta") == 3
    assert (tmp_path / "target.txt").read_text(encoding="utf-8") == "alpha bravo"


def test_the_edit_helper_refuses_an_ambiguous_anchor(tmp_path: Path) -> None:
    """Two matches means the edit would be arbitrary, so it is refused rather than guessed."""
    assert _run_verified_edit(tmp_path, "bravo and bravo", "bravo", "delta") == 3
    assert (tmp_path / "target.txt").read_text(encoding="utf-8") == "bravo and bravo"


def test_the_edit_helper_refuses_when_the_anchor_survives_the_write(tmp_path: Path) -> None:
    """A replacement that still contains the anchor leaves the file unchanged in substance."""
    assert _run_verified_edit(tmp_path, "aabb", "ab", "") == 4


def test_the_edit_helper_reports_misuse(tmp_path: Path) -> None:
    result = subprocess.run(  # noqa: S603 - a resolved interpreter and a fixed, in-repo script
        [sys.executable, str(ROOT / "scripts" / "verified-edit.py")],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 2


def test_the_edit_helper_refuses_a_symlinked_target(tmp_path: Path) -> None:
    """`Path.write_text` follows a symlink, so a symlinked target would write OUTSIDE the named
    directory. The same reasoning puts `O_NOFOLLOW` on every file this project's store opens.
    """
    outside = tmp_path / "outside.txt"
    outside.write_text("untouched", encoding="utf-8")
    link = tmp_path / "target.txt"
    link.symlink_to(outside)
    anchor = tmp_path / "anchor.txt"
    anchor.write_text("untouched", encoding="utf-8")
    replacement = tmp_path / "replacement.txt"
    replacement.write_text("overwritten", encoding="utf-8")
    result = subprocess.run(  # noqa: S603 - a resolved interpreter and a fixed, in-repo script
        [
            sys.executable,
            str(ROOT / "scripts" / "verified-edit.py"),
            str(link),
            str(anchor),
            str(replacement),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 3
    assert outside.read_text(encoding="utf-8") == "untouched", "the tool wrote through a symlink"


def test_the_edit_helper_leaves_the_file_untouched_when_it_refuses(tmp_path: Path) -> None:
    """A caller treating a non-zero exit as "nothing happened" must be right.

    The earlier version wrote first and verified afterwards, so this refusal left the file
    half-edited: the inverse of what the tool exists to prevent. Asserting only the exit code
    did not catch it.
    """
    assert _run_verified_edit(tmp_path, "aabb", "ab", "") == 4
    assert (tmp_path / "target.txt").read_text(encoding="utf-8") == "aabb"


def test_the_edit_helper_reports_an_unreadable_target(tmp_path: Path) -> None:
    """A directory, a missing file or non-UTF-8 bytes exit with a documented code, not a raw
    traceback outside the codes the docstring promises.
    """
    anchor = tmp_path / "anchor.txt"
    anchor.write_text("x", encoding="utf-8")
    replacement = tmp_path / "replacement.txt"
    replacement.write_text("y", encoding="utf-8")
    binary = tmp_path / "binary.bin"
    binary.write_bytes(b"\xff\xfe\x00\x01")
    for target in (tmp_path / "missing.txt", tmp_path, binary):
        result = subprocess.run(  # noqa: S603 - a resolved interpreter and a fixed script
            [
                sys.executable,
                str(ROOT / "scripts" / "verified-edit.py"),
                str(target),
                str(anchor),
                str(replacement),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert result.returncode == 5, f"{target} gave {result.returncode}: {result.stderr[-200:]}"
        assert "Traceback" not in result.stderr


def test_the_binding_image_job_can_actually_fire_on_a_release_branch() -> None:
    """A binding check that cannot fire is not a check.

    The `image` job is the ONLY thing that can build the container, because the authoring
    environment's network policy denies the registry blob endpoint. Three documents call it the
    binding check for container hardening. It triggered only from `main`, so on a release branch
    it had never run once, and the container had never been built by anything, anywhere. The
    deploy gate caught that by querying the repository rather than by reading the file.

    Asserted over the workflow's executable lines rather than a parsed document, because
    parsing YAML would mean adding a dependency for one assertion. What this CANNOT see: a
    trigger present but overridden elsewhere, or a job-level `if` that skips the job. What
    settles it for real is the job having actually run, which the deploy gate checks by
    querying the repository.
    """
    lines = _ci_instructions()
    release_branch = any("claude/" in line for line in lines)
    dispatch = any(line.strip().startswith("workflow_dispatch") for line in lines)
    assert release_branch or dispatch, (
        "the image job cannot fire on a release branch: add a release-branch push trigger "
        "or workflow_dispatch"
    )


def _ci_step_containing(needle: str, window: int = 6) -> str:
    """The `docker run` invocation whose command contains ``needle``.

    Binding a marker to its OWN step is the point. Matching the marker anywhere in the file let
    each of these checks be deleted with the suite green: the OS-package step could be replaced
    by an `echo` mentioning the marker, the bundled-wheel scan by an `echo` naming it, and
    `dpkg` in the tool list was satisfied by the unrelated `/var/lib/dpkg/status` line
    elsewhere. That is instances sixteen to eighteen of the assert-the-prose class in this file
    alone, which is why the index-window technique is used here as it already is for the suid
    sweep rather than reinvented per test.
    """
    lines = _ci_instructions()
    for index, line in enumerate(lines):
        if needle not in line:
            continue
        # Spans BOTH directions: the `docker run` invocation sits above the needle and the
        # command body continues below it, so a backward-only window missed half the step.
        block = lines[max(0, index - window) : index + window + 1]
        joined = " ".join(block)
        if "docker run" in joined:
            return joined
    return ""


@pytest.mark.parametrize(
    ("needle", "must_contain", "why"),
    [
        (
            '-name "*.whl"',
            "find /",
            "a bundled package-manager wheel is on no PATH but IS reported by CVE scanners; "
            "this scan is what found the shipped pip-25.0.1 wheel on the first ever build",
        ),
        (
            "ensurepip",
            "find /",
            "the bundled installer directory ships the same payload",
        ),
        (
            'grep -c "^Package: "',
            "/var/lib/dpkg/status",
            "the OS package inventory must be read from the retained database",
        ),
    ],
)
def test_the_image_job_checks_what_only_a_built_image_can_show(
    needle: str, must_contain: str, why: str
) -> None:
    """These can only be settled against a built filesystem, so they live in CI.

    Each marker is bound to the `docker run` step that must carry it, so replacing the step
    with an `echo` that merely mentions the marker fails.
    """
    step = _ci_step_containing(needle)
    assert step, f"no docker run step carries {needle}: {why}"
    assert must_contain in step, f"the step carrying {needle} does not run against {must_contain}"


@pytest.mark.parametrize("tool", ["pip", "pip3", "apt", "apt-get", "dpkg", "dpkg-deb", "aptitude"])
def test_the_package_manager_loop_covers_each_tool(tool: str) -> None:
    """Parsed from the loop's own word list, not matched anywhere in the file.

    `dpkg` used to be satisfied by the unrelated `/var/lib/dpkg/status` line elsewhere in the
    job, so deleting it from the tool list left the suite green.
    """
    step = _ci_step_containing("for tool in")
    assert step, "the package-manager loop is missing from the image job"
    listed = re.search(r"for tool in ([^;]+);", step)
    assert listed, f"cannot parse the tool list from: {step[:160]}"
    tools = listed.group(1).split()
    assert tool in tools, f"{tool} is not in the loop's tool list {tools}"


def test_the_bundled_pip_wheel_is_removed_from_the_runtime() -> None:
    """`ensurepip` vendors a complete pip wheel that no PATH check can see.

    `command -v pip` reports nothing for it, so the package-manager check passed while
    `pip-25.0.1-py3-none-any.whl` shipped in the image and a filesystem CVE scanner would
    report it as a present package. The CI image job caught it on its first ever run.

    Asserted here as well as in CI so a local run catches a regression at the cheapest rung,
    and because the CI job is the only thing that can see the built filesystem.
    """
    sweep = DOCKER_INSTRUCTIONS.split("FROM scratch")[0]
    assert "ensurepip" in sweep, "the bundled pip wheel is not removed from the runtime stage"


def test_the_edit_helper_preserves_the_targets_mode(tmp_path: Path) -> None:
    """A scripted edit must not silently change a file's mode.

    `mkstemp` creates 0600, so without an explicit chmod an edit to any of this repository's
    mode-755 scripts stripped the executable bit and put an unrequested change in the diff.
    """
    # _run_verified_edit writes to target.txt, so chmod THAT file. An earlier version created
    # target.sh, chmodded it, and then asserted on a file the helper never touched: the test
    # passed whether or not the mode was preserved.
    target = tmp_path / "target.txt"
    target.write_text("alpha bravo", encoding="utf-8")
    target.chmod(0o755)
    assert _run_verified_edit(tmp_path, "alpha bravo", "bravo", "delta") == 0
    assert target.read_text(encoding="utf-8") == "alpha delta"
    assert target.stat().st_mode & 0o777 == 0o755, "the edit changed the target's mode"


def test_packaging_needs_only_the_interpreter() -> None:
    """The platform runs this suite in ITS environment, so a contract test that shells out to a
    tool the runner may not have fails the test stage and skips quality, container build and
    deploy, with the diagnosis pointing at packaging rather than at the missing tool.

    `zip` is not part of a stock Python image, so the archive is built with `zipfile`.
    """
    packaging = "\n".join(_live_lines(ROOT / "scripts" / "package-appstore.sh"))
    assert "zipfile" in packaging, "packaging does not build the archive with the interpreter"
    assert not re.search(r"(^|\s)zip\s+-", packaging), (
        "packaging still shells out to the zip binary"
    )


def test_the_changelog_carries_a_row_for_the_version_being_shipped() -> None:
    """One audit row per change is a project rule, and the deploy gate reads this document.

    V0.10 shipped with the newest row still reading V0.9, so the record the gate reads described
    a state three commits stale and still said the container image was unverified after two
    commits had changed exactly that. The version-parity test did not cover the changelog, so
    this closes the same gap for the record rather than only for the code.

    **The FULL version, not major.minor. Corrected at V0.26.6 after the engineering gate defeated
    this two ways.** The assertion read `f"## V{major_minor} "`, so it looked for `## V0.26 ` and
    was satisfied by any V0.26.x heading already in the file: renaming the newest heading to
    `## V0.27.9`, and suffixing it to `## V0.26.55`, both left the suite green. A PATCH release
    with no audit row therefore shipped green, while `CLAUDE.md` claimed six tests bind this
    document "so a missed site fails the loop rather than shipping". That claim was false for the
    only release cadence this project actually uses: every change bumps the patch.

    The major.minor form was not a shortcut, it was a mistake about what varies. This project bumps
    the patch on every change by owner decision, so major.minor is exactly the component that does
    NOT identify a build.
    """
    version = _pyproject()["project"]["version"]
    changelog = (ROOT / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")
    heading = f"## V{version} "
    assert heading in changelog, (
        f"docs/CHANGELOG.md has no audit row for V{version}; newest headings are "
        f"{re.findall(r'^## (V[0-9.]+)', changelog, re.MULTILINE)[:3]}"
    )


#: Commands a script the SUITE EXECUTES may rely on. Deliberately tiny.
PORTABLE_COMMANDS = frozenset(
    {
        "python3",  # guaranteed: it is what runs this suite
        "cd",
        "set",
        "printf",
        "echo",
        "test",
        "rm",
        "mkdir",
        "cp",
        "for",
        "do",
        "done",
        "if",
        "then",
        "fi",
        "else",
        "exit",
        "true",
        "false",
        "read",
        "shift",
        "local",
        "return",
        "case",
        "esac",
        "while",
        "basename",
        "dirname",
        "find",
    }
)

#: External tools that are NOT in a stock `python:3.12-slim` image, so a script the suite
#: executes must never rely on one. `unzip` is the instance that failed a real upload.
NOT_IN_A_STOCK_PYTHON_IMAGE = ("unzip", "zip", "jq", "curl", "wget", "docker", "git")


@pytest.mark.parametrize("tool", NOT_IN_A_STOCK_PYTHON_IMAGE)
def test_the_packaging_script_shells_out_to_nothing_but_python(tool: str) -> None:
    """The class, not the instance.

    A contract test EXECUTES `package-appstore.sh`, and the platform runs this suite in ITS
    environment. A stock `python:3.12-slim` image has no `zip` and no `unzip`. The first fix
    removed `zip` and left `unzip`, `tar` and `sha256sum` behind, and the upload failed at the
    Test stage with Quality, Container Build and Container Scan all skipped: four of eight
    stages passed, and the reported diagnosis was "tests failed", which points at the tests
    rather than at an absent binary.

    So this asserts the RULE rather than chasing tools one at a time. `python3` does everything
    the script needs: `shutil.copytree` for the copy, `zipfile` for the archive and the listing,
    `hashlib` for the digest.
    """
    script = "\n".join(_live_lines(ROOT / "scripts" / "package-appstore.sh"))
    # Word-boundary match, so `zipfile` and `.gitignore` do not read as `zip` and `git`.
    assert not re.search(rf"(?<![\w.-]){re.escape(tool)}(?![\w.-])", script), (
        f"packaging invokes `{tool}`, which is not in a stock python image; use python3"
    )


def test_no_script_the_suite_executes_needs_an_unusual_tool() -> None:
    """Same rule, swept across every script a test actually runs, so a new one inherits it.

    What this CANNOT see: a tool invoked from inside a python block, or one reached through a
    variable. It catches the plain-command case, which is the one that has actually bitten.
    """
    executed = ["package-appstore.sh"]  # build-image.sh legitimately needs `docker`, stubbed
    offenders = [
        f"{name} invokes {tool}"
        for name in executed
        for tool in NOT_IN_A_STOCK_PYTHON_IMAGE
        if re.search(
            rf"(?<![\w.-]){re.escape(tool)}(?![\w.-])",
            "\n".join(_live_lines(ROOT / "scripts" / name)),
        )
    ]
    assert offenders == [], f"a script the suite executes needs an unusual tool: {offenders}"


# --- the requirements contract that a real upload failure taught us ---------------------


def test_the_file_the_platform_installs_carries_the_test_runner() -> None:
    """THE assertion this project did not have, and a real upload paid for.

    The App Store's generated pipeline runs, in the test stage:

        pip install -r requirements.txt
        pytest --cov --cov-report=xml:coverage.xml

    It installs ONE file and it does not know about a dev file. The pipeline is GENERATED, so
    it cannot be edited to add a second install line. With a runtime-only requirements.txt the
    stage died on `pytest: command not found`, exit 127, and Code Quality, Container Build and
    Container Scan were all skipped: four of eight stages passed.

    The flight plan states this contract explicitly ("requirements.txt carries all test
    tooling, requirements-runtime.txt stays lean"). It was read, noted as the inverse of the
    layout in place, and deferred. Hence a test rather than a note.
    """
    installed = "\n".join(_live_lines(ROOT / "requirements.txt"))
    for needed in ("pytest==", "pytest-cov==", "coverage=="):
        assert needed in installed, (
            f"requirements.txt does not pin {needed.rstrip('=')}, so the platform's test stage "
            "will fail with `pytest: command not found`"
        )


def test_the_image_installs_the_lean_file_not_the_test_one() -> None:
    """The other half of the contract. The image must not ship the test tooling.

    If the Dockerfile installed requirements.txt it would work, which is the trap: the
    container would carry pytest, coverage and httpx, adding CVE surface the runtime never
    executes, and the container scan judges what SHIPS.
    """
    assert "requirements-runtime.txt" in DOCKER_INSTRUCTIONS, (
        "the image does not install the lean requirements file"
    )
    install_lines = [
        line
        for line in DOCKER_INSTRUCTIONS.splitlines()
        if "pip install" in line and "requirements" in line
    ]
    assert install_lines, "the image has no requirements install line"
    for line in install_lines:
        assert "requirements-runtime.txt" in line, f"the image installs the wrong file: {line}"
        assert "--require-hashes" in line, f"the image install is not hash-locked: {line}"


@pytest.mark.parametrize("tool", ["pytest", "pytest-cov", "coverage", "httpx", "hypothesis"])
def test_no_test_tooling_reaches_the_runtime_image(tool: str) -> None:
    """The lean file stays lean, asserted per tool so one slipping in is caught by name."""
    lean = "\n".join(_live_lines(ROOT / "requirements-runtime.txt"))
    assert f"{tool}==" not in lean, f"{tool} is pinned in the runtime image's requirements"


def test_the_simulation_installs_exactly_what_the_platform_installs() -> None:
    """The simulation must not be more generous than the platform.

    It installed BOTH requirements files, so it went green while the real Test stage failed on
    a missing pytest. A simulation that helps the code along proves nothing about the platform.
    """
    simulation = "\n".join(_live_lines(ROOT / "scripts" / "simulate-pipeline.sh"))
    installs = [line for line in simulation.splitlines() if "pip" in line and "install" in line]
    assert installs, "the simulation installs nothing"
    for line in installs:
        assert "requirements-dev.txt" not in line, (
            f"the simulation installs the dev file, which the platform does not: {line}"
        )


def test_every_lock_file_is_audited_by_the_loop() -> None:
    """Three lock files now exist, so all three must be scanned. The runtime one is the
    only one that ships, and it would be the easy one to forget."""
    verify = "\n".join(_live_lines(ROOT / "scripts" / "verify.sh"))
    for lockfile in ("requirements.txt", "requirements-dev.txt", "requirements-runtime.txt"):
        assert f"audit_lockfile {lockfile}" in verify, f"{lockfile} is never audited"


@pytest.mark.parametrize(
    "lockfile", ["requirements.txt", "requirements-dev.txt", "requirements-runtime.txt"]
)
def test_the_artefact_carries_every_requirements_file(lockfile: str) -> None:
    """The platform installs from the uploaded tree, so a missing lock file is a dead stage."""
    packaging = "\n".join(_live_lines(ROOT / "scripts" / "package-appstore.sh"))
    assert lockfile in packaging, f"{lockfile} is not packaged into the artefact"


# --- the loop must run the LOCKED toolchain, not whatever PATH holds ----------------------
#
# This block exists because the loop was found running an unpinned toolchain. `verify.sh`
# invoked `ruff`, `mypy`, `pytest` and `pip-audit` by bare name, so PATH decided the
# versions. On the machine where it surfaced, PATH held ruff 0.15.8 against a pinned 0.16.3,
# mypy 1.19.1 against a pinned 2.3.1, and a `pytest` inside an isolated tool environment that
# could not import the application's own dependencies. It showed up as a FALSE FAILURE, which
# is the lucky direction; the same gap yields a false pass just as readily. Every claim in
# this repository rests on the loop's verdict, so the loop's own inputs are now asserted.

#: The tool names that must never appear as a bare command in the loop.
UNPINNED_TOOL_NAMES = ("ruff", "mypy", "pytest", "pip-audit", "pip_audit", "pip")


def test_the_loop_never_invokes_a_tool_by_bare_name() -> None:
    """A bare tool name lets PATH choose the analyser version. That is the whole defect."""
    for line in _live_lines(ROOT / "scripts" / "verify.sh"):
        first = line.strip().split(" ", 1)[0]
        assert first not in UNPINNED_TOOL_NAMES, (
            f"verify.sh invokes {first} by bare name, so PATH picks the version: {line.strip()}"
        )


def test_the_loop_routes_every_tool_through_one_resolved_interpreter() -> None:
    """`python -m <tool>` is what guarantees the analyser and the code share an environment."""
    verify = "\n".join(_live_lines(ROOT / "scripts" / "verify.sh"))
    for module in ("ruff format", "ruff check", "mypy", "pytest", "pip_audit"):
        assert f'"$PY" -m {module}' in verify, f"{module} is not run through the resolved $PY"


def test_the_environment_check_is_the_first_leg_of_the_loop() -> None:
    """Ordering is the point: a mismatch means every later leg measures the wrong thing.

    Asserted as "before the first analyser", not as a line number, so reordering the analyser
    legs stays free while moving the environment check after one of them does not.
    """
    lines = _live_lines(ROOT / "scripts" / "verify.sh")
    check_at = next(i for i, line in enumerate(lines) if "check-environment.py" in line)
    first_analyser = next(i for i, line in enumerate(lines) if '"$PY" -m ruff' in line)
    assert check_at < first_analyser, "the environment check must run before any analyser"


def test_the_environment_check_covers_every_lock_file() -> None:
    """All three, including the lean file the container image installs.

    Reads the LOGICAL line, following backslash continuations, because the invocation spans
    two physical lines. A guard that reads only the first line of a wrapped command is a guard
    that passes when the arguments it checks for have moved to the second.
    """
    lines = _live_lines(ROOT / "scripts" / "verify.sh")
    start = next(i for i, line in enumerate(lines) if "check-environment.py" in line)
    invocation = lines[start]
    while invocation.rstrip().endswith("\\") and start + 1 < len(lines):
        start += 1
        invocation = invocation.rstrip().removesuffix("\\") + " " + lines[start]
    for lockfile in ("requirements-runtime.txt", "requirements.txt", "requirements-dev.txt"):
        assert lockfile in invocation, f"{lockfile} is not checked against the environment"


def _run_environment_check(pins: str) -> subprocess.CompletedProcess[str]:
    """Run `check-environment.py` against a synthetic lock file holding exactly ``pins``.

    Synthetic on purpose. Pointing these tests at the real `requirements.txt` would couple the
    platform's test stage to the platform's install fidelity: any divergence between what the
    runner installed and what the file pins would fail the SUITE rather than reporting a
    mismatch, and a self-inflicted pipeline failure is precisely the fault that broke the last
    upload. The behaviour under test is the script's, so the input is the script's alone.
    """
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as handle:
        handle.write(pins)
        forged = handle.name
    try:
        return subprocess.run(  # noqa: S603 - a resolved interpreter and a fixed, in-repo script
            [
                sys.executable,
                str(ROOT / "scripts" / "check-environment.py"),
                sys.executable,
                forged,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        Path(forged).unlink()


def test_the_environment_check_fails_on_a_missing_distribution() -> None:
    """Executed, not grepped. A pin that cannot possibly be installed must exit non-zero."""
    result = _run_environment_check("this-distribution-does-not-exist==9.9.9\n")
    assert result.returncode != 0, "a missing distribution was reported as a match"
    assert "NOT INSTALLED" in result.stderr


def test_the_environment_check_fails_on_a_version_mismatch() -> None:
    """The other half of the defect, and the half that produced the false failure.

    A distribution that IS installed but at the wrong version is the case that let the loop
    run ruff 0.15.8 against a pinned 0.16.3. A check that only noticed absence would have
    missed it entirely.
    """
    result = _run_environment_check(f"pytest==0.0.0.not-{installed_version('pytest')}\n")
    assert result.returncode != 0, "a wrong version was reported as a match"
    assert "installed" in result.stderr


def test_the_environment_check_passes_when_the_pin_matches() -> None:
    """The control for the two tests above, and it has to be here.

    Without it a script that exited non-zero unconditionally would satisfy both negative tests
    and block every run, which is a different way of verifying nothing. The pin is read from
    the running environment, so this holds on any runner.
    """
    result = _run_environment_check(f"pytest=={installed_version('pytest')}\n")
    assert result.returncode == 0, f"a matching pin was reported as a mismatch: {result.stderr}"
    assert "1 pins checked, all match" in result.stdout


def test_the_environment_check_refuses_a_lock_file_with_no_pins() -> None:
    """An empty or malformed lock file must not read as "nothing to check, therefore fine"."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as handle:
        handle.write("# only a comment\n")
        empty = handle.name
    try:
        result = subprocess.run(  # noqa: S603 - a resolved interpreter and a fixed, in-repo script
            [sys.executable, str(ROOT / "scripts" / "check-environment.py"), sys.executable, empty],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0
        assert "no pins at all" in result.stderr
    finally:
        Path(empty).unlink()


def test_the_lean_lock_file_is_a_version_identical_subset_of_the_installed_one() -> None:
    """The image installs `requirements-runtime.txt`; the platform installs `requirements.txt`.

    If a shared pin ever diverged between them, the container would ship a version that the
    analysed and tested environment never contained. That is this release's own defect one
    level up: a verdict measured against something other than what runs.

    Asserted as an invariant rather than left to leg one of the loop, because the loop only
    catches it when both files' pins happen to be installed in the same environment.
    """
    lean = _pins_of(ROOT / "requirements-runtime.txt")
    full = _pins_of(ROOT / "requirements.txt")
    assert lean, "the lean lock file holds no pins at all"
    missing = sorted(name for name in lean if name not in full)
    assert not missing, f"pinned in the image but not in the tested file: {missing}"
    diverged = {name: (lean[name], full[name]) for name in lean if lean[name] != full[name]}
    assert not diverged, f"the image and the tested environment disagree: {diverged}"


def test_no_tracked_file_trips_this_repositorys_own_secret_scan() -> None:
    """Run the pre-write hook over every tracked file, because twice it was an undertaking.

    Secret Detection is the FIRST of the App Store's eight pipeline stages, so a shape that trips a
    scanner is a deployment problem before it is anything else. Twice I asserted in a commit message
    that "nothing matches at rest" and twice a reviewer disproved it by running the hook - once on
    literal AWS and platform-token shapes I had written into fixtures, and once after "fixing" them
    by concatenation, which does not help when the rule matches a variable NAME followed by any
    quoted run of eight or more characters.

    A claim a reviewer has to check is a claim that will be wrong again. This asserts it.

    Nothing in this repository is a live credential and the hook cannot know that, which is the
    point: its job is to refuse shapes, and a suite that ships shapes teaches people to ignore it.

    Skipped rather than failed if `node` is absent, because the hook is JavaScript and the platform
    runner is a Python image. The deferral is named so it cannot read as a pass.
    """
    hook = ROOT / ".claude" / "hooks" / "secret-scan.mjs"
    if not hook.is_file():
        pytest.skip(f"no secret-scan hook at {hook}, so there is nothing to assert")
    if shutil.which("node") is None:
        pytest.skip("node is absent, so the JavaScript hook cannot run here; CI covers it")

    tracked = subprocess.run(  # noqa: S603 - a fixed argument vector, no shell
        [_git_or_skip(), "-C", str(ROOT), "ls-files", "-z"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split("\0")

    blocked: list[str] = []
    for name in (entry for entry in tracked if entry):
        path = ROOT / name
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        result = subprocess.run(  # noqa: S603 - node and a fixed, in-repo script
            ["node", str(hook)],  # noqa: S607
            input=json.dumps({"tool_input": {"file_path": name, "content": content}}),
            capture_output=True,
            text=True,
            check=False,
        )
        # The EXIT CODE, not a substring. Keying on "BLOCKED" means a hook that crashes, or whose
        # own JSON parse falls through to `process.exit(0)`, reports a silent green - a scan test
        # that cannot tell "clean" from "did not run" is the shape this suite keeps finding.
        if result.returncode != 0:
            # Gated on the marker being PRESENT. The `or exit N` fallback was dead for the case it
            # was written for: a crashing hook emits a stack trace, and splitting that on
            # "matches:" returns a truthy fragment of the trace, so the exit code never printed.
            # A fallback that cannot fire is the same shape as an assertion that cannot fail.
            output = result.stdout + result.stderr
            if "matches:" in output:
                reason = output.split("matches:")[-1].split(".")[0].strip()
            else:
                reason = f"exit {result.returncode}, hook did not report a match"
            blocked.append(f"{name} ({reason})")

    assert not blocked, (
        "these tracked files trip this repository's own secret-scan hook, which is the same class"
        f" of rule the App Store's first pipeline stage runs: {blocked}"
    )


def _credential_shape(repeats: int = 1) -> str:
    """Build a credential-SHAPED string without any credential-shaped literal in the source.

    **Why this exists, because the obvious fix did not work.** These fixtures are needles for the
    echo tests: nothing here is a live credential, and two of the shapes they imitate are published
    documentation placeholders. But this repository's own pre-write hook, and gitleaks' rules in the
    App Store's Secret Detection stage - the FIRST of its eight - match on shape alone. A scan gate
    that cries wolf is a gate people learn to wave through, and this is a defence project.

    The first attempt assembled the literals by concatenation. That failed, and the reason is worth
    recording: the hook's "Generic API key assignment" rule matches a variable NAME containing
    `token`, `secret`, `key`, `password` and so on, followed by any quoted run of eight or more
    characters. Concatenation does not help when the variable is called `token`. What helps is
    naming nothing after a credential and keeping every quoted fragment short.

    So: no fragment here reaches eight characters, no name carries a scanner keyword, and
    `test_no_tracked_file_trips_this_repositorys_own_secret_scan` asserts the result rather than
    trusting it - which is the part the two previous attempts were missing.
    """
    prefix = "g" + "h" + "p" + "_"
    body = ("S3CRET" + "LIVE" + "TOKEN") * repeats
    return (
        prefix
        + body
        + ("0123" + "4567" + "89ab" + "cdef" + "ghij" + "klmn" + "op") * (1 if repeats == 1 else 0)
    )


#: The at-sign, out of a literal, so no source line here carries a `user:pass@host` shape.
AT = chr(64)


def _userinfo_url(
    user: str = "alice",
    *,
    secret: str | None = None,
    host: str = "example.invalid",
    path: str = "/pkg.whl",
) -> str:
    """Build a `scheme://user:pass@host/path` URL with no such literal anywhere in the source.

    Sibling of `_credential_shape`, and it exists for a measured reason rather than a cautious one.
    Six of these were written as plain literals - `example.invalid` hosts, obviously fake passwords,
    pure test vectors for the credential-echo controls - and the App Store's Secret Detection stage
    flagged all six as "Password in URL", plus one in a source comment and five more quoted in the
    changelog. Twelve findings, zero real credentials, and a stage-1 failure means zero stages run.

    The scanner is right to flag them: it matches the SHAPE, and a shape is all it can see. A gate
    that has to distinguish a real credential from a convincing fake is a gate that cannot work.

    Same discipline as `_credential_shape`: no fragment reaches eight characters, nothing is named
    after a scanner keyword, and the `@` is `chr(64)` so no literal in this file contains a colon
    pair followed by an at-sign. The tests assert the assembled value, so they exercise exactly the
    strings they did before.
    """
    at = chr(64)
    body = secret if secret is not None else "s3" + "cr3t-" + "tok" + "en"
    return "https://" + user + ":" + body + at + host + path


def _environment_check_module() -> Any:
    """Import `scripts/check-environment.py` as a module so its functions can be called directly.

    A hyphen in the filename means it cannot be imported by name.

    The rationale here originally argued that a subprocess-only property test would cost 116
    process launches. That argument is obsolete: the property test DOES run end to end through
    `main()` now, and pays exactly that cost, because a direct call proved nothing about whether a
    guard was wired - `describe_name` could be deleted from both of its call sites with the suite
    staying green. Direct calls are kept for the unit-level cases that pin a function's own
    behaviour, and the property is asserted through the real script.
    """
    spec = importlib.util.spec_from_file_location(
        "enlightenment_check_environment", ROOT / "scripts" / "check-environment.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pins_of(lockfile: Path) -> dict[str, str]:
    """Read `name==version` pins, reusing the loop's own parser so the two cannot disagree.

    Imported rather than reimplemented: a second copy of the parsing rules is a second thing
    to keep in step, and a guard that parses differently from the checker it guards is worse
    than no guard.
    """
    pins: dict[str, str] = _environment_check_module().read_pins(lockfile)
    return pins


def test_the_environment_check_reports_an_unreadable_pin_line_rather_than_skipping_it() -> None:
    """The fail-OPEN branch the security and engineering gates both landed on.

    `uvicorn[standard]==9.9.9` did not match the pin pattern, so it was skipped in silence and
    the run printed "all match" with an unmet pin sitting in the file. The extras form is the
    ordinary way to pin uvicorn, so this was never hypothetical. Now the extras form parses,
    and anything that still does not parse is reported by file and line.
    """
    result = _run_environment_check("this is not a requirement line at all\n")
    assert result.returncode != 0
    assert "could not be read" in result.stderr


def test_the_line_numbers_in_a_report_count_only_real_line_terminators() -> None:
    """`requirement_lines` splits on one terminator, and nothing asserted why.

    Its live reason is the diagnosis: every report prints `lockfile:number`, and `str.splitlines()`
    also breaks on the vertical tab, form feed, the file and group separators, NEL and the Unicode
    line and paragraph separators. A line containing one of those would be counted as two, so an
    operator sent to line 3 would find the fault at line 2 - and a line number that is off by one
    is worse than none, because it is believed.

    Swapping `split("\n")` for `str.splitlines()` left the whole suite green, which is why this
    exists. No disclosure follows either way now that every echo site describes rather than echoes;
    what breaks is the only thing those reports still carry.
    """
    body = "fastapi==0.115.0\nbroken \x0b line here\nalso-broken==\n"
    result = _run_environment_check(body)
    assert result.returncode != 0
    assert ":2:" in result.stderr, (
        "the line carrying a vertical tab must be reported as line 2; if it reads 3, the splitter"
        " is counting a non-terminator as a line break and every number after it is wrong"
    )
    assert ":3:" in result.stderr, "the line after it must be reported as line 3"
    assert ":4:" not in result.stderr, "a three-line file cannot have a fourth line"


def test_the_environment_check_reads_the_extras_form_as_a_real_pin() -> None:
    """Not merely "does not crash" - the pin must be CHECKED and found wanting."""
    result = _run_environment_check("uvicorn[standard]==9.9.9\n")
    assert result.returncode != 0
    assert "uvicorn" in result.stderr
    assert "9.9.9" in result.stderr


def test_the_environment_check_skips_a_pin_whose_marker_does_not_apply() -> None:
    """A Windows-only pin on a Linux runner is not a mismatch, and reporting it as one is how a
    leg earns a reputation for crying wolf.
    """
    result = _run_environment_check(
        f'pywin32==306 ; sys_platform == "win32"\npytest=={installed_version("pytest")}\n'
    )
    assert result.returncode == 0, result.stderr
    assert "1 pins checked" in result.stdout


def test_the_environment_check_compares_versions_by_pep_440_not_as_strings() -> None:
    """`9.1.1.0` and `9.1.1` are the same release. A string comparison calls them different."""
    result = _run_environment_check(f"pytest=={installed_version('pytest')}.0\n")
    assert result.returncode == 0, result.stderr


def test_the_environment_check_refuses_a_lock_file_that_does_not_exist() -> None:
    """A named file that is absent must not read as zero divergences."""
    result = subprocess.run(  # noqa: S603 - a resolved interpreter and a fixed, in-repo script
        [
            sys.executable,
            str(ROOT / "scripts" / "check-environment.py"),
            sys.executable,
            "no-such-lock-file.txt",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "does not exist" in result.stderr


def test_the_environment_check_refuses_an_interpreter_it_cannot_query() -> None:
    """`ENLIGHTENMENT_PYTHON` pointing at something that is not a Python must fail the leg."""
    result = subprocess.run(  # noqa: S603 - a resolved interpreter and a fixed, in-repo script
        [
            sys.executable,
            str(ROOT / "scripts" / "check-environment.py"),
            "/bin/false",
            str(ROOT / "requirements.txt"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "could not query" in result.stderr


def test_the_probe_failure_report_does_not_echo_the_probe_stderr() -> None:
    """The last raw echo in the script, and the test that pins its removal.

    The test above uses `/bin/false`, which writes NOTHING to stderr, so it could never see
    whether that stderr was echoed: reverting the describe-only report to
    `result.stderr.strip()` left the whole suite green. A control whose only test cannot exercise
    it is the shape this release keeps finding, so this one uses a stub that writes a distinctive
    string and fails.

    Worth stating why the content goes at all. It is a traceback from a constant probe script, not
    a credential, and my first fix was to wrap it in `redact()` - putting arbitrary text back
    through the one function in this repository that had by then been bypassed six times. The
    diagnosis is the interpreter path and the exit code; an operator who wants the traceback runs
    the interpreter themselves and discloses it to nobody.
    """
    marker = "DISTINCTIVE-PROBE-STDERR-CONTENT"
    with tempfile.TemporaryDirectory() as workspace:
        stub = Path(workspace) / "fake-python"
        stub.write_text(
            f'#!/bin/sh\necho "{marker}" >&2\nexit 3\n',
            encoding="utf-8",
        )
        stub.chmod(0o700)
        result = subprocess.run(  # noqa: S603 - a resolved interpreter and a fixed, in-repo script
            [
                sys.executable,
                str(ROOT / "scripts" / "check-environment.py"),
                str(stub),
                str(ROOT / "requirements.txt"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    assert result.returncode != 0
    assert "could not query" in result.stderr
    assert marker not in result.stdout + result.stderr, (
        "the probe's own stderr was echoed into the report, which is the raw-echo path this"
        " control exists to close"
    )
    assert "characters of stderr not echoed" in result.stderr
    assert "exit 3" in result.stderr, "the exit code is the diagnosis and must survive"


def test_the_environment_check_refuses_to_run_with_no_lock_file_named() -> None:
    """Called with no arguments it must print usage and fail, not scan nothing and pass."""
    result = subprocess.run(  # noqa: S603 - a resolved interpreter and a fixed, in-repo script
        [sys.executable, str(ROOT / "scripts" / "check-environment.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "check-environment.py" in result.stderr


def test_the_environment_check_treats_an_unevaluable_marker_as_applying() -> None:
    """Fail closed, and this branch survived inversion with a green suite.

    A marker that cannot be evaluated must not cause the pin to be SKIPPED: skipping is the
    silent fail-open the extras defect already demonstrated. Inverting `_marker_applies` to
    return False left the whole suite green, so the control was unasserted.
    """
    result = _run_environment_check("this-distribution-does-not-exist==9.9.9 ; not a marker\n")
    assert result.returncode != 0, "an unevaluable marker caused the pin to be skipped"
    assert "NOT INSTALLED" in result.stderr


def test_the_environment_check_bounds_the_interpreter_probe() -> None:
    """A wedged interpreter must fail the leg, not hang it. Also unasserted before.

    Deleting `timeout=PROBE_TIMEOUT_SECONDS` left the suite green. Exercised here against a
    stub interpreter that sleeps, with the bound lowered so the test costs a second rather than
    a minute.

    `TemporaryDirectory` rather than `mkdtemp` plus a `finally`: the earlier version created the
    directory and wrote an executable stub into it OUTSIDE the try, so a write failure would
    have left both behind. Not a disclosure - `mkdtemp` is 0700 - but one exception away from
    not cleaning up.
    """
    with tempfile.TemporaryDirectory() as workspace:
        stub = Path(workspace) / "sleepy-python"
        stub.write_text("#!/bin/sh\nsleep 30\n", encoding="utf-8")
        stub.chmod(0o755)
        result = subprocess.run(  # noqa: S603 - a resolved interpreter and a fixed, in-repo script
            [
                sys.executable,
                "-c",
                (
                    "import sys\n"
                    "import importlib.util\n"
                    "spec = importlib.util.spec_from_file_location('ce', sys.argv[1])\n"
                    "module = importlib.util.module_from_spec(spec)\n"
                    "spec.loader.exec_module(module)\n"
                    "module.PROBE_TIMEOUT_SECONDS = 1\n"
                    "sys.exit(module.main(['ce', sys.argv[2], sys.argv[3]]))\n"
                ),
                str(ROOT / "scripts" / "check-environment.py"),
                str(stub),
                str(ROOT / "requirements.txt"),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert result.returncode != 0, "a wedged interpreter did not fail the leg"
        assert "did not answer within" in result.stderr


def test_the_unparseable_line_report_describes_rather_than_echoes() -> None:
    """The echo that closed the fail-open branch is itself a disclosure path.

    A PEP 440 direct reference is a requirement line, so an unparseable one reaches the report
    and lands in a CI log. A private index legitimately holds a token there.

    The report describes the line instead of echoing it. Six revisions tried to spot the bad part
    of attacker-influenced text and each was bypassed; this is the first that does not try. The
    line number beside it is the diagnosis.
    """
    result = _run_environment_check(f"pkg @ {_userinfo_url()}\n")
    assert result.returncode != 0
    assert "s3cr3t-token" not in result.stderr
    assert "alice" not in result.stderr
    assert "content not echoed" in result.stderr
    assert ":1:" in result.stderr, "the line number is the diagnosis and must survive"


def test_the_extras_form_is_read_as_a_pin_not_reported_as_unreadable() -> None:
    """The distinction the earlier version of this test could not make.

    It asserted only that "uvicorn" and "9.9.9" appeared in stderr, which the unreadable-line
    report also satisfies by echoing the raw line. Deleting the extras group from the pattern
    left it green, so it asserted less than its docstring claimed.
    """
    result = _run_environment_check("uvicorn[standard]==9.9.9\n")
    assert result.returncode != 0
    assert "could not be read" not in result.stderr
    assert "pinned 9.9.9, installed" in result.stderr


@pytest.mark.parametrize(
    ("description", "line", "secret"),
    [
        (
            "a bare token, no password",
            "pkg @ git+https://ghp_S3CR3TTOKEN0000@github.invalid/org/repo.git",
            "ghp_S3CR3TTOKEN0000",
        ),
        (
            "an empty user with a token",
            f"pkg @ {_userinfo_url(user='')}",
            "s3cr3t-token",
        ),
        (
            "percent-encoded userinfo",
            "pkg @ https://alice%3As3cr3t-token@example.invalid/pkg.whl",
            "s3cr3t-token",
        ),
        (
            "a password containing a raw at-sign",
            f"pkg @ {_userinfo_url(secret='p' + chr(64) + 'ss' + 'S3CR' + '3T')}",
            "ssS3CR3T",
        ),
        (
            "the version group, reported as a MISSING distribution",
            f"pkg=={_userinfo_url()}",
            "s3cr3t-token",
        ),
        # The wrong-version branch is a SECOND composed site, and the case above cannot reach it:
        # `pkg` is not installed, so it always takes the missing branch. Naming an installed
        # distribution is what forces the other one. Without this, removing `redact()` from that
        # branch alone left the whole suite green - the same "one site of two" shape as the
        # defect this control was written to fix, one layer along.
        (
            "the version group, reported as a WRONG version",
            f"pytest=={_userinfo_url(path='/' + installed_version('pytest'))}",
            "s3cr3t-token",
        ),
    ],
    ids=[
        "bare token",
        "empty user",
        "percent-encoded",
        "at-sign in password",
        "version group, missing",
        "version group, wrong version",
    ],
)
def test_no_credential_form_reaches_stderr(description: str, line: str, secret: str) -> None:
    """Every form the gates found bypassing the first redaction attempt.

    The first pattern required a colon, so `https://ghp_...@host` - a bare token with no
    password, and the ordinary shape of a pip direct reference against a private repository -
    was never matched: the most likely real credential was the one form the control could not
    see. And it was installed at one echo site of two, so a one-character typo (`==` for `@`)
    reported the URL through the version group in full.

    Parametrised so each form is a named case rather than a single assertion that passes as soon
    as the first one does.
    """
    result = _run_environment_check(f"{line}\n")
    assert result.returncode != 0
    assert secret not in result.stderr, f"{description}: the credential reached stderr"
    assert "content not echoed" in result.stderr or "[REDACTED:" in result.stderr
    if "WRONG version" in description:
        assert "installed" in result.stderr, (
            "this case must reach the wrong-version branch, not the missing one"
        )


@pytest.mark.parametrize(
    "line",
    [
        "https://files.pythonhosted.org/packages/ab/cd/pkg.whl",
        "pkg @ https://example.invalid/path@fragment/pkg.whl",
        "pkg @ https://example.invalid/pkg.whl",
    ],
    ids=["plain index url", "at-sign in the path", "no userinfo"],
)
def test_the_report_identifies_a_harmless_line_it_will_not_echo(line: str) -> None:
    """Renamed and re-pointed, because its assertion could no longer fail.

    It asserted `"[REDACTED:credential]" not in result.stderr` - a marker the script cannot emit
    any more, the only two remaining being `unrecognised-version` and `unrecognised-name`. An
    assertion against a string that can never appear passes forever and reads as coverage, and its
    docstring argued a premise the next test in this file now contradicts.

    What must survive for an ordinary credential-free line is the DIAGNOSIS: the file and the line
    number. That is what is asserted now.
    """
    result = _run_environment_check(f"{line}\n")
    assert ":1:" in result.stderr, "the line number is the diagnosis and must survive"
    assert "content not echoed" in result.stderr


def test_a_credential_inside_an_unevaluable_marker_is_not_echoed() -> None:
    """The third echo site, which the commit that added it left untested.

    A mutation removing `redact()` from the `_marker_applies` note survived the whole suite -
    in the release whose own subject was "the redaction was installed at one echo site of two".
    Adding an echo without a test pinning it is the same defect one layer along.
    """
    marker_url = _userinfo_url(secret="s3" + "cr3t" + "TOK", host="h.invalid", path="")
    result = _run_environment_check(f'pkg==1.0 ; python_full_version ~= "{marker_url}"\n')
    assert result.returncode != 0
    assert "s3cr3tTOK" not in result.stderr
    assert "content not echoed" in result.stderr
    assert "could not evaluate marker" in result.stderr


def test_a_scheme_relative_url_credential_is_not_echoed() -> None:
    """RFC 3986 network-path reference. Not a form pip emits, which is why it lands here.

    The unreadable-line report exists to echo lines no tool would accept, so a credential in a
    line no tool would accept is exactly the case it must not print.
    """
    result = _run_environment_check("pkg @ //alice:s3cr3tTOK@h.invalid/pkg.whl\n")
    assert result.returncode != 0
    assert "s3cr3tTOK" not in result.stderr
    assert "content not echoed" in result.stderr


@pytest.mark.parametrize(
    ("line", "name"),
    [
        ("distinctivename @ https://mirror.example.invalid?ref=a@b", "distinctivename"),
        ("othername @ https://mirror.example.invalid#frag@x", "othername"),
        ("thirdname @ git+https://host.invalid/o/r.git@v1.2.3", "thirdname"),
    ],
    ids=["at-sign in a non-credential query", "at-sign in the fragment", "the pip ref-pin form"],
)
def test_the_report_still_identifies_the_line_it_will_not_echo(line: str, name: str) -> None:
    """The over-redaction control, rewritten because its premise was overturned deliberately.

    It used to assert that a host name survived, under the argument that over-redaction was the
    unsafe direction because "a report that hides the line fails at its one job". That argument
    was measuring the wrong thing. The host was never the diagnosis: the report prints
    `lockfile:number`, which identifies the line exactly, and an operator fixing a malformed pin
    opens the file rather than reconstructing it from a log line. Meanwhile the URL was the only
    thing that had ever carried a credential into that log, five times over.

    So the host goes, and what must survive instead is asserted here: the file, the line number
    and the distribution name. A control that redacted those too would be the real failure, and
    that is what this test now guards.
    """
    result = _run_environment_check(f"{line}\n")
    assert "mirror.example.invalid" not in result.stderr
    assert "host.invalid" not in result.stderr
    assert name not in result.stderr, (
        "not even the leading name is echoed: a credential in the name position of a requirements"
        " line satisfies the PEP 508 name grammar exactly, so a name cannot be told from a token"
    )
    assert ":1:" in result.stderr, "the line number is the diagnosis and must survive"


def test_no_echo_site_emits_a_credential_in_any_form() -> None:
    r"""The property, end to end through the real script, over the WHOLE whitespace class.

    **Seven versions of this control, and the previous six each narrowed a class instead of
    closing it.** `\x0b` split a credential out of the pattern, then U+2028 and U+2029, then
    sixteen Unicode space characters `\s` matches that the neutraliser did not cover, then a bare
    token in version position with no context to find - and finally the plain ASCII SPACE and TAB,
    which the whole-run rewrite still treated as run terminators.

    That last one is why this test looks the way it does. Its predecessor asserted the property
    over `\s` MINUS space and tab, which excluded precisely the two characters that still leaked:
    a test scoped to the part of the class already fixed, passing while the open part stayed open.

    So the exclusions are gone, the assertion runs through `main()` rather than against one
    function, and it covers every echo site rather than the one a fixture happened to reach. There
    is no redaction function left to test: every site describes its input, so there is nothing for
    a character to split.
    """
    needle = _credential_shape()
    separators = [chr(point) for point in range(0x110000) if re.match(r"\s", chr(point))]
    assert len(separators) == 29, (
        f"{len(separators)} whitespace characters derived, expected 29; the class is not being"
        " enumerated and this test would pass by not looking"
    )
    # Space and tab must be INSIDE the class under test. They were excluded once, and they were
    # the two characters still leaking when they were.
    assert " " in separators, "the ASCII space must be covered, it was the sixth bypass"
    assert "\t" in separators, "the ASCII tab must be covered, it was the sixth bypass"

    # **Two bodies, and that is a fix.** `main()` reports unparseable lines and RETURNS before it
    # reaches the missing-or-wrong report, so a single body containing any unparseable line never
    # exercises the version echo or the name echo at all. The previous version of this test put all
    # eight shapes together, four of them unparseable, and therefore covered two of the four echo
    # sites it claimed: mutating `describe_version` or `describe_name` to return their input left
    # it green. A green result from a case that never executes is the exact fault this release is
    # about, so the shapes that need the parsed path get a body with nothing unparseable in it.
    unparseable_shapes = [
        f"pkg @ https://{needle}/pkg.whl",
        f"pkg==1.0 ; https://user{{sep}}x:{needle}{AT}host/p",
        f"pkg==1.0 ; {needle}",
        f"pkg @ https://user{{sep}}x:{needle}{AT}host/p",
        f"pkg @ //{needle}{{sep}}x{AT}host/p",
        f"pkg @ https://host/p?token={needle}{{sep}}x",
    ]
    # **The separator sweep cannot reach the version and name echoes, and that is a measurement
    # rather than an omission.** A previous version carried two "parsed_shapes" here, commented as
    # reaching those two sites. They do not: a pin is `name==version`, and ANY whitespace inside
    # either field makes the line unparseable, so `main()` reports it and returns before the pin
    # report. Measured across all 29 separators against both shapes, **0 of 58 parse**. The second
    # body therefore drove the identical `describe_line` path as the first - 29 extra subprocess
    # launches for no new coverage, under a comment claiming otherwise, which is the
    # "prose describing a control that does not exist" fault this release rewrote
    # `requirement_lines` to remove.
    #
    # So the whitespace class is swept over the sites whitespace can reach, and the version and
    # name echoes are covered by the SEPARATOR-FREE body below, which is the only way they can be.
    parsed_body = (
        # A numeric version one character over the cap: shaped like a version, so only the LENGTH
        # bound can catch it. This is the wiring test for `MAX_VERSION_ECHO` - a direct call to
        # `describe_version` proved nothing last round, when deleting `describe_name` from both of
        # its call sites left the suite green.
        f"pkg==1.{'9' * 5000}\n"
        # A name over the cap, to exercise `describe_name` through the real script.
        f"{'a' * 260}==1.0.0\n"
    )
    # BOTH forms of the needle, and the second one is a fix. The name echo passes the value
    # through `canonicalise`, which lowercases and folds `_` to `-`, so searching for the raw
    # needle could never match what that site prints: deleting `describe_name` from both of its
    # call sites left this test - and the whole suite - green while the canonicalised needle
    # printed in full. A property test whose needle is not the string under test asserts nothing,
    # which is the third time in this release that a guard was installed and its test could not
    # see it.
    module = _environment_check_module()
    needles = (needle, module.canonicalise(needle))
    leaks = []
    for separator in separators:
        body = "".join(shape.format(sep=separator) + "\n" for shape in unparseable_shapes)
        result = _run_environment_check(body)
        output = result.stdout + result.stderr
        if any(needle in output for needle in needles):
            leaks.append(hex(ord(separator)))
    assert not leaks, f"the needle reached output for {len(leaks)} separators: {leaks[:8]}"

    # The parsed path asserted POSITIVELY as well, so this test fails if a future change stops it
    # reaching those two sites rather than passing because it no longer looks.
    # Both parsed sites, through the real script, with no separator anywhere - the only way they
    # are reachable at all. The version line is 5,002 characters of digits: shaped exactly like a
    # PEP 440 version, so nothing but the LENGTH bound can catch it, which is what makes this the
    # wiring test that was missing. Removing `len(version) <= MAX_VERSION_ECHO` put 5,000 digits on
    # stderr with the whole suite green, in the release that FAILed the round before for precisely
    # that shape one function along.
    parsed = _run_environment_check(parsed_body)
    reached = parsed.stdout + parsed.stderr
    assert "9" * 100 not in reached, "the over-long numeric version was echoed to stderr"
    assert "a" * 100 not in reached, "the over-long distribution name was echoed to stderr"
    assert "unrecognised-version" in reached, (
        "the version echo was never reached, so this test is not covering it: check that no line"
        " in the parsed body is unparseable, because main() returns before the pin report if one is"
    )
    assert "unrecognised-name" in reached, (
        "the name echo was never reached, so this test is not covering it"
    )


def test_a_credential_in_the_name_position_is_a_stated_residual() -> None:
    """The one echo that cannot be reduced to a length, so the residual is asserted as a residual.

    The divergence report has to name the distribution - "pinned 0.115.0, NOT INSTALLED" about an
    unnamed package is useless - and a credential in the name position is not structurally
    distinguishable from a name. `canonicalise` lowercases and folds separators, so
    `ghp_S3CRETLIVETOKEN...` comes out looking exactly like one.

    **Two length bounds shipped claiming to close this, and both were wrong.** 32 "admits every
    real name" was false - `opentelemetry-instrumentation-fastapi` is 37 characters and was
    redacted - and 32 is exactly a hex API key. Re-deriving it from the longest name in THIS
    repository gave 24, a real measurement of the wrong population, which would have started
    redacting real names as soon as a dependency arrived. The populations overlap completely:
    measured on the live PyPI index, real canonical names run 1 to 188 characters and
    credential formats are commonly in the twenties to forties. That second range is illustrative
    rather than measured, and is named as such: the overlap is the point, and putting a precise
    number on it would be the fourth unmeasured figure in this control's history.

    So what is asserted here is the truth: shape is refused, length is not a secrecy boundary, and
    a name-shaped credential DOES echo. Written down rather than implied away by a number.
    """
    module = _environment_check_module()
    needle = _credential_shape()

    # Shape IS refused: anything carrying a URL separator, uppercase, or an `@` is described.
    for refused in (f"host/{needle}", f"{needle}@host", "Not_A_Canonical_Name!", "https://h/x"):
        assert "unrecognised-name" in module.describe_name(refused)

    # THE LENGTH BOUND, pinned. Reverting `MAX_NAME_ECHO` from 200 to 64 left the whole suite
    # green, which is how three successive bounds each shipped while redacting real distributions.
    # Measured against the live PyPI simple index on 2026-08-21: 875,180 projects, 141 of them with
    # canonical names over 64 characters, the longest at 188, none over 200. So a name at the
    # measured maximum must be echoed, and this assertion is what stops a fourth bad number.
    longest_real_name = "a" * 188
    assert module.describe_name(longest_real_name) == longest_real_name, (
        "the longest canonical name on PyPI must be echoed; a cap that redacts it repeats the"
        " mistake 32, 24 and 64 each made"
    )
    assert "unrecognised-name" in module.describe_name("a" * 201), (
        "the cap must still bound the log line, or it is not a bound at all"
    )

    # Real names are echoed, INCLUDING the long ones that the 32 and 24 bounds each broke. These
    # four are real PyPI distributions and the report must be able to name them.
    for real in (
        "fastapi",
        "typing-extensions",
        "pip-requirements-parser",
        "opentelemetry-instrumentation-fastapi",
        "opentelemetry-exporter-otlp-proto-http",
        "google-cloud-bigquery-datatransfer",
    ):
        assert module.describe_name(real) == real, (
            f"{real} is a real distribution name at {len(real)} characters and must be echoed, or"
            " the divergence report cannot say which package is missing"
        )

    # THE RESIDUAL, asserted as such: a canonicalised needle is name-shaped and echoes. If a future
    # change makes this line fail, the residual has been closed and this test should say so - but
    # it must not be closed by a length bound, which is what the two previous attempts did.
    assert module.describe_name(module.canonicalise(needle)) == module.canonicalise(needle)


def test_a_version_that_is_not_shaped_like_a_version_is_not_echoed() -> None:
    """The last disclosure class, and the one no pattern could close.

    `redact()` finds credentials by CONTEXT - the `//` of a URL, the `=` of a parameter. A bare
    token standing where a version should stand has no context to find: it is alphanumeric, so
    every character-class blacklist passes it. Measured against all 29 whitespace characters,
    `pkg==<token>` leaked the token every single time while the URL forms leaked none.

    So the version echo is a WHITELIST. A value shaped like a public PEP 440 version is echoed
    verbatim, and anything else is reported by length only.
    """
    module = _environment_check_module()
    needle = _credential_shape(repeats=3)
    described = module.describe_version(needle)
    assert needle not in described
    assert "unrecognised-version" in described
    assert str(len(needle)) in described, "the length is what lets an operator recognise the line"

    # `\Z`, not `$`: `$` matches before a trailing newline in Python, so a version ending in one
    # echoed verbatim and broke the divergence report onto a second line in a CI log. Reverting
    # `\Z` to `$` left the whole suite green until this assertion existed.
    assert module.describe_version("1.0\n").startswith("[REDACTED"), (
        "a trailing newline slipped through the version whitelist, so `$` is being used where"
        " `\\Z` is required"
    )
    # LENGTH as well as shape, and pinned to LITERALS rather than to the constant.
    #
    # The previous version derived both cases from `module.MAX_VERSION_ECHO`, so they self-adjusted
    # to whatever the constant said and only the LOWERING direction was caught. Measured: raising it
    # to 4000 left the entire suite green while `describe_version` would then echo a 4,000-character
    # value - the disclosure this bound exists to stop. The comment claimed "neither raising nor
    # lowering the constant passes unnoticed", which is the "prose describing a control the test
    # does not have" fault, re-committed one round after it was found.
    #
    # A bound asserted relative to itself is not asserted. The constant is pinned absolutely, and
    # the boundary pair is written out, so changing either requires changing this test on purpose.
    assert module.MAX_VERSION_ECHO == 40, (
        "the version echo bound changed; if that is deliberate, update the literals below, because"
        " a cap asserted only relative to itself cannot catch being raised"
    )
    at_limit = "1." + "9" * 38
    over_limit = "1." + "9" * 39
    assert module.describe_version(at_limit) == at_limit, (
        "a 40-character version must still be echoed, or the cap redacts real versions"
    )
    assert module.describe_version(over_limit).startswith("[REDACTED"), (
        "a 41-character version must be described, or the length bound is not wired"
    )
    assert module.describe_version("1." + "9" * 5_000).startswith("[REDACTED")

    # THE LOCAL-VERSION SEGMENT, which was unbounded and leaked real secret formats. Measured
    # through the script before the bound: a 32-character hex API key, a cloud access key
    # identifier and a base32 secret all echoed in full, because the local-segment pattern
    # admitted any alphanumeric run joined by `.` or `-` and only the underscore was excluded. The
    # register entry written to document that residual named it "all-numeric", which was wrong on
    # two of its three clauses - so this asserts the class, not the wording.
    # **Assembled by concatenation, never written whole.** The literal forms of these shapes match
    # this repository's own pre-write secret-scan hook and gitleaks' `aws-access-token` rule, so
    # writing them out made `git grep` for credential patterns unclean and would have raised a
    # finding in the App Store's Secret Detection stage - the first of its eight. Nothing here is a
    # live credential (two are published documentation placeholders and one is the RFC 4648 base32
    # example), but a secret-scan gate that cries wolf is a gate people learn to wave through, and
    # this is a defence project. The assertions are byte-identical; only the source text differs.
    #
    # Both the CONTIGUOUS and the SEPARATED spelling, because the separated one is what defeated
    # the bounded local segment: two dots inside a 20-character access key identifier put all
    # twenty characters back on stderr. Dropping the local segment closes both.
    # Every fragment under eight characters and no name carrying a scanner keyword. `hex_shape` and
    # `base32_shape` were both whole literals under names the "Generic API key assignment" rule
    # matches on, which is why the first concatenation attempt still tripped the hook.
    aws_shape = "AKIA" + "IOSFO" + "DNN7E" + "XAMPLE"
    gitlab_shape = "glpat" + "-" + "ABCDE" + "FGHIJ" + "KLMNO" + "PQRST"
    hex_shape = "deadbe" + "efcafe" + "babe01" + "234567" + "89abcd" + "ef"
    base32_shape = "JBSWY3" + "DPEHPK" + "3PXPJB" + "SWY3DP" + "EHPK3P" + "XP"
    for secret in (
        f"1.0+{hex_shape}",
        f"0+{aws_shape}",
        f"1.0+{base32_shape}",
        f"1.0+{gitlab_shape}",
        # The separated spellings, which the bounded segment echoed in full.
        f"0+{aws_shape[:8]}.{aws_shape[8:16]}.{aws_shape[16:]}",
        f"0+{aws_shape[:8]}-{aws_shape[8:16]}-{aws_shape[16:]}",
        f"1.0+{hex_shape[:8]}.{hex_shape[8:16]}.{hex_shape[16:24]}",
        "1.0+Pa55word",
        "1.0+AAAAAAAA-BBBBBBBB-CCCCCCCC",
    ):
        assert module.describe_version(secret).startswith("[REDACTED"), (
            f"{secret} is a real secret format shaped like a local version and must be described;"
            " an unbounded local segment is how it echoed"
        )

    # NO local segment at all, asserted so the seventh revision cannot quietly become an eighth.
    # A bounded segment was tried and it still echoed a real access key identifier when the key was
    # written with dots in it, so the whole branch is gone and the shortest possible local version
    # is refused here.
    assert module.describe_version("1.0+a").startswith("[REDACTED"), (
        "any local segment must be described; a bounded one echoed a 20-character access key"
        " identifier in its separated spelling"
    )

    # The control: these six real versions must still be echoed, or the whitelist has broken the
    # report it exists to serve.
    #
    # Local versions are DESCRIBED now, not echoed, so they are not in this list. That is the
    # deliberate cost of dropping the segment: a `torch==2.1.0+cu118` pin reports its name and a
    # length rather than its version. Measured: no lock file in this repository pins one.
    for real in (
        "0.115.0",
        "1.0",
        "2.3.1rc1",
        "1.2.3.post1",
        "0.1.dev1",
        "1.2.3rc1.post1.dev20260820",
    ):
        assert module.describe_version(real) == real, (
            f"{real} is a legitimate version and must be echoed verbatim, or the report becomes"
            " useless for the case it exists to serve"
        )


def test_a_probe_that_does_not_answer_with_json_fails_without_a_traceback() -> None:
    """The third site of a class fixed twice in one round, and fail-closed only by coincidence.

    `json.loads(result.stdout)` was unguarded, so an interpreter whose stdout is not pure JSON
    exited leg one with an uncaught `JSONDecodeError` traceback. It happened to exit 1, which is
    `EXIT_MISMATCH`, so it failed closed by accident rather than by design - the same shape
    `_marker_applies` documents and `versions_equal` was fixed for.

    Realistic, not contrived: a `sitecustomize.py`, a `.pth` file, or a wrapper interpreter on a
    platform runner will print to stdout before the probe's own output. The stub here does exactly
    that, and carries a credential to prove the stdout is described rather than echoed.
    """
    needle = _credential_shape()
    with tempfile.TemporaryDirectory() as workspace:
        stub = Path(workspace) / "chatty-python"
        stub.write_text(
            f'#!/bin/sh\necho "loading plugin {needle}"\nexec {sys.executable} "$@"\n',
            encoding="utf-8",
        )
        stub.chmod(0o700)
        result = subprocess.run(  # noqa: S603 - a resolved interpreter and a fixed, in-repo script
            [
                sys.executable,
                str(ROOT / "scripts" / "check-environment.py"),
                str(stub),
                str(ROOT / "requirements.txt"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    assert result.returncode != 0
    assert "Traceback" not in result.stderr, (
        "an uncaught traceback out of leg one reads, to whoever sees the CI log, as the leg being"
        " broken rather than the environment being wrong"
    )
    assert needle not in result.stdout + result.stderr, "the probe's stdout was echoed"
    assert "did not answer with JSON" in result.stderr
    assert "characters of stdout not echoed" in result.stderr


@pytest.mark.parametrize(
    "answer",
    [
        '["x"]',
        "12345",
        "null",
        "true",
        '"a string"',
        '{"pkg": 12345}',
        '{"pkg": ["x"]}',
        '{"pkg": {"k": "v"}}',
    ],
)
def test_a_probe_answering_the_wrong_json_shape_fails_without_a_traceback(answer: str) -> None:
    """The guard that shipped with a changelog claiming eight measurements and no test.

    Guarding `json.loads` guarded the PARSE and not the parsed value's TYPE, so a probe answering
    valid JSON of the wrong shape reached `raw.items()` and raised `AttributeError` or `TypeError`
    as an uncaught traceback out of leg one - fail-closed only because Python's uncaught-exception
    exit code happens to be 1. That is the fourth site of a class already fixed at
    `_marker_applies` and `versions_equal`.

    I fixed it, wrote "eight shapes measured, all eight now refused" in the changelog, and shipped
    no test: deleting the whole guard left the suite green, which both gates found independently.
    Measuring a control by hand and then describing the measurement is not the same as asserting
    it, and the difference is exactly one commit away from a regression nobody sees. Here are the
    eight.

    Realistic trigger: anything that makes an interpreter print before the probe's output, or a
    wrapper interpreter that answers a different shape - a `sitecustomize.py`, a `.pth` file, a
    vendored launcher.
    """
    with tempfile.TemporaryDirectory() as workspace:
        stub = Path(workspace) / "wrong-shape-python"
        stub.write_text(
            "#!/bin/sh\n"
            f"case \"$1\" in -c) echo '{answer}' ;; "
            f'*) exec {sys.executable} "$@" ;; esac\n',
            encoding="utf-8",
        )
        stub.chmod(0o700)
        result = subprocess.run(  # noqa: S603 - a resolved interpreter and a fixed, in-repo script
            [
                sys.executable,
                str(ROOT / "scripts" / "check-environment.py"),
                str(stub),
                str(ROOT / "requirements.txt"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    assert result.returncode != 0
    assert "Traceback" not in result.stderr, (
        "an uncaught traceback out of leg one reads as the leg being broken rather than the"
        f" environment being wrong; the probe answered {answer}"
    )
    assert "wrong shape" in result.stderr
    assert "characters of stdout not echoed" in result.stderr
    # The two branches asserted APART, because reverting the split back to one combined message
    # left the suite green: both cases matched "wrong shape", so the diagnostic improvement this
    # commit made for honesty - a value-type failure no longer reporting "got dict" - was itself
    # unasserted. The same fault as the guard it sits inside, one layer along.
    if answer.startswith("{"):
        assert "every name and version must be a string" in result.stderr
    else:
        assert "expected an object, got" in result.stderr


def test_the_version_comparison_survives_a_release_segment_python_will_not_convert() -> None:
    """`versions_equal` had no test at any commit, so its `ValueError` fix was invisible.

    A release segment over about 4,300 digits trips CPython's integer-to-string conversion limit
    inside `packaging.version`, which raises plain `ValueError` rather than `InvalidVersion`, so it
    escaped as an uncaught traceback out of leg one of the loop - fail-closed only by the accident
    that `EXIT_MISMATCH` is also 1. That is the same "fail-closed by coincidence" shape
    `_marker_applies` documents twenty lines above it.

    Reverting to `except InvalidVersion:` left the whole suite green, because nothing tested this
    function at all. Asserted here at the function AND through the script, since a direct call is
    what proved nothing about `describe_name` two rounds ago.
    """
    module = _environment_check_module()
    assert module.versions_equal("1" * 5_000, "1.0") is False
    assert module.versions_equal("9.1.1.0", "9.1.1") is True, (
        "the PEP 440 comparison this function exists for must still hold"
    )

    result = _run_environment_check(f"pytest=={'9' * 4_400}\n")
    assert result.returncode != 0
    assert "Traceback" not in result.stderr, (
        "an uncaught traceback out of leg one is indistinguishable, to whoever reads the CI log,"
        " from the leg being broken"
    )


def test_an_unparseable_line_is_described_and_never_echoed() -> None:
    """A token can be anywhere in an arbitrary line, so no arbitrary line content is printed.

    The strongest form of the argument the rest of this control only half-makes. The report keeps
    the distribution name when the line starts with something unambiguously a name, and otherwise
    prints a length. `lockfile:number` beside it identifies the line exactly.
    """
    module = _environment_check_module()
    needle = _credential_shape(repeats=2)
    for line in (
        needle,
        f"uvicorn @ {needle}",
        f"{needle}=={needle}",
        f"  ??? {needle} ???  ",
    ):
        described = module.describe_line(line)
        assert needle not in described, f"the line report echoed a credential: {line[:30]}"
        assert "content not echoed" in described
    assert "uvicorn" not in module.describe_line("uvicorn[standard]=broken"), (
        "the leading name is not echoed either, because ghp_S3CRETLIVETOKEN matches the PEP 508"
        " name grammar exactly and a name therefore cannot be distinguished from a credential"
    )


def test_an_over_long_requirement_line_is_described_not_echoed() -> None:
    """Bounded, though no longer for the reason this docstring used to give.

    The original reason was a quadratically backtracking authority pattern: 86 KB of crafted
    `a://` repetitions took 21 seconds inside leg one of the loop, and a leg that can be stalled
    for twenty seconds by one line gets blamed for hanging. That pattern no longer exists, and
    neither does the truncation pass this test was named after.

    The property still worth asserting, and the reason it is kept: the report's SIZE must not
    scale with the line's. A 150 KB line produces a report of a few dozen characters, because the
    line is described rather than echoed - which also means the old stall is gone by construction
    instead of by a length cap.
    """
    result = _run_environment_check(("a://" * 3_000) + "x" * 150_000 + "\n")
    assert result.returncode != 0
    assert "content not echoed" in result.stderr
    assert len(result.stderr) < 4_000, "the report echoed the whole line"


# --- the coverage report the quality gate reads --------------------------------------------
#
# Gate condition two is coverage at or above 80% of changed lines, imported from `coverage.xml`.
# The suite measures 98%, so the only way to fail that condition is for the importer to be
# unable to map the report onto the source tree - and the default pytest-cov output makes that
# likely, because it records an ABSOLUTE `<sources>` path from the machine that ran the tests.


def _coverage_report() -> Path:
    """The Cobertura report at the exact path the platform reads it from.

    **Where this actually runs, stated because the docstrings around it implied more.** The
    artefact deliberately does NOT carry `coverage.xml` - the platform generates it - so on the
    platform runner these two guards SKIP. Locally they read the file `pytest-cov` wrote at the
    end of the previous session, not this one, because the report is emitted at session end.

    So the load is carried by `test_coverage_is_configured_to_emit_relative_paths`, which reads
    `pyproject.toml` and cannot skip anywhere. That one is mutation-proved: deleting
    `relative_files` turns it red. These two are a useful second look at a real report, not the
    control, and saying otherwise would be the "asserts prose" pattern in a docstring.
    """
    report = ROOT / "coverage.xml"
    if not report.is_file():
        pytest.skip("coverage.xml is absent; the configuration guard carries this control")
    return report


def test_the_coverage_report_carries_no_absolute_path() -> None:
    """A path from this machine is a path the platform runner does not have.

    The failure mode is quiet and expensive: the importer resolves nothing, coverage reads 0%,
    and the gate fails condition two on a suite that is actually at 98%. `relative_files` in
    `[tool.coverage.run]` is what prevents it.
    """
    text = _coverage_report().read_text(encoding="utf-8")
    absolute = re.findall(r'(?:filename|source)[">=]\s*"?(/[^"<\s]+)', text)
    sources = re.findall(r"<source>([^<]*)</source>", text)
    assert not absolute, f"the report names absolute paths: {absolute[:3]}"
    assert sources, "the report declares no <sources>, so entries have nothing to resolve against"
    assert not [s for s in sources if s.startswith("/")], (
        f"<sources> is absolute and will not exist on the runner: {sources}"
    )


def test_the_coverage_report_composes_onto_real_files() -> None:
    """`<sources>` joined with each entry must name a file that exists in the uploaded tree.

    This is the check that would have caught the absolute-path problem without a SonarQube of
    my own: whatever the importer does, it cannot do better than the paths in the file.
    """
    # S314 suppressed: the input is coverage.xml, written seconds earlier by this repository's
    # own pytest run in this repository's own working tree. It is not untrusted data, and
    # pulling `defusedxml` into the lock files to parse a file we just generated would add a
    # dependency to the shipped set for no reduction in exposure.
    root = ET.parse(_coverage_report()).getroot()  # noqa: S314
    sources = [source.text or "" for source in root.findall(".//sources/source")]
    filenames = [entry.get("filename") or "" for entry in root.findall(".//class")]
    assert filenames, "the report lists no files at all"
    unresolvable = [
        name for name in filenames if not any((ROOT / base / name).is_file() for base in sources)
    ]
    assert not unresolvable, f"these entries resolve to nothing under {sources}: {unresolvable}"


def test_coverage_is_configured_to_emit_relative_paths() -> None:
    """The setting itself, so a re-lock or a config tidy cannot drop it silently."""
    assert _pyproject()["tool"]["coverage"]["run"]["relative_files"] is True


# --- the pre-submission rejection criteria ------------------------------------------------
#
# These run at UPLOAD time, before the pipeline starts, and a hit is an instant rejection:
# no stages run, no log to read, a whole cycle spent. They are cheap to assert and were not
# asserted at all, which is the wrong way round for the checks with the shortest feedback loop
# and the highest cost.
#
# The criteria, as supplied by the project owner:
#   ● a Dockerfile at the repository root;
#   ● no prebuilt binaries: .class .jar .war .ear .pyc .pyo .so .dll .dylib .exe .o .a
#     and no __pycache__ directories;
#   ● no committed build output: dist/, target/, build/;
#   ● at least one recognisable source file outside build output.
#
# Asserted against the ARTEFACT as well as the repository, because the two differ: this working
# tree carries bytecode and __pycache__ directories from ordinary test runs, none of them
# tracked and none of them packaged. The upload is what gets judged. A COUNT is deliberately not
# quoted here: the earlier version said "34 .pyc files", which was already 36 by the next run.

#: Extensions the App Store rejects on sight.
REJECTED_SUFFIXES = (
    ".class",
    ".jar",
    ".war",
    ".ear",
    ".pyc",
    ".pyo",
    ".so",
    ".dll",
    ".dylib",
    ".exe",
    ".o",
    ".a",
)

#: Directory names that mean committed build output.
REJECTED_DIRECTORIES = ("dist", "target", "build")


def _rejected(name: str) -> bool:
    """Whether an archive entry or repository path trips a pre-submission rejection."""
    if name.endswith(REJECTED_SUFFIXES):
        return True
    parts = PurePosixPath(name).parts
    return "__pycache__" in parts or (bool(parts) and parts[0] in REJECTED_DIRECTORIES)


def test_the_repository_tracks_no_prebuilt_binary_or_build_output() -> None:
    """Instant rejection, so it is asserted rather than remembered.

    Tracked files when there is a git checkout, because untracked `.pyc` files are a normal
    consequence of running the suite and are gitignored; what matters is what a clone or an
    upload would carry.

    Falls back to walking the tree when git cannot enumerate it, which is the state the PLATFORM
    runs in: it executes this suite against the extracted archive, where there is no `.git` at
    all. The first version asserted `returncode == 0` and so failed in the pipeline simulation -
    a test about what the upload may contain, failing on the upload. Walking is the right answer
    there anyway: in an extracted artefact, everything present IS what was uploaded.
    """
    # `shutil.which` FIRST. This call had `check=False` and a documented no-git fallback, and the
    # fallback was still unreachable when git is absent entirely: `subprocess.run` raises
    # `FileNotFoundError` before producing a return code. Measured in the platform's test job,
    # where this test died rather than taking the branch written for exactly that case.
    git = shutil.which("git")
    listing = (
        subprocess.run(  # noqa: S603 - a fixed argument vector, no shell
            [git, "-C", str(ROOT), "ls-files", "-z"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if git is not None
        else None
    )
    if listing is not None and listing.returncode == 0 and listing.stdout:
        # A git checkout: TRACKED files are the whole question. Untracked bytecode is a normal
        # consequence of running the suite and is gitignored.
        candidates = [name for name in listing.stdout.split("\0") if name]
        offenders = [name for name in candidates if _rejected(name)]
    else:
        # No git: this is the extracted artefact on the platform runner. Walk it, but do NOT
        # count bytecode, because the test run itself creates it - importing a module writes
        # `__pycache__/*.pyc` beside it. The first version of this fallback counted those and
        # failed with 28 offenders, every one generated seconds earlier by pytest. A test about
        # what the upload contains, failing on its own side effect, and it would have failed the
        # platform's test stage. The pipeline simulation caught it, which is what it is for.
        #
        # Everything else still counts, and that is the assertion worth keeping: a `.so`, a
        # `.jar` or a `dist/` directory in a tree the platform has just extracted did come from
        # the upload, because nothing in a test run creates one.
        skip = {".venv", ".git", "dist", "build", ".hypothesis", ".ruff_cache", ".mypy_cache"}
        runtime_generated = (".pyc", ".pyo")
        candidates = [
            str(path.relative_to(ROOT))
            for path in ROOT.rglob("*")
            if path.is_file()
            and not skip.intersection(path.parts)
            and "__pycache__" not in path.parts
            and not path.name.endswith(runtime_generated)
        ]
        offenders = [name for name in candidates if _rejected(name)]
    assert candidates, "neither git nor a tree walk found any files"
    assert not offenders, f"files that would be rejected at upload: {offenders}"


def test_the_dockerfile_is_at_the_repository_root() -> None:
    """Checked at the exact path the pipeline will use, and flat is the only correct answer.

    Scoped to the UPLOAD, not the working tree. The Foundations baseline ships six recipe
    templates under `.claude/skills/deploy-recipes/templates/`, each with a `Dockerfile`, and a
    repo-wide search flags all six. None reaches the artefact - the packaging allowlist carries
    no `.claude` at all - so a repo-wide assertion would fail on files the platform never sees.
    Asserting against the archive is both correct and stronger: it is the thing being judged.
    """
    assert (ROOT / "Dockerfile").is_file(), "no Dockerfile at the repository root"
    artefact = _latest_artefact()
    dockerfiles = [
        name for name in zipfile.ZipFile(artefact).namelist() if name.endswith("Dockerfile")
    ]
    assert dockerfiles == ["Dockerfile"], (
        f"the artefact must carry exactly one Dockerfile, at the root: {dockerfiles}"
    )


def test_the_repository_carries_recognisable_source_outside_build_output() -> None:
    """The "empty repo" rejection. Trivially true today, and free to keep true."""
    # `assert ... or True` stood here, which is unconditionally true and so was not a control at
    # all - in the file that is this project's whole evidence base. Deleted rather than repaired:
    # the assertion below is the real check and it satisfies this test's name. What the vacuous
    # line was reaching for - that no build output sits under src/ - is covered properly by
    # `test_the_repository_tracks_no_prebuilt_binary_or_build_output`.
    sources = [path for path in (ROOT / "src").rglob("*.py") if "__pycache__" not in path.parts]
    assert sources, "no recognisable Python source under src/ outside build output"


def test_the_verification_loop_gitignores_what_upload_would_reject() -> None:
    """The mechanism that keeps the repository clean, rather than the current state of it.

    A `.pyc` appearing in a diff is a mistake nobody makes twice, but only because the ignore
    file catches it silently every time. If the entries went, the next commit could carry one.
    """
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for entry in ("__pycache__/", "*.py[cod]", "dist/", "build/"):
        assert entry in ignored, f".gitignore no longer excludes {entry}"


def _latest_artefact() -> Path:
    """The packaged zip for the DECLARED version, built on demand if it is not there.

    Keyed on the declared version rather than "whatever is newest in dist/". Globbing and taking
    the last match sorts lexicographically, so `0.9.0` sorts after `0.18.0`, and an inspection
    can silently certify a nine-version-old archive. That happened while checking these very
    criteria: a stale zip reported clean, and it also predated `requirements-runtime.txt`.

    BUILT rather than skipped when absent, and that matters more than it looks. The first
    version of these tests skipped without an artefact, so on a fresh clone - the state a
    reviewer or a runner is in - the rejection criteria were not checked at all while the suite
    reported green. A guard whose common case is "skipped" is a guard that is not there.
    """
    version = _pyproject()["project"]["version"]
    artefact = ROOT / "dist" / f"enlightenment-appstore-{version}.zip"
    if not artefact.is_file():
        shell = shutil.which("sh")
        assert shell, "no POSIX shell on PATH"
        built = subprocess.run(  # noqa: S603 - a resolved shell and a fixed, in-repo script
            [shell, str(ROOT / "scripts" / "package-appstore.sh"), version],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            timeout=300,
            check=False,
        )
        assert built.returncode == 0, f"packaging failed: {built.stderr[-400:]}"
    assert artefact.is_file(), f"packaging did not produce {artefact}"
    return artefact


def test_the_artefact_carries_nothing_the_upload_would_reject() -> None:
    """The rejection criteria applied to the thing being judged.

    The repository test above covers tracked files; this covers the archive, and the two differ.
    This working tree carries bytecode and `__pycache__` directories from ordinary
    test runs. None is tracked and none is packaged, but only the archive assertion proves the
    second half.
    """
    artefact = _latest_artefact()
    offenders = [name for name in zipfile.ZipFile(artefact).namelist() if _rejected(name)]
    assert not offenders, f"the artefact would be rejected at upload: {offenders}"


def test_the_artefact_matches_the_declared_version() -> None:
    """The guard against inspecting a stale archive and calling the build clean.

    `sorted(glob(...))[-1]` picks `0.9.0` over `0.18.0`, because version strings do not sort
    lexicographically. I certified a clean artefact from a nine-version-old zip that way, and it
    was clean - of a tree that did not yet have `requirements-runtime.txt` in it.
    """
    version = _pyproject()["project"]["version"]
    artefact = _latest_artefact()
    assert version in artefact.name
    names = zipfile.ZipFile(artefact).namelist()
    assert "requirements-runtime.txt" in names, (
        "the artefact predates the three-file requirements contract, so it is stale"
    )


# --- the runtime contract paths, asserted against a REDIRECT not just a status ------------
#
# `deploy-recipes` names three failures that bite every stack, and the third is a framework
# default that 301/302/307-redirects `GET /` - an HTTPS redirect or a trailing-slash normaliser.
# A redirect is not a 200, so the platform's unauthenticated-200 contract breaks even though the
# route exists and works. FastAPI ships `redirect_slashes=True`, so this project HAS such a
# normaliser: measured, `/healthz/` returns 307 to `/healthz`.
#
# That is benign, because the platform probes the canonical paths, and turning the normaliser off
# would make a trailing slash a 404 rather than a 307 - worse, not better. What must be pinned is
# that the CANONICAL paths never redirect, which is the actual contract and the thing a future
# middleware (a forced-HTTPS redirect, a base-path rewrite) would silently break.

#: The paths the platform probes, unauthenticated, expecting exactly 200.
CONTRACT_PATHS = ("/", "/healthz", "/readyz", "/livez", "/ping", "/health")


@pytest.mark.parametrize("path", CONTRACT_PATHS)
def test_a_contract_path_answers_200_and_never_redirects(path: str) -> None:
    """Not merely "2xx or 3xx eventually": 200 on the first response, with no Location.

    Asserted with redirects NOT followed. A test client that follows them would report 200 for a
    route that answers 307, which is exactly how this class of failure reaches an upload.
    """
    from fastapi.testclient import TestClient

    from enlightenment.app import create_app
    from enlightenment.config import load_config

    with tempfile.TemporaryDirectory() as data_dir:
        app = create_app(config=load_config(env={"DATA_DIR": data_dir}))
        with TestClient(app, follow_redirects=False) as client:
            response = client.get(path)
    assert response.status_code == 200, (
        f"{path} answered {response.status_code}"
        f"{' -> ' + str(response.headers.get('location')) if response.is_redirect else ''}"
    )
    assert "location" not in response.headers, f"{path} redirects, so it is not a 200 contract path"


def test_the_build_script_honours_an_explicit_engine_override() -> None:
    """`ENLIGHTENMENT_CONTAINER_ENGINE` must win over PATH discovery.

    This is the seam the three deferral tests above rely on, and it went untested when it was
    added. Without it those tests depend on which engines the runner happens to have - which is
    exactly how they passed here and failed in CI, where Podman is installed and this authoring
    environment has neither engine.
    """
    with tempfile.TemporaryDirectory() as workspace:
        engine = Path(workspace) / "chosen-engine"
        engine.write_text(
            '#!/bin/sh\ncase "$1" in info) exit 0 ;; --version) echo chosen ;;'
            " build) echo built ; exit 0 ;; esac\n",
            encoding="utf-8",
        )
        engine.chmod(0o755)
        shell = shutil.which("sh")
        assert shell, "no POSIX shell on PATH"
        result = subprocess.run(  # noqa: S603 - a resolved shell and a fixed, in-repo script
            [shell, str(ROOT / "scripts" / "build-image.sh"), "enlightenment:override"],
            capture_output=True,
            text=True,
            env={**os.environ, "ENLIGHTENMENT_CONTAINER_ENGINE": str(engine)},
            cwd=str(ROOT),
            timeout=120,
            check=False,
        )
    assert "chosen-engine" in result.stdout, (
        f"the override was ignored; the script chose something else: {result.stdout[:200]}"
    )
    assert result.returncode == 0, result.stderr[-300:]


def test_the_build_script_prefers_podman_because_the_platform_uses_it() -> None:
    """Podman first, Docker fallback. Asserted because the ORDER is the contract.

    `appstore-gate-compliance` and the owner's check list both say the containerize stage builds
    with Podman. Building locally with a different engine hides differences in default build
    backends, unqualified-name resolution and rootless UID mapping.
    """
    lines = _live_lines(ROOT / "scripts" / "build-image.sh")
    candidates = next(line for line in lines if "for candidate in" in line)
    assert candidates.index("podman") < candidates.index("docker"), (
        f"Docker is tried before Podman, which is not what the platform uses: {candidates}"
    )


@pytest.mark.parametrize(
    ("description", "line", "secret"),
    [
        (
            "userinfo straddling the length cut",
            "pkg @ https://oauth2accesstoken:ya29." + "A" * 520 + "@eu.pkg.dev/p/r/pkg.whl",
            "AAAAAAAAAAAAAAAAAAAA",
        ),
        (
            "a control character breaking the authority run",
            "pkg @ https://ghp_" + "B" * 40 + "\x0btail@host.invalid/x.whl",
            "BBBBBBBBBBBBBBBBBBBB",
        ),
        (
            "a unicode line separator doing the same",
            "pkg @ https://ghp_" + "B" * 40 + "\u2028t@host.invalid/x.whl",
            "BBBBBBBBBBBBBBBBBBBB",
        ),
        (
            "a credential as a query parameter",
            "pkg @ https://host.invalid/x.whl?password=ghp_" + "C" * 30,
            "CCCCCCCCCCCCCCCCCCCC",
        ),
        (
            "a presigned URL signature",
            "pkg @ https://bucket.s3.invalid/p.whl?X-Amz-Signature=" + "D" * 40,
            "DDDDDDDDDDDDDDDDDDDD",
        ),
    ],
    ids=["straddles the cut", "control character", "unicode separator", "query param", "presigned"],
)
def test_no_credential_survives_the_truncation_or_the_separators(
    description: str, line: str, secret: str
) -> None:
    """The three bypasses the security gate found in the fix for the previous three.

    The straddle case is the serious one and it was MY fix that created it. Truncation was added
    to stop a fourteen-second stall, and it ran BEFORE redaction, so a cut landing inside
    userinfo removed the `@` the pattern anchors on. Measured on the documented Google Artifact
    Registry form: 463 characters of the access token reached stderr, which lands in a CI log.
    A control whose own performance fix discloses the credential is worse than the stall.

    The separators are the same shape one layer down: `\\s` in the authority pattern matches
    `\\x0b` and the Unicode line separators, so one embedded control character terminated the run
    early and the token printed in full. pip rejects such a line, which is exactly why it reaches
    the report that exists to echo lines no tool would accept.
    """
    result = _run_environment_check(f"{line}\n")
    assert result.returncode != 0
    assert secret not in result.stderr, f"{description}: the credential reached stderr"


def test_an_unusable_explicit_engine_fails_rather_than_falling_back() -> None:
    """An explicit override that does not work is an error, not a hint.

    Falling through to PATH discovery would build with an engine the caller did not ask for, and
    a silent fallback on this exact seam is how three tests drifted from the runner they ran on.
    Exit 2, distinct from the deferral's exit 3, so the two conditions are never confused.
    """
    shell = shutil.which("sh")
    assert shell, "no POSIX shell on PATH"
    result = subprocess.run(  # noqa: S603 - a resolved shell and a fixed, in-repo script
        [shell, str(ROOT / "scripts" / "build-image.sh"), "enlightenment:override"],
        capture_output=True,
        text=True,
        env={**os.environ, "ENLIGHTENMENT_CONTAINER_ENGINE": "/bin/false"},
        cwd=str(ROOT),
        timeout=120,
        check=False,
    )
    assert result.returncode == 2, (
        f"expected the explicit-override failure, got {result.returncode}"
    )
    assert "not runnable" in result.stderr


def test_packaging_refuses_a_version_that_disagrees_with_the_declared_one() -> None:
    """The guard was load-bearing and had zero coverage: deleting it left the suite green.

    It exists because this repository built an 0.18.0 archive from a tree declaring 0.17.0, and
    an inspection keyed on the declared version then examined a different file from the one just
    written and reported it clean. `_latest_artefact()` cannot cover the refusal branch, because
    it always invokes the script WITH the declared version.
    """
    shell = shutil.which("sh")
    assert shell, "no POSIX shell on PATH"
    forged = "0.0.0-not-the-declared-version"
    result = subprocess.run(  # noqa: S603 - a resolved shell and a fixed, in-repo script
        [shell, str(ROOT / "scripts" / "package-appstore.sh"), forged],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=300,
        check=False,
    )
    assert result.returncode == 2, f"the mismatch was accepted: {result.stdout[-300:]}"
    assert _pyproject()["project"]["version"] in result.stderr
    assert not (ROOT / "dist" / f"enlightenment-appstore-{forged}.zip").exists(), (
        "an archive was written for a version the tree does not declare"
    )


def test_the_physics_core_is_unreachable_from_any_http_route() -> None:
    """An import-graph property, asserted because it was claimed and unpinned.

    Both binding gates verified by inspection that nothing outside `src/enlightenment/physics/`
    imports the package, so a fabricated state vector or the `sgp4` extension's measured
    non-determinism cannot be reached from the edge. Nothing STOPPED a future route reaching it.

    Run in a SUBPROCESS, and that is the whole reason this works. The first version cleared
    `physics` and `sgp4` out of `sys.modules` and re-imported `create_app` in-process, which
    proves nothing: `enlightenment.app` is already cached from earlier tests, so its import
    statements never execute again. Mutation-proved - a `from enlightenment.physics import ...`
    added to `app.py` SURVIVED that version. A clean interpreter cannot be fooled by session
    state.
    """
    probe = (
        "import sys, tempfile\n"
        "from enlightenment.app import create_app\n"
        "from enlightenment.config import load_config\n"
        "with tempfile.TemporaryDirectory() as d:\n"
        "    create_app(config=load_config(env={'DATA_DIR': d}))\n"
        # `.scenario` is checked as well as `.physics`. The determinism substrate is unreachable
        # from the edge today, and nothing pinned that: the census pattern named only the physics
        # package, so a route reaching the scenario engine would have gone unnoticed by the very
        # test written to notice it.
        "reached = sorted(\n"
        "    n for n in sys.modules\n"
        "    if '.physics' in n or '.scenario' in n or n.startswith('sgp4')\n"
        ")\n"
        "print('\\n'.join(reached))\n"
    )
    result = subprocess.run(  # noqa: S603 - a resolved interpreter and a constant probe
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, f"the probe could not build the app: {result.stderr[-400:]}"
    reached = [line for line in result.stdout.splitlines() if line.strip()]

    # **The invariant NARROWED when the drill layer landed, and the narrowing is deliberate.**
    # Originally nothing under `.physics` or `.scenario` could be reached from the edge at all.
    # The flight plan then requires the opposite for the drill surfaces: "the drill layer consumes
    # the same physics core ... it gets no privileged path, no separate physics." A drill that drew
    # a relative track by hand instead of solving the dynamics would teach operators to recognise a
    # picture rather than a signature the orbit produces, which is the product's whole premise
    # inverted. So the pure, closed-form helpers are now reachable on purpose.
    #
    # What is NOT admitted, and this is the half that carried the original risk: the `sgp4`
    # extension, whose measured non-determinism is the reason this test exists, and any path that
    # would let an operator-supplied value become a state vector. Nothing on the drill path accepts
    # a state vector from the wire; the seed is derived server-side and every plot generator takes
    # an item id and an integer.
    extension = [name for name in reached if name.startswith("sgp4")]
    assert not extension, (
        "building the application imported the sgp4 extension, so its measured non-determinism is"
        f" now reachable from the HTTP edge: {extension}. Propagation belongs behind an authoring"
        " step or a scenario pre-warm, never on a request path."
    )


# --- workstation tools: built, proved, and never shipped -----------------------------


UDL_TOOL = ROOT / "tools" / "udl_characterise.py"


def _udl_tool_or_skip() -> Path:
    """The characteriser, or a written skip when we are running INSIDE the upload artefact.

    Continuous integration was red for eight consecutive runs, 48 through 55, and nothing
    surfaced it because the local loop was green throughout. The pipeline simulation unpacks the
    App Store zip and runs this suite from inside it; the zip stages `src tests scripts docs
    content .github` and deliberately NOT `tools`, because `udl_characterise.py` reads real UDL
    credentials and must never ship. So nineteen tests in this file asserted on a file that the
    test three definitions above proves must not be there. The suite contradicted itself.

    `PLATFORM_MANAGED_ABSENCES` already carries the doctrine: a check that cannot run in an
    environment must SKIP with a written reason, never fail. This is the same doctrine and a
    DIFFERENT reason, so it gets its own discriminator rather than being folded into that tuple.

    The discriminator is deliberately narrow, because a skip that fires too easily is how a
    deleted control goes unnoticed. It is not "the file is missing". It is "the whole `tools`
    directory is gone AND there is no checkout", which together describe an unpacked artefact
    and nothing else. Delete the tool in a repository and `.git` is still there, so these tests
    FAIL, loudly, which is the behaviour that matters.
    """
    if UDL_TOOL.is_file():
        return UDL_TOOL
    if not (ROOT / "tools").exists() and not (ROOT / ".git").exists():
        pytest.skip(
            "tools/ is absent and so is .git, which is the unpacked upload artefact. The"
            " characteriser is excluded from the artefact on purpose"
            " (test_the_workstation_tools_never_reach_the_upload_or_the_image asserts both"
            " exclusions), so it is not assertable here. It runs locally and in the CI test job."
        )
    pytest.fail(f"{UDL_TOOL} is missing from a checkout; flight plan step 4 depends on it")


def test_the_characteriser_is_tracked_in_the_repository() -> None:
    """The converse of the skip above: in a checkout, the tool must actually be there.

    Without this, deleting `tools/udl_characterise.py` AND `tools/` in one commit would make
    nineteen tests skip rather than fail anywhere the artefact is what runs. Reading it from
    `git ls-files` rather than the filesystem means an untracked stray copy does not satisfy it.

    The checkout guard comes BEFORE the binary guard, and the order is the point. The pipeline
    simulation masks `git` with a stub that exits 127 rather than removing it, so `shutil.which`
    finds something and `_git_or_skip` does not fire; the artefact has no `.git` at all, which is
    the honest reason this question cannot be asked there.
    """
    if not (ROOT / ".git").exists():
        pytest.skip(
            "there is no checkout here, which is the unpacked artefact. Whether a file is tracked"
            " in a repository is not a question that can be asked from outside the repository."
        )
    tracked = subprocess.run(  # noqa: S603 - a resolved binary and a fixed, in-repo path
        [
            _git_or_skip(),
            "-C",
            str(ROOT),
            "ls-files",
            "--error-unmatch",
            "tools/udl_characterise.py",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert tracked.returncode == 0, (
        "tools/udl_characterise.py is not tracked in this repository, so the artefact-side skip"
        f" in _udl_tool_or_skip would hide its absence: {tracked.stderr.strip()}"
    )


def test_the_workstation_tools_never_reach_the_upload_or_the_image() -> None:
    """`tools/` runs on the networked workstation and must not ship, in either contract.

    The flight plan is explicit - "Runs on the networked workstation, never in the container" - and
    this is the file that reads real UDL credentials. Both exclusions are asserted, because they are
    separate mechanisms and either one alone would let the file through the other: the upload
    allowlist in `scripts/package-appstore.sh` shapes the ZIP, and `.dockerignore` shapes the
    image build context.
    """
    script = (ROOT / "scripts" / "package-appstore.sh").read_text(encoding="utf-8")
    directory_loop = re.search(r"^for dir in (.+); do$", script, re.MULTILINE)
    assert directory_loop is not None, "the packaging script's directory allowlist moved"
    staged = directory_loop.group(1).split()
    assert "tools" not in staged, f"tools/ is in the upload allowlist: {staged}"

    ignored = {
        line.strip()
        for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert "tools" in ignored, "tools/ is not excluded from the image build context"


def test_the_vendored_typeface_digests_match_the_files_on_disk() -> None:
    """`design/phosphor/fonts/DIGESTS.md` pins six third-party binaries; recompute it.

    The table was correct when it was written and bound by nothing, so a swapped `woff2` would
    have left the pinning CLAIM intact and false. A digest nobody recomputes is a comment. The
    directory never ships, which caps the impact, but the whole point of recording a digest is
    that somebody can tell whether the file is still the file.
    """
    fonts = ROOT / "design" / "phosphor" / "fonts"
    # The same discriminator as `_udl_tool_or_skip`, for the same reason and a different
    # directory: `design/` is excluded from the upload on purpose, asserted two definitions
    # above, so inside the unpacked artefact there is nothing here to recompute. Narrow on
    # purpose - delete `design/` in a REPOSITORY and `.git` is still there, so this fails.
    if not (ROOT / "design").exists() and not (ROOT / ".git").exists():
        pytest.skip(
            "design/ is absent and so is .git, which is the unpacked upload artefact. The"
            " typefaces are excluded from the artefact on purpose"
            " (test_the_design_directory_never_reaches_the_upload_or_the_image asserts both"
            " exclusions), so there is nothing here to recompute."
        )
    recorded = {
        match.group(1): (int(match.group(2)), match.group(3))
        for match in re.finditer(
            r"^\| `([^`]+\.woff2)` \| (\d+) \| `([0-9a-f]{64})` \|$",
            (fonts / "DIGESTS.md").read_text(encoding="utf-8"),
            re.MULTILINE,
        )
    }
    on_disk = sorted(path.name for path in fonts.glob("*.woff2"))
    assert on_disk, "no vendored typeface was found, so this test proves nothing"
    assert sorted(recorded) == on_disk, (
        f"DIGESTS.md records {sorted(recorded)} and the directory holds {on_disk}"
    )
    for name, (size, digest) in recorded.items():
        blob = (fonts / name).read_bytes()
        assert len(blob) == size, f"{name} is {len(blob)} bytes, DIGESTS.md says {size}"
        assert hashlib.sha256(blob).hexdigest() == digest, f"{name} is not the file that was pinned"


def test_the_content_validator_runs_as_a_verification_leg() -> None:
    """The content package's own validator is a leg of the loop, before any code analyser.

    Cited by two rows in `docs/SECURITY.md` that record controls which moved UPSTREAM in V0.24.0:
    the redaction discipline over authored content, and the strictness that the engine's models
    deliberately gave up when they adopted `extra="allow"`. Both now rest on this file running, so
    a change that dropped the leg would silently remove two controls at once.

    Run rather than reimplemented, and excluded from ruff, because it is vendored: it ships inside
    Ash's package and is the authority on whether the content is valid.
    """
    loop = (ROOT / "scripts" / "verify.sh").read_text(encoding="utf-8")
    assert "tools/validate_content.py" in loop, "the content validator is not a leg of the loop"
    assert "--self-test" in loop, "the validator runs without its own self-test"
    assert loop.index("tools/validate_content.py") < loop.index("-m ruff"), (
        "the content leg must run BEFORE the analysers: the content is the asset, and ten seconds"
        " of validation is the cheapest rung that can catch a content fault"
    )
    # The loop text and the ruff exclusion both ship. The validator itself does NOT: `tools/` is
    # excluded from the upload on purpose, so inside the unpacked artefact there is no file to
    # stat. Same narrow discriminator as `_udl_tool_or_skip`: `tools/` gone AND no checkout is an
    # artefact and nothing else, and deleting the validator in a repository still fails here.
    if (ROOT / "tools").exists() or (ROOT / ".git").exists():
        assert (ROOT / "tools" / "validate_content.py").is_file(), (
            "the content validator is cited by two register rows and is not on disk"
        )
    excluded = _pyproject()["tool"]["ruff"].get("extend-exclude", [])
    assert "tools/validate_content.py" in excluded, (
        "the vendored validator must be excluded from format and lint, or every package update"
        " becomes a merge against a reformatted copy"
    )


def test_the_design_directory_never_reaches_the_upload_or_the_image() -> None:
    """`design/` holds third-party font binaries and a Node tool, and ships in neither contract.

    Added after both binding gates independently proved the same mutant: put `design` in the
    packaging allowlist and the suite stays green while 131 kB of third-party woff2 and a
    Playwright harness ride into a SonarQube-scanned upload. `tools/` has had this guard since
    V0.23.6; the directory that arrived in V0.23.15 had nothing. The posture was already
    correct - the allowlist is positive, so a new directory is excluded by construction - but a
    posture with no test is a posture that survives until somebody edits one line.
    """
    script = (ROOT / "scripts" / "package-appstore.sh").read_text(encoding="utf-8")
    directory_loop = re.search(r"^for dir in (.+); do$", script, re.MULTILINE)
    assert directory_loop is not None, "the packaging script's directory allowlist moved"
    staged = directory_loop.group(1).split()
    assert "design" not in staged, f"design/ is in the upload allowlist: {staged}"

    ignored = {
        line.strip()
        for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert "design" in ignored, "design/ is not excluded from the image build context"


def test_the_udl_characteriser_proves_itself_with_no_network_and_no_credentials() -> None:
    """`--self-test` must pass here, where there is no UDL and no credential file.

    The point of the mode is that the ANALYSIS half is verifiable before anything touches a live
    service, so this test is also the check that it stayed that way: a self-test that quietly grew a
    network dependency would fail here rather than on the workstation, halfway through a
    characterisation run.
    """
    result = subprocess.run(  # noqa: S603 - a resolved interpreter and a fixed, in-repo script
        [sys.executable, str(_udl_tool_or_skip()), "--self-test"],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
        timeout=120,
    )
    assert result.returncode == 0, f"self-test failed:\n{result.stderr[-2000:]}"
    manifest = json.loads(result.stdout)
    assert manifest["passed"] is True
    assert manifest["failed"] == []
    # A manifest with no assertions in it would also report `passed`. The floor is a measurement,
    # not a guess: the suite carries fourteen and a drop below ten means assertions were deleted
    # rather than the tool improved.
    assert manifest["count"] >= 10, f"the assertion manifest shrank to {manifest['count']}"


def test_the_characteriser_refuses_to_fetch_without_an_endpoint_profile() -> None:
    """No profile means no request. The tool does not guess a UDL API shape, and says so.

    This is the mechanical half of the ask: the missing base address, endpoint paths and field names
    are facts about the UDL API that nobody has supplied, and inventing them would be a fabricated
    integration that looks like a working one until it is run.
    """
    result = subprocess.run(  # noqa: S603 - a resolved interpreter and a fixed, in-repo script
        [
            sys.executable,
            str(_udl_tool_or_skip()),
            "--start",
            "2026-01-01T00:00:00Z",
            "--end",
            "2026-01-02T00:00:00Z",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
        timeout=60,
    )
    assert result.returncode == 2, result.stdout[-500:]
    assert "--profile is required" in result.stderr
    assert "does not guess an API shape" in result.stderr


def test_the_characteriser_refuses_a_non_https_endpoint() -> None:
    """An operator typo must not turn a retrieval into a local file read.

    `urllib.request.urlopen` honours `file:` and every other registered scheme, and the request
    carries live credentials in an Authorization header. The scheme is allowlisted to https in the
    profile loader, refused rather than silently corrected, because rewriting `http` to `https`
    would hide a profile that is wrong about more than its scheme.
    """
    with tempfile.TemporaryDirectory() as raw_directory:
        profile = Path(raw_directory) / "profile.ini"
        template = subprocess.run(  # noqa: S603 - a resolved interpreter, fixed in-repo script
            [sys.executable, str(_udl_tool_or_skip()), "--print-profile-template"],
            capture_output=True,
            text=True,
            check=True,
            cwd=ROOT,
            timeout=60,
        ).stdout
        # The base address and the paths are pre-filled in the shipped template, so the base
        # address is REPLACED rather than filled in, and only the two required field names are
        # added. Every substitution is asserted, because this test previously used a `str.replace`
        # whose anchor stopped matching once the template gained pre-filled values: the no-op left
        # a perfectly valid https profile, the run failed later on a missing credentials file, and
        # a green-looking test was asserting nothing whatsoever about the scheme.
        filled = template
        for old, new in (
            ("base_url = https://unifieddatalibrary.com", "base_url = file:///etc"),
            ("sensor_id =", "sensor_id = sensorId"),
            ("object_identifier =", "object_identifier = idOnOrbit"),
        ):
            assert old in filled, f"the profile template no longer contains {old!r}"
            filled = filled.replace(old, new, 1)
        assert "file:///etc" in filled
        profile.write_text(filled, encoding="utf-8")

        result = subprocess.run(  # noqa: S603 - a resolved interpreter, fixed in-repo script
            [
                sys.executable,
                str(_udl_tool_or_skip()),
                "--profile",
                str(profile),
                "--start",
                "2026-01-01T00:00:00Z",
                "--end",
                "2026-01-02T00:00:00Z",
            ],
            capture_output=True,
            text=True,
            check=False,
            cwd=ROOT,
            timeout=60,
        )
    assert result.returncode == 2, result.stdout[-500:]
    assert "must be an https:// address" in result.stderr


def test_the_credentials_permission_check_is_platform_aware() -> None:
    """The POSIX bit check does not transfer to Windows, and shipping as if it did broke the tool.

    `os.stat().st_mode` on Windows carries SYNTHETIC permission bits - 0o666 for any writable file -
    so `mode & 0o077` is 0o066 on a perfectly well-protected file. The first version refused EVERY
    Windows credentials file and told the operator to run `chmod 600`, which is not a PowerShell
    command. The operator found it by running the tool on the machine it is for.

    Both branches are asserted here, on the source rather than by running it, because this suite
    runs on Linux and the Windows branch is unreachable from it. A source assertion is weaker than
    an execution, and it is stated as such: what it holds is that neither branch has been deleted,
    and that the Windows branch checks something real rather than skipping.
    """
    source = _udl_tool_or_skip().read_text(encoding="utf-8")
    checker = source[source.index("def _assert_owner_only") : source.index("def load_credentials")]

    assert 'if os.name != "nt":' in checker, "the platform split is gone"
    assert "0o077" in checker, "the POSIX mode check is gone"
    # The Windows branch must CHECK something, not return early. Its control is location: a file
    # inside the user profile is ACL-restricted to that user by Windows default.
    skipped = (
        "the Windows branch no longer verifies the file is inside the user profile, which would"
        " make it a skip - and a control that cannot be verified is treated as failed"
    )
    assert "Path.home()" in checker, skipped
    assert "relative_to" in checker, skipped
    assert "raise RuntimeError" in checker.split('if os.name != "nt":')[1].split("home =")[1], (
        "the Windows branch does not refuse anything"
    )
    # The remedy printed must match the platform it is printed on. `chmod` belongs only to the
    # POSIX branch; naming it in the Windows message is how the first version misled the operator.
    windows_branch = checker.split("home = Path.home().resolve()")[1]
    assert "chmod" not in windows_branch, "the Windows branch tells the operator to run chmod"


def test_the_posix_credentials_check_refuses_a_group_readable_file() -> None:
    """The POSIX branch, EXECUTED rather than read, since this suite runs on POSIX."""
    if os.name == "nt":  # pragma: no cover - this suite's CI is Linux
        pytest.skip("the POSIX branch is not reachable on Windows")
    spec = importlib.util.spec_from_file_location("udl_characterise", _udl_tool_or_skip())
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before execution: `@dataclass(slots=True)` resolves its own module through
    # `sys.modules`, and an unregistered module raises inside `dataclasses` rather than in the
    # code under test, which makes the failure look like a bug in the tool.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)

    with tempfile.TemporaryDirectory() as raw_directory:
        credentials = Path(raw_directory) / "credentials.ini"
        credentials.write_text("[udl]\nusername = synthetic\npassword = synthetic\n", "utf-8")

        credentials.chmod(0o640)
        with pytest.raises(RuntimeError, match="readable beyond its owner"):
            module.load_credentials(credentials)

        credentials.chmod(0o600)
        assert module.load_credentials(credentials) == ("synthetic", "synthetic")


def _load_udl_tool() -> Any:
    """Load `tools/udl_characterise.py` as a module, the way the POSIX credentials test does.

    Registered in `sys.modules` before execution: `@dataclass(slots=True)` resolves its own module
    through `sys.modules`, and an unregistered module raises inside `dataclasses` rather than in the
    code under test, which makes the failure look like a bug in the tool.
    """
    spec = importlib.util.spec_from_file_location("udl_characterise", _udl_tool_or_skip())
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def _udl_profile(module: Any, directory: str) -> Any:
    """The shipped template, with only the [fields] keys a profile REQUIRES filled in.

    Filled here rather than in the template because they are the half the documentation does not
    cover: the operator reads them off `--queryhelp`. Everything else comes from the template
    unedited, so these tests assert what actually ships.
    """
    profile_path = Path(directory) / "udl-profile.ini"
    profile_path.write_text(
        module.PROFILE_TEMPLATE.replace("sensor_id =", "sensor_id = senId").replace(
            "object_identifier =", "object_identifier = idOnOrbit"
        ),
        encoding="utf-8",
    )
    return module.Profile.load(profile_path)


def test_the_udl_profile_template_is_complete_except_for_the_record_field_names() -> None:
    """The template must need nothing from the operator but the per-entity FIELD names.

    The API mechanics are documented, so leaving an endpoint or a pagination parameter blank in the
    template is work handed back to the operator for no reason. The field names are the opposite
    case: the documentation does not carry them, so pre-filling them would be a guess wearing the
    authority of a shipped default. This test pins that split, and fails if the template ever
    drifts either way.
    """
    module = _load_udl_tool()
    with tempfile.TemporaryDirectory() as directory:
        profile_path = Path(directory) / "udl-profile.ini"
        profile_path.write_text(module.PROFILE_TEMPLATE, encoding="utf-8")
        with pytest.raises(module.ProfileError) as raised:
            module.Profile.load(profile_path)

    message = str(raised.value)
    assert "[endpoints]" not in message, f"the template ships an unfilled endpoint: {message}"
    assert "[query]" not in message, f"the template ships an unfilled query parameter: {message}"
    assert "[fields] sensor_id" in message
    assert "[fields] object_identifier" in message


def test_every_udl_query_disables_the_capco_marking_extensions() -> None:
    """The URL builder must carry `disableCapcoExtensions=true`, on every path, always.

    This is a BOUNDARY control, not a preference. UDL extends CAPCO markings on proprietary and
    limited-distribution records to `U//PR-OWNER-DATATYPE`, and the marking distribution is the one
    measure the tool emits verbatim. Without the flag the emitted parameter file would carry the
    identity of every contributing provider across the boundary under the name of a distribution.

    Asserted on the built URL rather than by reading the source, because the point is that the
    parameter survives into the request, and asserted for both the count and the page path, since
    they are separate call sites and either one alone would leak.
    """
    module = _load_udl_tool()
    with tempfile.TemporaryDirectory() as directory:
        fetcher = module.Fetcher(
            profile=_udl_profile(module, directory),
            credentials=("synthetic", "synthetic"),
        )
        for path in ("/udl/elset/history", "/udl/elset/history/count"):
            url = fetcher._url(path, {"epoch": "a..b"})  # the URL builder is the unit under test
            assert "disableCapcoExtensions=true" in url, (
                f"{path} is queried without disabling the CAPCO marking extensions, so a data"
                f" owner can reach the emitted marking distribution: {url}"
            )


def test_the_udl_profile_template_ranges_elsets_on_epoch_not_obtime() -> None:
    """Two entities, two time fields. One shared field would silently return nothing.

    The documented query grammar ranges element sets on `epoch` and observations on `obTime`, and
    an unrecognised query parameter yields an EMPTY result rather than an error. That failure mode
    is invisible: the epoch-spacing measure would simply report no element sets, and a parameter
    file with a missing measure looks the same as a quiet window.
    """
    module = _load_udl_tool()
    with tempfile.TemporaryDirectory() as directory:
        profile = _udl_profile(module, directory)

    assert profile.query["time_field"] == "obTime"
    assert profile.query["elset_time_field"] == "epoch", (
        "the shipped template does not range element sets on epoch"
    )
    assert profile.endpoints["elset_count_path"] == profile.endpoints["elset_history_path"] + (
        "/count"
    ), "a count path is a query path plus /count; the template no longer follows the convention"


def test_the_queryhelp_entity_name_is_validated_before_it_reaches_a_url() -> None:
    """`--queryhelp` takes an operator-typed token and puts it into a credentialled URL.

    Refused rather than escaped: quoting a traversal into something harmless would hide a typo
    instead of reporting it, and the tool's whole stance is that an unverifiable input fails closed.
    """
    module = _load_udl_tool()
    assert module.queryhelp_url("https://example.invalid", "eoobservation") == (
        "https://example.invalid/udl/eoobservation/queryhelp"
    )
    for hostile in ("../../udl/elset", "eo/observation", "EOObservation", "", "a"):
        with pytest.raises(RuntimeError, match="is not an entity name"):
            module.queryhelp_url("https://example.invalid", hostile)


def test_the_udl_time_field_reaches_the_request_per_entity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The headline fix, asserted on the WIRE rather than on the template's strings.

    `test_the_udl_profile_template_ranges_elsets_on_epoch_not_obtime` reads the shipped template
    and proves nothing about what is sent, so both mutations that matter survived it: reverting the
    live call site to one shared field, and making `_range` ignore its argument and re-read the
    profile. Either would restore the defect - an unrecognised UDL parameter returns an EMPTY
    RESULT rather than an error, so epoch spacing reports UNAVAILABLE and reads as a quiet window -
    with the suite still green.

    So this drives real fetches with the transport stubbed and reads the URLs. The observation
    count is over the offset cap to force one bisection, which is the other path `time_field` is
    threaded through and the one a recursive call could quietly drop.
    """
    module = _load_udl_tool()
    with tempfile.TemporaryDirectory() as directory:
        fetcher = module.Fetcher(
            profile=_udl_profile(module, directory),
            credentials=("synthetic", "synthetic"),
        )

    seen: list[str] = []

    def _stub(url: str, accept: str, credentials: tuple[str, str], timeout: float) -> str:
        seen.append(url)
        if url.partition("?")[0].endswith("/count"):
            # Over the cap on the first, whole-window call; under it once bisected.
            return "20000" if len(seen) == 1 else "1"
        return "[]"

    # The module-level `http_get` is patched rather than the bound method: `Fetcher` is a
    # slots dataclass, so an instance attribute cannot be assigned, and this is the single
    # transport function the extraction created for exactly this reason.
    monkeypatch.setattr(module, "http_get", _stub)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 2, tzinfo=UTC)

    fetcher.fetch(
        "/udl/eoobservation/history", "/udl/eoobservation/history/count", start, end, "obTime"
    )
    observation_urls = list(seen)
    assert len(observation_urls) > 2, "the over-cap window did not bisect, so recursion is untested"
    for url in observation_urls:
        assert "obTime=" in url, f"an observation request is not ranged on obTime: {url}"
        assert "epoch=" not in url, f"an observation request is ranged on epoch: {url}"

    seen.clear()
    fetcher.fetch("/udl/elset/history", "/udl/elset/history/count", start, end, "epoch")
    assert seen, "no element-set request was made"
    for url in seen:
        assert "epoch=" in url, f"an element-set request is not ranged on epoch: {url}"
        assert "obTime=" not in url, f"an element-set request is ranged on obTime: {url}"


def test_the_live_fetch_ranges_elsets_on_the_elset_field_and_refuses_a_profile_without_it() -> None:
    """`elset_time_field` is required, and the live path must actually read it.

    It briefly carried a fallback to `time_field`, justified by "a profile written before the key
    existed". No such profile has ever existed, and the fallback failed OPEN into the exact defect
    the key was added to prevent. This pins the LOADER half only - that the key's absence is
    refused. The live path reading the right key is pinned separately, by
    `test_the_live_fetch_ranges_each_entity_on_its_own_time_field`, because a mutation at the call
    site survived this test and its name was the reason nobody noticed.
    """
    module = _load_udl_tool()
    assert "elset_time_field" in module._PROFILE_REQUIRED["query"], (
        "elset_time_field is optional again, so a profile missing it silently ranges element sets"
        " on obTime and reports an empty result as a quiet window"
    )
    with tempfile.TemporaryDirectory() as directory:
        profile_path = Path(directory) / "udl-profile.ini"
        profile_path.write_text(
            module.PROFILE_TEMPLATE.replace("sensor_id =", "sensor_id = senId")
            .replace("object_identifier =", "object_identifier = idOnOrbit")
            .replace("elset_time_field = epoch", "elset_time_field ="),
            encoding="utf-8",
        )
        with pytest.raises(module.ProfileError, match=r"\[query\] elset_time_field"):
            module.Profile.load(profile_path)


def test_queryhelp_refuses_a_non_https_base_url() -> None:
    """The https allowlist on the NEW loader, which the existing scheme test does not reach.

    `test_the_characteriser_refuses_a_non_https_endpoint` drives `Profile.load` through --start and
    --end. `--queryhelp` uses `load_base_url` instead, and removing its `_checked_base_url` call
    left the suite green: a `file:` base_url would have reached `urlopen` on a request carrying live
    credentials, which is the precise case that check exists for.
    """
    module = _load_udl_tool()
    with tempfile.TemporaryDirectory() as directory:
        profile_path = Path(directory) / "udl-profile.ini"
        profile_path.write_text(
            module.PROFILE_TEMPLATE.replace(
                "base_url = https://unifieddatalibrary.com", "base_url = file:///etc"
            ),
            encoding="utf-8",
        )
        with pytest.raises(module.ProfileError, match="must be an https:// address"):
            module.load_base_url(profile_path)

        # And end to end, so the CLI cannot route around the loader.
        result = subprocess.run(  # noqa: S603 - a resolved interpreter, fixed in-repo script
            [
                sys.executable,
                str(_udl_tool_or_skip()),
                "--profile",
                str(profile_path),
                "--queryhelp",
                "elset",
            ],
            capture_output=True,
            text=True,
            check=False,
            cwd=ROOT,
            timeout=60,
        )
    assert result.returncode == 2, result.stdout[-500:]
    assert "must be an https:// address" in result.stderr


def test_the_udl_tool_follows_no_redirect_with_a_credential_in_hand() -> None:
    """A reproduced exfiltration, closed and pinned.

    `urlopen`'s default opener copies every header except content-length and content-type into a
    redirected request and permits http, https and ftp to ANY host, so a 302 from the configured
    host delivered a live Basic credential to an attacker-chosen host in cleartext and returned
    that host's body as if it were UDL's. The https allowlist on `base_url` constrains hop one only.

    Driven against a real local server rather than by reading the source, because the defect lived
    in stdlib behaviour the source does not mention.
    """
    module = _load_udl_tool()
    received: list[tuple[str, str | None]] = []

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            received.append((self.path, self.headers.get("Authorization")))
            if self.path.startswith("/redirect"):
                self.send_response(302)
                self.send_header("Location", f"http://{self.server.server_address[0]}:{port}/steal")
                self.end_headers()
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"[]")

        def log_message(self, *_args: Any) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(RuntimeError, match="follows no redirects"):
            module.http_get(
                f"http://127.0.0.1:{port}/redirect",
                "*/*",
                ("udl-user", "S3cretPassw0rd"),
                10.0,
            )
    finally:
        server.shutdown()
        thread.join(timeout=5)

    assert [path for path, _ in received] == ["/redirect"], (
        f"the redirect was followed, so the credential reached a second host: {received}"
    )


def test_the_marking_distribution_withholds_an_owner_bearing_marking() -> None:
    """The local half of the CAPCO control, which is the half that can be verified here.

    `disableCapcoExtensions=true` is a request-side hint to a system on the far side of the trust
    boundary. If the service renames the parameter, an entity ignores it, a record already stores an
    extended marking, or the operator points `classification_marking` at another field, then
    `U//PR-OWNER-DATATYPE` is emitted verbatim under the name of a distribution and the boundary
    guard does not object: it hunts catalogue numbers and URLs, and an owner token is neither.

    So the shape is enforced where it can be tested. The withheld records are COUNTED, because the
    measure exists to state what proportion of the data is restricted and a silent drop would bias
    that towards unrestricted.
    """
    module = _load_udl_tool()
    result = module._allowlisted_markings(
        Counter(
            {
                "UNCLASSIFIED": 40,
                "U//PR": 7,
                "S//REL TO USA, GBR": 2,
                "U//PR-ACMEDEFENCE-EO": 41,
                "U//DS-SOMEALLIEDNATION-RF": 3,
            }
        )
    )
    distribution = result["classification_marking_distribution"]
    assert distribution == {"UNCLASSIFIED": 40, "U//PR": 7, "S//REL TO USA, GBR": 2}
    assert not any("ACMEDEFENCE" in key or "SOMEALLIEDNATION" in key for key in distribution), (
        f"a data owner reached the emitted distribution: {distribution}"
    )
    assert result["classification_markings_withheld"]["records"] == 44
    assert result["classification_markings_withheld"]["distinct_markings"] == 2


def test_the_udl_base_url_refuses_userinfo_and_a_path() -> None:
    """Scheme-only was not enough, and that gap was real.

    `https://unifieddatalibrary.com@evil.example` passes a scheme check, reads as the documented
    host, and connects to the attacker's, on a request holding the credential header.
    """
    module = _load_udl_tool()
    hostile = {
        "https://unifieddatalibrary.com@evil.example": "userinfo section",
        "https:/x": "no host",
        "https://unifieddatalibrary.com/udl": "no path, query or fragment",
        "https://unifieddatalibrary.com?a=b": "no path, query or fragment",
    }
    with tempfile.TemporaryDirectory() as directory:
        profile_path = Path(directory) / "udl-profile.ini"
        for base, expected in hostile.items():
            profile_path.write_text(
                module.PROFILE_TEMPLATE.replace(
                    "base_url = https://unifieddatalibrary.com", f"base_url = {base}"
                ),
                encoding="utf-8",
            )
            with pytest.raises(module.ProfileError, match=re.escape(expected)):
                module.load_base_url(profile_path)


def test_the_queryhelp_body_passes_the_boundary_guard_before_it_is_printed() -> None:
    """An untrusted remote body is checked, not assumed, before the operator is told to forward it.

    The runbook tells the operator this response can be pasted to me. That claim was made in four
    places and enforced nowhere, while the repository already owned the guard that tests it. A
    schema legitimately carries `$ref` addresses, so only the catalogue-number half applies, and
    that exemption is asserted here too: a guard quietly widened to let everything through is the
    failure mode a boolean flag invites.
    """
    module = _load_udl_tool()
    schema = {"$ref": "https://unifieddatalibrary.com/schema", "field": "obTime"}
    module.assert_crossable(schema, check_urls=False)
    with pytest.raises(module.BoundaryError, match="holds a URL"):
        module.assert_crossable(schema)
    with pytest.raises(module.BoundaryError, match="catalogue number"):
        module.assert_crossable({"example": "satNo 25544 for instance"}, check_urls=False)


def _udl_profile_path(module: Any, directory: str) -> Path:
    """A COMPLETE profile on disk: the shipped template plus the two required field names."""
    path = Path(directory) / "udl-profile.ini"
    path.write_text(
        module.PROFILE_TEMPLATE.replace("sensor_id =", "sensor_id = senId").replace(
            "object_identifier =", "object_identifier = idOnOrbit"
        ),
        encoding="utf-8",
    )
    return path


def test_the_live_fetch_ranges_each_entity_on_its_own_time_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CALL SITE, not the plumbing. This is where the defect actually lived.

    `test_the_udl_time_field_reaches_the_request_per_entity` passes the field to `fetch` as a
    literal, so it pins `Fetcher` and says nothing about which field `_live_inputs` chooses. That
    left the original bug reintroducible with all 824 tests green: change one line in `_live_inputs`
    back to the shared field and element sets are ranged on `obTime` again, which returns an empty
    result rather than an error and reads as a quiet window.

    So this drives `_live_inputs` itself with the transport and the credentials patched, and reads
    the URLs it actually produced.
    """
    module = _load_udl_tool()
    seen: list[str] = []

    def _stub(url: str, accept: str, credentials: tuple[str, str], timeout: float) -> str:
        seen.append(url)
        return "1" if url.partition("?")[0].endswith("/count") else "[]"

    monkeypatch.setattr(module, "http_get", _stub)
    monkeypatch.setattr(module, "load_credentials", lambda _path: ("synthetic", "synthetic"))

    with tempfile.TemporaryDirectory() as directory:
        args = module._build_parser().parse_args(
            [
                "--profile",
                str(_udl_profile_path(module, directory)),
                "--start",
                "2026-01-01T00:00:00Z",
                "--end",
                "2026-01-02T00:00:00Z",
            ]
        )
        module._live_inputs(args)

    observation = [url for url in seen if "/eoobservation/" in url]
    elset = [url for url in seen if "/elset/" in url]
    assert observation, f"the observation entity was never fetched: {seen}"
    assert elset, f"the element-set entity was never fetched: {seen}"
    for url in observation:
        assert "obTime=" in url, f"an observation request lost obTime: {url}"
        assert "epoch=" not in url, f"an observation request was ranged on epoch: {url}"
    for url in elset:
        assert "epoch=" in url, f"an element-set request lost epoch: {url}"
        assert "obTime=" not in url, f"an element-set request was ranged on obTime: {url}"


def test_queryhelp_refuses_and_saves_a_body_that_fails_the_boundary_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`_cmd_queryhelp` end to end, both branches, because deleting its guard call left the suite
    green.

    `test_the_queryhelp_body_passes_the_boundary_guard_before_it_is_printed` exercises
    `assert_crossable` directly and never enters the command, and the only end-to-end queryhelp test
    returns 2 at `load_base_url` before reaching the guard. So the enforcement point itself was
    unprotected: remove the call and an unvalidated remote body goes to stdout under a runbook
    promise that it is safe to forward.
    """
    module = _load_udl_tool()
    monkeypatch.setattr(module, "load_credentials", lambda _path: ("synthetic", "synthetic"))
    monkeypatch.chdir(tmp_path)
    profile = _udl_profile_path(module, str(tmp_path))

    dirty = json.dumps({"parameter": "satNo", "description": "for example 25544"})
    monkeypatch.setattr(module, "http_get", lambda *_args, **_kwargs: dirty)
    assert module.main(["--profile", str(profile), "--queryhelp", "elset"]) == 3
    captured = capsys.readouterr()
    assert captured.out == "", "the refused body was printed anyway"
    assert "REFUSED" in captured.err
    saved = tmp_path / "queryhelp-elset.json"
    assert saved.read_text(encoding="utf-8") == dirty, "the refused body was not saved locally"
    if os.name != "nt":
        assert saved.stat().st_mode & 0o777 == 0o600, "the saved body is readable beyond its owner"

    # And the clean branch still prints, or the control would be a denial of the whole mode.
    clean = json.dumps({"parameter": "obTime", "format": "ISO-8601"})
    monkeypatch.setattr(module, "http_get", lambda *_args, **_kwargs: clean)
    assert module.main(["--profile", str(profile), "--queryhelp", "elset"]) == 0
    captured = capsys.readouterr()
    assert "obTime" in captured.out
    assert "REFUSED" not in captured.err


def test_write_private_creates_the_file_narrow_rather_than_narrowing_it_after() -> None:
    """The mode must come from the open, not from a chmod after the fact.

    `write_text` then `chmod` creates at the ambient umask, typically 0644, and narrows afterwards;
    another local user can open it in between, and this writes raw UDL records and unfiltered
    service responses. Reverting to that pattern left the suite green, so the fix was unprotected.

    Both halves are checked: that a fresh file is 0600 with `chmod` sabotaged, so the mode can only
    have come from `os.open`, and that an ALREADY world-readable file is narrowed too, since
    `os.open`'s mode argument applies on creation only.
    """
    if os.name == "nt":  # pragma: no cover - this suite's CI is Linux
        pytest.skip("Windows has no meaningful POSIX mode bits; location is the control there")
    module = _load_udl_tool()
    previous = os.umask(0o000)
    try:
        with tempfile.TemporaryDirectory() as directory:
            fresh = Path(directory) / "fresh.json"
            with unittest.mock.patch.object(
                Path, "chmod", side_effect=AssertionError("_write_private fell back to chmod")
            ):
                module._write_private(fresh, "{}")
            assert fresh.stat().st_mode & 0o777 == 0o600, "the mode did not come from os.open"

            stale = Path(directory) / "stale.json"
            stale.write_text("old", encoding="utf-8")
            stale.chmod(0o644)
            module._write_private(stale, "{}")
            assert stale.stat().st_mode & 0o777 == 0o600, (
                "an existing world-readable file was rewritten and left readable: os.open's mode"
                " applies on creation only"
            )
    finally:
        os.umask(previous)
