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
| The cap holds whatever ORDER the framing headers arrive in | `middleware.py` | `test_the_cap_holds_whatever_order_the_framing_headers_arrive_in` |
| The cap runs whatever CASE the method token arrives in | `middleware.py` | `test_a_lower_case_method_token_does_not_skip_the_cap` |
| An unparsable `If-Match` is ignored, not a 500 | `app.py` | `test_an_exotic_if_match_parses_to_no_revision_rather_than_raising` |
| No config file shadows the manifest's pytest settings | `pyproject.toml` | `test_no_configuration_file_shadows_the_manifests_pytest_settings` |
| The release version matches across the manifest and the package | both | `test_the_release_version_matches_across_the_manifest_and_the_package` |
| The BUILT artefact carries no `.git`, `.venv`, `var/`, `dist/` or `.env` | `scripts/package-appstore.sh` | `test_no_build_output_can_reach_the_platform_checkout` |
| The edit helper refuses a symlinked target and never half-edits | `scripts/verified-edit.py` | `test_the_edit_helper_refuses_a_symlinked_target`, `test_the_edit_helper_leaves_the_file_untouched_when_it_refuses` |
| The BODY drain is time-bounded on a TOTAL budget, so a framed body cannot park a socket | `middleware.py` | `test_a_client_that_frames_a_body_and_stops_sending_is_timed_out`, `test_the_budget_is_total_not_per_message`, `test_the_shipped_drain_budget_is_finite_and_wired_into_the_app` |
| The image script defers rather than passing, proved by EXECUTING it | `scripts/build-image.sh` | `test_no_reachable_daemon_defers_with_a_banner_and_a_non_zero_exit` |
| An unserved app holds no probe thread, and the lifespan releases the one it made | `app.py` | `test_building_an_app_spawns_no_thread_however_the_pool_is_created`, `test_the_lifespan_releases_the_probe_thread_it_created` |
| A declared length is not trusted when a transfer-encoding is present | `middleware.py` | `test_a_declared_length_is_not_trusted_when_a_transfer_encoding_is_present` |
| A probe path is never drained, so it cannot be parked unmetered | `middleware.py`, `app.py` | `test_a_probe_path_is_never_drained_even_for_a_body_method`, `test_the_apps_body_cap_exempts_the_probe_paths` |
| The probe runs on its own pool, so a burst cannot starve store work | `app.py` | `test_the_probe_runs_on_its_own_dedicated_thread_pool` |
| The probe pool SERIALISES its work, which is what orders publication | `app.py` | `test_the_probe_pool_serialises_its_work` |
| A probe after shutdown fails closed instead of using the shared executor | `app.py` | `test_a_probe_after_shutdown_fails_closed_rather_than_using_the_shared_executor` |
| Every control this document cites resolves to a test that exists | docs | `test_every_test_named_in_the_security_policy_exists` |
| The edit helper refuses a missing or ambiguous anchor | `scripts/verified-edit.py` | `test_the_edit_helper_refuses_a_missing_anchor`, `test_the_edit_helper_refuses_an_ambiguous_anchor` |
| The snapshot is not read through a symlink | `storage.py` | `test_the_snapshot_is_not_read_through_a_symlink` |
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
| No secret in any response, log, or audit line | `app.py`, `audit.py` | `test_diagnostics_never_exposes_a_token_value_or_an_exact_length` |
| Operator values normalised before use | `config.py` | `test_clean_strips_quotes_whitespace_and_control_characters` |
| Storage proved by a REAL write, never an existence check | `storage.py` | `test_probe_writable_reports_the_errno_when_the_write_is_refused`. NOTE: skipped when the suite runs as root, because root bypasses directory permissions, so this control is proved on the CI runner rather than locally. The file-not-a-directory case runs on every uid but does NOT kill an existence-check mutant, since it never reaches the write; citing that one here was wrong |
| Probe cannot hang; hard timeout shorter than the platform's | `app.py` | `test_a_hanging_probe_times_out...` |
| Probe cost bounded by TIME and by CONCURRENCY (single-flight) | `app.py` | `test_a_readiness_flood_causes_one_real_write...`, `test_concurrent_readiness_requests_run_one_probe_between_them` |
| Concurrent callers all receive one verdict, so none can race to overwrite another | `app.py` | `test_concurrent_callers_all_receive_the_same_verdict` |
| The rate limiter sits OUTSIDE the body cap, so oversize requests spend budget | `app.py` | `test_the_middleware_order_puts_the_limiter_outside_the_body_cap`, `test_an_oversize_request_still_spends_rate_limit_budget` |
| A probe path declaring a body that never arrives still answers | `middleware.py` | `test_a_liveness_request_declaring_a_body_that_never_arrives_still_answers` |
| The existence check for a partial update runs inside the store lock | `storage.py` | `test_the_cap_cannot_turn_a_must_exist_merge_into_a_partial_append` |
| The constant-time primitive is present and no token is compared with `==` | `auth.py` | `test_the_token_comparison_uses_the_constant_time_primitive` |
| Backups carry the same restrictive mode as the snapshot | `storage.py` | `test_the_snapshot_and_its_backups_share_the_same_restrictive_mode` |
| The lock path is not followed through a symlink | `storage.py` | `test_the_lock_file_is_not_followed_through_a_symlink` |
| A storage fault leaves the app unready, never unstartable | `app.py` | `test_the_app_still_starts_and_diagnoses_itself_when_the_snapshot_is_corrupt` |
| The rate-limit key table fails CLOSED when full | `ratelimit.py` | `test_a_full_table_refuses_a_new_caller_rather_than_evicting_a_tracked_one` |
| The HEALTHCHECK port is validated, never interpolated raw | `healthcheck.py` | `test_a_hostile_port_is_refused_rather_than_interpolated` |
| Store input and output runs off the event loop | `app.py` | `test_no_store_call_runs_on_the_event_loop` |
| Non-root numeric user, no suid or sgid bits, flat image | `Dockerfile` | `tests/test_appstore_contract.py` |

