# ENLIGHTENMENT - Flight plan

**Name:** ENLIGHTENMENT (confirmed by owner, 16 August 2026). Proposed slug `enlightenment`.
**Owner:** Ash Higgins, Technical Director, Bluestaq Limited
**Date:** 16 August 2026
**Version:** 1.0 (draft for tidy)
**Classification:** Not classified (confirmed by owner, 16 August 2026). See Security and classification for the one boundary this does not settle.

---

## Vision and single job

● **In one sentence:** ENLIGHTENMENT is a standalone orbital warfare simulation trainer that turns JCO Protect and Defend procedures into a game operators want to play, so that when a real event lands they already know what to do without looking it up.
● **Single job:** build instant, correct recall of the action required for each event type in the procedure library.
● **Why now:** the JCO cell runs a follow-the-sun watch with mixed-experience crews and a living procedure set. Procedures change faster than formal courseware can be rewritten, and there is no individual-skill trainer between exercises. Slingshot's Laboratory and TALOS occupy the high-fidelity simulation ground for the US; nothing occupies the learning-instrumentation ground, and nothing is sovereign.

The pain, stated plainly: a new analyst on shift has to find the right procedure, read it, and interpret it while an event is unfolding. An experienced analyst has the recall but no way to prove it or keep it fresh across procedures they rarely see. Neither is served by a document library.

The three-step plan: the operator plays short, varied scenarios; ENLIGHTENMENT scores against the procedure's own expected response and debriefs against what an expert would have seen; the operator arrives at the console already knowing the move.

---

## Users and experience

● **Primary user:** military space domain analysts and Protect and Defend operators in the JCO cell and adjacent UK Space Command roles. Mixed experience, from never having seen an element set through to seasoned orbital analysts. **Assume zero prior knowledge as the floor.** The application must onboard someone who does not know what an elset is, and still stretch someone who has been reading light curves for years.
● **Secondary users:** content authors and instructors who maintain the procedure library and scenario set; supervisors who need aggregate readiness evidence.
● **Their context:** shift work, time pressure, shared operations rooms, often headphones-off. Motivated by competence and mission readiness, not by trivia or streaks. Highly allergic to anything that feels childish or like surveillance.
● **The one thing the interface must make effortless:** going from "an event is happening" to "I know which procedure this is and what step one is" in seconds, repeatedly, without reading a manual.
● **Look and feel:** dark mission-control, continuous with the PSIRENS visual language (confirmed by owner, 16 August 2026). Navy `#162646` ground, `#739BCF` for structure and labels, green for nominal, red for alert. Copper-amber `#C67C00` excluded from product UI per house rule. Dense but calm; typography carries hierarchy, not chrome. Precise operational language throughout: missions and scenarios, never levels-and-loot.

**Contrast, measured not assumed (all figures WCAG 2.2, computed 16 August 2026):**

| Colour | On `#162646` | Verdict |
| --- | --- | --- |
| Ink `#E8EDF5` | 12.76:1 | Body text, pass |
| Ink dim `#9FB0CC` | 6.83:1 | Body text, pass |
| Blue 2 `#739BCF` | 5.23:1 | Body text, pass |
| Green `#27AE60` | 5.22:1 | Body text, pass |
| Red `#C0504D` | 3.21:1 | **Body text, fail** |
| Blue 1 `#385FAF` | 2.45:1 | **Fails even the 3:1 graphic floor** |

Two hard rules follow, and they are code standards not preferences:

■ **Blue 1 `#385FAF` never carries text and never conveys status.** At 2.45:1 it fails the graphic floor as well as the text floor. It is a structural fill and border colour only, behind lighter marks. This is the single most likely accessibility defect in a PSIRENS-derived palette and it should be a grep gate.
■ **Alert red is lightened to `#E06C69`** (4.66:1 on navy, 5.32:1 on the darker ground) wherever it carries text or a small mark. `#C0504D` is retained only for large fills where 3:1 suffices. Alert text that fails contrast is the worst possible place to fail.

**Where dark mission-control and learning pull apart, and how the design resolves it:**

