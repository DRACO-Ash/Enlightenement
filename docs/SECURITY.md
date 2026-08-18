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
| **Writes CLOSED by default**: no token and no opt-in means 401 | `config.py`, `app.py` | `test_writes_are_refused_by_default_with_no_token_configured` |
| Anonymous writes need an explicit opt-in, and cannot combine with a token | `config.py` | `test_anonymous_writes_require_the_explicit_opt_in` |
| A token below the minimum length refuses to start | `config.py` | `test_a_token_shorter_than_the_minimum_refuses_to_start` |
| A token without an allowed origin refuses to start | `config.py` | `test_a_token_without_an_allowed_origin_refuses_to_start` |
| Health paths public, and nothing else | `app.py` | `test_health_paths_stay_public_when_a_token_is_configured` |
| Boundary validation rejects, never coerces | `models.py` | `test_a_malformed_body_is_rejected_generically` |
| Unknown keys rejected (`extra="forbid"`) | `models.py` | same, `body1` case |
| Body cap enforced on BYTES READ, so chunked framing cannot bypass it | `middleware.py` | `test_an_oversize_chunked_body_is_refused_on_bytes_read` |
| The cap runs ahead of authentication | `middleware.py` | `test_an_oversize_chunked_body_is_refused_before_authentication` |
| Two-tier rate limiting, 429 in both tiers | `ratelimit.py`, `app.py` | `test_the_coarse_tier...`, `test_the_strict_tier...` |
| Probe paths never rate-limited | `app.py` | `test_probe_paths_are_never_rate_limited` |
| A wildcard origin refuses to start, unconditionally | `config.py` | `test_a_wildcard_origin_always_refuses_to_start_even_without_a_token` |
| Every exposed method survives a preflight | `app.py` | `test_every_exposed_method_survives_a_preflight_from_the_allowed_origin` |
| A 413 or 429 still carries the cross-origin header | `app.py` | `test_a_rate_limited_response_still_carries_the_cross_origin_header` |
| Anti-shrink merge; a partial update deletes nothing | `storage.py` | `test_a_partial_patch_keeps_every_field...` |
| Atomic write; no half-written or orphaned file | `storage.py` | `test_write_is_atomic...`, `test_a_failed_write_leaves_no_temporary_file_behind` |
| Writes serialised by an exclusive lock; no lost update across processes | `storage.py` | `test_two_processes_writing_at_once_lose_no_record` |
| A stale revision is a 409, never a silent overwrite | `storage.py`, `app.py` | `test_a_stale_expected_revision_is_refused...`, `test_a_stale_if_match_is_a_409...` |
| Backup before a destructive write, pruned to retention | `storage.py` | `test_a_backup_is_taken_before_an_overwrite...` |
| Log injection blocked; actor sanitised and capped | `audit.py` | `test_newline_injection_cannot_forge_a_second_line` |
| EVERY reflected log value sanitised, lines emitted as JSON | `audit.py`, `app.py` | `test_an_event_line_sanitises_every_string_field_structurally` |
| Generic client errors; detail server-side only | `app.py` | `test_an_unhandled_error_returns_a_generic_message...` |
| No secret in any response, log, or audit line | `app.py`, `audit.py` | `test_diagnostics_reports_booleans_and_lengths_but_never_a_secret_value` |
| Operator values normalised before use | `config.py` | `test_clean_strips_quotes_whitespace_and_control_characters` |
| Storage proved by a REAL write, never an existence check | `storage.py` | `test_probe_reports_an_existing_path_that_is_a_file...` |
| Probe cannot hang; hard timeout shorter than the platform's | `app.py` | `test_a_hanging_probe_times_out...` |
| Probe cost bounded by TIME, so an unauthenticated flood cannot exhaust volume IOPS | `app.py` | `test_a_readiness_flood_causes_one_real_write_not_one_per_request` |
| A storage fault leaves the app unready, never unstartable | `app.py` | `test_the_app_still_starts_and_diagnoses_itself_when_the_snapshot_is_corrupt` |
| The rate-limit key table fails CLOSED when full | `ratelimit.py` | `test_a_full_table_refuses_a_new_caller_rather_than_evicting_a_tracked_one` |
| The HEALTHCHECK port is validated, never interpolated raw | `healthcheck.py` | `test_a_hostile_port_is_refused_rather_than_interpolated` |
| Store input and output runs off the event loop | `app.py` | exercised throughout `test_http.py` |
| Non-root numeric user, no suid or sgid bits, flat image | `Dockerfile` | `tests/test_appstore_contract.py` |