Each control was mutation-proved before submission: the code it protects was broken in a
copy of the tree and the named test went red. Mutants have been killed across three rounds,
covering the anti-shrink merge, the token compare, both rate-limit boundary
directions, the readiness fail-closed branch, the unknown-key rejection, the size cap, the
actor sanitiser, the closed-by-default write posture, the cross-origin method list, the
strict tier on both write routes, the byte-counting body cap, the probe cache, the port
validation, the exclusive write lock, the revision guard, the fail-closed key table, the
worker count, the package-manager purge, the package-database retention, and the two binding
image checks in continuous integration.

**Surviving mutants.** Not "all of them", which is what an earlier version of this section
claimed twice while independent runs kept finding more. A mutation claim is worth exactly what
the run behind it measured, and three separate rounds have proved that on this project:

| Round | Claimed | Independently found |
|---|---|---|
| 1 | 8 killed | 8 killed, 1 survivor recorded |
| 2 | 21 killed, 1 survivor | 4 survivors (32-mutant run) |
| 3 | 11 run, 3 survivors closed | 2 further survivors (11-mutant run) |
| 4 | 10 run, 10 killed after closing 2 survivors | 3 further survivors (engineering), 2 (security) |
| 5 | 6 run, 6 killed after closing all 5 | 1 MAJOR (a claimed proof disproved), 2 survivors (eng), 2 (sec) |
| 6 | 10 run, 10 killed after closing all 3 survivors | 2 MAJORs, 4 survivors, 1 dangling citation |
| 7 | 9 run, 9 killed after closing the last survivor | **both gates PASS**; 6 MINORs (eng), 5 (sec) |
| 8 | 10 run, 10 killed or shown neutralised by a layer | pending confirmation |

Survivors that remain, each with the reason it is or is not load-bearing:

