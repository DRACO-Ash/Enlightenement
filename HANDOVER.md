# Handover: Enlightenment, V0.11.0

Prepared 2026-08-19 at commit `a96e9e9` on branch `claude/bluestaq-app-store-server-6scbm5`.
Written to be read cold, by someone who was not here.

**Nothing has been submitted to the App Store. Nothing has been deployed. No pull request has
been opened.** The branch is pushed; that is the only external state that exists.

## The one thing to know before anything else

**Both binding review gates last returned FAIL on this lineage, and their findings are fixed but
NOT re-verified.**

| Gate | Last PASS | Last verdict on this lineage |
|---|---|---|
| `engineering-reviewer` | round 7, commit `068b1c4` | **FAIL** on `8f64118` (5 MAJORs) |
| `security-reviewer` | rounds 4, 5, 7, latest `068b1c4` | **FAIL** on `8f64118` (same 5 MAJORs) |
| `deploy-gate` | never | **FAIL** on `0.8.0` (3 BLOCKERs) |

Every one of those findings is closed in `a96e9e9`. None of the three gates has run against
`a96e9e9`. So the correct statement of readiness is: **the work is believed complete and is
unverified at the head.** Re-run all three before anything ships. Do not read the earlier PASSes
as covering the current commit; they do not.

## What is verified right now

● **Verification loop green** at `a96e9e9`: `ruff format`, `ruff check`, `mypy --strict` over 12
  modules, 326 tests collected (325 passed, 1 skipped), branch coverage **98.50%** against an 80%
  floor, Cobertura written to `coverage.xml`, `pip-audit` clean over BOTH lockfiles.
● **Continuous integration green** at `a96e9e9`, all three jobs, including the binding `image` leg.
● **The container builds and runs.** Measured against the built filesystem, not the Dockerfile
  text: `Config.User = 10001:10001`; zero setuid or setgid paths, swept as root with stderr
  surfaced; no package-manager binary on `PATH`; no bundled package-manager wheel; dpkg database
  retained so the platform scanner can still enumerate. Live probes on 8080: `/` 200, `/livez`
  `/ping` `/health` 200, `/api/v1/diagnostics` 200 with the exact token length asserted absent.
● **Pipeline simulation green** against the real artefact on the pinned interpreter with
  `GITLAB_CI=true`.
● **Artefact built:** `dist/enlightenment-appstore-0.11.0.zip`, 167,905 bytes, SHA-256
  `3830449f14d3f67ebcf763a6ef10957359bf47e4018697e2a6972511da90c35d`. 53 files, flat at the root,
  no `.git`, `.venv`, `var/`, `dist/` or `.env`.
● **Working tree clean**, versions in step at 0.11.0 across `pyproject.toml` and the package.

### The one CI result that looks wrong and is not

`/readyz` returns **503** in CI. No file-storage add-on is mounted there, so the non-root user
cannot write the image's own default directory. The application starts, serves every liveness
path, publishes a complete diagnosis (`errno 13 EACCES` plus the resolved directory) and reports
itself unready.

This was deliberately not "fixed". A writable in-image directory would let a pod whose add-on
volume failed to mount run happily on ephemeral storage and lose every training session at the
next restart. **A loud unready state beats silent data loss.** In production the add-on injects
`STORAGE_MOUNT_PATH` and this path is green.

## What is decided, and what is still open

**Owner decisions taken 2026-08-18**, recorded in `docs/DEPLOYMENT.md`:

| Field | Value |
|---|---|
| Category | Training / Simulation |
| Visibility | Private to the Bluestaq Ltd team |
| Resources | Request 1Gi / 1 CPU, limit 2Gi / 2 CPU |
| Scenario vocabulary | Left an open, length-capped field. No invented terms |

**Still open, and needing a human:**

1. **The team token.** Visibility is private-to-team, so `ENLIGHTENMENT_TEAM_TOKEN` must be set
   (24 characters minimum, marked SECRET), and setting it makes `ALLOWED_ORIGIN` mandatory: the
   app refuses to start with one and not the other. It is not generated, not held anywhere in this
   repository, and must never appear in a commit, a document, or a chat transcript.
   Safe failure mode: forget the token and you get a read-only service, never an open one.
