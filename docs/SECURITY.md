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
| **The answer key never crosses the wire before the operator commits.** The served drill has no answer field, no explanation, and no derived expected value for a computed numeric item; the reveal is the response to the scored POST. Asserted on the raw response BODY against the real 140-item library, because a field added to a model shows up in the bytes whether or not anything parsed it | `training/drill.py`, `generators/base.py`, `training_api.py` | `test_a_served_drill_carries_no_answer_key`, `test_a_served_drill_carries_no_derived_value_for_a_computed_item`, `test_the_wire_form_never_carries_the_derived_expected_value`, `test_an_unanswered_drill_carries_no_answer_key_in_its_raw_body` |
| Interface served with a strict Content Security Policy: `script-src 'self'`, no external origin, `frame-ancestors 'none'` | `training_api.py` | `test_the_interface_is_served_with_a_strict_policy` |
| Interface files served from a two-entry allowlist, never a path join | `training_api.py` | `test_the_interface_script_is_served_from_an_allowlist` |
| No markup-parsing or dynamic-code sink in the client; every content value written as text | `ui/app.js` | `test_the_interface_never_writes_an_untrusted_value_as_markup` |
| Air-gap posture: no CDN, no external request in any shipped asset | `ui/` | `test_the_interface_makes_no_external_request` |
| Every drill answer validated at the boundary, `extra="forbid"`, every field capped | `models.py` | `test_a_malformed_answer_is_refused_at_the_boundary` |
| **Red is reserved for RECENCY on plot surfaces and is never used for a verdict.** Provisional, pending an owner decision. In the operator's real toolset red means "the most recent data", consistently, in the heat map, the LAT/LON view and the light curves. Using it for "your call was wrong" here would teach one colour two unrelated ways, and transfer of training turns on the practice environment's surface features matching the job's. The verdict classes use the other channels plus a glyph, so the meaning never rests on colour alone either | `ui/index.html`, `ui/app.js` | `test_red_is_reserved_for_recency_and_never_used_for_a_verdict` |
| Produced-answer length bounded before any normalisation work | `scoring/matching.py` | `test_a_pathological_answer_is_bounded_before_any_work_is_done` |
| Scoring endpoint strictly rate limited, as a write | `app.py`, `training_api.py` | `test_answering_is_strictly_rate_limited` |
| **The redaction control moved UPSTREAM in V0.24.0.** The illustrative library was re-checked at the serving edge for a protected identifier. The shipped library is Ash's package, whose own `_version` block states that no real object identifier appears in any prompt or answer and whose validator is the authority; re-deriving that judgement over content this project did not author was the weaker control, not the stronger one | `tools/validate_content.py` (vendored), `scripts/verify.sh` | `test_the_content_validator_runs_as_a_verification_leg` |
| Progress file, which will hold personal performance data, never world-readable | `training/progress.py` | `test_the_progress_file_is_never_world_readable` |
| Damaged progress file degrades to defaults rather than returning a 500 with internal detail | `training/progress.py` | `test_a_damaged_progress_file_degrades_to_defaults_rather_than_a_500`, `test_a_run_row_of_an_unknown_shape_is_skipped_rather_than_fatal` |
| Run history capped, so a free-text field cannot grow a file read whole on every request | `training/progress.py` | `test_run_history_is_capped_so_the_file_cannot_grow_without_limit` |
| A content fault is a 503 on the training routes and never takes the health paths down | `app.py`, `training_api.py` | `test_a_broken_content_tree_is_a_503_naming_the_files_and_never_takes_health_down` |
| Token compared in constant time with a length guard | `auth.py` | `tests/test_auth.py` |
| No configured token cannot authorise (fail closed) | `auth.py` | `test_no_configured_token_cannot_authorise` |
| Every cost-incurring and state-changing route gated | `app.py` | `test_a_write_without_a_token_is_refused...` |
| **Writes CLOSED by default**: no token and no opt-in means 401 | `config.py`, `app.py` | `test_writes_are_refused_by_default_with_no_token_configured` |
| The one deliberately UNGATED write has its OWN rate budget, so an open route cannot spend a gated route's allowance and shut it. While the two shared the strict limiter, twenty unauthenticated drill answers left an authenticated session write answering 429 | `app.py` (`_guard_drill_rate`, `DRILL_LIMIT`) | `test_an_unauthenticated_answer_flood_cannot_shut_the_gated_writes` |
| The set of state-changing routes is CLOSED OVER, not enumerated. The closure WALKS `app.routes` through every routing idiom the application could use - a decorator, an `include_router`, a mount, a sub-application, a WebSocket - and RAISES on any route object it has not been taught, so a new idiom fails the suite rather than passing silently. Every non-idempotent route it finds must answer 401 in the closed default, or be named in `UNGATED_WRITES`, or (for a WebSocket, which no HTTP verb can probe) in `REVIEWED_WEBSOCKETS`. Both binding gates defeated the first version of this row, which read `route.methods` and skipped what did not have it | `app.py`, `training_api.py` | `test_every_state_changing_route_is_gated_or_explicitly_excepted` |
| Anonymous writes need an explicit opt-in | `config.py` | `test_anonymous_writes_require_the_explicit_opt_in` |
| A token alongside the anonymous opt-in refuses to start; the two cannot combine | `config.py` | `test_a_token_alongside_anonymous_writes_refuses_to_start` |
| A token below the minimum length refuses to start | `config.py` | `test_a_token_shorter_than_the_minimum_refuses_to_start` |
| A token without an allowed origin refuses to start | `config.py` | `test_a_token_without_an_allowed_origin_refuses_to_start` |
| Health paths public, and nothing else | `app.py` | `test_health_paths_stay_public_when_a_token_is_configured` |
| Boundary validation rejects, never coerces | `models.py` | `test_a_malformed_body_is_rejected_generically` |
| Unknown keys rejected (`extra="forbid"`) | `models.py` | same, `body1` case |
| And on the PATCH model specifically, so an attacker-chosen `id` cannot reach the merge | `models.py`, `app.py` | `test_a_patch_with_an_unknown_key_is_rejected` |
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
| An honest oversize declaration is refused WITHOUT reading the body | `middleware.py` | `test_an_honest_oversize_declaration_is_refused_without_reading_the_body` |
| A probe path is never drained, so it cannot be parked unmetered | `middleware.py`, `app.py` | `test_a_probe_path_is_never_drained_even_for_a_body_method`, `test_the_apps_body_cap_exempts_the_probe_paths` |
| The probe runs on its own pool, so a burst cannot starve store work | `app.py` | `test_the_probe_runs_on_its_own_dedicated_thread_pool` |
| The probe pool SERIALISES its work, which is what orders publication | `app.py` | `test_the_probe_pool_serialises_its_work` |
| A probe after shutdown fails closed instead of using the shared executor | `app.py` | `test_a_probe_after_shutdown_fails_closed_rather_than_using_the_shared_executor` |
| Every control this document cites resolves to a test that exists | docs | `test_every_test_named_in_the_security_policy_exists` |
| **The redaction control moved UPSTREAM in V0.24.0 and is no longer ours.** The illustrative loader carried a four-shape gate over content this project authored. The shipped content is now Ash's package, whose `_version` block states "no real object identifiers appear in any prompt or answer" and whose own `tools/validate_content.py` is the authority. That validator runs as leg 2 of the verification loop, before any analyser, so a package that failed its own redaction discipline fails the build. What this project no longer does is re-derive a redaction judgement over content it did not author | `tools/validate_content.py` (vendored), `scripts/verify.sh` | `test_the_content_validator_runs_as_a_verification_leg` |
| **Retired with the redaction gate in V0.24.0.** No finding is produced here any more, so there is nothing to echo | n/a | n/a |
| **Retired with the redaction gate in V0.24.0.** Ordering was a property of a two-stage load this project no longer performs | n/a | n/a |
| **Retired with the redaction gate in V0.24.0.** The five-digit ambiguity was a property of a pattern this project ran over content it authored. The shipped content is Ash's and its redaction discipline is upstream; see the row above | n/a | n/a |
| A content fault yields NO drill, never a partial library: a missing required file or malformed JSON is REPORTED and carried, the drill routes answer 503 naming the fault, and the health paths stay 200 | `content/loader.py` | `test_a_missing_required_file_refuses_to_load_rather_than_serving_a_partial_library`, `test_malformed_json_is_reported_and_never_raised` |
| **REVERSED in V0.24.0, deliberately, and this is a trade rather than a removal.** The illustrative models rejected unknown keys so a typo could not silently score nothing. The shipped content package carries far more per record than the engine reads, and a model that rejected an unmodelled field would turn a content author adding a field into a build failure, which is the coupling the package exists to avoid. So the models now set `extra="allow"` and the strictness moved upstream: `schemas/enlightenment.schema.json` and `tools/validate_content.py` are authoritative, the validator is leg 2 of the loop, and what the models still enforce is the shape the ENGINE depends on. **What is no longer caught here: a typo in a field the engine does not read.** | `content/models.py`, `tools/validate_content.py` | `test_an_unmodelled_field_is_carried_rather_than_rejected`, `test_the_content_validator_runs_as_a_verification_leg` |
| A malformed content file is reported, never raised, so a content typo cannot stop the container serving the health path that would explain it | `content/loader.py` | `test_malformed_json_is_reported_and_never_raised` |
| The loaded library cannot be mutated by a caller: every content model is a FROZEN pydantic model rather than a mutable record handed out by copy. One shared library serves every operator in the process, so a caller that could write to a drill would change the answer key under everyone else. **Corrected at V0.24.1:** this row cited a test that asserted only that an unmodelled field is CARRIED, which says nothing about mutability - `frozen=False` left the whole suite green while the register went on claiming the control, and the row additionally claimed to be "stronger than the previous control" on that evidence. The claim is now proved | `content/models.py` | `test_a_loaded_record_cannot_be_mutated_by_a_caller` |
| A stimulus is drawn from the SAME seed on every machine and in every process: the salt is a SHA-256 digest, never the builtin `hash`, whose string hashing Python randomises per process. Until V0.24.1 the same seed drew a different surface in every process, so a debrief redrew a picture the operator never saw and the determinism gate was void while every in-process test passed | `generators/base.py` | `test_the_same_seed_draws_the_same_surface_in_a_separate_process` |
| A rendered stimulus does not contradict its authored scene on any of the agreements the table names, and every one of the 140 drills is rendered and checked against them. **Corrected again at V0.25:** this row claimed the invisible burn and the boolean drift onset were "both now fixed and both now asserted". Neither was true. The burn is NOT fixed - an along-track velocity change is nearly parallel to the velocity it modifies, so it steps the subsequent drift rate rather than turning the track, and a blind change-point detector over the distance panel finds no events at any burn count, so the manoeuvre COUNT is not readable and DRL-0008 now fails closed with no expected value rather than marking a correct reading wrong. The drift onset was fixed in code and asserted by nothing: an onset of 0.999 of the window drew no drift with the suite green. Both are now measured on the marks | `generators/products.py`, `generators/base.py` | `test_no_rendered_stimulus_contradicts_its_own_authored_scene`, `test_a_manoeuvre_steps_the_drift_rate_and_the_count_is_not_scored`, `test_an_authored_drift_onset_actually_draws_a_drift`, `test_no_authored_value_in_the_library_is_silently_clamped`, `test_the_unread_parameter_census_does_not_regress`, `test_every_declared_read_actually_changes_the_surface`, `test_a_burned_track_carries_no_duplicate_vertex` |
| An item the service could not mark moves no rating, resets no schedule and writes no history row. The matcher refused correctly and the loop then scored the refusal as wrong, costing the operator six rating points on a question nobody could answer | `training/drill.py` | `test_an_unscorable_item_does_not_move_a_rating_or_the_schedule` |
| The speed bonus is decided by the server's own clock, and the client's figure reaches no predicate and no award at all. **Corrected at V0.24.3:** the first repair took `min(measured, claimed)` so a slow network could not cost an operator a bonus they earned, which closed a claim of `0` and left every other value open - `elapsed_ms: 1` on a run the server had timed at 21.5 seconds against a 20 second target still bought the bonus over the real route, and the test behind the row tried only `0`. A concession on a value the client controls is the same hole with a nicer reason | `training/drill.py` | `test_the_speed_bonus_is_decided_by_the_server_clock_not_the_client_s` |
| The served-drill map is bounded by age and by count. It grew by one entry per unauthenticated `GET /api/v1/drill/next` and never shrank, which is unauthenticated memory exhaustion ending in an out-of-memory kill: availability loss on the one thing the split health probes exist to protect. The refusal message promised an expiry that no code implemented | `training/drill.py` | `test_the_served_drill_map_is_bounded_by_count`, `test_an_expired_run_is_refused_with_the_message_that_promises_it` |
| A content file of the wrong SHAPE is reported, never raised. A JSON array where an object belongs raised `AttributeError` out of `create_app` itself, so the container did not start and NO health path answered - a crash loop where the contract promises a 503 naming the fault, and the realistic trigger is a typo in `thresholds.local.json`, the one file an operator writes by hand | `content/loader.py` | `test_a_content_file_of_the_wrong_top_level_shape_is_reported_rather_than_raised`, `test_a_damaged_package_still_lets_the_service_start_and_answer_its_health_paths` |
| What the service cannot do is disclosed on a surface an operator can reach: how many rubric rules have no predicate, and how many stimuli carry authored parameters no renderer reads. Both counts were honest in the commit message, the changelog and three docstrings, and absent from the product, which is the one place a supervisor would look | `training/drill.py`, `training_api.py` | `test_the_manifest_discloses_what_is_not_wired` |
| A content-supplied count cannot make a response arbitrarily large, or cost arbitrary time to render. `obs_count: 18000` read as a headcount produced 159 MB from one anonymous GET; capping that ONE parameter left nine others producing 8 MB to 146 MB, and three that never finished rendering - a cost no byte budget can see, because it is spent before there are any bytes to measure. Every count that sizes a loop or a mark list is now bounded at the renderer that consumes it, and the service budget is ENFORCED in `serve()` rather than only asserted in a test: it was declared as a runtime bound and referenced nowhere outside the suite, so it held for the shipped library and for no other content tree, and `CONTENT_DIR` is a supported operator knob | `generators/products.py`, `training/drill.py` | `test_every_served_stimulus_stays_inside_a_stated_payload_budget`, `test_a_stimulus_over_the_budget_is_refused_rather_than_served`, `test_a_hostile_content_count_cannot_make_a_large_payload` |
| An item whose answer the renderer must compute is refused whatever its response format says. The sentinel check lived only in the numeric matcher, and DRL-0030 carries it on a free-classification item: the text matcher compared the operator's prose against the literal string `computed_from_params`, so every real answer was marked wrong, the rating dropped and the cue reset. All three computed items now resolve a value from the surface, and the refusal covers the case where one does not | `scoring/matching.py`, `generators/products.py` | `test_a_numeric_item_resolves_the_value_it_will_be_scored_against`, `test_an_unscorable_item_does_not_move_a_rating_or_the_schedule` |
| Declared aggregation the evaluator does not apply reaches the response body, not only a method nobody calls. `unimplemented_aggregation` was computed and serialised by `Evaluation.as_dict()`, which nothing invoked, so the disclosure was as silent as the omission it replaced | `scoring/evaluator.py`, `training/drill.py` | `test_the_reveal_names_the_aggregation_the_evaluator_does_not_apply`, `test_a_declared_aggregation_this_evaluator_does_not_apply_is_named`, `test_the_speed_cap_in_the_content_actually_caps`, `test_partial_credit_scales_the_rule_award_by_the_item_s_own_fraction` |
| A content file the loader cannot DECODE is reported like any other content fault, so the container starts and the health paths answer. `UnicodeDecodeError` and `RecursionError` escaped the handler, which named `json.JSONDecodeError` alone: no health path answered and there was nothing to screenshot. The trigger is the workflow this project has written down - the owner's workstation is Windows PowerShell, whose `Out-File` and `>` write UTF-16LE by default, and `thresholds.local.json` is the one content file an operator edits by hand | `content/loader.py`, `training/progress.py`, `storage.py` | `test_a_content_file_that_is_not_utf_8_or_is_nested_too_deeply_is_reported` |
| An answer token the RENDERER computed is matched whole, escaped, and never as a pattern. A bare string was iterated character by character, so typing one letter of "east" scored full credit; the escape is pinned so a token carrying a metacharacter is inert rather than wild | `scoring/matching.py` | `test_a_derived_answer_token_is_matched_whole_and_never_as_a_pattern` |
| A plot never states two opposite things about the same data. On the waterfall the axis placed the newest observations at the bottom and the recency ramp coloured the OLDEST end red, on one panel, in a product where red-for-recency is the first thing an analyst reads. The geometry and the colour are now asserted together, and an inverted axis carries its own reason so the interface cannot caption a timeline "brighter upward" | `generators/products.py`, `generators/base.py`, `ui/app.js` | `test_the_newest_observations_are_drawn_nearest_the_longitude_axis`, `test_an_inverted_axis_states_its_own_reason_for_being_inverted` |
| A timeline is labelled with timestamps, and those labels come from the SEED rather than the clock. Bare day numbers cannot be correlated against a pass schedule or a provider post, which is what an operator does with a time axis; and a label read off the wall clock would relabel the same surface differently on every render, breaking the replay this project gates on. The epoch is synthetic and the footer says so rather than implying a real collection | `generators/products.py`, `ui/app.js` | `test_the_waterfall_time_axis_is_labelled_with_timestamps_not_bare_numbers`, `test_the_timeline_labels_come_from_the_seed_and_never_from_the_clock` |
| An absurd authored figure is reported verbatim and drawn to a scale the panel can express, and the header states BOTH. DRL-0005 carries the real -22,900,000°/day ASTRA 1M artefact, and the whole lesson is that a reported figure cannot be right: drawn literally it spans 114 million degrees and shows nothing. The header read "drawn to scale", which is the negation of the clamp, and it is the ONLY client-visible disclosure because the wire form strips the server's derived facts | `generators/products.py` | `test_an_absurd_authored_rate_is_clamped_for_drawing_and_reported_verbatim` |
| An item's authored partial and reject entries are honoured by every matcher, including the one that scores an answer the renderer computed. `match_derived_text` consulted neither, so a half-correct answer the content awards 0.5 credit scored zero and both authored misconceptions lost their teaching text - a content instruction silently ignored, in a matcher added the same week as the reporting built to prevent exactly that | `scoring/matching.py` | `test_a_computed_item_still_awards_the_credit_its_content_authors` |
| A numeric item whose prompt asks for a magnitude AND a direction scores them separately. The generator's expected value is signed, so "0.12 deg/day west" was marked wrong for omitting a minus sign the prompt never asked for, while the direction the prompt did ask for went unscored. Before the value was wired the item refused harmlessly; wiring it turned a harmless refusal into a penalty on the correct answer | `scoring/matching.py` | `test_a_numeric_answer_scores_its_magnitude_and_its_direction_separately` |
| An item that cannot resolve its own answer is withheld from SELECTION as well as from scoring, and is named on the manifest. Refusing to score it was right and insufficient: selection is a pure function of due-state and rating and the unscored path advances no schedule, so the same item was served on every turn - measured at rating 1340, six consecutive serves of DRL-0008 with no rating movement, an absorbing state that ends the session where the penalty it replaced cost six rating points | `training/drill.py` | `test_an_item_that_cannot_resolve_its_answer_is_not_served_twice_in_a_row`, `test_the_withheld_items_are_named_rather_than_silently_dropped` |
| Two products on one composite board cannot both supply the answer: the merge refuses rather than letting draw order decide which renderer's value is scored | `training/drill.py` | `test_two_products_on_one_board_cannot_both_supply_the_answer` |
| A renderer's arithmetic on a content value never stops the container starting. The load-time answer probe guarded only `LookupError`, so a single NaN in a content parameter raised out of `create_app` itself - and `asgi.py` calls `create_app()` at import, so the worker never booted: a crash loop with no health path to screenshot. Four of five probe cases did it, one commit after the loader's decode faults were closed for the same reason. At request time the same fault now earns the author-facing 503 the module documents rather than a generic 500 | `training/drill.py` | `test_a_renderer_arithmetic_fault_never_stops_the_container_starting`, `test_a_renderer_arithmetic_fault_is_an_author_facing_503_not_a_500` |
| A composite board cannot name the same product twice. An unknown product id already fails closed, so duplication was the one lever left to inflate the render loop: a board naming one product thirty times rendered 126 MB and burned seven seconds of CPU on ONE unauthenticated request, and the payload budget can only refuse that after the memory is allocated. Refused rather than de-duplicated, because the same product twice is a content fault and collapsing it silently would change the authored board | `generators/__init__.py` | `test_a_composite_board_cannot_name_the_same_product_twice`, `test_no_authored_composite_board_duplicates_a_product` |
| The items withheld from selection are named on the SERVED manifest, not only by the method behind it. The route did not serialise the list, so "named on the manifest" was true of a method and false of every surface an operator can reach | `training_api.py` | `test_the_withheld_items_are_named_on_the_served_manifest` |
| A direction answer that names more than one direction, or denies the one drawn, is refused. Widening the token match to a prefix accepted "eastwest" and "eastasdfgh" as a correct reading of an eastward drift, and the anywhere-in-the-response search accepted "not east" and "east or west": full credit for a self-contradictory answer moves a rating that was not earned | `scoring/matching.py` | `test_a_direction_answer_is_refused_when_it_names_more_than_one_or_denies_one` |
| A serve-time refusal withholds the item, so a session cannot be ended by one unservable drill. `select` is a pure function of rating and due-state and a refusal records no run, so an item whose renderer RAISES was chosen again on every request: measured, one NaN on a content parameter produced six consecutive 503s on the same item with no progress. The load-time probe cannot see this class - it inspects only items whose answer is computed, and this one raised while rendering. An explicitly named item is still never substituted, and every withheld item is named on the served manifest with its reason | `training/drill.py` | `test_a_serve_time_refusal_withholds_the_item_and_the_session_continues`, `test_an_explicitly_named_item_is_never_substituted_when_it_refuses`, `test_a_package_with_nothing_servable_refuses_instead_of_raising_from_min` |
| A correct direction answer carrying an unrelated negation is not penalised, and a denial of the drawn direction is refused. The first version searched the whole response for any "no", "not", "never" or "neither", so it refused correct readings, and it missed the denials it existed for. **Corrected again at V0.26.3:** this row said the denial rule was "scoped to a short window before the direction", and a window of up to two words jumps a clause: measured, "not station-keeping, drifting east at 0.279 deg/day" scored partial and five more correct answers scored nothing, so the row recorded the second version of this check as a fix while it was still refusing correct readings. The rule now requires the direction to FOLLOW the denial across a closed vocabulary of motion words. Three residual under-catches are named in the module docstring and held in the test rather than claimed closed | `scoring/matching.py` | `test_a_direction_answer_is_refused_when_it_names_more_than_one_or_denies_one`, `test_an_unrelated_negation_does_not_cost_a_correct_numeric_answer` |
| The unread-parameter census subtracts only the renderers ON the board, and an unknown product on a composite board fails closed. The census fix was verified by nothing: reverting it to subtract every registered renderer's vocabulary left the whole suite green, because every ratchet call used the default empty board and never reached the path that produces the served figure | `generators/base.py`, `generators/__init__.py` | `test_the_unread_census_uses_the_resolved_board_and_not_every_renderer`, `test_an_unknown_product_on_a_composite_board_fails_closed` |
| A withhold reason is length-bounded before it reaches the unauthenticated manifest or the run log. A refusal message embeds the `repr` of the authored parameter that caused it, and `content/models.py` declares no maximum length on any value in `params`: measured, a 3,000-character `newest_at` produced a 3,100-character reason, stored verbatim, across up to 140 items. `MAX_WITHHOLD_REASON` is 256, measured against the longest reason any real content fault produces here (190 characters), and a cut reason is MARKED so a shortened diagnosis does not read as a complete one | `training/drill.py`, `training_api.py` | `test_a_withhold_reason_is_bounded_before_it_reaches_the_unauthenticated_manifest`, `test_the_withheld_items_are_named_on_the_served_manifest` |
| Every shortened identifier goes through one function, `served_identifier`, at every wire and every storage sink, and every one of its nineteen call sites is held by a test on BOTH axes: a raw value is distinct and unbounded, a truncation is bounded and collides, and each mutation is invisible to the other's test. A plain truncation cuts silently, so two ids sharing a prefix longer than the cap collapse into one string - an identifier no author wrote, on an operator-facing surface, and every comparison against it silently failing. `served_identifier` appends a digest of the whole string. **The output form is a persisted format**, written into `progress.json` and compared on the way back, so it is pinned by a golden-value test. **The bound is BYTES of UTF-8, not code points**, because every ceiling this project asserts on a SERVED BODY or on a CUT is in bytes and one `U+1F600` is one code point and four. Scoped precisely: the pydantic INPUT caps in `models.py` count code points, so `notes` at 2,000 admits 8,000 bytes, and they are bounded downstream by the served byte ceiling rather than being a second unit nobody reconciles. The cut sites are the six that matter: a 64-code-point cap admitted 256 bytes, and the hostile tree's ASCII poison made the two units indistinguishable. Measured with astral identifiers, `GET /api/v1/me` served 17,407 bytes against a 16,384-byte ceiling the suite reported as held. `served_identifier`, `capped`, `bounded_reason` and `_bounded` all cut on bytes now, without splitting a code point; ASCII is unchanged, so the persisted form is not. Held as a UNIT, because reverting any single one of those cuts leaves every route ceiling satisfied - the bodies cross a ceiling only when several revert together, and a control that fires only on the combination holds none of the parts. A competency NAME keeps the MARKED bound and no digest, because prose is not an identity, and `audit.py` cuts a log value at 256 BYTES unmarked and undigested, so a caller shortens before `log_event` rather than relying on the sink. That sink was the last one counting CODE POINTS after this row began asserting bytes: one anonymous request whose path carried 400 emoji produced a 2,945-byte log line against a documented cap of 256, because a line renders with `ensure_ascii=True` and one astral character becomes twelve. **Seven instances of this fault reached seven consecutive releases, each outside the scope of the sweep before it; `docs/CHANGELOG.md` carries that history from V0.26.6, where the unmarked truncation was introduced, and this row deliberately does not - a register cell that grows a clause per round is how a claim outlives the code it describes.** | `training/drill.py`, `training_api.py` | `test_two_oversized_library_documents_are_named_distinctly_in_the_refusal`, `test_two_long_ids_produce_two_distinct_log_lines_and_two_distinct_load_errors`, `test_the_answer_route_logs_two_distinct_names_for_two_long_ids`, `test_the_shortened_identifier_form_is_pinned_because_it_is_persisted`, `test_every_content_bound_is_measured_in_bytes_not_code_points`, `test_the_unbuilt_product_log_line_names_two_long_ids_distinctly`, `test_a_serve_time_refusal_names_two_prefix_sharing_ids_distinctly`, `test_the_persisted_run_labels_are_bounded_and_distinct`, `test_a_long_item_id_still_gets_a_fresh_seed_on_every_attempt`, `test_two_long_item_ids_do_not_collapse_into_one_on_the_manifest` |
| A withheld item is excluded from SELECTION as well as declared on the manifest, and two long ids do not collapse into one. **The bound introduced at V0.26.6 to keep 3,003-character ids off the anonymous manifest was applied to the wrong thing: `_unresolvable` was keyed on the BOUNDED id while `select` tested the raw one, so from V0.26.6 to V0.26.11 any authored id over 64 characters was declared withheld and still selected.** Measured at 65 characters: 94 declared, zero excluded, and eight consecutive serves returned one item with no run recorded - the absorbing state closed at V0.26 and the serve-time feedback added at V0.26.1, both defeated on an anonymous route while this register recorded them closed. `_bounded` also truncates without a marker, so ids sharing a 64-character prefix collided: 140 distinct authored ids served ONE entry under a synthetic id matching nothing an author wrote, understating the gap 94-fold. Keys are raw now, the bound is applied at the wire, and a cut id carries a digest so it stays distinct and cannot read as what the author typed | `training/drill.py` | `test_a_withheld_item_with_a_long_id_is_excluded_from_selection_not_only_declared`, `test_two_long_item_ids_do_not_collapse_into_one_on_the_manifest`, `test_a_serve_time_refusal_withholds_the_item_and_the_session_continues` |
| The withheld collections are count-capped and report an honest untruncated total. Bounded per entry and uncapped in COUNT until V0.26.11: 140 drills served 17,014 bytes against this project's own 16 kB ceiling, 560 served 64,675, and the runtime path grew over the container's life because a serve-time refusal carries a 256-character reason rather than the 32-character load-time one. The body ceiling cannot see this and never could - 140 uncapped entries with bounded ids are about 13 kB - so the cap is held by an explicit count assertion, and the total's VALUE is pinned against a measured literal because a hardcoded total survived a range check | `training/drill.py`, `training_api.py` | `test_the_withheld_collections_are_count_capped_and_report_an_honest_total` |
| No anonymous JSON route serves a content-sized body, held by enumerating the ROUTE TABLE, asserting the enumeration, and driving the STATE a stateful route serves from. A per-field assertion holds only the fields somebody thought of, and every narrowing so far was made by a filter rather than declared: filtering on `GET` hid an anonymous `POST`, filtering on an unparameterised path hid the library routes, measuring an idempotent route on a single draw hid every item after the first, and an enumeration asserting nothing about itself could be narrowed to one route without turning red. The control therefore compares discovered routes against an exact set over the whole route table, calls each with resolved parameters and a valid body, asserts status before size, refuses an empty measurement, drives serve-then-answer across the item space, and splits the diagnostic ceiling from `MAX_PAYLOAD_BYTES` rather than asserting one number over both. Library documents FAIL CLOSED on a 64 kB budget rather than being field-bounded, because the flight plan makes that library an anonymous reference a per-field cap would mutilate; a companion assertion proves the shipped library still serves. **Scoped honestly: this holds the routes the app declares, on the fields this hostile tree poisons, and every exclusion is named with a reason rather than made by a filter.** **The TENTH surface was the one route excluded from the enumeration, and both reasons given for excluding it were false.** `GET /api/v1/sessions` was recorded as token-gated, which is true of the writes and false of the read, and as governed by `storage.MAX_SESSIONS` "which their own tests hold", while `MAX_SESSIONS` appeared in the suite only in that sentence. Measured on the wire at the cap, every field inside its declared maximum and accepted with 201: **1,231,926 bytes of ASCII and 4,711,926 with astral characters from one unauthenticated request**, the second past `MAX_PAYLOAD_BYTES`. Capped at `MAX_SERVED_SESSIONS`, newest kept, with the untruncated total and a `truncated` flag beside it, and swept with a byte ceiling against a store driven to its cap in astral characters. **Ten surfaces across eight releases, and the sweeps written to end the class were themselves four of them; `docs/CHANGELOG.md` carries that history and this row does not.** | `training_api.py`, `training/drill.py` | `test_no_anonymous_route_serves_a_content_sized_body_on_a_hostile_tree`, `test_a_stateful_route_is_measured_across_the_item_space_not_on_one_draw`, `test_an_anonymous_content_503_is_bounded_per_error_and_not_only_in_count`, `test_an_authored_param_name_is_bounded_on_the_anonymous_manifest`, `test_the_anonymous_session_listing_is_count_capped_and_reports_an_honest_total` |
| A derived direction token is escaped before it is compiled into the contradiction pattern. Held before a generator ever derives that token from content: today `expected_text` is only ever one of four literals, so deleting `re.escape` left the suite green - unheld rather than exploitable, and the guard is the cheaper of the two things to keep. A metacharacter-bearing token either raises `re.error` inside scoring, failing an operator's submission on content they cannot see, or silently matches something the plot never drew | `scoring/matching.py` | `test_a_derived_direction_token_is_never_compiled_as_a_pattern` |
| A refusal names the KEY and its DOMAIN, never the authored value that failed it, held by enumerating the ROUTE TABLE rather than by one renderer's message. **The boundary never interpolates an exception it did not author**: `ContentParameterError` is the marker for a message the code composed, and everything else is reduced to its exception CLASS with the detail logged server-side. That is what closes the class rather than one instance of it, because a coercion site added later leaks nothing while it waits to be converted. `authored_number` and `authored_count` name the key and the type it had to be, so the author-facing diagnosis survives. Structural identifiers - a generator name, a product id - are still named, because a typo in one is undiagnosable otherwise, and each is shortened at its raise site so none can size a response. **Recorded closed from V0.26.3 and defeated in TWO anonymous requests against a copy of the shipped tree**: V0.26.3 removed the one explicit interpolation and left the mechanism that carried values, since `float` puts the string it could not parse into its own message and `training/drill.py` reflected that verbatim onto `GET /api/v1/drill/next` and the manifest's `withheld_reasons`; the cited test held one refusal on one renderer, which is the per-field fault one level up. `docs/CHANGELOG.md` carries that history from V0.26.3. **Both refusal branches are held, and the claim that one could not be was false.** V0.26.23 recorded here that re-interpolating the exception in the ARITHMETIC branch survives the suite because no `ArithmeticError` message on CPython 3.12 carries its operand. `timedelta` interpolates its own argument: an authored `days: -1000000007` raises `OverflowError: days=-1000000007; must have magnitude <= 999999999`, and with the exception restored that operand reached both anonymous surfaces with the suite green. A string poison cannot reach that branch - it fails coercion first - so the holding test drives a NUMERIC one as well | `training/drill.py`, `generators/base.py`, `generators/products.py`, `content/models.py` | `test_no_anonymous_route_serves_an_authored_content_value_in_a_refusal`, `test_no_anonymous_route_serves_an_authored_value_from_a_load_failure`, `test_no_refusal_message_quotes_the_authored_value_that_caused_it` |
| The STORED SNAPSHOT gets the same boundary rule as the content tree, and an unreadable one fails closed rather than 500. `GET /api/v1/sessions` is anonymous by the decision at accepted risk 5 and called `store.load` with no handler, so every malformed shape the store already refuses reached an unauthenticated caller as a generic 500: not JSON, not UTF-8, top level not an object, nested too deep - and a string that PARSES and then cannot be encoded, which raises inside pydantic's serialiser while the response renders. That last one is why this row exists: the snapshot had no encodability check, so **"the snapshot is trusted stored state" and "the progress file is not" were two different answers to one question in adjacent modules**. `TrainingStore.load` runs the same walk as `content/loader` now and raises `ValueError` like every other malformed shape; the route answers 503 `store_unavailable` with the fault named, length-bounded, and no stored value in it. Not reachable from the HTTP edge - a surrogate in a body is a generic 422 in every form - so the precondition is write access to the data volume, an actor this model puts out of scope. Closed anyway, because a route that 500s on its own data cannot be diagnosed from a screenshot. The dependency-free health paths are asserted to stay 200 alongside | `storage.py`, `app.py` | `test_an_unreadable_snapshot_fails_closed_on_the_anonymous_listing` |
| Content that cannot be encoded as UTF-8 is refused at the LOAD boundary, so the tree fails closed rather than one route crashing. A lone surrogate is legal JSON - `json.loads` of `"\ud800"` returns a `str` that `str.encode("utf-8")` refuses - so an author can write one as an escape sequence with no invalid byte in the file, and nothing downstream expected it. Measured: three drills whose IDS carried one produced a **500 on the anonymous `/api/v1/me`**, because `served_identifier` encodes to measure a length; and one in an unvalidated PROSE leaf of a procedure produced a **500 on the anonymous `/api/v1/content/procedure/{id}`**, raised by pydantic's serialiser while rendering the response, which no application code touches. A traceback on an unauthenticated route from authored data breaks two rules at once. **Sanitising at each serve site was tried first and was the wrong shape:** the identifier path was fixed and the 500 moved to the next unvalidated field, because a per-field defence holds the fields somebody thought of. The check is at `content/loader._read_json`, the one place content enters the process. The refusal names the file, the count and a JSON pointer, never the offending VALUE. A key IS named, because a pointer to a key is the key - the same structural-identifier carve-out this register records for a generator name, and the key goes out through `utf8` so the unencodable character is replaced rather than served. `identifiers.utf8` is kept as defence in depth so a future caller cannot reintroduce the crash | `content/loader.py`, `identifiers.py` | `test_a_lone_surrogate_in_content_fails_the_load_closed_rather_than_crashing_a_route` |
| A withheld item's ID is bounded on the anonymous manifest, at both write sites and where the reason is composed. The reason was capped at V0.26.3 under a comment saying content does not set the size of an anonymous response, and the comment was false in the same fields on the same route: `content/models.py` declares `id: str` with no maximum, and 40 items with 3,003-character ids produced a 243,539-byte unauthenticated response. Bounding the key alone then left the message useless - a 3,004-character id filled `MAX_WITHHOLD_REASON` before the sentence began, so the served reason was the id and the truncation marker | `training/drill.py` | `test_a_withheld_item_id_is_bounded_before_it_reaches_the_unauthenticated_manifest` |
| An item keeps its FIRST withhold reason and logs it once. Inverting the dedupe to last-writer-wins left all 966 tests green, and coverage named the gap outright: the already-withheld branch was never taken anywhere in the suite. `_named` does not consult the withheld set, so a named item that keeps refusing keeps reaching `_withhold` - without the guard every anonymous request for it appends another line to the run log, unbounded, and the reason an author reads becomes whichever refusal happened last rather than the one that explains why the item was never served. **This control was closed with prose alone in V0.26.3 and given a driver in V0.26.4** | `training/drill.py` | `test_an_item_keeps_its_first_withhold_reason_and_logs_it_once` |
| A pool in which every candidate refuses spends a bounded budget and then says the budget was spent. `serve` re-raised the last item's refusal on its final attempt, which made the budget error unreachable and told the operator "one item is broken" when the fact was "four candidates refused". The budget's VALUE is asserted against a literal, because the first version of that assertion compared against the constant under test and widening the budget to eight left it green. **Bounded at V0.26.4:** the message carries a content-sized reason and reaches the unauthenticated `/api/v1/drill/next` as a 503 detail, so `MAX_WITHHOLD_REASON` applied at `_withhold` alone was a bound at one of two exits | `training/drill.py` | `test_a_refusing_pool_raises_the_budget_error_after_exactly_the_allowed_attempts` |
| An explicitly named item is attempted ONCE and never substituted. `_named` returns the same item on every call, so without the early raise a refusing named item is withheld four times to reach the same outcome, and the substitution test cannot see it because the budget message still carries the item id that test matches on. Twice a gate found this mutation surviving, so the assertion is now the attempt COUNT | `training/drill.py` | `test_a_named_item_is_attempted_once_and_never_retried`, `test_an_explicitly_named_item_is_never_substituted_when_it_refuses` |
| The waterfall's time direction is validated before it reaches operator-facing prose. `{"newest_at": "sideways"}` rendered "Newest observations at the sideways.", and for the top case the axis note and the panel note asserted opposite geometries on the same panel | `generators/products.py` | `test_the_waterfall_time_direction_is_validated_before_it_reaches_prose` |
| Every READ route is reviewed and none may reach an answer key. The state-change closure skips every idempotent method by design, so a future `GET` returning a whole drill would have shipped with the suite green - and a read route is precisely the shape that leaks a key | `training_api.py` | `test_every_read_route_is_reviewed_and_none_may_reach_an_answer_key` |
| The rating band, the proper scoring rule and the off-scale confidence refusal are asserted rather than merely executed. `training/scoring.py` survived the V0.24.0 rewrite and its tests did not: three mutants - the band removed, the Brier reduced to an absolute difference, the confidence guard disabled - all passed the full suite | `training/scoring.py` | `test_a_rating_cannot_leave_the_band_however_long_the_streak`, `test_the_brier_score_punishes_a_confident_error_quadratically`, `test_an_off_scale_confidence_is_refused_rather_than_coerced`, `test_no_confidence_step_asserts_certainty` |
| Content-supplied strings are length-bounded before they reach the progress file. `extra="allow"` is the deliberate reversal that lets the package load unedited; the residual was length, and a 5000-character `version` was stored verbatim on a run row in a file read whole on every request | `training/drill.py` | `test_a_content_supplied_version_is_length_capped_before_it_is_stored` |
| **NOT IMPLEMENTED at V0.24.0, and recorded as a gap rather than dropped.** The illustrative loader pinned a rubric to a procedure version so a content edit could not silently rescore history. The shipped package's rubrics carry `applies_to` scenario ids and no version pin, and the new loader does not add one. What partly covers it: every run record carries the content HASH it was scored under, so an old result stays interpretable even though it cannot be re-scored. Closing it properly needs a decision from the content author about where the pin lives | `content/loader.py`, `training/drill.py` | `test_a_scored_run_records_the_content_hash_it_was_scored_under` |
| The edit helper refuses a missing or ambiguous anchor | `scripts/verified-edit.py` | `test_the_edit_helper_refuses_a_missing_anchor`, `test_the_edit_helper_refuses_an_ambiguous_anchor` |
| The snapshot is not read through a symlink | `storage.py` | `test_the_snapshot_is_not_read_through_a_symlink` |
| The cap runs ahead of authentication | `middleware.py` | `test_an_oversize_chunked_body_is_refused_before_authentication` |
| Two-tier rate limiting, 429 in both tiers | `ratelimit.py`, `app.py` | `test_the_coarse_tier...`, `test_the_strict_tier...` |
| Probe paths never rate-limited | `app.py` | `test_probe_paths_are_never_rate_limited` |
| A relative `DATA_DIR` refuses to start | `config.py` | `test_relative_data_dir_is_refused` |
| The filesystem root as `DATA_DIR` refuses to start | `config.py` | `test_filesystem_root_as_data_dir_is_refused` |
| An out-of-range `PORT` is refused, never clamped or defaulted silently | `config.py` | `test_port_defaults_to_8080_and_validates` |
| A nonsensical rate-limit bound is refused at construction | `ratelimit.py` | `test_a_nonsensical_limit_is_refused` |
| A wildcard origin refuses to start, unconditionally | `config.py` | `test_a_wildcard_origin_always_refuses_to_start_even_without_a_token` |
| And so does `null`, whatever its case or padding, which is what a sandboxed iframe and a `file://` page send | `config.py` | `test_an_anonymous_or_wildcard_origin_refuses_to_start` |
| Every exposed method survives a preflight | `app.py` | `test_every_exposed_method_survives_a_preflight_from_the_allowed_origin` |
| A 413 or 429 still carries the cross-origin header | `app.py` | `test_a_rate_limited_response_still_carries_the_cross_origin_header`, `test_an_oversize_response_still_carries_the_cross_origin_header` |
| `X-Content-Type-Options: nosniff` on every user-stack response | `middleware.py` | `test_every_user_stack_response_carries_nosniff`, `test_nosniff_is_appended_when_absent`, `test_nosniff_does_not_override_a_handler_that_set_it` |
| The 500 no user middleware reaches sets both headers itself | `app.py` | `test_a_500_carries_its_own_headers_because_no_user_middleware_reaches_it` |
| Anti-shrink merge; a partial update deletes nothing | `storage.py` | `test_a_partial_patch_keeps_every_field...` |
| Atomic write; no half-written or orphaned file | `storage.py` | `test_write_is_atomic...`, `test_a_failed_write_leaves_no_temporary_file_behind` |
| Writes serialised by an exclusive lock; no lost update across processes | `storage.py` | `test_two_processes_writing_at_once_lose_no_record` |
| A stale revision is a 409, never a silent overwrite | `storage.py`, `app.py` | `test_a_stale_expected_revision_is_refused...`, `test_a_stale_if_match_is_a_409...` |
| Backup before a destructive write, pruned to retention | `storage.py` | `test_a_backup_is_taken_before_an_overwrite...` |
| The session collection is capped, newest kept, so the snapshot cannot grow without bound | `storage.py` | `test_the_cap_boundary_holds_in_both_directions`, `test_the_cap_keeps_the_newest_and_never_drops_the_fresh_entry` |
| The backup SOURCE is not read through a symlink | `storage.py` | `test_a_symlinked_snapshot_cannot_be_copied_into_a_backup` |
| The backup TARGET is not written through one either, so a planted backup path cannot overwrite the file it points at | `storage.py` | `test_a_symlinked_backup_target_cannot_overwrite_the_file_it_points_at` |
| Log injection blocked; actor sanitised | `audit.py` | `test_newline_injection_cannot_forge_a_second_line` |
| Actor and every reflected value LENGTH-CAPPED and sanitised, in `audit()` as well as `log_event()` | `audit.py` | `test_actor_is_length_bounded`, `test_a_reflected_value_is_length_bounded`, `test_an_audit_line_sanitises_every_string_field_not_only_the_actor` |
| EVERY reflected log value sanitised, lines emitted as JSON | `audit.py`, `app.py` | `test_an_event_line_sanitises_every_string_field_structurally` |
| All three state-changing routes (`POST /api/v1/sessions`, `PATCH /api/v1/sessions/{id}`, `POST /api/v1/drill/answer`) EMIT an audit line naming the actor, which is the accountability control under a shared token. The drill line additionally carries NEITHER the submitted answer nor any score: the plan forbids a personal performance figure in a log line, and an operator's own words are performance data | `app.py`, `training_api.py` | `test_local_anonymous_mode_allows_the_write_and_records_the_actor_as_anonymous`, `test_a_gated_write_emits_one_audit_line_naming_the_token_actor`, `test_every_accepted_answer_emits_one_audit_line_carrying_no_performance_data` |
| A missing or blank actor becomes `anonymous`, never an empty field | `audit.py` | `test_missing_or_blank_actor_becomes_anonymous` |
| Generic client errors; detail server-side only | `app.py` | `test_an_unhandled_error_returns_a_generic_message...` |
| No secret in any response, log, or audit line | `app.py`, `audit.py` | `test_diagnostics_never_exposes_a_token_value_or_an_exact_length`, `test_nothing_on_app_state_exposes_the_configuration` |
| Operator values normalised before use | `config.py` | `test_clean_strips_quotes_whitespace_and_control_characters` |
| An oversize operator value is REJECTED, never truncated into a different value | `config.py` | `test_an_over_long_value_is_rejected_not_truncated` |
| Storage proved by a REAL write, never an existence check | `storage.py` | `test_probe_writable_reports_the_errno_when_the_write_is_refused`. NOTE: skipped when the suite runs as root, because root bypasses directory permissions, so this control is proved on the CI runner rather than locally. The file-not-a-directory case runs on every uid but does NOT kill an existence-check mutant, since it never reaches the write; citing that one here was wrong |
| Probe cannot hang; hard timeout of 2.0 s. **The comparison against the platform's own probe timeout is `TBC, re-verify`**: the App Store publishes no `timeoutSeconds` in any document this repository holds, and a Kubernetes default of 1 s would make ours longer. Asked of the owner by name rather than inferred. What the test holds is that the probe cannot hang and that the timeout is the documented figure | `app.py` | `test_a_hanging_probe_times_out...` |
| Probe cost bounded by TIME and by CONCURRENCY (single-flight) | `app.py` | `test_a_readiness_flood_causes_one_real_write...`, `test_concurrent_readiness_requests_run_one_probe_between_them` |
| Concurrent callers all receive one verdict, so none can race to overwrite another | `app.py` | `test_concurrent_callers_all_receive_the_same_verdict` |
| The rate limiter sits OUTSIDE the body cap, so oversize requests spend budget | `app.py` | `test_the_middleware_order_puts_the_limiter_outside_the_body_cap`, `test_an_oversize_request_still_spends_rate_limit_budget` |
| A probe path declaring a body that never arrives still answers | `middleware.py` | `test_a_liveness_request_declaring_a_body_that_never_arrives_still_answers` |
| The existence check for a partial update runs inside the store lock | `storage.py` | `test_the_cap_cannot_turn_a_must_exist_merge_into_a_partial_append` |
| The BYTECODE `auth.token_ok` executes is the bytecode `auth.py` compiles, so a forged code object cannot present canonical source | `auth.py` | `test_the_executed_bytecode_is_the_reviewed_implementation` |
| And its SOURCE is the reviewed four statements, naming which one moved when it fires | `auth.py` | `test_the_token_comparison_uses_the_constant_time_primitive` |
| `hmac` in `auth.py` is the standard library module AND `compare_digest` is still the C builtin, so neither the module nor the attribute can be substituted | `auth.py` | `test_the_primitive_name_resolves_to_the_standard_library_module` |
| `token_ok` is neither wrapped nor decorated, naming which frame moved when it fires; the guard against anything running first is the code-object pin above | `auth.py` | `test_token_ok_is_neither_wrapped_nor_decorated` |
| No token is compared with `==` anywhere in the package | `auth.py` and every module | `test_no_module_compares_a_token_with_plain_equality` |
| Backups carry the same restrictive mode as the snapshot | `storage.py` | `test_the_snapshot_and_its_backups_share_the_same_restrictive_mode` |
| The lock path is not followed through a symlink | `storage.py` | `test_the_lock_file_is_not_followed_through_a_symlink` |
| A storage fault leaves the app unready, never unstartable | `app.py` | `test_the_app_still_starts_and_diagnoses_itself_when_the_snapshot_is_corrupt` |
| A RAISING probe reads as unready, never as a pass | `app.py` | `test_a_probe_that_raises_reads_as_unready_never_as_a_pass` |
| A non-object snapshot is rejected, not coerced | `storage.py` | `test_a_non_object_snapshot_is_rejected` |
| A malformed `sessions` field is rejected on migration | `storage.py` | `test_migrate_rejects_a_malformed_sessions_field` |
| A non-integer revision is rejected on migration | `storage.py` | `test_migrate_rejects_a_non_integer_revision` |
| The rate-limit key table fails CLOSED when full | `ratelimit.py` | `test_a_full_table_refuses_a_new_caller_rather_than_evicting_a_tracked_one` |
| The HEALTHCHECK port is validated, never interpolated raw | `healthcheck.py` | `test_a_hostile_port_is_refused_rather_than_interpolated` |
| A malformed port reads UNHEALTHY, never a silent fallback that probes a different port | `healthcheck.py` | `test_a_hostile_port_never_reaches_a_url` |
| A non-200 liveness answer is UNHEALTHY | `healthcheck.py` | `test_any_non_200_liveness_response_is_unhealthy` |
| A transport failure is UNHEALTHY, never a pass | `healthcheck.py` | `test_any_transport_failure_is_unhealthy_never_a_pass` |
| The container probe targets `/livez`, so a storage outage cannot restart a healthy container | `healthcheck.py` | `test_the_probe_targets_the_liveness_path_not_readiness` |
| The image healthcheck timeout is 3.0 s and cannot hang. **Shorter than the platform's probe window is `TBC, re-verify`** for the reason in the row above: there is no platform figure in this repository to compare against, so the cited test compares against this project's own assumed window and says so | `healthcheck.py` | `test_the_timeout_is_shorter_than_a_platform_probe_window` |
| Store input and output runs off the event loop | `app.py` | `test_no_store_call_runs_on_the_event_loop` |
| Non-root numeric user, no suid or sgid bits, flat image | `Dockerfile` | `tests/test_appstore_contract.py` |