● **`hmac.compare_digest` to `==`** (`auth.py`): survives every BEHAVIOURAL test, because the
  difference is timing, not output. Caught instead by a source assertion that the primitive is
  present, plus a module-wide check that no token is compared with plain equality. The timing
  property itself stays unassertable and is recorded as such.
● **Deleting the `store.seed()` call at boot** (`app.py`): survives, and is harmless rather
  than proved. `load()` returns an empty snapshot when the file is absent and `upsert_session`
  creates it, so seeding makes the first read cheaper and is not a control.
● **The guarded `int()` conversion in `_expected_rev`** (`app.py`): survives while the 19-digit
  length bound holds, because the bound catches every hostile spelling the suite can express. It
  is kept anyway, and this is a different judgement from the inert drain guard that was DELETED
  for being unreachable. That guard was behaviourally identical to the line after it. This one
  catches a different failure: an `int()` that raises for a reason other than length, which is
  precisely the category that has already bitten this function twice, once on a character class
  and once on the interpreter's digit limit. A backstop against the next unknown spelling cannot
  be asserted by enumerating known spellings, and its absence is what made the first two fixes
  incomplete. The bound itself IS pinned by a test, so the layer in front of it cannot be
  loosened silently.
● **The `_declared_over_cap` early refusal** (`middleware.py`): NO LONGER a survivor. An
  earlier version of this ledger said it was, which was wrong in the safe direction:
  `test_an_honest_oversize_declaration_is_refused_without_reading_the_body` passes a `receive`
  that raises, so disabling the refusal fails that test. Listed here because a ledger that
  under-reports its own coverage is still a ledger that is wrong.

Closed after surviving: the `asyncio.to_thread` offload, the dedicated probe pool, the quoted
bind address in the launch command, the dev-lockfile audit leg, the snapshot symlink defence,
the ASCII-digit port guard, the application's own exempt-path wiring for the body cap, the
lifespan pool release, the single-worker serialisation of the probe pool, the shipped drain
budget and its total-rather-than-per-message property, and the deferral behaviour of
`scripts/build-image.sh`, which is now EXECUTED against a stub `docker` rather than grepped.

REMOVED rather than closed: the lazy pool creation. Listed separately because it was never
killed and never could be. No test can distinguish lazy from eager creation, so the branch was
deleted rather than defended, and calling that a closed mutant would be the same overstatement
this ledger exists to prevent.

FIFTEEN mutants across the rounds were killed only after fixing the TEST rather than the code,
and the count is spelled out here because an earlier version of this paragraph said "six" and
then listed four:

1. and 2. Two asserted a Dockerfile invariant against the file's own explanatory prose.
3. One matched `--user 0` inside the comment explaining why the flag is needed, rather than in
   the command.
4. One matched a shell function call inside a commented-out line.
5. One asserted the image script's deferral by grepping for `THIS IS NOT A PASS` and `exit 3`
   anywhere in the file, so rewriting the no-daemon leg to `echo PASS; exit 0` stayed green.
   That test is deleted; four tests now EXECUTE the script against a stub `docker`.
6. One counted probe threads by NAME, and every pool names its worker `probe_0`, so a set of
   names deduplicated across applications and the assertion was vacuous.
7. One claimed lazy pool creation saved threads. A `ThreadPoolExecutor` starts no worker until
   work is submitted, so the test passed whether the pool was built lazily or eagerly. The
   branch was then REMOVED rather than defended: a dereferenced executor's worker also exits
   when the executor is collected, so no test could ever distinguish the two variants.
8. One asserted the drain bound by injecting the timeout, so the CONSTANT the container runs
   with was never read: setting it to 86 400 seconds left every test green.
9. One asserted the drain bound with a fake that stops sending, so making the budget
   per-message instead of total left the suite green. That mutant also made the test HANG
   rather than fail, because the test relied on the bound it was testing to terminate. Both
   the budget and the test's own bound are now explicit.