■ **Density must vary by mode, palette must not.** Cognitive load theory is unambiguous that a novice on a dense display spends attention on the display rather than the content, and the expertise-reversal effect says the scaffolds that fix that for a novice actively harm an expert. So the drill surface strips to almost nothing: one plot, one input, one confidence control. The scenario surface is full operational density. Same colours, same type, same grammar, so it still reads as one tool and the transfer to the real console is preserved.
■ **Learning needs a "look here" signal, and the palette has no colour free for it.** Red is alert, green is nominal, blue 2 is structure, and amber is excluded from product UI by house rule. The debrief's central move is highlighting the cue the operator missed on the actual data they were looking at, and it must not read as an alarm. **This is a real decision, flagged in the open questions.** The recommendation is a single pedagogical highlight treatment using ink-bright `#E8EDF5` outline plus a brief pulse, reserved exclusively for debrief signalling and used nowhere else, so it never competes with operational semantics. The alternative is a narrow house-rule exception admitting copper-amber for this one purpose.
■ **Status is never colour alone.** Red and green as the alert and nominal pair is the classic deuteranopia trap. Every status carries a shape and a text label as well as a colour; a labelled triangle, not a red dot.
■ **Motion is a reward moment and a hazard.** The reveal in the drill loop is where the product earns its "one more" feeling, so it gets real motion design. It also honours `prefers-reduced-motion` completely, with a non-motion equivalent that still marks the moment.
■ **Typography floor of 18px** per house style, which matters more here than in a monitoring tool because operators read procedure text under time pressure, not just glance at glyphs.
● **Feel reference and "done looks like":** the reference is PSIRENS at v1.4.12 plus a chess.com Puzzle Rush pacing model. Acceptance line for the owner: *"It looks like a tool I would leave open on the second monitor during a shift, and the drill loop is tight enough that I do one more without deciding to."*
● **Tone rule:** errors are learning events, never failures. No punitive mechanics anywhere.

---

## Outcomes and success measures

The transformation: from "I know the procedures exist" to "I recognise this event and act correctly under time pressure."

Observable measures, in priority order:

● **Skill gain (headline).** Accuracy and time-to-correct-classification on **held-out cue patterns the operator has not recently seen**, measured pre and post. This is Kirkpatrick Level 2 and it is the metric the product is optimised for.
● **Calibration.** Brier score on the operator's stated confidence, trending down. Confident errors are the thing this is built to remove.
● **Coverage.** Percentage of active procedures in the library on which the operator has demonstrated current competence, with decay modelled by the spacing scheduler.
● **Retention at interval.** Performance on a procedure at 30 and 90 days since last exposure.
● **Voluntary return rate.** Not engagement for its own sake, but the honest test of "does it feel like a game": do operators open it when nobody told them to.

**Competency axes (invented here, because no external framework applies; confirmed with owner 16 August 2026).** Six axes, each scored with a confidence interval, never a bare number:

1. **Cue detection.** Spotting that something in the data is not nominal, and how quickly.
2. **Event classification.** Naming the event correctly, and discriminating between look-alikes (separation versus breakup, station-keeping versus manoeuvre).
3. **Procedure recall.** Knowing which procedure governs and what step one is, unprompted.
4. **Physical reasoning.** Judging plausibility against orbital mechanics. Is that drift rate physically possible, does that delta-v make sense for that platform.
5. **Uncertainty and calibration.** Confidence matched to evidence, and treating a data artefact as a peer hypothesis rather than a footnote.
6. **Reporting.** Producing the right content, at the right threshold, at the right time.

These axes are the scoring spine, the dashboard shape, and the coverage report. They are ours, so they are also revisable; version them like content.

Explicitly **not** success measures: daily active users, session length, points accumulated, tutorials completed. Those are diagnostics, not outcomes.

---

## Scope and journeys

**Core journeys, in order:**

1. **First run, zero knowledge.** Operator signs in, is asked nothing, and is dropped into a 90-second guided worked example: here is a plot, here is the cue, here is what an expert calls it. Ends with the operator making one correct call themselves.
2. **Drill loop (the heart of the product).** A rated, timed cue-recognition drill. A short data presentation, a produced answer with a confidence level, immediate reveal, next. Elo-rated so difficulty tracks the operator. This is where recall is built.
3. **Scenario run.** A full event scenario on a running clock: read the data, classify the event, identify the governing procedure, execute the decision points, produce the report content. Threat type withheld by default.
4. **Debrief.** Deterministic replay of the exact scenario with the expert's read overlaid: what the expert saw and when, what the operator saw and when, which rule fired and why, what it cost. Self-explanation prompt before the reveal.
5. **Free analysis (sandbox).** Load or fork a scenario, alter parameters, watch what happens, no scoring.
6. **Dashboard.** Where the operator stands, what has decayed, what is recommended next, and why.
7. **Authoring.** A content author edits a procedure or adds a new one as a validated data file; dependent scenarios and rubrics are flagged stale rather than silently drifting.

**Out of scope for v1 (named deliberately, not deferred by accident):**

● 3D globe. 2D-first, per the research recommendation. An offline Cesium globe is a later flourish.
● Live UDL connectivity. Schema-faithful synthetic data only, `dataMode` set to `SIMULATED` or `EXERCISE`.
● Celestrak or any live TLE feed.
● Electronic warfare, directed energy and cyber scenario categories.
● Leaderboards and cohort comparison of any kind.
● In-app WYSIWYG procedure editor. Version-controlled validated files first.
● Multiplayer, crew-position and instructor-in-the-loop modes.
● Mobile layouts. Desktop, two-monitor context.

