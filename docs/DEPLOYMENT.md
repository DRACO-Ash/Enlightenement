# Deployment parameters: Enlightenment

The single source of the App Store platform settings for this application. The operator
configures the store from this table, so nothing here is left implicit in prose. Regenerate
it whenever any value changes; a later delivery need only ship the delta.

Status: prepared for the FIRST delivery. Not yet submitted. Nothing has been deployed.

## Application record

| Field | Value |
|---|---|
| Display name | Enlightenment |
| Slug | `enlightenment` |
| URL | `enlightenment.apps.bluestaq.com` |
| Detected template | `python` (root `requirements.txt` with a root `Dockerfile`) |
| Quality gate | Binding: line coverage 80% or more, zero open violations, hotspots reviewed |
| Category | Training / Simulation. Owner decision, 2026-08-18. If the console's list uses different wording, pick its nearest equivalent and record the exact string here rather than forcing this one |
| Visibility | Private to the Bluestaq Ltd team. Owner decision, 2026-08-18 |
| App type | Web App |
| Content directory | `CONTENT_DIR`, and only that name. `ENLIGHTENMENT_CONTENT_DIR` was read by the loader's own resolver at V0.24.0 and is now dead. An operator who set it got the baked-in tree served over HTTP while the validator checked a different one, so verification leg 2 could pass green against content the server never loads. Set nowhere in the Dockerfile: platform injection wins, as for `PORT` and `DATA_DIR` |
| Version | 0.26.5, matching `pyproject.toml` and `src/enlightenment/__init__.py` |
| Short description | Orbital warfare training application. Records and reviews training sessions against a shared, audited dataset. |
| Full description | Enlightenment is an orbital warfare training application for the Bluestaq Ltd team. It records training sessions and their outcomes to a durable, audited dataset held on a persistent volume, and serves them over a small authenticated HTTP interface. Every write is authenticated against a shared team token, validated at the boundary, serialised so no concurrent update can be silently lost, and recorded as one structured audit line. Reads, the health paths, and a secret-free diagnostics read-out stay unauthenticated so the service can always be diagnosed. Writes fail closed: with no token configured they are refused rather than opened. The training scenario vocabulary is deliberately left open pending the project owner's controlled terms, rather than populated with invented ones. |

## Runtime contract

| Field | Value |
|---|---|
| Container port | 8080 |
| `PORT` handling | Read at runtime, default 8080, bound `0.0.0.0`. Never `ENV PORT=` |
| Launch command | `exec gunicorn enlightenment.asgi:app -k uvicorn.workers.UvicornWorker -b 0.0.0.0:${PORT:-8080} --workers 1 --timeout 60 --access-logfile - --error-logfile -` (verbatim; the worker count is load-bearing, see Concurrency below) |
| User | `10001:10001`, numeric and non-root |
| Root path | `GET /` returns 200 with JSON. Never a 302 |
| Liveness paths | `/livez`, `/ping`, `/health`. Always 200, dependency-free |
| Readiness paths | `/healthz`, `/readyz`. 200 when storage accepts a real write, else 503 with the resolved directory and errno |
| Diagnostics | `GET /api/v1/diagnostics`. Unauthenticated and secret-free by construction |
| Image healthcheck | `python -m enlightenment.healthcheck`, 5 second timeout, 3 retries. Probes `/livez`, NOT readiness: a Docker HEALTHCHECK is a liveness signal and anything acting on it restarts the container, so pointing it at readiness would restart the pod on a storage fault |
| **Platform readiness probe** | Configure on `/healthz`. That is the path carrying the real-write proof and the diagnostic 503 |
| **Platform liveness probe** | Configure on `/livez`. Dependency-free, so a storage fault never restarts a healthy container |

## Environment variables

**This deployment sets two variables, and only two.** Visibility is private to the Bluestaq
Ltd team, so `ENLIGHTENMENT_TEAM_TOKEN` must be set, and setting it makes `ALLOWED_ORIGIN`
mandatory: the application refuses to start with one and not the other. Every OTHER row is
`[delete]`.

The default for a code-defaults application is an EMPTY tab, and that remains the rule for
every variable the platform injects. Anything typed in is an override and a liability, and
guidance prose pasted into a value field has cost a deploy cycle per variable, so every row
below is either COPY-PASTE EXACT or explicitly `[delete]`.

Safe either way: if the token is left unset the application still starts and still serves
reads and health, it simply refuses every write with a 401. The failure mode of forgetting the
token is a read-only service, never an open one.

