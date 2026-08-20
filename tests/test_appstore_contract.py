"""Mechanised App Store upload-gate contract checks.

These assert the CLASS, not one named instance, so a regression cannot reappear quietly.
Every negative assertion below is classified per environment: it is either true in every
checkout, or explicitly gated on the platform runner. No assertion here may be
guaranteed-false on the machine that gates the deploy.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from importlib.metadata import version as installed_version
from pathlib import Path
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
    sweep = re.search(r"^RUN find / -xdev -perm /6000 .*$", DOCKER_INSTRUCTIONS, re.MULTILINE)
    assert sweep, "the suid/sgid sweep is missing"
    line = sweep.group(0)
    assert "-type f" in line
    assert "-type d" in line
    assert "|| true" not in line, "the sweep is a mandatory step and must fail closed"


def test_nothing_follows_the_suid_sweep_in_its_stage() -> None:
    """A later instruction can re-introduce the class the sweep just cleared."""
    prep = DOCKER_INSTRUCTIONS.split("FROM scratch")[0]
    sweep_index = prep.index("RUN find / -xdev -perm /6000")
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
    settings = _properties(ROOT / "sonar-project.properties")
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

    shell = shutil.which("sh")
    assert shell, "no POSIX shell on PATH"
    built = subprocess.run(  # noqa: S603 - a resolved shell and a fixed, in-repo script
        [shell, str(ROOT / "scripts" / "package-appstore.sh"), "0.0.0-contract-test"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=300,
        check=False,
    )
    assert built.returncode == 0, f"packaging failed: {built.stderr[-500:]}"
    artefact = ROOT / "dist" / "enlightenment-appstore-0.0.0-contract-test.zip"
    try:
        with zipfile.ZipFile(artefact) as package:
            names = package.namelist()
    finally:
        artefact.unlink(missing_ok=True)

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
    """Run scripts/build-image.sh with a stub `docker` earlier on PATH."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "docker"
    fake.write_text(stub, encoding="utf-8")
    fake.chmod(0o755)
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
    defined: set[str] = set()
    for module in sorted((ROOT / "tests").glob("test_*.py")):
        defined.update(
            re.findall(
                r"^(?:async )?def (test_[A-Za-z0-9_]+)",
                module.read_text(encoding="utf-8"),
                re.MULTILINE,
            )
        )
    dangling = sorted(
        name
        for name in cited
        if name not in defined
        and not (name in elided and any(known.startswith(name) for known in defined))
    )
    assert dangling == [], f"docs/SECURITY.md cites tests that do not exist: {dangling}"
    assert cited, "the sweep found no cited test names, so it is asserting nothing"


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
    """
    version = _pyproject()["project"]["version"]
    major_minor = ".".join(version.split(".")[:2])
    changelog = (ROOT / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")
    heading = f"## V{major_minor} "
    assert heading in changelog, (
        f"docs/CHANGELOG.md has no audit row for V{major_minor}; newest headings are "
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


def _pins_of(lockfile: Path) -> dict[str, str]:
    """Read `name==version` pins, reusing the loop's own parser so the two cannot disagree.

    Imported rather than reimplemented: a second copy of the parsing rules is a second thing
    to keep in step, and a guard that parses differently from the checker it guards is worse
    than no guard.
    """
    spec = importlib.util.spec_from_file_location(
        "enlightenment_check_environment", ROOT / "scripts" / "check-environment.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    pins: dict[str, str] = module.read_pins(lockfile)
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


def test_the_environment_check_redacts_a_credential_before_echoing_a_line() -> None:
    """The echo that closed the fail-open branch is itself a disclosure path.

    A PEP 440 direct reference is a requirement line, so an unparseable one reaches the report
    and lands in a CI log. A private index legitimately holds a token there.
    """
    result = _run_environment_check("pkg @ https://alice:s3cr3t-token@example.invalid/pkg.whl\n")
    assert result.returncode != 0
    assert "s3cr3t-token" not in result.stderr
    assert "alice" not in result.stderr
    assert "[REDACTED:credential]" in result.stderr


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
            "pkg @ https://:s3cr3t-token@example.invalid/pkg.whl",
            "s3cr3t-token",
        ),
        (
            "percent-encoded userinfo",
            "pkg @ https://alice%3As3cr3t-token@example.invalid/pkg.whl",
            "s3cr3t-token",
        ),
        (
            "a password containing a raw at-sign",
            "pkg @ https://alice:p@ssS3CR3T@example.invalid/pkg.whl",
            "ssS3CR3T",
        ),
        (
            "reported through the version group, not the unreadable report",
            "pkg==https://alice:s3cr3t-token@example.invalid/pkg.whl",
            "s3cr3t-token",
        ),
    ],
    ids=["bare token", "empty user", "percent-encoded", "at-sign in password", "version group"],
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
    assert "[REDACTED:credential]" in result.stderr


@pytest.mark.parametrize(
    "line",
    [
        "https://files.pythonhosted.org/packages/ab/cd/pkg.whl",
        "pkg @ https://example.invalid/path@fragment/pkg.whl",
        "pkg @ https://example.invalid/pkg.whl",
    ],
    ids=["plain index url", "at-sign in the path", "no userinfo"],
)
def test_redaction_does_not_touch_a_url_without_credentials(line: str) -> None:
    """The control for the test above. A pattern that redacted every URL would pass it.

    Over-redaction is not harmless here: the unreadable-line report exists to tell an operator
    which line to fix, and a report that hides the line fails at its one job.
    """
    result = _run_environment_check(f"{line}\n")
    assert "[REDACTED:credential]" not in result.stderr