**Smallest useful version:** the drill loop plus the debrief, covering **three Event-Response procedures** (Manoeuvre, RPO, and the Separation versus Breakup discrimination), with the procedure library data model seeded with all fifteen procedures but only those three wired to scenarios. That alone is a usable trainer. Everything else is expansion along a proven spine.

---

## Archetype and stack

● **Archetype: server.** A process runs at runtime: an authoritative simulation clock, a scoring engine, and per-operator persistent state. Nothing about this is static.
● **Language and stack:** Python 3.12, FastAPI, served single-file SPA. Physics runtime is `sgp4` (MIT, validated against the Vallado AIAA 2006-6753 test vectors) plus `skyfield` for frames and time, plus NumPy. High-fidelity authoring (Lambert, force models) happens **offline** with `hapsira` or Orekit and is baked into scenario ground truth, so no JVM and no numba in the container.
● **Why:** it matches the org's proven App Store stack (PSIRENS), keeps the physics in one testable language, and holds the memory budget. Client-side propagation is deliberately **not** used: the server ships pre-computed track segments and the client interpolates. That removes the client/server divergence failure mode entirely and drops `satellite.js` from the bundle.
● **Frontend:** single-file SPA, no framework, no CDN, all assets vendored. Canvas and SVG for the plot surfaces (GEO belt longitude versus inclination, Hill-frame relative motion, range versus time, light curve, Gabbard, event timeline).
● **Transport:** WebSocket for the scenario clock, with a polling fallback. Deterministic snapshot plus event log makes reconnect trivial.
● **Deployment target:** Bluestaq App Store, container archetype, per CONTEXT-001 Section 7.

**App Store submission facts:**

● **Slug:** `enlightenment` proposed, lowercase, single word. **TBC, re-verify uniqueness in the store before first upload (owner: Ash).** Display name separate.
● **Category and visibility:** TBC, re-verify (owner: Ash).
● **Resource envelope:** 1Gi memory proposed, matching PSIRENS. The 256Mi floor is not realistic once several concurrent scenario clocks and a scenario cache are live. Set in the Configuration tab, never the Dockerfile.
● **Environment variables:** no external API credentials required for v1, which is a deliberate design win. Expect only `PORT` (platform-injected, never set in the Dockerfile), a signing secret for session state, and a content-directory path. Secret handling per house standard, session-scoped, never process-global.
● **Storage add-on:** **confirmed available and writable by uid 10001** (owner: Ash, 16 August 2026). Operator progress persists across deployments on the mounted volume. This settles the persistence design: SQLite, single file, no fallback needed.
● **Rollback target:** the previously deployed image tag, tested before first production upload.
● **Identity (decided, because the answer is not yet known and waiting costs more than designing around it):** ENLIGHTENMENT builds its own identity layer behind a single `IdentityProvider` adapter, using `itsdangerous` plus `bcrypt` per house standard. If the shell turns out to pass a signed-in identity via a header, that becomes a second implementation of the same adapter and nothing else in the codebase changes. **TBC, re-verify: whether the shell passes identity, and via which header (owner: Ash).** The adapter means this is no longer a blocker.
● **Runtime contract unknown still to confirm:** whether saving an environment variable restarts the pod or leaves an old pod serving old values. **TBC, re-verify (owner: Ash).** The highest-risk surface is the one the local loop never tests.
● **Container contract (settled, from CONTEXT-001):** read `PORT` defaulting to 8080, bind `0.0.0.0`, run as uid 10001, unauthenticated 200 on `/`, `/healthz` and `/readyz`, two requirements files (`requirements.txt` carries all test tooling, `requirements-runtime.txt` stays lean).

---

## Structure

**High-level structure and key components:**

