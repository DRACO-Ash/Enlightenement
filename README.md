# Enlightenment

An orbital warfare training application. Server archetype, deployed to the Bluestaq App
Store at `enlightenment.apps.bluestaq.com` under the `python` container template.

## Quick start

```sh
python3.12 -m venv .venv
.venv/bin/pip install --require-hashes --no-deps -r requirements.txt -r requirements-dev.txt
sh scripts/verify.sh          # the verification loop
.venv/bin/python -m enlightenment
```

**Writes are closed by default.** With no `ENLIGHTENMENT_TEAM_TOKEN` set, every write route
returns 401 while reads, the health paths, and the diagnostics read-out stay open. To host for
a team, set `ENLIGHTENMENT_TEAM_TOKEN` (at least 24 characters) and `ALLOWED_ORIGIN` together;
a token without an origin makes the application refuse to start, as does a wildcard origin at
any time. An origin alone is harmless and simply leaves writes closed. For local
single-user work with writes open, set `ENLIGHTENMENT_ALLOW_ANONYMOUS=1`, which cannot be
combined with a token.

## The endpoints

| Method and path | Auth | Purpose |
|---|---|---|
| `GET /` | none | 200 with name, version, status. Never a redirect |
| `GET /livez`, `/ping`, `/health` | none | Liveness. Always 200, dependency-free |
| `GET /healthz`, `/readyz` | none | Readiness. Proves storage with a real write; 503 with the errno when it cannot |
| `GET /api/v1/diagnostics` | none | Secret-free read-out: booleans, lengths, errnos, own identity |
| `GET /api/v1/sessions` | none | List training sessions. Emits an ETag, answers 304 |
| `POST /api/v1/sessions` | token | Create or fully upsert a session. Honours `If-Match`, 409 on a stale revision |
| `PATCH /api/v1/sessions/{id}` | token | Partial update, anti-shrink. Honours `If-Match` |

## Documentation

- `CLAUDE.md`: the always-true conventions and the hard rules.
- `docs/DEPLOYMENT.md`: the App Store deployment parameters table.
- `docs/SECURITY.md`: the threat model, the controls, and every accepted risk.
- `docs/CHANGELOG.md`: one audit row per change.
- `.claude/skills/`: the Bluestaq Foundations baseline this project inherits.