2. **The category string.** If the console's list words it differently, take its nearest
   equivalent and correct the record. Do not force the string above.
3. **The descriptions.** Drafted in `docs/DEPLOYMENT.md` from what the application does. Approve
   or rewrite them; they are copy, not fact, so they are the owner's to set.
4. **Re-run the three gates** against `a96e9e9`, then submit only on a `deploy-gate` PASS plus an
   explicit human yes.

## The environment tab

Two variables are set and **every other row is `[delete]`**. Full table in
`docs/DEPLOYMENT.md`. Guidance prose pasted into a value field is a catalogued platform failure,
so each row there is either copy-paste exact or an explicit delete.

## Rollback and withdrawal

There is **no rollback**: this would be the first ever deployment, so no previous image tag and no
earlier package exists, and that cannot be manufactured. The withdrawal path for a first
deployment is written in `docs/DEPLOYMENT.md`. Its most important line: **never delete and
recreate under the same slug.** App-record residue is a known platform failure that recovers only
with a fresh slug, which changes the URL the team has been given. Deleting is the step that is
hard to undo, not the deploying.

## Where to read what

| Question | File |
|---|---|
| Platform settings, env tab, budget, probes, rollback | `docs/DEPLOYMENT.md` |
| Threat model, every control with its test, accepted risks, mutation ledger | `docs/SECURITY.md` |
| One audit row per version, with what was verified and what was not | `docs/CHANGELOG.md` |
| Conventions and hard rules | `CLAUDE.md` |
| The verification loop | `scripts/verify.sh` |

## What went wrong on the way, so it is not repeated

Eleven releases and five review cycles. The code on the request path settled early; what kept
failing was the accuracy of the record and the quality of the test instruments.

● **Three real defects the reviewers found in shipped behaviour**, each measured rather than
  argued: two gunicorn workers silently losing about half of all acknowledged writes; a body cap
  that a chunked request walked straight past (45 MB to 326 MB resident on one unauthenticated
  request); and write routes open by default because an absent token was treated as permission.
● **A claim in the release record certifying a source change the diff did not contain.** The edit
  was a `str.replace` whose anchor missed, so it silently did nothing. Fixed by
  `scripts/verified-edit.py`, which refuses a missing anchor, an ambiguous anchor, a symlinked
  target, and a write it cannot verify.
● **Eighteen instances of tests asserting prose rather than behaviour.** A test that matched a
  Dockerfile invariant against the file's own explanatory comment. A test that found `--user 0`
  in the comment explaining why the flag is needed. Three CI checks satisfied by any mention of
  their marker anywhere in the file. The ledger in `docs/SECURITY.md` lists all of them.
● **A binding check that could not fire.** The CI `image` job was named as the binding check for
  container hardening in three documents, and triggered only on `main`, so on a release branch it
  had never run once. The container had never been built by anything, anywhere. Fixing the trigger
  immediately exposed a real defect: the image shipped `pip-25.0.1-py3-none-any.whl` under
  `ensurepip`, invisible to `command -v pip` and fully visible to a filesystem CVE scanner.
● **Mutation counts running ahead of the evidence.** Independent runs kept finding survivors I had
  claimed killed. `docs/SECURITY.md` now carries a per-round table of claimed against found, and
  the habit that fixed it is running the CONTROL suite FIRST on a COMPLETE copy: an incomplete
  copy once made eight mutants look killed by a test that was failing for an unrelated reason.

Three lessons worth carrying to the next project:

1. **A `PATH` check answers "what can the entrypoint run"; a scanner asks "what is in the image".**
   Different questions. Three releases of documentation asserted the second while testing only the
   first.
2. **When no test can distinguish two variants, the branch is not a control.** Remove it rather
   than defend it with another test.
3. **A fail-safe that depends on having enumerated every hostile input is not a fail-safe.** The
   `If-Match` guard needed three rounds because the first two enumerated spellings instead of
   catching the class.