● **Procedure Library.** Versioned, schema-validated content: purpose and entry conditions, roles, ordered steps with responsible role and notes or warnings, threshold criteria, reporting requirements, transition rules, closure criteria, and a status field (draft, active, deprecated). Immutable versions with pointers; every run records the exact content version hash it was scored under.
● **Scenario Engine.** Deterministic, server-authoritative, fixed-timestep, seeded PRNG. Scenarios are parameterised templates: the expected response is fixed, the instantiation (regime, longitude, sensor availability, noise, event timing) is seeded. Every generated scenario passes a solvability check before it is served.
● **Physics Core.** SGP4 propagation, frame and time conversions, Clohessy-Wiltshire relative motion, simplified phase-corrected photometric model, delta-v accounting. Pure functions, small, no I/O.
● **Drill Engine.** Elo-rated cue-recognition items, scheduled by FSRS. **The answer is never on screen.** Production, not recognition.
● **Scoring Engine.** Config-driven decision tables, not a monolithic function. Every score decomposes into which rule fired, on which evidence, against which procedure version. Explainability is a requirement, not a nicety, because the debrief depends on it.
● **Debrief Engine.** Replays the run from seed plus event log and overlays the expert trace.
● **Progress Store.** Per-operator skill estimates per axis with confidence intervals, FSRS scheduling state, run history.
● **SPA shell.** Dashboard, Drill, Scenarios, Sandbox, Library, Settings. Guided and Free Analysis toggle. Single page, no full reloads.

**Where data and state live:**

● **Content** (procedures, scenario templates, rubrics, taxonomy, gamification config) lives as version-controlled JSON or YAML files in the image, hot-reloadable, JSON Schema validated on load with safe failure. A malformed file is rejected with an author-facing error and never serves a broken scenario.
● **Operator state** lives in **SQLite on the storage add-on volume**, single file, transactional, zero-admin, WAL mode. Confirmed available and writable by uid 10001, so this is settled with no fallback path to maintain.
● **Run artefacts** (seed, event log, content version hashes, score decomposition) are written immutably so a debrief months later is still interpretable.
● **Nothing in browser storage.** Stated requirement.

---

## Data and integrations

● **Data held:** synthetic scenario data shaped to the UDL public schemas (element sets, positional observations for EO, radar and RF, photometric observations, and NOTSO-style event notices), the procedure library, and per-operator performance records tied to a named individual.
● **Sources:** everything served at runtime is authored or generated. No live feed in v1. Realism is drawn from public sources only: Secure World Foundation Global Counterspace Capabilities, CSIS Space Threat Assessment, the SPARTA v4.0 matrix, and the public UDL schema shapes.
● **Offline UDL characterisation pass (added 16 August 2026; a prerequisite, not a refinement).** The synthetic generator cannot invent realistic imperfection, and clean training data is negative training: it teaches that anomalies are obvious and produces operators whose cue-to-action mapping breaks on the first ragged real feed. So real UDL data is characterised **once, offline, on the workstation**, and what ships is a **noise model, not data**.
  ■ **What is measured, as distributions:** observation gap and revisit statistics per sensor; astrometric and photometric residual distributions per sensor; elset epoch spacing including near-duplicate epochs; outlier and missing-field rates; the real distribution of classification markings; and correlation quality, so the uncorrelated-track rate in training reflects the real one.
  ■ **Why epoch spacing specifically:** the LEARNED register records an ASTRA 1M case where a millisecond epoch gap produced a drift rate of about minus 22,900,000 degrees per day. That artefact class is exactly what competency axis five exists to train, and no generator invents it unaided.
  ■ **What crosses the boundary:** a small parameter file of distributions. No records, no object identifiers, nothing traceable to a real asset. Redaction discipline intact.
  ■ **Runtime posture is unchanged:** no UDL call, no credential, no egress, air-gap preserved.
  ■ **The noise model is versioned content** with an owner and a review date, because sensor mixes change and a stale noise model silently teaches yesterday's data quality.
● **Integrations:** none at runtime for v1. Any later real-data integration sits behind an explicit adapter boundary, logged, and marked so there is never ambiguity about which objects are real and which are synthetic threat actors.
● **Sensitivity:** the scenario data is not sensitive by construction. The **performance data on named personnel is** personal data under UK GDPR and is the sensitive asset in this system.
● **Taxonomy tagging:** every scenario and expected response carries SPARTA technique IDs, pinned to version 4.0, giving free coverage analytics and a shared vocabulary.

---

## Security and classification

