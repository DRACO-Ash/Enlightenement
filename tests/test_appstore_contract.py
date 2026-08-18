"""Mechanised App Store upload-gate contract checks.

These assert the CLASS, not one named instance, so a regression cannot reappear quietly.
Every negative assertion below is classified per environment: it is either true in every
checkout, or explicitly gated on the platform runner. No assertion here may be
guaranteed-false on the machine that gates the deploy.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

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

#: True when running on the platform's GitLab runner, which adds files to the checkout.
ON_PLATFORM_RUNNER = os.environ.get("GITLAB_CI") == "true"


# --- the runtime contract -----------------------------------------------------------


def test_dockerfile_sits_at_the_repository_root() -> None:
    """A nested Dockerfile fails the build with `context must be a directory`."""
    assert (ROOT / "Dockerfile").is_file()


@pytest.mark.parametrize("banned", ["ENV PORT=", "ENV DATA_DIR="])
def test_no_baked_environment_default_can_defeat_the_injected_value(banned: str) -> None:
    """True in every checkout: a baked default overrides what the platform injects."""
    assert banned not in DOCKER_INSTRUCTIONS


def test_the_launch_command_binds_every_interface_on_the_platform_port() -> None:
    """gunicorn and uvicorn default to 127.0.0.1, which the platform probe cannot reach."""
    assert "0.0.0.0:${PORT:-8080}" in DOCKER_INSTRUCTIONS


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
    "tool",
    ["/usr/bin/apt", "/usr/bin/apt-get", "/usr/bin/dpkg", "/opt/venv/bin/pip"],
)
def test_no_package_manager_survives_into_the_shipped_image(tool: str) -> None:
    """The scanner judges what is IN the image, not what the entrypoint runs. Checked as a
    class rather than for pip alone, which is all the first version removed.
    """
    sweep = DOCKER_INSTRUCTIONS.split("FROM scratch")[0]
    assert tool in sweep, f"{tool} is not removed from the runtime filesystem"


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
    lines = _ci_instructions()
    joined = "\n".join(lines)
    assert "for tool in pip pip3 apt apt-get" in joined
    for tool in ("dpkg", "aptitude"):
        assert tool in joined, f"the CI package-manager check does not cover {tool}"


# --- the quality gate ---------------------------------------------------------------


def test_sonar_configuration_scopes_sources_tests_and_the_coverage_report() -> None:
    props = (ROOT / "sonar-project.properties").read_text(encoding="utf-8")
    assert "sonar.sources=src" in props
    assert "sonar.tests=tests" in props
    assert "sonar.python.coverage.reportPaths=coverage.xml" in props


def test_a_bare_pytest_run_still_emits_the_cobertura_report_the_gate_reads() -> None:
    """Only the xml report writes the file Sonar consumes; a bare run would score 0%."""
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "--cov-report=xml:coverage.xml" in pyproject
    assert "--cov-fail-under=80" in pyproject


def test_the_local_complexity_cap_is_tighter_than_the_platform_cap() -> None:
    """Sonar S3776 caps cognitive complexity at 15; a looser local cap is a future
    upload failure."""
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    cap = re.search(r"max-complexity\s*=\s*(\d+)", pyproject)
    assert cap is not None
    assert int(cap.group(1)) <= 15


# --- dependency hygiene -------------------------------------------------------------


@pytest.mark.parametrize("lockfile", ["requirements.txt", "requirements-dev.txt"])
def test_every_locked_requirement_is_exact_and_hash_pinned(lockfile: str) -> None:
    text = (ROOT / lockfile).read_text(encoding="utf-8")
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
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").split()
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
    where packaging has been run, which is every checkout about to be uploaded. The
    invariant that actually holds everywhere is that `dist/` is git-ignored AND excluded
    from the upload allowlist, so it can never be in the platform's checkout at all. That
    the suite then passes in that checkout is proved end to end by
    `scripts/simulate-pipeline.sh`, which unzips the artefact and runs the suite there.
    """
    assert "dist/" in (ROOT / ".gitignore").read_text(encoding="utf-8").split()
    packaging = (ROOT / "scripts" / "package-appstore.sh").read_text(encoding="utf-8")
    assert 'rm -rf "$STAGE/.git" "$STAGE/.venv" "$STAGE/var" "$STAGE/dist"' in packaging


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


def test_the_image_script_never_reports_a_pass_for_an_unreachable_registry() -> None:
    """A failure to CHECK is not a pass. The deferral banner and a non-zero exit are the
    only honest outcome when the registry cannot be reached.
    """
    script = (ROOT / "scripts" / "build-image.sh").read_text(encoding="utf-8")
    assert "THIS IS NOT A PASS" in script
    assert "exit 3" in script