10. to 13. Four contract assertions read their target file RAW, so a COMMENT satisfied them:
    the SonarQube coverage path, the pytest coverage flag, `.env` in `.gitignore`, and the
    packaging purge that keeps `.git`, `.venv` and `dist/` out of the upload. Each was measured
    surviving as a commented-out line. They now go through a `.properties` parser, `tomllib`,
    and an executable-lines reader, so a comment cannot satisfy a contract assertion.

14. One asserted the packaging purge by matching a comment-stripped LINE, so a trailing
    `# TODO restore: rm -rf ...` on a live line deleted the purge with the suite green. It now
    BUILDS the artefact and inspects the zip. While fixing it, a reviewer's measurement
    corrected the claim behind it: the real control is the allowlist copy loop, which never
    copies those paths, and the `rm -rf` is a defensive re-check behind it. Removing either
    layer alone still yields a clean artefact; removing BOTH is what the test catches, which is
    what layered defence is supposed to look like.
15. One exempted every ellipsis-elided citation from the documentation sweep, leaving 12 of 63
    cited names unchecked. Elided names are now resolved by prefix.

All fifteen would have passed while the control was removed. Assertions here are about what
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
7. **Socket parking during the HEADER phase is not bounded by this application.** The body
   drain is bounded on a total budget, measured: 120 connections that frame a body and stop
   sending are all answered 408 and the listener's file descriptors return to their baseline.
   A connection that stops BEFORE the blank line ending the headers never reaches the ASGI
   application at all, so neither the drain bound nor the rate limiter can see it: 200 such
   connections took a worker from 10 to 210 descriptors and were still parked 27 seconds
   later. This is not fixable inside an ASGI application without writing a custom protocol,
   and it is what an ingress read timeout exists for. Recorded as an accepted residual with
   the platform ingress named as its bound, rather than left as an omission. It predates the
   drain bound and is not a regression of it.
8. **A name-shaped credential in a lock file's NAME position reaches the divergence report.**
   `scripts/check-environment.py` must name the distribution it found missing, or "pinned
   0.115.0, NOT INSTALLED" identifies nothing. A credential is not structurally distinguishable
   from a distribution name: `canonicalise` lowercases and folds separators, so a Personal Access
   Token comes out matching the PEP 503 name grammar exactly. `CANONICAL_NAME` rejects anything
   carrying a URL separator, an `@`, or surviving uppercase, and that is the whole control;
   `MAX_NAME_ECHO` bounds one log line and is explicitly NOT a secrecy boundary. Three length
   bounds were tried as one (32, then 24, then 64) and each excluded real distributions while
   admitting common secret formats, because the populations overlap: measured against the live
   PyPI simple index on 2026-08-21, 875,180 projects, longest canonical name 188 characters.
   Accepted because the report cannot do its one job without the name.