| Variable | Operator action | Source | Notes |
|---|---|---|---|
| `PORT` | `[delete]` | Platform-injected | Code default 8080 |
| `STORAGE_MOUNT_PATH` | `[delete]` | Injected by the FILE_STORAGE add-on | Code reads it at request time |
| `DATA_DIR` | `[delete]` | Optional override | Only to point storage somewhere other than the add-on mount |
| `ENLIGHTENMENT_TEAM_TOKEN` | **SET.** Generate at least 24 characters, mark the field SECRET | Operator-set secret | Required for this deployment: visibility is private to the team. Under 24 characters the app refuses to start. Never pasted into a comment, a document, or a commit |
| `ALLOWED_ORIGIN` | `https://enlightenment.apps.bluestaq.com` | Operator-set | Mandatory whenever the token is set. `*` and `null` both refuse to start, in any letter case, whether or not a token is set. `null` is the Origin a sandboxed iframe or a `file://` page sends, so allowing it names no real caller |
| `ENLIGHTENMENT_ALLOW_ANONYMOUS` | `[delete]` | Operator-set | Local single-user work ONLY. Opens every write route to any caller. Cannot combine with a token: the app refuses to start on the contradiction |
| `BUILD_ID` | `[delete]` | Optional, stamped by CI | Falls back to the package version |

**Build-time only, never an App Store variable:** `ENLIGHTENMENT_CONTAINER_ENGINE` selects the
container engine `scripts/build-image.sh` uses. Podman first by default, because that is what the
platform's containerize stage uses; Docker as a fallback. Set it only to force a specific engine
on a developer machine. An override naming an engine that is not runnable **fails with exit 2**
rather than falling back to discovery, because an explicit choice that silently builds with
something else is worse than no override. It never belongs in the platform's environment tab.

`ENLIGHTENMENT_PYTHON` is the same class: it selects the interpreter `scripts/verify.sh` runs
every leg through, for a runner that installs into the system environment rather than a virtual
environment. Build-time only.

## Access posture (read before configuring the environment tab)

**Writes are closed by default.** With no `ENLIGHTENMENT_TEAM_TOKEN` and no
`ENLIGHTENMENT_ALLOW_ANONYMOUS`, every write route returns 401 while `GET /`, the health
paths, the session listing, and the diagnostics read-out stay open. That combination is
deliberate: an absent token is the container default and this tab is documented as empty, so
treating "no token" as "open" would place an unauthenticated write endpoint on a public
ingress by omission. It was measured doing exactly that before the fix.

Reads and diagnostics stay open so the posture is recoverable: an operator can always see
what the application thinks its configuration is, even when writes are shut.

## Concurrency

The training snapshot is a file-backed read-modify-write store, so the write path is
serialised three ways and all three matter:

● The launch command runs **one** worker. Two workers were measured losing half of all
  acknowledged writes, with a 201 and an audit line returned for each one that vanished.
● Every write holds an exclusive `fcntl.flock` across load, merge, and rename, so a second
  process cannot lose an update even if the worker count changes or the pod restarts.
● Each snapshot carries a monotonic `rev`. A caller may send `If-Match`, and a mismatch is a
  409 rather than a silent overwrite. This is the backstop where advisory locking does not
  hold, such as some network mounts.

If a future change needs more than one worker, move the store to the database add-on rather
than raising the worker count.

## Add-ons

| Add-on | Enable | Why | Injects |
|---|---|---|---|
| FILE_STORAGE | Yes | The atomic JSON snapshot needs a persistent volume | `STORAGE_MOUNT_PATH` |

**`securityContext.fsGroup` is required.** This container runs non-root (`10001`) and mounts
the file-storage add-on. The add-on volume is root-owned by default, so every write returns
`EACCES` until an operations request sets `securityContext.fsGroup`. This is platform-general
for every non-root workload using the add-on, not specific to this application. Raise the
request with the deployment. The readiness path will report `503` with `errno 13 (EACCES)` and
the resolved directory until it is set, so the symptom is unambiguous.

## Resource budget

| Resource | Request | Notes |
|---|---|---|
| Memory | Request 1Gi, limit 2Gi. Owner decision, 2026-08-18 | ONE gunicorn worker (see Concurrency), no in-memory dataset of size. Measured floor about 73 MiB resident across master and worker under 120 requests, on the host interpreter rather than the container, so treat it as a floor and not the number to size to |
| CPU | Request 1 CPU, limit 2 CPU. Owner decision, 2026-08-18 | Request-bound, no batch work. One worker, asynchronous and input-output bound |

## Rollback

**First release. There is no previous version to roll back to.** Stated plainly rather than
implied: nothing through V0.8 has been submitted or deployed, `origin/main` carries a single
commit, and no App Store record exists. There is therefore no previous image tag and no earlier
package to resubmit, and that cannot be manufactured.

### Withdrawing THIS deployment, if it has to come out

