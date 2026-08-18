"""Mechanised App Store upload-gate contract checks.

These assert the CLASS, not one named instance, so a regression cannot reappear quietly.
Every negative assertion below is classified per environment: it is either true in every
checkout, or explicitly gated on the platform runner. No assertion here may be
guaranteed-false on the machine that gates the deploy.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tomllib
import zipfile
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
    lines = _ci_instructions()
    joined = "\n".join(lines)
    assert "for tool in pip pip3 apt apt-get" in joined
    for tool in ("dpkg", "aptitude"):
        assert tool in joined, f"the CI package-manager check does not cover {tool}"


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