9. **A numeric credential of 40 characters or fewer in VERSION position reaches the same report,
   and this item was wrong twice before it was right.**

   The first version claimed `SAFE_VERSION` "excludes every credential format that carries a
   letter, an underscore or a separator". Two of those three clauses were false. The PEP 440
   local-version segment was unbounded, `\+[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*`, so anything
   alphanumeric joined by `.` or `-` was version-shaped: measured through the real script,
   `1.0+deadbeefcafebabe0123456789abcdef` (a 32-character hex API key),
   `0+AKIAIOSFODNN7EXAMPLE` (a cloud access key identifier) and a base32 secret all echoed in
   full. Only the underscore was excluded.

   The second version documented that class honestly and left it open. That was the wrong call:
   documenting a hole is not closing one, and this hole admitted the commonest fixed-length
   secret formats there are.

   **So the segment is bounded now**, to eight characters per component and at most three
   components. Every real local version still echoes - `+cu118`, `+cpu`, `+abcdef.1`, `+local.1`,
   the PyTorch and build-tag forms - and a 20-to-38-character token is reported by length instead.
   Measured: none of the three lock files pins a local version at all, so the bound costs nothing.

   **What remains, stated for the third time and this time measured.** Two earlier versions of
   this item called the residual "all-numeric". It is not. Any value matching `SAFE_VERSION` under
   40 characters echoes, which is a numeric release plus an optional local segment of up to three
   alphanumeric components of eight characters each. Measured: `0+AKIAIOSFODNN7EXAMPLE` is now
   described, and `0+AKIAIOSF.ODNN7EXA.MPLE` - the same 20-character cloud access key identifier,
   split across components - still echoes in full.

   So the bound narrows the class by length PER RUN. It does not exclude letter-bearing values, and
   an operator must not read it as doing so. What it does exclude is any undotted token over eight
   characters, which is the form a credential actually arrives in.

   Accepted because there is no separation to be had: real local versions run from 3 characters
   (`+cpu`) to 13 (`+computecanada`) and real secrets from 16 up, so a total-length cap fails the
   same way the name cap did at 32, 24 and 64. The report has to say which version is pinned or it
   cannot do its job.

   Items 8 and 9 are the residue of a control revised seven times. Six revisions tried to spot a
   credential inside attacker-influenced text and each was bypassed; the seventh stopped echoing
   arbitrary text at all, which closed every site except the two that must name what they found.
   Both are stated at the code site, asserted in the test suite as residuals rather than as
   controls, and recorded here because this register is where a reader looks.

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

## What the first container build proved, and what it found

**The image has now been built.** The CI `image` job ran for the first time on 2026-08-19 against
commit `e97a593`, after the trigger was fixed so it could fire at all. Four things are therefore
no longer taken on construction alone, they are measured against the built filesystem:

● `Config.User` is `10001:10001`, numeric and non-root.
● **Zero** setuid or setgid paths, files or directories, with the sweep run as root and its stderr
  surfaced so it cannot pass blind.
● No package-manager binary on `PATH`.
● The dpkg database is present, so the platform scanner can still enumerate OS packages.

The container also RAN and answered every platform probe, from the built image on port 8080:

```
GET /        200        GET /livez  200        GET /ping 200      GET /health 200
GET /readyz  503        with a complete diagnosis: errno 13, EACCES, resolved directory
GET /api/v1/diagnostics 200, and CI asserts the exact token length is absent
boot.access  {"authRequired":false,"writesOpen":false,"buildId":"v0.10.0"}
```

**The 503 there is correct, and worth explaining because it looks like a fault.** No file-storage
add-on is mounted in CI, so the non-root user cannot write the image's own default directory. The
application therefore starts, serves every liveness path, publishes a full diagnosis, and reports
itself UNREADY. That is the designed behaviour and it is deliberately not softened: making the
in-image directory writable would let a pod whose volume failed to mount run happily on ephemeral
storage and lose every training session on the next restart. A loud unready state is better than
silent data loss, so the fail-closed branch stays.

**And the first run found a real defect**, which is the argument for the check existing.
`ensurepip` vendors a complete pip wheel, `pip-25.0.1-py3-none-any.whl`. It is not a binary, so
`command -v pip` reported nothing and the package-manager check passed, while a filesystem CVE
scanner would report pip as a shipped package. The claim "the runtime ships no package manager"
was therefore FALSE, in exactly the way a reviewer hypothesised and could not settle without a
build. `ensurepip` is now removed in the prep stage and asserted both locally and in CI.

The lesson is not about pip. It is that a `PATH` check answers "what can the entrypoint run",
while the scanner asks "what is in the image", and those are different questions. Three releases
of documentation asserted the second while only testing the first.

## What is still unverified, and why

The image build now runs in CI, so the items above are confirmed. What remains unconfirmed is the
platform's OWN policy scan and SonarQube ruleset, which are server-side. The image also cannot be
built in the authoring environment. A Docker daemon starts in the authoring
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
