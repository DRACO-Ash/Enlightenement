# ENLIGHTENMENT API and transport contract

| | |
| --- | --- |
| **Document** | ENL-SPEC-02 |
| **Version** | 1.0 |
| **Date** | 29 August 2026 |
| **Status** | Build specification |

---

## 1. Principles

**Server-authoritative.** The client renders and may predict. It never decides truth. Any score, any scenario state, any progression decision comes from the server.

**The client never receives the answer before the operator commits.** This is the architectural expression of the production-format rule. A drill payload contains the stimulus and the prompt. Accept values, reject values and the explanation arrive only in the response to a submission. **If the answer is in the browser, the training does not work**, and it will be in the browser if anyone builds a convenient combined endpoint.

**No egress.** Every asset served locally. No CDN, no map tiles, no external fonts.

**Health endpoints are unauthenticated and leak nothing.**

---

## 2. Conventions

● Base path `/api/v1`
● JSON in and out, UTF-8
● Times ISO 8601 UTC with `Z`
● Errors: `{"error": {"code": "...", "message": "...", "detail": {...}}}` with a generic message to the client and detail only in the server log
● Auth by session cookie, `HttpOnly`, `SameSite=Strict`, `Secure` where TLS terminates upstream
● `PORT` from environment, bind `0.0.0.0`

---

## 3. Health

| Method | Path | Auth | Returns |
| --- | --- | --- | --- |
| GET | `/` | none | 200, SPA shell |
| GET | `/healthz` | none | 200 `{"status":"ok"}` |
| GET | `/readyz` | none | 200 when content loaded and database reachable, else 503 |
| GET | `/version` | none | 200 `{"app":"...","content_hash":"..."}` |

`/readyz` returns 503 while content is loading or if any content file failed validation. **A malformed content file must not produce a running application that serves broken scenarios.**

---

## 4. Session

| Method | Path | Body | Returns |
| --- | --- | --- | --- |
| POST | `/api/v1/session` | `{operator_id, password}` | 200 sets cookie, `{operator, stages, ratings}` |
| DELETE | `/api/v1/session` | | 204 |
| GET | `/api/v1/session` | | 200 current operator, or 401 |
| POST | `/api/v1/session/visibility-ack` | | 204, records acknowledgement of the visibility notice |

Behind `IdentityProvider`. If the shell later supplies identity by header, this becomes a second implementation and nothing else changes.

---

## 5. Dashboard

| Method | Path | Returns |
| --- | --- | --- |
| GET | `/api/v1/me` | Competency estimates **with confidence intervals**, both ratings, chain length, stage progress, decay by procedure, what is due |
| GET | `/api/v1/me/history?limit=&before=` | Run summaries within retention |
| GET | `/api/v1/me/export` | Full personal export, JSON. Operator-initiated |

`/api/v1/me` **must not** return a bare competency estimate. The interval is part of the value.

---

## 6. Drill

```
POST /api/v1/drill/next
  → { drill_run_id, item_id, elo, prompt, response_format,
      stimulus: { product_id, generator, params, rendered },
      confidence_required, time_target_s }
```

Selection: FSRS due first, then Elo-matched to the operator's drill rating, interleaved across procedures. **Never returns `answer` or `explain`.**

```
POST /api/v1/drill/{drill_run_id}/submit
  { response, confidence, elapsed_ms }
  → { correct, credit, matched: "accept"|"partial"|"reject",
      explain, note, brier, rating_delta, next_due_at,
      score_components: [ { rule_id, award, explain } ] }
```

Submission is idempotent on `drill_run_id`. A second submission returns the first result rather than rescoring.

---

## 7. Synthesis

```
POST /api/v1/synthesis/next   { tier? }
  → { run_id, tier, products: [ { product_id, rendered, label } ],
      prompt, response_format, expected_components? }
```

`expected_components` lists the six argument components at tier 3 and above, so the client can scaffold the entry form. **It carries the component names only, never the expert's content.**

```
POST /api/v1/synthesis/{run_id}/submit
  { conclusion, evidence_chain, alternatives_eliminated,
    confidence, falsifier, gaps, products_used }
  → { components_present, score_components, fusion_rating_delta,
      chain_length, economy_bonus, challenge? }
```

At tier 5 the response carries a `challenge`. The operator then either defends or revises:

```
POST /api/v1/synthesis/{run_id}/challenge-response
  { action: "defend"|"revise", body }
  → { score_components, expert_comparison }
```

---

## 8. Scenario

REST to start and stop; WebSocket for the running clock.

```
POST /api/v1/scenario/start   { scenario_id?, difficulty_band? }
  → { run_id, scenario_id, seed, narrative_frame,
      clock: { sim_start, rate, state: "running" },
      products_available: [product_id],
      timing: { indication_at, standard_ref } }

POST /api/v1/scenario/{run_id}/end   { reason }
  → { outcome, total_score, debrief_url }
```

### 8.1 WebSocket

Connect `GET /api/v1/scenario/{run_id}/stream`, upgrade. Session cookie authorises. **Server to client:**