The normal rollback does not apply to a first deployment, so the withdrawal path is written
here rather than improvised under pressure:

1. **Take the application out of service through the lifecycle action in the console.** Do NOT
   delete the app record as a first move.
2. **Do not delete and recreate under the same slug.** The platform's known failure is app-record
   residue: a recreated app under a slug that has been used before can fail with zero pipeline
   stages run, and recovery then needs a fresh slug, which changes the URL the team has been
   given. Deleting is the step that is hard to undo, not the deploy.
3. **If a recreate is genuinely required**, confirm with the platform owners that the old app
   record AND its generated GitLab project are both cleared before recreating, and expect to
   need a new slug. Treat the URL as changed until proved otherwise.
4. **The data survives independently.** The snapshot lives on the file-storage add-on volume, not
   in the image, so taking the application out of service does not destroy it.

Once a version HAS shipped, rollback is the ordinary path: redeploy the previous image tag or
resubmit the previous package. The snapshot carries `schemaVersion` and every destructive write
takes a timestamped backup first (five retained), so a data rollback is a file restore inside
the volume.

## Pre-submission checklist

- [x] Verification loop green (`sh scripts/verify.sh`), 967 passed and 2 skipped, coverage 97.19%
- [x] Pipeline simulation green against the version being shipped (`sh scripts/simulate-pipeline.sh 0.26.5`; with no argument the script defaults to 0.1.0 and would simulate a zip that is not the one going up)
- [x] Version identical in `pyproject.toml` and `src/enlightenment/__init__.py`
- [x] Slug identical in code, docs, and this table
- [x] Package flat, `Dockerfile` at the zip root, tests included
- [ ] Container image built and the policy posture verified (**deferred to CI, not a pass**: a Docker daemon was started successfully in the authoring environment, but the container registry's blob endpoint is denied by that environment's network policy, so no base-image layer can be pulled. The Dockerfile is therefore neither proved nor disproved here. The CI `image` job builds it, asserts the numeric non-root user, asserts zero setuid or setgid paths in the shipped image, asserts no package manager ships, and probes the health paths on 8080. That job is the binding check.)
- [ ] `engineering-reviewer` PASS. **Last verdict was FAIL, on commit `08a384e`**, with one MAJOR:
      the fourth defeat of the constant-time detection control in four rounds. `inspect.getsource`
      reads the location a code object SELF-REPORTS, and `types.CodeType.replace()` writes
      `co_filename` and `co_firstlineno`, so a forged code object was handed the canonical source
      while returning `True` unconditionally - and the round-seventeen changelog had cited those two
      fields as the reason the pin was safe. The control is now the executed BYTECODE compared
      against `auth.py` compiled from disk. The verdict BEFORE that was FAIL on `03d9788`, with one
      BLOCKER and five MAJORs. The BLOCKER was an unconditional authentication bypass surviving the
      whole loop: the AST body pin on `token_ok` read the module's SOURCE, so leaving the canonical
      `def` untouched, appending a naked wrapper with a break-glass branch, spoofing its
      `__qualname__` and rebinding the module-level name passed every check with ruff and mypy
      silent. The pin now follows the code object `auth.token_ok` reaches. The MAJORs were a
      substitutable `hmac.compare_digest` attribute, two docstrings claiming a closure they did not
      have, a stale collected count, and this bullet naming the wrong prior FAIL. An earlier PASS at
      commit `068b1c4` is not evidence about this tree and the tick claiming it has been removed.
      Every finding is closed in this release; the gate re-runs against this head and the tick goes
      back only on the verdict itself.
- [ ] `security-reviewer` PASS. **The verdict was PASS on commit `be19697`**, after a 60-mutant
      campaign across `src/` and a live black-box run: no BLOCKER, no MAJOR. It confirmed all four
      new regression tests are the SOLE killer of the control they name, that all nine promoted
      exemptions are real, and it recomputed every published register figure independently. **The
      tick is withheld deliberately**: commits since that verdict changed `auth.py`'s regression
      control and `audit()`'s sanitisation of reflected values, both security boundaries, and the
      rule this checklist already states for the engineering row applies equally here - a PASS
      against an ancestor is not evidence about this tree. The tick returns on a verdict against
      this head.
- [ ] `deploy-gate` PASS. Returned FAIL at V0.8.0 with three blockers, none of them a defect in
      the application: five undefined submission fields, an unset resource budget, and a container
      contract that could not be confirmed because the CI `image` job named as its binding check
      had never run and could not fire on this branch. The owner decisions and the budget are now
      recorded above, and the trigger is fixed in V0.9.0, so the job can run. Re-run the gate once
      it has.
- [ ] Explicit human confirmation to publish