Each control was mutation-proved before submission: the code it protects was broken in a
copy of the tree and the named test went red. Mutants have been killed across the twelve rounds
the ledger below counts, covering the anti-shrink merge, the token compare, both rate-limit boundary
directions, the readiness fail-closed branch, the unknown-key rejection, the size cap, the
actor sanitiser, the closed-by-default write posture, the cross-origin method list, the
strict tier on both GATED write routes and the separate budget on the ungated one, the
byte-counting body cap, the probe cache, the port
validation, the exclusive write lock, the revision guard, the fail-closed key table, the
worker count, the package-manager purge, the package-database retention, and the two binding
image checks in continuous integration.

**Surviving mutants.** Not "all of them", which is what an earlier version of this section
claimed twice while independent runs kept finding more. A mutation claim is worth exactly what
the run behind it measured, and every round in this table has proved that on this project - most
sharply at round 12, where the mutation that mattered was aimed at the round-11 CHECK rather than at
the code, and killed it:

| Round | Claimed | Independently found |
|---|---|---|
| 1 | 8 killed | 8 killed, 1 survivor recorded |
| 2 | 21 killed, 1 survivor | 4 survivors (32-mutant run) |
| 3 | 11 run, 3 survivors closed | 2 further survivors (11-mutant run) |
| 4 | 10 run, 10 killed after closing 2 survivors | 3 further survivors (engineering), 2 (security) |
| 5 | 6 run, 6 killed after closing all 5 | 1 MAJOR (a claimed proof disproved), 2 survivors (eng), 2 (sec) |
| 6 | 10 run, 10 killed after closing all 3 survivors | 2 MAJORs, 4 survivors, 1 dangling citation |
| 7 | 9 run, 9 killed after closing the last survivor | **both gates PASS**; 6 MINORs (eng), 5 (sec) |
| 8 | 10 run, 10 killed or shown neutralised by a layer | 2 MAJORs (eng, both documents), 1 MINOR (sec) |
| 9 | 8 run, 8 killed | 2 MAJORs, 4 MINORs (eng, all documents); **`security-reviewer` PASS** |
| 10 | 5 run, 5 killed | 3 MAJORs, 5 MINORs (eng, all documents); **`security-reviewer` PASS** on the exact head |
| 11 | 2 run, 2 killed | the ordering claim `_install_cors` had carried since it was written; the round's own changelog said "three", withdrawn to this figure |
| 12 | 8 run, 8 killed | 1 BLOCKER in the round-eleven completeness check itself (both gates): it matched `def test_` and so could not see `async def`, missing 17 of 20 tests in the one suite that motivated it |
| 13 | 19 run, 19 killed | 3 MAJORs from each gate on the SAME check: `tests/test_appstore_contract.py:624` read `tree.body`, so a class-nested test was invisible while the docstring claimed class nesting was survived; the cited-suite guard read FILE references only, so `test_healthcheck.py` and its three fail-closed branches were unswept; and four exemption REASONS asserted a mutation relationship that mutation disproved |
| 14 | 9 run, 9 killed, 1 required survivor | 3 MAJORs (eng): the row-only citation filter admitted the MUTANT LEDGER's own rows, so a control cited only there read as cited; the `==` census excluded every `ast.Call`, so `str(token) == expected` survived; and two published figures were never measured |
| 15 | 22 run, 20 killed, 2 deliberate survivors | 6 MAJORs (sec) from a 92-mutant campaign: FOUR controls deletable with the suite green - the backup TARGET `O_NOFOLLOW` (read access escalating to arbitrary file overwrite), both audit emissions, the constant-time compare behind a decoy call, and the PATCH `extra="forbid"` - plus 9 further exemption reasons disproved and an unbounded elided-citation prefix |
| 15b | included above | 1 MAJOR (eng) on the SAME control: the tightened constant-time check was a substring test on the deciding return, so a decoy moved inside it kept plain equality deciding; plus 2 figures published without re-measuring and 1 justification measurement falsified |
| 16 | 9 run, 9 killed | **`security-reviewer` PASS** (60 mutants, no BLOCKER, no MAJOR); 4 MINORs, 3 closed: a FOURTH position on the constant-time check (`operator.eq`, `in (x,)`, `__eq__`, and a `startswith` guard needing no comparison at all), two uncovered `models.py` length caps, and `audit()` merging extra fields unsanitised |
| 16b | included above | 6 MAJORs (eng), the first structural: the AST body pin was defeated TWICE without touching the body - `hmac` rebound to a class whose `compare_digest` is `a == b`, and `token_ok` decorated with a prefix oracle - so a pin over statements is blind to what their names mean and what wraps them; plus 4 stale published figures and a tick describing an ancestor commit |
| 17 | 5 run, 5 killed | **1 BLOCKER (eng): an unconditional authentication bypass surviving the whole loop.** The AST body pin read the MODULE's source, so leaving the canonical `def` untouched, appending a naked wrapper with a break-glass branch, spoofing `__qualname__` and rebinding the module name passed every check with ruff and mypy silent. Plus a substitutable `hmac.compare_digest` attribute, two docstrings claiming a closure they lacked, and 2 stale document records |
| 18 | 8 run, 6 killed, 2 deliberate survivors | 1 MAJOR (eng), the FOURTH defeat of one control in four rounds: `inspect.getsource` reads the location a code object SELF-REPORTS, and `types.CodeType.replace()` writes `co_filename` and `co_firstlineno`, so a forged code object was handed the canonical source and returned `True` unconditionally. The round-17 changelog had cited those two fields as the reason the pin was safe |
| 19 | platform run | **The App Store's Secret Detection stage found 12 findings on the first upload**: 12 literal `user:pass@host` shapes across the echo-control test vectors, one source comment and five changelog quotes. Zero live credentials, but a scanner cannot tell a fake from a real one, and my local sweeps had no "Password in URL" rule at all - a check is worth what it tests |