Each control was mutation-proved before submission: the code it protects was broken in a
copy of the tree and the named test went red. Twenty-one mutants have been killed across two
rounds, covering the anti-shrink merge, the token compare, both rate-limit boundary
directions, the readiness fail-closed branch, the unknown-key rejection, the size cap, the
actor sanitiser, the closed-by-default write posture, the cross-origin method list, the
strict tier on both write routes, the byte-counting body cap, the probe cache, the port
validation, the exclusive write lock, the revision guard, the fail-closed key table, the
worker count, the package-manager purge, the package-database retention, and the two binding
image checks in continuous integration.

One mutant SURVIVED and is recorded rather than hidden: replacing `hmac.compare_digest` with
`==` in `auth.py` leaves the suite green. The constant-time property is not assertable by a
functional test, which is a property of timing, not a gap in the suite. The functional
fail-closed behaviour is covered; the timing property rests on using the standard-library
primitive, and the review gates read that line.

Two of those mutants were killed only after fixing the TEST rather than the code: one
asserted a Dockerfile invariant against the file's own explanatory prose, and one matched
`--user 0` inside the comment explaining why the flag is needed rather than in the command.
Both would have passed while the control was removed. Assertions here are about what
executes, never about the words beside it.

## Accepted risks (deliberate decisions, not oversights)

1. **Shared-token model, no per-user identity.** Any holder of the team token has the same
   authority. A hostile authenticated team member is out of scope. `_token_dependency` in
   `app.py` is the single-sign-on seam where a per-user provider would attach.
2. **Diagnostics is unauthenticated.** `GET /api/v1/diagnostics` returns booleans, errnos,
   a coarse size BAND for the team token, and this process's own uid and gid. Never a secret
   value and never the token's exact length: an exact count tells an attacker how many
   characters to attack, so the band plus an enforced 24-character minimum carries the
   stale-versus-correct signal instead. Reachability is the point: the field evidence is that
   a read-out only useful after authentication ends up unreachable in exactly the deploy
   failures it exists to diagnose. Reviewed as an accepted information-exposure trade for
   operability.
3. **Rate-limit keying is coarse.** Callers are keyed by remote address. Behind the platform
   gateway many callers can share one address, so the limiter protects the process rather
   than fairly apportioning per user. Acceptable while the token is shared.
4. **The rate limiter is per process.** The container runs a single worker, so the
   configured limit is the effective limit today. If the worker count ever rises, the
   effective limit rises with it; an exact global limit would need a shared store. The
   purpose is process protection, which this achieves.
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

## What is still unverified, and why

The container image has never been built. A Docker daemon starts in the authoring
environment, but the registry's blob endpoint is denied by that environment's network
policy, so no base-image layer can be pulled and the Dockerfile is neither proved nor
disproved. Container hardening therefore rests on two things: static assertions over the
Dockerfile text in `tests/test_appstore_contract.py`, and the CI `image` job, which is the
binding check. Both were themselves found wanting on first review and have been corrected:
the suid sweep now runs as root (a non-root `find` cannot descend into a directory it cannot
read, so it returned zero while bits could still ship), the package-manager check now covers
the class rather than pip alone, and the readiness assertion now captures and checks the
status code rather than accepting any reply. Until that job has run green, treat container
hardening as unverified, not as passing.