● **Classification of this work and its outputs: Not classified** (confirmed by owner, 16 August 2026).
● **Classification of the source procedures: Not classified** (confirmed by owner, 16 August 2026). That removes the handling constraint on authoring.
● **The redaction gate stays anyway, and this is deliberate.** Unclassified is not the same as unrestricted. The procedures still contain protected-object exclusion lists by catalogue number, internal tool click-paths, chat-channel and product-naming conventions, and OPSEC guidance. **None of that belongs in the application, the content files, the repository, or generated scenario data**, regardless of marking, because aggregating it into a distributable training artefact changes its exposure. ENLIGHTENMENT teaches that such a list exists and must be checked; it never holds the list.
● **Redaction discipline:** a mandatory authoring check before any procedure or scenario enters the content tree. Does this reference a specific real asset, channel, credential or click-path? If yes, it is generalised or cut. **Reviewer: Ash** (same owner as authoring, which is a single point of failure, noted under Constraints).
● **What is worth defending:** the personal performance data, and the integrity of the scoring path. The realistic attacker is not a nation state, it is an operator gaming the scorer and an accidental disclosure through content.
● **Secrets:** a session signing secret only. Environment variables, never the repository, never logged, never echoed. No external API credentials in v1.
● **Sign-in:** yes, and it is a **real boundary**, because it gates access to personal performance records. Whether the App Store shell supplies identity via a header or ENLIGHTENMENT runs its own identity layer is TBC above; the fallback pattern is `itsdangerous` plus `bcrypt` per house standard.
● **Privacy posture (decided by owner, 16 August 2026: supervisors see individual results).** This is a legitimate call in a readiness context and the plan implements it. It is not cost-free, so the controls below are part of the design rather than optional extras:
  ■ **No covert observation.** Operators are told, at first run and in the interface, exactly what their supervisor can see, in the same words the supervisor sees it. Surprise is what destroys trust in a tool like this, not visibility.
  ■ **Purpose limitation, stated explicitly.** The declared purpose is training development and readiness assurance. If the data is later used for performance management or discipline, that is a new purpose requiring a new notice and a DPIA revision. Write the purpose into the privacy notice and the interface, not just the DPIA.
  ■ **Show competence, not failure.** Supervisor views surface current competence, coverage and decay by axis. They do not surface raw failed attempts, sandbox activity, or drill misses, because a drill miss is the mechanism by which the product works. Penalising the practice loop would destroy the loop.
  ■ **Sandbox and free analysis are never scored and never reported.** Operators need a place to be wrong in private or they will not explore.
  ■ **Retention limit.** Detailed run artefacts age out on a defined schedule; aggregate competence persists. **TBC, re-verify: retention period (owner: Ash, as DPL).**
  ■ **Motivational risk, named:** Self-Determination Theory evidence says perceived surveillance erodes intrinsic motivation, which is the engine this product runs on. The mitigations above are what keep the decision from costing voluntary return rate. Watch that metric after launch; it is the early warning.
● A **DPIA is required** before any named-individual performance data is collected, with a lawful basis identified. Consent is not the right basis in an employment context. **TBC, re-verify: DPIA sign-off and staff consultation route (owner: Ash, as DPL).**
● **Air-gap posture:** no CDN, no map tiles, no external calls at runtime. The application must function fully with no egress.

---

## Observability and audit

Not in the original thirteen areas, added because the supervisor-visibility decision made it load-bearing.

● **Audit of access to personal data.** Every supervisor view of an individual operator's results writes a structured one-line JSON audit record: who viewed, whose record, when, which view. This is the control that makes the visibility decision defensible to the operator and to an assessor, and it is cheap to build now and expensive to retrofit.
● **Audit of content changes.** Every procedure, rubric and scenario edit records author, timestamp, content version hash and the reason for the change. Attribution is not optional for content that drives scoring.
● **Structured logging to stderr**, one line per privileged action, actor sanitised and capped. Generic errors to the client, detail server-side.
● **No secret, credential or personal performance figure in any log line.**
● **Health and readiness** at `/healthz` and `/readyz`, unauthenticated, 200, no sensitive data in the body.
● **Version stamp** visible in the interface and in the health payload, so an operator reporting a problem names the build without being asked.
● **Rollback signal:** a defined check after deploy that says healthy or roll back, tested before the first production upload.

---

## Performance budget

Also added; the research made the case and the plan had no numbers.

● **Cue to feedback under 100ms** for a drill answer. This is the muscle-memory loop and it is the one latency that matters most; if it drags, the loop breaks and the product stops working as a memory system.
● **Scenario tick broadcast at a fixed cadence** the client can interpolate against, with the server authoritative.
● **First meaningful paint under two seconds** on the dashboard, cold.
● **Scenario start under one second** from click, using a pre-warmed scenario cache.
● **Rate limiting** on the scoring and scenario-start endpoints, two-tier, to stop a stuck client or an impatient operator from starving the shift. Modest limits; this is an internal tool, not a public API.

---

## Code standards