Survivors that remain, each with the reason it is or is not load-bearing:

● **`hmac.compare_digest` to `==`** (`auth.py`): NO LONGER a survivor, and this bullet described
  the wrong control for two releases. It said the mutant was caught by "a source assertion that the
  primitive is present, plus a module-wide check that no token is compared with plain equality".
  Both statements were true and neither was sufficient: the presence assertion fell to a decoy call,
  then to a decoy inside the deciding return, then to `operator.eq`, `.__eq__` and `in (x,)`, which
  are calls rather than comparisons; and the module-wide census cannot see it at all, because it
  matches identifier names and the shipped operands are `supplied` and `reference`. A fifth defeat
  needed no comparison: a `startswith` guard AHEAD of an untouched canonical return leaks a prefix
  oracle while the primitive still ships and is still reached.
  `test_the_token_comparison_uses_the_constant_time_primitive` now pins `token_ok`'s body against
  a canonical four-statement literal, and all five positions are measured dead. **The body pin was
  then defeated TWICE more without touching the body**, one frame out in each direction: the
  engineering gate deleted `import hmac` and bound the name to a class whose `compare_digest` is
  `a == b`, and it decorated `token_ok` with a `startswith` prefix oracle that returns before the
  function is reached. Both green on the full loop, no lint warning. An AST pin over a body cannot
  see what its names mean or what wraps it, so two sibling tests now check exactly those two
  frames and carry their own rows. **And "two frames" undercounted: there were four.** `hmac.compare_digest` can be REASSIGNED while `auth.hmac` stays the standard library module, and the name `token_ok` can be rebound to a wrapper that spoofs `__qualname__` while the canonical `def` sits untouched - the engineering gate measured the second as an UNCONDITIONAL AUTHENTICATION BYPASS surviving the whole loop with ruff and mypy silent. Enumerating frames was the wrong method, exactly as enumerating equality spellings was. The pin now follows the CODE OBJECT the public name reaches, via `inspect.getsource(auth.token_ok)`, and the primitive is checked by TYPE rather than module identity. Nine positions measured dead in total. **A tenth followed immediately**: `inspect.getsource` reads the location a code object SELF-REPORTS, and both fields are writable, so a forged code object presented the canonical source while returning `True`. The control is now the executed BYTECODE, compared against `auth.py` compiled from disk, which is the first assertion in this sequence that is not an enumeration of surfaces. The count is a history of this control, never a bound on what is possible. The TIMING property
  itself stays unassertable by any functional test and is recorded as such in `auth.py`.
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
  under-reports its own coverage is still a ledger that is wrong. **And this paragraph was for one
  release the ONLY place that test was named**, which let it read as a cited control to a sweep
  that scanned the whole document. It has a control-table row now, and the sweep reads rows only:
  a mention in prose is a note, not a promise that something fails if it regresses.

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

   And a stronger form of the same risk is UNTESTED, not merely accepted: `_client_key`
   collapsing to one constant key for every caller survives the whole suite. The consequence
   is availability - one caller would consume the global and write budgets for everyone behind
   the gateway. It is untested because `TestClient` presents a single client host, so asserting
   distinct keys through the app is awkward rather than trivial; the reason is testability, not
   that the risk is negligible. Recorded here rather than left silent, which is the difference
   between an accepted risk and an oversight.
