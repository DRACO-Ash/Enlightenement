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

With no team token set the application runs in single-user local mode with authentication
off, bound to loopback. Set `ENLIGHTENMENT_TEAM_TOKEN` and `ALLOWED_ORIGIN` together to host
it for a team; a token with a wildcard origin makes the application refuse to start.

## The endpoints

| Method and path | Auth | Purpose |
|---|---|---|
| `GET /` | none | 200 with name, version, status. Never a redirect |
| `GET /livez`, `/ping`, `/health` | none | Liveness. Always 200, dependency-free |
| `GET /healthz`, `/readyz` | none | Readiness. Proves storage with a real write; 503 with the errno when it cannot |
| `GET /api/v1/diagnostics` | none | Secret-free read-out: booleans, lengths, errnos, own identity |
| `GET /api/v1/sessions` | none | List training sessions |
| `POST /api/v1/sessions` | token | Create or fully upsert a session |
| `PATCH /api/v1/sessions/{id}` | token | Partial update, anti-shrink |

## Documentation

- `CLAUDE.md`: the always-true conventions and the hard rules.
- `docs/DEPLOYMENT.md`: the App Store deployment parameters table.
- `docs/SECURITY.md`: the threat model, the controls, and every accepted risk.
- `docs/CHANGELOG.md`: one audit row per change.
- `.claude/skills/`: the Bluestaq Foundations baseline this project inherits.
