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
| Category | TBC, re-verify with the project owner |
| Visibility | TBC, re-verify with the project owner |

## Runtime contract

| Field | Value |
|---|---|
| Container port | 8080 |
| `PORT` handling | Read at runtime, default 8080, bound `0.0.0.0`. Never `ENV PORT=` |
| Launch command | `exec gunicorn enlightenment.asgi:app -k uvicorn.workers.UvicornWorker -b 0.0.0.0:${PORT:-8080}` |
| User | `10001:10001`, numeric and non-root |
| Root path | `GET /` returns 200 with JSON. Never a 302 |
| Liveness paths | `/livez`, `/ping`, `/health`. Always 200, dependency-free |
| Readiness paths | `/healthz`, `/readyz`. 200 when storage accepts a real write, else 503 with the resolved directory and errno |
| Diagnostics | `GET /api/v1/diagnostics`. Unauthenticated and secret-free by construction |
| Image healthcheck | `python -m enlightenment.healthcheck`, 5 second timeout, 3 retries |

## Environment variables

For a code-defaults application the correct operator console state is an **EMPTY**
Environment Variables tab. Platform-injected variables arrive at the pod level; anything
typed into the tab is an override and a liability. Guidance prose pasted into a value field
has cost a deploy cycle per variable, so every row below is either COPY-PASTE EXACT or
explicitly `[delete]`.

| Variable | Operator action | Source | Notes |
|---|---|---|---|
| `PORT` | `[delete]` | Platform-injected | Code default 8080 |
| `STORAGE_MOUNT_PATH` | `[delete]` | Injected by the FILE_STORAGE add-on | Code reads it at request time |
| `DATA_DIR` | `[delete]` | Optional override | Only to point storage somewhere other than the add-on mount |
| `ENLIGHTENMENT_TEAM_TOKEN` | Set only to host for a team | Operator-set secret | Unset means single-user local mode. If set, `ALLOWED_ORIGIN` must also be set |
| `ALLOWED_ORIGIN` | `https://enlightenment.apps.bluestaq.com` | Operator-set | Mandatory whenever the token is set. A wildcard with a token makes the app refuse to start |
| `BUILD_ID` | `[delete]` | Optional, stamped by CI | Falls back to the package version |

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
| Memory | TBC, re-verify against the App Store envelope before submission | Two gunicorn workers, no in-memory dataset of size |
| CPU | TBC, re-verify against the App Store envelope before submission | Request-bound, no batch work |

## Rollback

**First release. There is no previous version to roll back to.** Stated honestly rather than
implied. Once V0.2 exists, rollback is redeploying the previous image tag; the JSON snapshot
carries `schemaVersion` and every destructive write takes a timestamped backup first (five
retained), so a data rollback is a file restore inside the volume.

## Pre-submission checklist

- [x] Verification loop green (`sh scripts/verify.sh`)
- [x] Pipeline simulation green (`sh scripts/simulate-pipeline.sh`)
- [x] Version identical in `pyproject.toml` and `src/enlightenment/__init__.py`
- [x] Slug identical in code, docs, and this table
- [x] Package flat, `Dockerfile` at the zip root, tests included
- [ ] Container image built and the policy posture verified (**deferred to CI, not a pass**: a Docker daemon was started successfully in the authoring environment, but the container registry's blob endpoint is denied by that environment's network policy, so no base-image layer can be pulled. The Dockerfile is therefore neither proved nor disproved here. The CI `image` job builds it, asserts the numeric non-root user, asserts zero setuid or setgid paths in the shipped image, asserts no package manager ships, and probes the health paths on 8080. That job is the binding check.)
- [ ] `engineering-reviewer` PASS
- [ ] `security-reviewer` PASS
- [ ] `deploy-gate` PASS
- [ ] Explicit human confirmation to publish