4. **The rate limiter is per process.** The container runs a single worker, so the
   configured limit is the effective limit today. If the worker count ever rises, the
   effective limit rises with it; an exact global limit would need a shared store. The
   purpose is process protection, which this achieves.
5. **Reads are open, and ONE write is too.** `GET /api/v1/sessions` is unauthenticated
   because the dataset is low-sensitivity and its integrity, not its secrecy, is what is
   defended. The session writes are gated by the team token. **`POST /api/v1/drill/answer`
   is NOT**, deliberately, and this sentence used to say "writes are gated" flatly, which a
   reviewer defeated in one request: with a token configured, an unauthenticated answer
   returned 200 and moved persisted state. A reviewer trusting the old sentence would have
   stopped looking at exactly the route that writes.
   The reason is flight plan step 10: operator identity does not exist yet, so every drill
   write goes to the synthetic `DEMONSTRATION_OPERATOR` and no record of a named individual
   is created before the DPIA is closed. Run history is capped at `MAX_RUN_HISTORY`, so the
   open write cannot grow the store without bound.
   Two compensating controls, both now bound by tests rather than asserted here. The route has
   its OWN rate budget, `DRILL_LIMIT`, and that separation is itself a finding: while it shared
   the strict limiter with the gated session writes, twenty unauthenticated answers left an
   authenticated `POST /api/v1/sessions` answering 429. Behind the platform gateway many callers
   share one address (accepted risk 4), so that was a single unauthenticated client able to hold
   the team's gated write path shut. **The split raises the cost of that attack; it does not
   remove it.** Measured after the split: 240 unauthenticated drill answers still leave an
   authenticated `POST /api/v1/sessions` answering 429, because the coarse tier is consumed in
   middleware before any route guard runs, including on the requests the drill guard then
   refuses. So the residual is 240 requests per window where it was 20, a twelvefold mitigation
   rather than a closure, and the remaining bound is the platform ingress, exactly as accepted
   risk 7 records for header-phase parking. The coarse tier stays shared deliberately: a global
   ceiling that a route could opt out of would not be a ceiling. The second control is the audit line, which
   carries the item and the actor and neither the answer text nor any score; deleting it used to
   leave the whole suite green, so it was a claim rather than a control, and it is a control now.
   **When identity lands, this route gets the token dependency and this paragraph goes.**
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
9. **A numeric credential of 40 characters or fewer in VERSION position reaches the divergence
   report, and this item was wrong three times before it was right.**

   `SAFE_VERSION` is a whitelist: a numeric release with optional pre, post and dev segments, and
   nothing else. The PEP 440 local-version segment used to be part of it and is now gone, which is
   the seventh and last revision of this control.

   ● Unbounded, the segment let any alphanumeric run joined by `.` or `-` through, so a
     32-character hex key or a cloud access key identifier in version position echoed in full.
   ● Bounded to eight characters per component and three components, the CONTIGUOUS spelling of
     the credential formats checked was described, and a SEPARATED spelling that fitted the bound
     was not: two dots inside a 20-character access key identifier put all twenty characters back
     on stderr, reconstructible by deleting the dots. The quantifier matters and an earlier version
     of this bullet overstated it - a format longer than 24 characters had no separated spelling the
     three-component bound admitted, so "the separated spelling was not described" was true only up
     to 24 characters.
   ● Its own promise was also false. "Every real local version still echoes" was disproved by
     genuine build tags: semver's `+20130313144700`, `+ubuntu0.22.04.1`, `+git20260821abc`, and a
     local label containing an underscore, which PEP 440 permits.

   Three successive descriptions of that segment were each wrong once - as "all-numeric", as
   covering "a 20-to-38-character token", and as keeping "every real local version". The two
   populations overlap in length, which is why no bound worked; no numbers are given here because
   four successive unmeasured ones were. Dropping the segment costs nothing measurable - no lock
   file here pins a local version - and replaces three clauses that kept drifting with one that
   cannot.

   **What remains is irreducible, stated as the GRAMMAR rather than as an instance.** Any value of
   `MAX_VERSION_ECHO` characters or fewer (40, inclusive) matching `SAFE_VERSION` echoes: a digit
   run with optional dots, optionally carrying one pre-release token from a fixed vocabulary and a
   `.post` or `.dev` tail. So `1preview1.post1.dev1` echoes as well as `1.2.3`.

   A purely numeric secret is the common case and the previous wording named only that, which was
   narrower than the regex by exactly one case - while `describe_version`'s docstring claimed "item
   9 carries the same words". It does now. Accepted because the report has to say which version is
   pinned or it cannot do its job, and a numeric string in release position is indistinguishable
   from a version because it IS one.