| Type | Payload | Notes |
| --- | --- | --- |
| `clock` | `{sim_time_ms, rate, state}` | Fixed cadence, default 1 Hz |
| `product` | `{product_id, rendered, posted_at_sim_ms}` | A provider has delivered. **Recomputes the governing timing leg** |
| `trigger` | `{trigger_id, at_sim_ms, event}` | An EBAT trigger fired |
| `timing` | `{leg:"indication"\|"product", deadline_sim_ms, remaining_ms}` | Sent on start and on every product arrival |
| `challenge` | `{body}` | Tier 5 only |
| `ended` | `{outcome, debrief_url}` | |

**Client to server:**

| Type | Payload |
| --- | --- |
| `action` | `{action_type, payload}` where action_type is `open_product`, `enter_procedure`, `request_product`, `task_collection`, `notify`, `close_thread`, `triage` |
| `report` | `{report_kind, body}` |
| `pause` / `resume` / `rate` | `{rate}` where permitted by band |
| `ack` | `{last_seq}` for reconnect |

### 8.2 Reconnect

Because the simulation is deterministic and server-authoritative, reconnect is a snapshot plus replay:

```
GET /api/v1/scenario/{run_id}/snapshot?since_seq=
  → { sim_time_ms, state, events_since: [...], timing }
```

The client discards local state and rebuilds. **It never extrapolates the clock across a disconnect.**

### 8.3 Timing, which is not optional

Both legs computed server-side. `remaining_ms` is always against the **governing** leg. A `timing` message is emitted whenever a product arrives, because the governing leg can change mid-event. The client renders both clocks and highlights the governing one.

Where a scenario's procedure is a daily crew operations task, `timing` is **not sent** and latency is not scored. Those tasks have no timing standard and inventing one would be wrong.

---

## 9. Report

```
POST /api/v1/report/analyse   { run_id, report_kind, body }
  → { detection_results, anatomy_results, conditional_results,
      latency: {from_indication_s, from_last_product_s, governing_leg, band} }
```

Deterministic, offline, using `report-detection-patterns.json`. Returns findings, never a grade.

```
POST /api/v1/report/submit   { run_id, report_kind, body }
  → { score_components, expert_comparison: { body, elements_present },
      self_assessment_prompts: [...] }
```

The expert version is released **only after submission**. The response states plainly that prose quality is not marked.

---

## 10. Debrief

```
GET /api/v1/debrief/{run_id}
  → { run, timeline: [...], expert_trace?, score_components,
      anatomy_coverage, highlights: [...], missed: [...] }
```

`highlights` carry `{product_id, feature_ref, at_sim_ms, expert_saw, ruled_out}` for rendering the pedagogical highlight over the operator's own data.

Where the scenario has no expert trace, `expert_trace` is null and the client says so rather than degrading silently. **Seven of twelve scenarios are currently untraced.**

---

## 11. Content and authoring

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/api/v1/content/manifest` | operator | Loaded versions and hash |
| GET | `/api/v1/content/procedure/{id}` | operator | Read a procedure |
| GET | `/api/v1/content/product/{id}` | operator | Definition and layout |
| POST | `/api/v1/authoring/trace` | author | Begin trace capture on a scenario |
| POST | `/api/v1/authoring/trace/{id}/observation` | author | Capture one observation |
| POST | `/api/v1/authoring/trace/{id}/finalise` | author | Includes the `would_have_missed` prompt |

Trace authoring is how the single-author dependency is fixed. Writes to `authored_trace`, status `draft` until a second expert validates.

---

## 12. Supervisor

**Blocked pending the multinational visibility decision.** Build the endpoints, gate them behind a configuration flag, default off.

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/api/v1/supervisor/cohort` | Aggregate only, minimum cohort size enforced |
| GET | `/api/v1/supervisor/operator/{id}` | Individual. **Writes an audit row before returning** |

The audit row is written **before** the response, not after, so a failed response still records the attempt. Returns competence, coverage and decay. Never raw failed attempts, drill misses or sandbox activity.

---

## 13. Rate limits

Two tier, modest. This is an internal tool, not a public API.

| Scope | Limit |
| --- | --- |
| Scenario start | 10 per operator per minute |
| Drill next | 60 per operator per minute |
| Report analyse | 30 per operator per minute |
| Everything else | 300 per operator per minute |

Purpose is protecting a ten-operator shift on a 1Gi envelope from a stuck client, not defending against attack.

---

## 14. Performance budget

| Path | Target |
| --- | --- |
| Drill submit round trip | under 100 ms |
| Drill next | under 200 ms |
| Scenario start | under 1 s |
| Dashboard | under 500 ms |
| Clock tick jitter | under 50 ms |

The drill submit target is the important one. It is the muscle-memory loop, and if it drags the loop breaks and the memory system stops working.

---

## 15. What must never appear

● Any endpoint returning a drill answer before submission
● Any endpoint returning expert trace content before submission
● Any competency estimate without its confidence interval
● Any supervisor read of an individual without an audit row
● Any timing computation using one leg only
● Any external network call at runtime