● **Conventions:** house Python standard. Fully typed, MyPy and Pyright strict compatible, Ruff and Black compliant, docstrings, structured logging, explicit exception handling. Executable production code, never pseudocode. SOLID, DRY, KISS, YAGNI.
● **Cognitive complexity capped at 15 per function**, enforced locally by the `cognitive_complexity` gate before upload. Physics decomposes naturally into small pure functions; this cap is an ally, not an obstacle.
● **Surgical edits.** `str_replace` with unique anchors, never wholesale rewrites.
● **What must never appear:** a hardcoded credential, a client-side gate on anything that matters, a fabricated field name or API behaviour, a real protected-object identifier, an internal tool click-path, or a scoring decision the debrief cannot explain.
● **Language and spelling: UK English**, confirmed. No em-dashes. `●` or `■` bullets, never dashes. Code identifiers and config follow ecosystem norms, not house style.
● **Palette rules are enforced, not trusted:** a grep gate fails the build on `#385FAF` used as a text or status colour, and on `#C0504D` used for text or small marks. Contrast is measured in test, not eyeballed in review.
● **Frontend accessibility floors are code standards, not polish:** WCAG 2.2 AA, contrast met on charts and text, colour-blind-safe palettes, status never encoded by colour alone (a labelled shape, not a red dot), keyboard operability of every plot surface, focus management in overlays, live regions used sparingly and at a controlled cadence, `prefers-reduced-motion` honoured. Audio optional and off by default; this runs in a shared operations room.

---

## Quality and testing bar

"Tested" here means the physics is provably right and the scoring is provably reproducible.

● **Golden tests** of the propagator against the published Vallado AIAA 2006-6753 SGP4 test vectors. Non-negotiable; this is the foundation everything else scores against.
● **Property-based tests** (Hypothesis) of invariants: two-body energy and momentum conservation, frame round-trips within tolerance, element-set round-trips, angle wrapping across the plus or minus 180 seam.
● **Deterministic replay tests:** the same seed yields an identical event log and an identical score decomposition, run to run.
● **Content integrity tests:** every procedure and scenario file validates against its schema; every scenario passes the solvability check; every rubric references a resolvable procedure version.
● **Frame and time bug traps** as named regression tests: TEME treated as J2000, leap seconds, GMST errors, degrees versus radians, TLE epoch misuse.
● **Coverage floor: 80 per cent**, the App Store gate figure, measured on the Python side. The SPA is excluded from coverage and duplication but **is still analysed for issues**.
● **Gates that must pass before done:** local loop green, `simulate-pipeline.sh` including the grep gates for the known SonarQube rules the eslint proxy cannot see, then the platform SonarQube quality gate at zero violations, coverage at least 80 per cent, and A ratings on security, reliability and security review.
● **Scorer validation, which is a quality gate the toolchain does not cover:** the automated scorer must be checked for agreement with expert human raters on a validation set before any operator is scored by it. An unvalidated scorer is a wrong answer delivered with confidence, which is the exact failure this product exists to prevent.

---

## Constraints and ownership

● **Deadline:** TBC, re-verify (owner: Ash). Nothing in the brief assumes one.
● **Budget:** engineering time only; all dependencies are permissively licensed (sgp4 MIT, Skyfield MIT, Cesium Apache 2.0 if later adopted). No licence cost.
● **Concurrency target:** up to **10 concurrent operators**, one shift crew (confirmed by owner, 16 August 2026). 1Gi holds that comfortably with headroom for the scenario cache.
● **Owners:** Ash owns product, classification, redaction sign-off, expert-trace authoring and the deploy decision. **Confirmed 16 August 2026: Ash authors and validates the expert traces.** That de-blocks the build but concentrates the largest non-engineering dependency in one person. Mitigations, built into the plan rather than hoped for: expert traces are authored as validated data files, not code, so they can be written in batches between builds; the drill layer needs far fewer traces than scenario mode, so the smallest useful version is reachable on a small authoring budget; and every trace records its author and date so a second SME can be added later without re-authoring the first set.
● **Irreversible decisions requiring explicit confirmation:** first App Store publish, and any decision to collect named-individual performance data before the DPIA is signed.

---

## The one creative risk

**The drill loop, where the answer is never on screen, scheduled by a spaced-repetition engine that re-injects your own misses into future full scenarios.**

Everyone else in this space builds fidelity. Slingshot has a digital space twin and an AI adversary and a $27M USSF contract; competing on simulation realism is a losing bet and the wrong bet. The bold move is to treat this as a **memory system that happens to render orbits**, not a simulator that happens to score.

Concretely: an Elo-rated cue-recognition drill in which the operator must **produce** the classification and the first procedural action, never pick from a visible list, with a stated confidence scored by a proper scoring rule. When they miss, FSRS decides when that class of cue reappears, and it reappears **inside a full scenario**, not as a flashcard. Retrieval practice, spacing, interleaving and calibration, all invisible, all wrapped in something that feels like Puzzle Rush.

**Why it is worth it:** it is the only mechanism in the research that directly produces the stated end goal, instant recall, and it is the thing a fidelity-first competitor cannot bolt on afterwards.

**How it is kept from leaking into the disciplined parts:** the drill layer consumes the same physics core, the same procedure library and the same scoring engine as scenario mode. It gets no privileged path, no separate physics, and no exemption from the gates. The boldness is in the loop design, not in the plumbing.