10. **`X-Content-Type-Options: nosniff` is sent; Content-Security-Policy and `Referrer-Policy` are
    deliberately not.** The first is not inert here: a stored `title` or `notes` comes back inside a
    `GET /api/v1/sessions` body, and a browser pointed straight at that URL decides for itself what
    the bytes are. `NoSniffMiddleware` sets it on every response the USER STACK produces,
    including one a middleware answers itself - a 413 from the body cap, a 429 from the limiter -
    which is why it is registered outermost among user middleware, asserted by
    `test_the_middleware_order_puts_the_limiter_outside_the_body_cap`.

    It cannot reach further than that, and this item said "every response" for one round after that
    was disproved. Starlette installs `ServerErrorMiddleware` above every user middleware, and that
    is what renders the unhandled-exception 500, so `_install_error_handlers` sets both this header
    and the configured-origin `access-control-allow-origin` on that response itself. The claim was
    corrected in the middleware, the handler and the test, and left standing here - in the item the
    changelog nominates as carrying the current position, which is the one that mattered.

    The other two are inert on this service and are recorded as absent rather than left unexplained:
    it serves JSON and plain text only (`/livez`, `/ping` and `/health` return `PlainTextResponse`;
    there is no `HTMLResponse`, no template, no static file and no `text/html` anywhere in the
    source), it sets no cookies, and CORS refuses to start on a wildcard or `null` origin. They
    would be a policy claim with nothing to enforce. Revisit if this service ever serves a document
    or sets a cookie.

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
