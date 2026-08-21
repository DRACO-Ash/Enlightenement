#!/usr/bin/env python3
"""Assert that what is INSTALLED equals what the lock files PIN, and refuse to run otherwise.

Why this exists, recorded plainly because it invalidated earlier work rather than merely
improving on it: `scripts/verify.sh` used to invoke bare `ruff`, `mypy`, `pytest` and
`pip-audit`, so the loop ran whatever those names resolved to on PATH. On this machine PATH
held ruff 0.15.8 against a pinned 0.16.3, mypy 1.19.1 against a pinned 2.3.1, and a `pytest`
inside an isolated tool environment that could not import the application's own dependencies
at all. The drift surfaced as a FALSE FAILURE, which is the lucky direction. The same gap
produces a false PASS just as easily, and the loop is the thing every other claim rests on:
"the verification loop is green" has to mean "green against the dependency set the container
ships and the platform installs", or it means nothing.

Usage:

    python3 scripts/check-environment.py <interpreter> <lockfile> [<lockfile> ...]

Every `name==version` pin in each lock file must be installed in `<interpreter>`'s
environment at exactly that version. A missing distribution and a mismatched one are both
failures; neither is a warning. Exit 0 when every pin matches, 1 otherwise, with every
divergence listed rather than only the first, because fixing them one round-trip at a time
is how a re-lock turns into an afternoon.

Hash lines and continuations are skipped: this reads the pins, not the hashes. `pip install
--require-hashes` already enforces the hashes at install time, and duplicating that check
here would be a second implementation of it to keep in step.

**The check is one-directional, and that is a decision rather than an omission.** Every pin
must be installed at its pinned version; an EXTRA distribution present but not pinned is not
reported. Asserting the reverse would fail on every runner, because `pip`, `setuptools` and
`wheel` are provided by the interpreter's own environment and are not all pinned here. A leg
that fails on a correct environment is a leg people learn to skip, which costs more than the
latent hole it closes. If an unpinned distribution ever matters, `pip-audit` scans the lock
files in leg six and the container installs only `requirements-runtime.txt`.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

from packaging.markers import Marker
from packaging.version import InvalidVersion, Version

EXIT_OK = 0
EXIT_MISMATCH = 1
EXIT_MISUSE = 2

#: Hard bound on the version probe. Generous for the work (listing installed distributions)
#: and short enough that a wedged interpreter fails the leg instead of hanging it.
PROBE_TIMEOUT_SECONDS = 60

#: The script name, an interpreter, and at least one lock file.
MINIMUM_ARGUMENTS = 3

#: A pin line: distribution name, optional extras in brackets, `==`, version, then optionally
#: an environment marker after `;` and a trailing ` \` introducing the hash block.
#:
#: The extras group is not decoration. Without it, `uvicorn[standard]==9.9.9` did not match,
#: `read_pins` skipped the line in silence, and the checker printed "1 pins checked, all match"
#: with an unmet pin sitting in the file. A control that silently ignores what it cannot parse
#: is fail-OPEN, in the one leg the rest of the loop's meaning now rests on. The extras form is
#: also the ordinary way to pin uvicorn, so this was not a hypothetical.
PIN = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)"
    r"(?:\[[^\]]*\])?"
    r"==(?P<version>[^\s;\\]+)"
    r"\s*(?:;\s*(?P<marker>[^\\]*?))?\s*\\?$"
)


class UnparsedLine(NamedTuple):
    """A requirement line the pin pattern rejected, kept so it can be reported not dropped."""

    lockfile: str
    number: int
    text: str


def requirement_lines(lockfile: Path) -> list[str]:
    """Split ``lockfile`` on newlines ONLY, never with `str.splitlines()`.

    `str.splitlines()` also splits on the vertical tab, form feed, the file and group separators,
    NEL and the Unicode line and paragraph separators. A requirements file has exactly one line
    terminator that means anything, and treating those others as breaks is a disclosure path: a
    credential URL containing one is torn into two "lines", NEITHER of which holds the ``@`` the
    redaction pattern anchors on, so both halves echo in clear. Measured: a token embedded before
    a ``\\x0b`` printed in full.

    **That reason is history, and the sentence that stood here was worse than history: it
    described `redact()` neutralising the separator "as a second layer" after `redact()` had
    been deleted.** Prose describing a control that no longer exists is the same fault as code
    with no caller, in the file whose own commit message says so, and it is what a reader would
    have trusted.

    The live reason to split on one terminator alone is the diagnosis. Every report prints
    ``lockfile:number``, and inventing extra line breaks makes that number wrong: an operator
    sent to line 12 finds nothing there, because the fault is at line 11 and an earlier line was
    counted twice. A line number that is off by one is worse than none, because it is believed.
    """
    return [line.rstrip("\r") for line in lockfile.read_text().split("\n")]


def read_pins(lockfile: Path) -> dict[str, str]:
    """Return `{canonical name: version}` for every applicable pin in ``lockfile``.

    A pin whose environment marker does not apply to the running interpreter is skipped
    deliberately: `pywin32==306 ; sys_platform == "win32"` is not expected to be installed on
    Linux, and reporting it as missing would be a false failure that teaches people to ignore
    this leg.
    """
    pins: dict[str, str] = {}
    for raw in requirement_lines(lockfile):
        line = raw.strip()
        if not _is_requirement_line(line):
            continue
        match = PIN.match(line)
        if match is None:
            continue
        if not _marker_applies(match.group("marker")):
            continue
        pins[canonicalise(match.group("name"))] = match.group("version")
    return pins


def read_unparsed(lockfile: Path) -> list[UnparsedLine]:
    """Return every requirement line the pin pattern could not read.

    Reported rather than ignored. `read_pins` returning fewer entries than the file holds is
    indistinguishable, from the caller's side, from a file that holds fewer pins - which is
    exactly how the extras form went unnoticed.
    """
    unparsed: list[UnparsedLine] = []
    for number, raw in enumerate(requirement_lines(lockfile), start=1):
        line = raw.strip()
        if not _is_requirement_line(line):
            continue
        if PIN.match(line) is None:
            unparsed.append(UnparsedLine(lockfile.name, number, line))
    return unparsed


def _is_requirement_line(line: str) -> bool:
    """True for a line that should name a pinned requirement.

    Blank lines, comments, pip options, `-r` includes and the `--hash=...` continuation lines
    are all legitimately not pins. Everything else is, and must parse.
    """
    # One test, not two: `--hash=...` already starts with `-`, so a separate check for it could
    # never return False. The earlier version had one, under a docstring implying it did work.
    return bool(line) and not line.startswith(("#", "-"))


def _marker_applies(marker: str | None) -> bool:
    """Whether an environment marker holds for the interpreter running this script.

    A marker that cannot be evaluated is treated as APPLYING, so an unreadable marker becomes
    a reported mismatch rather than a silent skip. Fail closed, as everywhere else.
    """
    if not marker:
        return True
    try:
        return bool(Marker(marker).evaluate())
    except Exception:  # deliberately broad; the reason is below
        # Deliberately broad, and `InvalidMarker` alone was not enough. Measured escapes from
        # the narrower version: `python_full_version ~= "banana"` raises `UndefinedComparison`,
        # and `python_version >= "3." + "9" * 100000` raises `ValueError` from CPython's
        # 4300-digit integer conversion limit. Both left this function as an uncaught traceback,
        # fail-closed only by the coincidence that Python exits 1 and EXIT_MISMATCH is 1.
        #
        # `packaging` parses and evaluates a mini-language over file content, so its failure
        # surface is not enumerable from the outside. Attacked with eighteen hostile markers it
        # executes nothing (`__import__("os").system("id")` raises `InvalidMarker`) and does not
        # backtrack pathologically (5,000 conjunctions in 0.08s), but "no code execution" and
        # "only ever raises these three types" are different claims and only the first is tested.
        #
        # Named on the way past, because the exit code alone leaves an operator looking at
        # "NOT INSTALLED" with no way to tell a real mismatch from a marker that could not be
        # evaluated. Fail closed AND say why.
        #
        # DESCRIBED, and that is the third time this project has fixed a class of disclosure at
        # some of its echo sites and not all of them. The version echo got `describe_version` and
        # the unparsed-line echo got `describe_line`, both fail-closed, precisely because the old
        # `redact()` could not catch a credential with no context - and this site kept it. A
        # marker has no line number of its own to print, which makes echoing its content even
        # harder to justify than at the sites that do. Measured end to end: a line reading
        # `pkg==1.0 ; index_credential_<token>` parses as a pin with a marker, the marker fails to
        # evaluate, and 43 characters of the token reached stderr and would have reached a CI log.
        #
        # A marker is a PEP 508 expression, so its CONTENT is never the diagnosis: the line number
        # and the fact that it would not evaluate are. Same treatment as the other two sites.
        sys.stderr.write(
            f"  note: could not evaluate marker, treating as applicable:"
            f" {len(marker)} characters, content not echoed\n"
        )
        return True


#: **`redact()` used to live here, and it is gone.** Six bypasses, each one closed and each one
#: leaving the shape that produced it: a pattern that must FIND something - the `@` of userinfo,
#: the `=` of a parameter, the whitespace that ends a run - before it can hide anything. Move or
#: remove the thing it looks for and the credential prints. In order: truncating before redacting
#: (463 characters of a live Google Artifact Registry token to stderr); requiring a colon, so a
#: bare Personal Access Token never matched; `str.splitlines()` tearing the line at NEL and
#: U+2028; sixteen Unicode space characters that `\s` matches and the neutraliser did not; a bare
#: token in version position, which has no surrounding context to find at all; and an ASCII space
#: or tab inside userinfo, which the whole-run rewrite still treated as a terminator.
#:
#: The sixth is what settled it. Each fix had narrowed the class - 29 characters, then 16, then 2 -
#: which felt like progress and was a function converging on a limit above zero. No pattern can
#: find a secret in arbitrary text, so the answer was never a better pattern. It was to stop
#: echoing arbitrary text.
#:
#: Every echo site DESCRIBES its input now. The version echo takes a strict PEP 440 whitelist
#: (`describe_version`); the unparseable-line and marker reports emit a length only
#: (`describe_line`); the interpreter-probe failure reports an exit code. Each prints
#: `lockfile:number` beside it, which was always the actual diagnosis. With no caller left,
#: `redact()`, `URL_CREDENTIALS`, `QUERY_CREDENTIALS`, `NON_PRINTABLE` and `MAX_ECHO_LENGTH` were
#: deleted rather than kept for a future caller to trust.


#: Longest version echoed verbatim. With the local segment gone, the longest shape this whitelist
#: admits is a numeric release plus pre, post and dev segments - `1.2.3rc1.post1.dev20260820`, 26
#: characters - so 40 is generous. This bounds one log line; it is not a secrecy boundary, for the
#: same reason `MAX_NAME_ECHO` is not.
MAX_VERSION_ECHO = 40

#: A version this script is willing to echo VERBATIM. Public PEP 440 shape, and strict: a
#: numeric release with optional pre, post and dev segments. No local segment, and no letters
#: outside the fixed pre-release vocabulary.
#:
#: **The local segment is GONE, and that is the seventh and last revision of this control.** It
#: admitted a real disclosure twice over. Unbounded, `\+[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*` let any
#: alphanumeric run joined by `.` or `-` through, so a 32-character hex key or a cloud access key
#: identifier in version position echoed in full. Bounded to eight characters per component and
#: three components, the CONTIGUOUS spelling of every mainstream credential format was described -
#: twenty-one measured - and the SEPARATED spelling was not: inserting two dots into a 20-character
#: access key identifier put all twenty characters back on stderr, reconstructible by deleting the
#: dots. The bound closed the accidental paste and left the deliberate one open.
#:
#: It also could not keep its own promise. "Every real local version still echoes" was falsified by
#: genuine build tags: semver's own `+20130313144700`, `+ubuntu0.22.04.1`, `+git20260821abc`,
#: `+computecanada`, and a local label containing an underscore, which PEP 440 permits. The clause
#: was wrong in both directions at once, and three successive versions of it were each wrong once.
#:
#: The lengths overlap, which is why no bound worked: real local labels run past fifteen characters
#: and real secrets start below twenty. Stated qualitatively on purpose - an earlier version of this
#: reasoning carried a "3 to 13" range and a "16 up" range, neither measured, and the same file put
#: the credential population at "20 to 45" fifty-seven lines away.
#:
#: Dropping it costs nothing measurable - none of the three lock files pins a local version - and
#: buys an invariant that cannot drift. A `torch==2.1.0+cu118` pin reports its NAME plus
#: `[REDACTED:unrecognised-version, 12 characters]`, which is enough for an operator who has to
#: open the lock file anyway. A simpler invariant is worth more than the echo it removes.
#:
#: What remains is irreducible and is stated in `docs/SECURITY.md` item 9: a numeric string in
#: release position is indistinguishable from a version, because it IS one.
#:
#: This is a whitelist, and it exists because `redact()` cannot close the last disclosure class
#: by pattern. `redact()` finds credentials by their CONTEXT - the ``//`` of a URL, the ``=`` of a
#: query parameter. A bare token standing where a version should stand, `pkg==ghp_<48 chars>`,
#: has no context to find: it is alphanumeric, so every character-class blacklist passes it, and
#: it echoed in full through the "pinned X, NOT INSTALLED" report. Measured across all 29
#: whitespace characters, that form leaked the token every time while the URL forms leaked none.
#:
#: A blacklist asks "does this look dangerous"; the answer for high-entropy alphanumerics is no.
#: A whitelist asks "does this look like the one thing I expect", and a credential does not look
#: like `0.115.0`. Every version pip reports and every version a correct lock file pins matches
#: this. What fails it is malformed input, which is exactly the path that discloses.
SAFE_VERSION = re.compile(
    r"\A[0-9]+(?:\.[0-9]+)*"
    r"(?:(?:a|b|rc|alpha|beta|c|pre|preview)[0-9]+)?"
    r"(?:\.post[0-9]+)?(?:\.dev[0-9]+)?\Z"
)


def describe_version(version: str) -> str:
    """Echo ``version`` if it is shaped like a version AND short, else describe it.

    Fail closed. An unrecognised value is reported by LENGTH, which is what an operator needs to
    recognise the line they are looking at, and by nothing else.

    **The length half was missing, and its absence was a live disclosure.** `SAFE_VERSION`
    constrains SHAPE and not size, so `pkg==1.<5000 nines>` printed all five thousand digits to
    stderr: shaped like a version, and therefore echoed verbatim. `MAX_ECHO_LENGTH` had bounded
    every echo in this file and was deleted along with `redact()`, which removed the bound from
    the one site that still needed it. Deleting dead code is right; deleting a live bound because
    it lived next to dead code is how a fix becomes a regression.

    A real PEP 440 version is short. With the local segment gone, the longest shape this whitelist
    admits is a numeric release with pre, post and dev segments - `1.2.3rc1.post1.dev20260820`, 26
    characters - so the cap costs nothing real.

    **The residual, stated as `describe_name` states its own, and corrected three times before it
    was right.** What echoes is any value of `MAX_VERSION_ECHO` characters or fewer matching
    `SAFE_VERSION`: a numeric release with optional pre, post and dev segments, and nothing else.
    So a purely NUMERIC secret of that length or shorter echoes, because a numeric string in
    release position is indistinguishable from a version - it IS one. That is irreducible, and it
    is the whole residual.

    It took three goes to say that. The first version called the residual "all-numeric" while the
    local segment was still unbounded, which was false by every letter-bearing format. The second
    said the same thing after bounding the segment, which changed the per-component length and not
    the class. The third described the bounded class correctly and was still describing a segment
    that should not have existed. Deleting the segment made the sentence true by making it simple,
    which is the lesson worth keeping: three attempts to describe a control accurately were worth
    less than one decision to remove the part that needed describing.

    `docs/SECURITY.md` item 9 carries the same words. Both were edited together, because fixing one
    of two locations is the fault `describe_name`'s docstring below records having committed.
    """
    if len(version) <= MAX_VERSION_ECHO and SAFE_VERSION.match(version):
        return version
    return f"[REDACTED:unrecognised-version, {len(version)} characters]"


#: Longest distribution name echoed verbatim. **This bound is about output length, NOT about
#: secrecy, and two wrong versions of it shipped before that was admitted.**
#:
#: The first said 32 "admits every real name". Measured, it does not:
#: `opentelemetry-instrumentation-fastapi` is 37 characters,
#: `opentelemetry-exporter-otlp-proto-http` 38, `google-cloud-bigquery-datatransfer` 34 - exactly
#: the dependencies a FastAPI service acquires, all of them described instead of named, defeating
#: the report's one job. 32 is also precisely the length of a hex API key, so the bound admitted
#: the whole of the commonest fixed-length secret format while excluding real names.
#:
#: The second was worse. Told the figure was invented, I re-derived it from the longest name
#: pinned in THIS repository (`pip-requirements-parser`, 23) and set 24 - which is a real
#: measurement of the wrong population. A lock file gains dependencies; the bound would have
#: started redacting real names the first time one arrived.
#:
#: The honest reading is that no length separates the two populations. Real names run 1 to 188
#: characters, and credential formats are commonly in the twenties to forties - illustrative, not
#: measured, and named as such because an unmeasured range stated as a measurement is the fault this
#: file has committed four times. They overlap, so a length cap CANNOT provide
#: secrecy here and pretending otherwise is what produced two bad numbers.
#:
#: **And then a third, which is why this one is measured.** The version that replaced them said 64
#: was "PyPI's own maximum name length". PyPI has no such maximum: its project-name validation is a
#: pattern with no length validator, `packaging` implements the PEP 503 grammar with no length
#: bound, and `projects.name` is a text column. Measured against the live simple index on
#: 2026-08-21: **875,180 projects, of which 141 have canonical names longer than 64 characters, the
#: longest at 188, and none over 200.** (The project COUNT drifts daily - a re-measure the next day
#: gave 875,199 - while the maximum did not move. The count is dated for that reason and nothing
#: depends on it.) So 64 excluded 141 real distributions exactly as 32 and 24
#: did, and the justification was asserted rather than checked - in the constant whose entire
#: comment is about not doing that.
#:
#: 200 is above every name that exists and below anything worth reading in a log line. It is an
#: OUTPUT bound and not a secrecy boundary; the residual is stated in `describe_name` rather than
#: implied away by a number.
MAX_NAME_ECHO = 200

#: A PEP 503 canonical distribution name, which is what `canonicalise` produces.
CANONICAL_NAME = re.compile(r"\A[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\Z")


def describe_name(name: str) -> str:
    """Echo ``name`` if it is shaped and sized like a distribution name, else describe it.

    **The residual in this file, stated rather than hidden.** The divergence report cannot do its
    one job without naming the distribution - "pinned 0.115.0, NOT INSTALLED" about an unnamed
    package is useless - so unlike every other echo here, this one cannot be reduced to a length.

    And a credential in the name position is not structurally distinguishable from a name.
    Measured: `ghp_S3CRETLIVETOKEN...==1.0.0` parses as a pin, and the report printed the
    canonicalised token in full. `canonicalise` lowercases and folds separators, so a token comes
    out looking exactly like a name.

    **So this is a residual, not a control, and the earlier wording overstated it.** Two versions
    of `MAX_NAME_ECHO` claimed to bound the disclosure by length, and both picked a number that
    excluded real distributions while admitting common secret formats, because the two populations
    overlap completely. A length test cannot separate them.

    What is left is honest and small: `CANONICAL_NAME` rejects anything that is not PEP 503
    name-shaped, which excludes a URL, a token containing `@` or `:` or `/`, and any value with
    uppercase or underscores surviving canonicalisation. A lowercase alphanumeric secret in the
    name position DOES still echo. That is the accepted residual, and it is accepted because the
    divergence report cannot do its one job without naming the distribution - "pinned 0.115.0,
    NOT INSTALLED" about an unnamed package tells an operator nothing.

    The length cap is retained only to bound the size of one log line. 200 is above every canonical
    name measured on the live PyPI simple index on 2026-08-21, the longest of 875,180 being 188
    characters; PyPI itself enforces no name-length maximum. It is not a secrecy boundary.

    An earlier version of this paragraph said "at PyPI's own maximum name length", and the
    retraction of that invented claim was applied forty lines above and not here, so the file
    contradicted itself and the false justification shipped next to the function it justified.
    Fixing one of a claim's two locations is the same fault as installing a control at one echo
    site of two.
    """
    if len(name) <= MAX_NAME_ECHO and CANONICAL_NAME.match(name):
        return name
    return f"[REDACTED:unrecognised-name, {len(name)} characters]"


def describe_line(text: str) -> str:
    """Describe an unparseable lock-file line without echoing its content.

    The argument `redact()` could only half-make, which is why `redact()` no longer exists. It
    was revised six times, and every revision closed one shape of a credential that reached stderr
    because the function echoed attacker-influenced text and tried to spot the bad part. This
    function does not try. It echoes a length and nothing else.

    **It echoed a leading distribution name for about ten minutes, and the test written in the
    same change caught it.** A PEP 508 name is `[A-Za-z0-9][A-Za-z0-9._-]*`, and
    `ghp_S3CRETLIVETOKEN...` satisfies that exactly: underscores and alphanumerics, nothing else.
    A credential standing in the name position of a requirements line is indistinguishable from a
    name, so "the name is safe to echo" was another guess dressed as a rule - the sixth in this
    control's history, and the reason it is now the only one not shipped.

    The caller prints ``lockfile:number`` beside this, so the line is identified exactly. An
    operator fixing a malformed pin opens the file; they do not reconstruct it from the log line.
    Giving up the content costs nothing that was load-bearing and closes the class completely.
    """
    return f"unparseable, {len(text)} characters, content not echoed"


def canonicalise(name: str) -> str:
    """PEP 503 name normalisation, so `pip_audit` and `pip-audit` compare equal."""
    return re.sub(r"[-_.]+", "-", name).lower()


def versions_equal(pinned: str, installed: str) -> bool:
    """Compare two versions by PEP 440 semantics, not as strings.

    `pytest==9.1.1.0` and an installed `9.1.1` are the same release and a string comparison
    calls them different. That failed in the safe direction, but a leg that cries wolf on a
    correct environment is a leg people learn to skip.

    Catches `ValueError` as well as `InvalidVersion`, because a release segment over about 4,300
    digits trips CPython's integer-to-string conversion limit inside `packaging`, which raises
    plain `ValueError` and escaped as an uncaught traceback. Fail-closed either way and no content
    was echoed, so this is hygiene rather than a hole - but an uncaught traceback out of leg one is
    indistinguishable, to whoever reads the CI log, from the leg being broken.
    """
    try:
        return Version(pinned) == Version(installed)
    except (InvalidVersion, ValueError):
        return pinned == installed


def installed_versions(interpreter: str) -> dict[str, str]:
    """Ask ``interpreter`` what it actually has, rather than assuming it is this process.

    Run out of process on purpose: the loop's interpreter is the one that must satisfy the
    pins, and it is not necessarily the one running this script.
    """
    probe = (
        "import json\n"
        "from importlib.metadata import distributions\n"
        "print(json.dumps({d.metadata['Name']: d.version for d in distributions()"
        " if d.metadata['Name']}))\n"
    )
    # Why S603 is suppressed below: a list argv with shell=False, and a probe that is a
    # constant string literal with no interpolation. `interpreter` is a path from argv, and
    # argv is trusted in all three contexts this runs in - the local loop, GitHub CI, and
    # the platform - because anyone able to set it could already set PATH or execute code
    # directly. The timeout is the real control here: a wedged interpreter would otherwise
    # hang the whole loop until the CI job timed out, and a loop that hangs reports nothing.
    try:
        result = subprocess.run(  # noqa: S603
            [interpreter, "-c", probe],
            capture_output=True,
            text=True,
            check=False,
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        # A timeout is a failure to CHECK, and a failure to check is never a pass. Reported
        # as a mismatch rather than raised, so the loop's exit code stays the whole story.
        sys.stderr.write(f"FAIL: {interpreter} did not answer within {PROBE_TIMEOUT_SECONDS}s\n")
        raise SystemExit(EXIT_MISMATCH) from None
    if result.returncode != 0:
        # DESCRIBED, not echoed, and not redacted either. This was the last raw echo in the file,
        # and my first fix for it was to wrap it in `redact()` - which put arbitrary text back
        # through the one function in this repository that has been bypassed six times. The probe
        # is a constant script and the interpreter comes from argv, so what lands here is a
        # traceback; "so it is realistically fine" is the exact sentence that preceded every one
        # of those six bypasses.
        #
        # The diagnosis is the interpreter path and the exit code. An operator who needs the
        # traceback runs the interpreter themselves, which is one command and discloses nothing to
        # a CI log.
        sys.stderr.write(
            f"FAIL: could not query {interpreter}: exit {result.returncode},"
            f" {len(result.stderr)} characters of stderr not echoed\n"
        )
        raise SystemExit(EXIT_MISMATCH)

    try:
        raw: dict[str, str] = json.loads(result.stdout)
    except json.JSONDecodeError as unparseable:
        # The third site of a class fixed twice already this round, at `versions_equal` and
        # `_marker_applies`: an uncaught exception out of leg one that is fail-closed only by the
        # coincidence that `EXIT_MISMATCH` happens to be 1. Reproduced with an interpreter wrapper
        # that writes one line to stdout before exec, which a `sitecustomize.py`, a `.pth` file or a
        # wrapper interpreter on a platform runner will do. The stdout is DESCRIBED, not echoed,
        # like every other report in this file.
        sys.stderr.write(
            f"FAIL: {interpreter} did not answer with JSON:"
            f" {unparseable.msg} at position {unparseable.pos},"
            f" {len(result.stdout)} characters of stdout not echoed\n"
        )
        raise SystemExit(EXIT_MISMATCH) from None
    # The TYPE as well as the parse, because guarding only the parse left the fourth site of this
    # class one line below the third. Measured with stub interpreters: `["x"]`, `12345`, `null` and
    # `true` all parse cleanly and then raise `AttributeError: 'list' object has no attribute
    # 'items'` or `TypeError: object of type 'int' has no len()` as an uncaught traceback out of leg
    # one - fail-closed only because Python's uncaught-exception exit code happens to be 1, which is
    # the same accident `_marker_applies` and `versions_equal` were fixed for.
    #
    # Realistic, not contrived: anything that makes an interpreter print before the probe's own
    # output shifts the JSON, and a wrapper that answers a different shape entirely is a wrapper
    # somebody wrote for another purpose.
    if not isinstance(raw, dict) or not all(
        isinstance(name, str) and isinstance(version, str) for name, version in raw.items()
    ):
        sys.stderr.write(
            f"FAIL: {interpreter} answered JSON of the wrong shape:"
            f" expected an object of strings, got {type(raw).__name__},"
            f" {len(result.stdout)} characters of stdout not echoed\n"
        )
        raise SystemExit(EXIT_MISMATCH)

    return {canonicalise(name): version for name, version in raw.items()}


class Divergences(NamedTuple):
    """What a scan of the lock files found. Split out so `main` stays inside the complexity cap."""

    checked: int
    missing: list[str]
    wrong: list[str]
    unreadable: list[UnparsedLine]


def scan(lockfiles: list[str], installed: dict[str, str]) -> Divergences:
    """Compare every applicable pin in ``lockfiles`` against ``installed``.

    Raises :class:`FileNotFoundError` for a lock file that does not exist, because a named
    file that is absent is a caller error rather than a mismatch to report alongside others.
    """
    missing: list[str] = []
    wrong: list[str] = []
    unreadable: list[UnparsedLine] = []
    checked = 0
    for name in lockfiles:
        lockfile = Path(name)
        if not lockfile.is_file():
            raise FileNotFoundError(name)
        unreadable.extend(read_unparsed(lockfile))
        for pinned_name, pinned_version in read_pins(lockfile).items():
            checked += 1
            actual = installed.get(pinned_name)
            # Described where the line is COMPOSED, not at one echo site. The first version
            # guarded only the unreadable-line report, and this is the other place a URL
            # reaches stderr: the version group is `[^\s;\\]+`, which swallows a whole URL, so
            # `pkg==https://user:token@host/x` - a one-character typo of the direct-reference
            # form the redaction was written for - printed the credential in full.
            if actual is None:
                missing.append(
                    f"  {describe_name(pinned_name)}:"
                    f" pinned {describe_version(pinned_version)}, NOT INSTALLED"
                )
            elif not versions_equal(pinned_version, actual):
                wrong.append(
                    f"  {describe_name(pinned_name)}: pinned {describe_version(pinned_version)},"
                    f" installed {describe_version(actual)}"
                )
    return Divergences(checked, missing, wrong, unreadable)


def main(argv: list[str]) -> int:
    if len(argv) < MINIMUM_ARGUMENTS:
        sys.stderr.write(f"{__doc__}\n")
        return EXIT_MISUSE

    interpreter = argv[1]
    try:
        found = scan(argv[2:], installed_versions(interpreter))
    except FileNotFoundError as absent:
        sys.stderr.write(f"FAIL: lock file {absent.args[0]} does not exist\n")
        return EXIT_MISMATCH

    if found.unreadable:
        # Reported BEFORE the empty-file case, because it is the more specific diagnosis: a
        # file of nothing but unreadable lines would otherwise be blamed on holding no pins.
        #
        # A line this script cannot parse must NEVER read as a match. The extras form
        # (`uvicorn[standard]==1.2.3`) was silently skipped once, and the run printed
        # "all match" with an unmet pin sitting in the file.
        sys.stderr.write("FAIL: lines that should name a pin could not be read\n")
        for entry in found.unreadable:
            sys.stderr.write(f"  {entry.lockfile}:{entry.number}: {describe_line(entry.text)}\n")
        return EXIT_MISMATCH

    if not found.checked:
        sys.stderr.write("FAIL: the lock files named contained no pins at all\n")
        return EXIT_MISMATCH

    if found.missing or found.wrong:
        sys.stderr.write(f"FAIL: the environment does not match the lock files ({interpreter})\n")
        # Deduplicated: a distribution pinned in both lock files would otherwise be reported
        # twice, and a wall of repeats reads as a bigger problem than it is.
        for line in dict.fromkeys(found.wrong + found.missing):
            sys.stderr.write(f"{line}\n")
        sys.stderr.write(
            "\nRe-install before trusting any verdict from this loop:\n"
            "  .venv/bin/pip install --require-hashes --no-deps "
            "-r requirements.txt -r requirements-dev.txt\n"
        )
        return EXIT_MISMATCH

    sys.stdout.write(f"  {found.checked} pins checked, all match ({interpreter})\n")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv))