---

## Definition of done

For the smallest useful version:

● The local loop is green and `simulate-pipeline.sh` passes including every grep gate.
● The propagator passes the Vallado golden vectors, and deterministic replay is proven by test.
● The App Store SonarQube gate passes: zero violations, coverage at or above 80 per cent, A on security, reliability and security review.
● The container honours the contract: `PORT` read, `0.0.0.0` bound, uid 10001, `/`, `/healthz` and `/readyz` returning 200 unauthenticated.
● Deployed to the App Store, healthy, with a tested rollback to the previous image tag.
● The procedure library holds all fifteen procedures as validated, versioned data; three are wired to scenarios and drills.
● A content author can edit a procedure's steps or thresholds, or add a new procedure, **without a code deployment**, and dependent scenarios and rubrics are flagged stale.
● An operator with **no prior knowledge** can go from first run to a correct unaided classification in under fifteen minutes, verified with a real person, not asserted.
● The debrief reproduces a scored run exactly and explains every point gained or lost by naming the rule and the evidence.
● The DPIA is signed before the first named-individual record is written.
● Redaction review has signed off every published procedure and scenario as clean.

---

## Foundations skill mapping

Which skill governs each part, so the build agent knows where to look rather than inventing standards.

| Part | Skill |
| --- | --- |
| Bootstrap, archetype decision, ordering | `getting-started` |
| Toolchain, runtime pin, verified environment | `environment-setup`, `toolchain-adapters` |
| Pinning, lockfile, CVE scan | `dependencies` |
| `createApp` factory, structure, surgical edits | `code-architecture` |
| SQLite store, boundary validation, seeding, anti-shrink merge | `data-layer` |
| Routes, health and readiness, rate limiting, background jobs | `api-and-integration` |
| SPA structure, offline-first, escaping untrusted values | `frontend-and-rendering` |
| Scenario clock state, sync, debounced writes | `state-management` |
| Tokens, palette, light and dark, component grammar | `design-system` |
| WCAG 2.2 AA, keyboard, live regions, reduced motion | `accessibility` |
| Identity adapter, secrets, config, CSP, container hardening | `security-hardening` |
| Audit rows, logging, health, rollback signal | `observability-and-audit` |
| Test strategy, coverage, parity and security-property tests | `testing-standards` |
| PR pipeline mirroring the local loop | `ci-cd` |
| Lean build context, version normalisation | `packaging` |
| Python container recipe, coverage report path | `deploy-recipes` |
| Upload gate, failure catalogue, pipeline simulation | `appstore-gate-compliance` |
| Templates, port rule, quality gate, env-var two-stage save | `app-store-deployment` |
| Pre-submit scoring | `app-store-readiness` |
| Ship runbook, rollback, human confirmation | `release-and-deploy` |
| Effort and token discipline | `resource-discipline` |
| Prompt patterns, review, debugging | `working-with-ai` |
| Unfamiliar terms | `glossary` |
| End-of-build lessons | `project-retrospective` |

**Deliberately excluded, with reasons** (justify-exclusion discipline):

● `llm-integration` and `ai-update-scan`: ENLIGHTENMENT has no LLM call and no outbound search. Adding one would import an egress dependency, a budget cap and a prompt-injection surface into an air-gapped trainer for no gain. If an adaptive scenario generator is ever wanted, revisit deliberately.
● `script-mode-engineering`: applies to the offline UDL characterisation pass (build step 4) and any authoring script used to bake scenario ground truth, per CONTEXT-001 Section 3. It does not apply to the container application, which is server archetype.

---

## Build plan

Thirteen steps, ordered so the risky things are proven before the expensive things are built. No implementation code until the go-ahead.

**Phase 0, prove the foundation.**
1. **Environment and skeleton.** Pin the runtime, scaffold the App Store container contract from the first commit (`PORT`, `0.0.0.0`, uid 10001, three health paths, two requirements files, `simulate-pipeline.sh` with the grep gates). Prove it builds and passes the simulated pipeline before there is anything to deploy.
2. **Physics core plus golden tests.** SGP4 propagation, frame and time conversions, Clohessy-Wiltshire relative motion. Vallado test vectors green, property tests green, named traps for the TEME-as-J2000 and angle-wrap bugs. Nothing else is built until this is right, because everything scores against it.
3. **Determinism harness.** Seeded PRNG, fixed timestep, event log, snapshot. Prove by test that the same seed yields an identical event log twice. This is the gate the debrief depends on.
4. **UDL characterisation pass, offline, Script mode.** A single-file stdlib-only retriever and analyser, per CONTEXT-001 Section 3, because any UDL retrieval task defaults to Script mode. Credentials from `~/.config/phase_offset/credentials.ini` via `configparser` with `interpolation=None`. Honours the LEARNED register: `Accept: */*` on history list, `text/plain` on count, trailing-Z microsecond `obTime` ranges, and time-slicing rather than offset pagination above the 10,000 `firstResult` cap. Emits the noise-model parameter file plus a `--self-test` JSON assertion manifest. **Runs on the networked workstation, never in the container.** Output is committed as versioned content; nothing else crosses.

