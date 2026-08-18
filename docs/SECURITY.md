# Security policy: Enlightenment

The threat model, the controls, and every deliberately accepted risk. A risk recorded here
is a decision; a risk not recorded here is an oversight.

## Threat model

The high-value assets are the shared team token and the integrity of the training dataset.
The dataset is low-sensitivity: its integrity (not being shrunk or poisoned) matters more
than its secrecy. The trust boundary is the HTTP edge: request bodies, path parameters, the
token header, and anything the operator types into the console are untrusted until validated.

Realistic attackers: an unauthenticated client probing the public ingress; a malformed or
oversize body; a crafted actor string attempting log injection; a caller flooding the
state-changing route.

## Controls, each with a test that fails if it regresses

| Control | Where | Test |
|---|---|---|
| Token compared in constant time with a length guard | `auth.py` | `tests/test_auth.py` |
| No configured token cannot authorise (fail closed) | `auth.py` | `test_no_configured_token_cannot_authorise` |
| Every cost-incurring and state-changing route gated | `app.py` | `test_a_write_without_a_token_is_refused...` |
| Health paths public, and nothing else | `app.py` | `test_health_paths_stay_public_when_a_token_is_configured` |
| Boundary validation rejects, never coerces | `models.py` | `test_a_malformed_body_is_rejected_generically` |
| Unknown keys rejected (`extra="forbid"`) | `models.py` | same, `body1` case |
| Request body size cap | `app.py` | `test_an_oversize_body_is_refused_before_it_is_parsed` |
| Two-tier rate limiting, 429 in both tiers | `ratelimit.py`, `app.py` | `test_the_coarse_tier...`, `test_the_strict_tier...` |
| Probe paths never rate-limited | `app.py` | `test_probe_paths_are_never_rate_limited` |
| CORS fail-closed; wildcard with a token refuses to start | `config.py` | `test_wildcard_origin_with_a_token_refuses_to_start` |
| Anti-shrink merge; a partial update deletes nothing | `storage.py` | `test_a_partial_patch_keeps_every_field...` |
| Atomic write; no half-written or orphaned file | `storage.py` | `test_write_is_atomic...`, `test_a_failed_write_leaves_no_temporary_file_behind` |
| Backup before a destructive write, pruned to retention | `storage.py` | `test_a_backup_is_taken_before_an_overwrite...` |
| Log injection blocked; actor sanitised and capped | `audit.py` | `test_newline_injection_cannot_forge_a_second_line` |
| Generic client errors; detail server-side only | `app.py` | `test_an_unhandled_error_returns_a_generic_message...` |
| No secret in any response, log, or audit line | `app.py`, `audit.py` | `test_diagnostics_reports_booleans_and_lengths_but_never_a_secret_value` |
| Operator values normalised before use | `config.py` | `test_clean_strips_quotes_whitespace_and_control_characters` |
| Storage proved by a REAL write, never an existence check | `storage.py` | `test_probe_reports_an_existing_path_that_is_a_file...` |
| Probe cannot hang; hard timeout shorter than the platform's | `app.py` | `test_a_hanging_probe_times_out...` |
| Non-root numeric user, no suid or sgid bits, flat image | `Dockerfile` | `tests/test_appstore_contract.py` |

Each control was mutation-proved before submission: the code it protects was broken in a
copy of the tree and the named test went red. Eight mutants across the anti-shrink merge, the
token compare, both rate-limit boundary directions, the readiness fail-closed branch, the
unknown-key rejection, the size cap, and the actor sanitiser were all killed.

## Accepted risks (deliberate decisions, not oversights)

1. **Shared-token model, no per-user identity.** Any holder of the team token has the same
   authority. A hostile authenticated team member is out of scope. `_token_dependency` in
   `app.py` is the single-sign-on seam where a per-user provider would attach.
2. **Diagnostics is unauthenticated.** `GET /api/v1/diagnostics` returns booleans, lengths,
   errnos, and this process's own uid and gid, never a secret value. Reachability is the
   point: the field evidence is that a read-out only useful after authentication ends up
   unreachable in exactly the deploy failures it exists to diagnose. Reviewed as an accepted
   information-exposure trade for operability.
3. **Rate-limit keying is coarse.** Callers are keyed by remote address. Behind the platform
   gateway many callers can share one address, so the limiter protects the process rather
   than fairly apportioning per user. Acceptable while the token is shared.
4. **The rate limiter is per process.** With two gunicorn workers the effective limit is
   double the configured value. A shared store would be needed for an exact global limit;
   the current purpose is process protection, which this achieves.
5. **Reads are open.** `GET /api/v1/sessions` is unauthenticated because the dataset is
   low-sensitivity and its integrity, not its secrecy, is what is defended. Writes are gated.
6. **Dataset confidentiality is out of scope.** Recorded, not assumed.

## Recovery, not just fail-closed

A control can be perfectly fail-closed and still be a design defect if its failure is
unrecoverable. Two consequences are built in:

- A storage fault makes the application **unready**, never **unstartable**. An app that
  refuses to boot cannot serve the diagnosis explaining why.
- The team token gates writes only. Losing or mangling it never locks anyone out of the
  diagnostics read-out or the health paths, so recovery never depends on the thing that failed.

## Secrets handling

No real secret is in the repository, the image, or any log. `.env.example` names every
variable with an empty placeholder; `.env` is git-ignored and excluded from the upload
allowlist. The Dockerfile contains no `ENV` naming a secret. Rotation happens at the
provider and is applied through the App Store env-var lifecycle: `save_env_vars` with the
COMPLETE set, then `apply_env_vars`. The repository never held a real value, so rotation
touches the environment only.