**Phase 1, the smallest useful version.**
5. **Content schemas and loader.** Procedure, scenario template, rubric and expert-trace schemas. JSON Schema validation, hot reload, safe failure on malformed content. Seed all fifteen procedures as data.
6. **Scoring engine.** Config-driven decision tables, score decomposition recorded per run, no monolithic function. Explainability is the acceptance test.
7. **Drill loop.** Elo-rated cue items, produced answers with stated confidence, Brier scoring, FSRS scheduling. The creative risk, built early rather than late so it is proven not hoped.
8. **Debrief.** Replay from seed and event log with the expert trace overlaid, self-explanation prompt before reveal.
9. **SPA and plot surfaces.** Dashboard, drill, debrief. GEO belt and Hill-frame plots first; light curve, Gabbard, range-versus-time next. Accessibility floors met as written, not retrofitted.

**Phase 2, complete the loop.**
10. **Identity behind the adapter**, sessions, and the audit trail for supervisor access.
11. **Scenario mode** on the running clock over WebSocket, for the three confirmed procedures.
12. **Scorer validation** against expert human rating on a held-out set, before any operator is scored. A gate, not a task.

**Phase 3, ship.**
13. **Readiness, deploy, rollback.** Run the readiness check, upload, verify healthy, prove the rollback, and only then put it in front of an operator.

**The one thing that would change this order:** if the DPIA slips, steps 9 and 11 proceed against synthetic accounts and no named-individual record is written until it is signed.

---

---

## Open questions (TBC, re-verify)

**Platform, blocking first upload:**
1. Is the slug `enlightenment` unique in the App Store, and what category and visibility? (Owner: Ash) **Still open, blocks upload only.**
2. ~~Storage add-on availability.~~ **Answered 16 August 2026: available and writable by uid 10001. SQLite confirmed.**
3. ~~Shell-supplied identity.~~ **De-blocked by the `IdentityProvider` adapter. Still worth confirming, but no longer gates the build.**
4. Does saving an environment variable restart the running pod, or can an old pod keep serving old values? (Owner: Ash) **Still open, affects deploy procedure only.**

**Content and authority:**
5. ~~Procedure marking and redaction reviewer.~~ **Answered 16 August 2026: source procedures are Not classified; Ash is the redaction reviewer. Redaction gate retained regardless of marking.**
6. ~~Expert-trace author.~~ **Answered 16 August 2026: Ash. Mitigations for the single-point dependency recorded under Constraints.**
7. ~~Competency framework.~~ **Answered 16 August 2026: none exists; six axes invented and recorded under Outcomes.**
8. ~~Which procedures for v1?~~ **Answered 16 August 2026: Manoeuvre, RPO, and Separation versus Breakup. Confirmed.**

**Policy and legal:**
9. DPIA sign-off, lawful basis, staff consultation route, and the retention period for detailed run artefacts. (Owner: Ash, as DPL) **Open, and blocks the first named-individual record, not the build.**
10. ~~Supervisor visibility.~~ **Answered 16 August 2026: supervisors see individual results. Transparency, purpose-limitation and scope controls recorded under Security and classification.**

**Scope and sizing:**
11. Deadline. (Owner: Ash) **Open.** Concurrency answered: 10.
12. ~~Product name.~~ **Answered 16 August 2026: ENLIGHTENMENT.**

**Design:**
13. **The debrief highlight treatment.** Red, green and blue 2 are committed to operational semantics and copper-amber is excluded from product UI by house rule, leaving nothing free to say "look here" on the data. Recommendation: an ink-bright outline plus brief pulse, reserved exclusively for debrief signalling. Alternative: a narrow house-rule exception for copper-amber in this one pedagogical use. (Owner: Ash) **Open, and it shapes the debrief, which is the highest-value feature in the product.**

14. **Noise-model review cadence.** The characterisation output is versioned content that goes stale as sensor mixes change. Recommendation: reviewed on the same cycle as the procedure library, with a re-run triggered by any known change to the UDL provider set. (Owner: Ash) **Open, does not block the build.**

**Remaining truly open, in priority order:** debrief highlight treatment (13), slug uniqueness (1), environment-variable restart behaviour (4), DPIA and retention (9), deadline (11), noise-model review cadence (14).
