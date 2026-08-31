# ENLIGHTENMENT: Claude Code build guidance

| | |
| --- | --- |
| **Document** | ENL-BUILD-01 |
| **Date** | 29 August 2026 |
| **For** | Ash Higgins |
| **Purpose** | How to take the flight plan, the content package and the governance pack into a Claude Code build stream |

---

## 1. The core insight about how to run this build

**You are not asking Claude Code to build a training application. You are asking it to build a content engine, and the training application is what the content does when loaded.**

That distinction should shape every session. The content package is 113 drills, 102 cues, 12 scenarios, 11 procedures and a synthesis ladder, all validated JSON. **None of that should become code.** If you find Claude Code writing a hardcoded scenario, a switch statement over event types, or a scoring rule expressed in Python, something has gone wrong and it will cost you later when a procedure changes.

**But do not over-read that rule.** It is not an instruction to avoid writing classes. The engine needs real, well-designed, hand-written code: product generators, the physics core, the scoring evaluator, the scheduler. Section 1.1 draws the line precisely, and getting it wrong in the cautious direction produces a codebase that tries to express drawing logic in JSON, which is worse than the failure it was avoiding.

The corollary is that the build is smaller than it looks. Strip out the content and what remains is: a container that meets the App Store contract, a physics core, a deterministic scenario runner, a scoring engine that evaluates declarative rules, a spaced-repetition scheduler, a set of plot renderers, and a single-page interface. That is a substantial but tractable application, and every part of it is described somewhere in the material you already have.

### 1.1 The line between code and content

**The test is not "is it complex" or "is it domain knowledge". It is: does the number of these change when a content author does their job?**

| Thing | Form | Count | Changes when |
| --- | --- | --- | --- |
| Product generator | **Hand-written class** | ~10 | An engineer works |
| Physics core | **Hand-written module** | 1 | An engineer works |
| Scoring evaluator | **Hand-written class** | 1 | An engineer works |
| Spacing scheduler | **Hand-written class** | 1 | An engineer works |
| Scenario runner | **Hand-written class** | 1 | An engineer works |
| Product definition and layout | JSON | 10 | A provider changes their product |
| Procedure | JSON | 11 | A procedure is revised |
| Cue | JSON | 102 | A content author works |
| Drill | JSON | 113 | A content author works |
| Scenario template | JSON | 12 | A content author works |
| Rubric rule | JSON | 45+ | A content author works |
| Expert trace | JSON | 5+ | A subject matter expert works |

**There are exactly twelve generators to build.** Ten product renderers and two composition modes, declared canonically in the `_generator_contract` block at the top of `content/drills.json`. **Read that block before writing any renderer.**

Earlier drill authoring used 58 ad-hoc generator names. They have been consolidated and the originals are preserved as `_legacy_generator` in each drill's params for traceability only. **Do not implement them.** The content validator now fails the build if any drill references a generator outside the canonical twelve.

| Generator | Product | Type |
| --- | --- | --- |
| `waterfall` | PRD-WATERFALL | Renderer |
| `residual` | PRD-RESIDUAL | Renderer |
| `dc_table` | PRD-DC-TABLE | Renderer |
| `light_curve` | PRD-PHOTOMETRY | Renderer |
| `tric` | PRD-TRIC | Renderer |
| `neighbourhood` | PRD-NEIGHBORHOOD | Renderer |
| `coco` | PRD-COCO | Renderer |
| `pass_schedule` | PRD-PASS-SCHEDULE | Renderer |
| `ephemeris` | PRD-EPHEMERIS | Renderer |
| `gabbard` | PRD-GABBARD | Renderer |
| `composite` | Two or more of the above | Composition mode |
| `probe` | Whichever the params name | Composition mode |

The two composition modes orchestrate renderers and render nothing themselves. `composite` presents multiple products for cross-product reconciliation, with `params.products` listing product IDs or `"all"` for the full board, and `params.tier` setting the synthesis tier. `probe` presents a state and asks a single anatomy or no-action question.

**Products are classes and this is deliberate.** Ten product types, the number moves roughly never, and each needs genuine engineering. A waterfall generator producing twenty thousand scattered observations with realistic collection gaps and drift streaks emerging from populated regions is not derivable from a JSON description of required fields. Attempting to generate it from the definition means putting drawing logic into JSON, which is writing Python in JSON and loses both.

**Do not build a code generator for the product classes.** Ten hand-written classes is not a maintenance problem. A generator maintaining ten classes it does not understand is.

**What the JSON should drive instead is the contract**, by two cheap mechanisms:

● **A registry.** Each generator registers against its product ID. The content validator then checks that every product referenced by a drill or scenario has a registered generator, so content referencing a product nobody built fails at load rather than at runtime. This extends the existing cross-reference validation one step into the code.
● **Contract tests that read the layout file.** `product-layouts.json` already carries a `generator_contract` block: waterfall must produce observation-level scatter at realistic density; light curve must plot against solar equatorial phase angle with an inverted magnitude axis; relative motion panels must use independent per-panel scales. Write tests that read those requirements and assert each renderer honours them. When a layout is corrected, and one already has been, the test fails and names the renderer to fix.

**The generator is code, the contract is data, the tests are the join.** That gives the discipline of generation, with the JSON staying authoritative and drift caught automatically, without the fragility of generated classes.

---

## 2. What to give Claude Code, and in what order

### 2.1 The persistent context

Put these in the repository before the first session, because Claude Code will read them repeatedly:

| File | Purpose |
| --- | --- |
| `CLAUDE.md` | Standing instructions. Stack, standards, container contract, what must never happen |
| `docs/flight-plan.md` | The ENLIGHTENMENT flight plan, thirteen areas |
| `docs/build-plan.md` | The thirteen-step build plan from the flight plan |
| `content/` | The entire content package, unmodified |
| `spec/` | **Three build specifications. Read before the surfaces they describe** |
| `docs-TIMING-STANDARDS.md` | Authoritative timing standard. Do not infer it |

**`CLAUDE.md` is the highest-leverage file in the repository.** Everything else is read when relevant; this is read every session. Keep it short enough that it is actually read: the container contract, the four quality gates, the surgical-edit rule, the never-do list, and a single line pointing at the build plan.

### 2.2 The kick-off prompt

Unchanged from the flight plan, and still right:

```
Read the standards in CLAUDE.md and the skills, then read the flight plan below.
Before writing any code, produce a step-by-step build plan: name the archetype,
and for each part name the skill it satisfies. Call out risks and anything in the
plan that is unclear or missing. Wait for my go-ahead before writing code.
```

Let it produce its own plan even though you have one. Where its plan and yours diverge, that divergence is the most useful information you will get all session, because it shows what the material fails to communicate.

---

### 2.3 The three build specifications

These close what was previously design intent. **Read the relevant one before building the surface it describes**, because they contain decisions rather than suggestions.

| Spec | Covers | Read before |
| --- | --- | --- |
| `spec/ENL-SPEC-01-data-model.md` | Full SQLite DDL, retention classes, what deliberately has no table | Step 5, content loader and persistence |
| `spec/ENL-SPEC-02-api-contract.md` | Every endpoint, the WebSocket protocol, reconnect, rate limits, performance budget | Step 5 onward, and before any client work |
| `spec/ENL-SPEC-03-interface.md` | Shell, tokens, client state model, all seven surfaces, onboarding, accessibility, build order | Step 9 |

Three decisions in those specs were previously open and are now taken. The debrief highlight is ink-bright outline plus a single pulse, reserved for debrief signalling. The board reveals progressively across the synthesis tiers and the interface says why. The dual timer is a build requirement rather than an option.

**One rule that spans all three.** Any endpoint that returns a drill answer, an expert trace, or an accept value before the operator has submitted breaks the training. The production-format rule is architectural, not cosmetic, and it is easy to defeat by building a convenient combined endpoint.

---

## 3. Session structure

**The single most important discipline: one session, one step of the build plan.** Not two. The failure mode with a package this size is a session that tries to do steps 4 through 8, produces something plausible for all of them, and is wrong in a way that only surfaces at step 11.

### 3.1 The shape of a good session

1. **Orient.** Point at the build step and the content files it touches.
2. **Plan before code.** Have it state what it will build and against which content, and stop.
3. **Check the plan.** This is where you catch a misread of the schema, and it costs a minute.
4. **Build.**
5. **Prove.** Run the gate. Not "does it work" but "show me it passes."
6. **Commit with the step named** in the message.

### 3.2 What to do at the start of every session after the first

Have it run the content validator before anything else:

```
python3 tools/validate_content.py --content-dir content --self-test
```

**Seventeen assertions, zero errors expected.** Two of them exist specifically to protect this handover: `generators_canonical` fails if any drill references a generator outside the twelve, and `response_formats_declared` fails if a drill uses a response format the schema does not declare. Both caught real defects during the final review, as did `detection_patterns_compile`. If content has drifted, you find out in ten seconds rather than at the end of a session. It is also the fastest way to re-orient a fresh session in the material.

---

## 4. Build order, and where the risk actually sits

The thirteen-step plan holds. What follows is where I would spend the supervision, because the steps are not equally risky.

### Phase 0: prove the foundation

**Step 1, container contract.** Low risk, high consequence. Scaffold the App Store contract from the first commit: `PORT`, `0.0.0.0`, uid 10001, three health paths, two requirements files, `simulate-pipeline.sh` with the grep gates. Prove the simulated pipeline passes before there is anything to deploy. Getting this at the end is how upload cycles get burned.

**Step 2, physics core and golden tests. Supervise this one closely.** The Vallado test vectors either pass or they do not, so correctness is verifiable, but this is where an LLM will most confidently produce plausible wrong astrodynamics. Insist on the golden tests before any other physics is written. Named traps for TEME-as-J2000 and the angle-wrap seam.

**Step 3, determinism harness.** Low risk, high consequence. Same seed, identical event log, twice. Everything downstream depends on it and it is trivially provable.

**Step 4, UDL characterisation pass.** Script mode, runs on your workstation, never in the container. Independent of the rest and can happen in parallel.

### Phase 1: the smallest useful version

**Step 5, content schemas and loader.** Straightforward, and the point where you insist on the three loader behaviours: refuse to serve a scored scenario with placeholder thresholds, reject a seed failing its solvability check, record the content version hash on every run. Those are content decisions, not engineering ones, and they will be omitted unless stated.

**Step 6, scoring engine. Highest architectural risk in the build.** The temptation is a function per rule. The requirement is a declarative evaluator over the rubric JSON, where adding a rule is adding data. Ask directly: *if I add a rubric rule tomorrow, what code changes?* If the answer is any, stop and redo it.

**Step 7, drill loop.** The creative risk, built early on purpose. Elo, FSRS, produced answers, Brier scoring.

**Step 8, debrief.** Replay from seed and event log with the expert trace overlaid.

**Step 9, SPA and plot surfaces.** The largest single chunk. `spec/ENL-SPEC-03-interface.md` specifies the shell, tokens, state model and all seven surfaces with a build order. Follow that order: debrief before dashboard is deliberate, because the debrief determines what the scenario runner must record and discovering that afterwards means changing both.

### Phase 2 and 3

**Step 10, identity behind the adapter, and audit.** Blocked on the multinational visibility decision. Build the adapter, defer the visibility model.

**Step 11, scenario mode** over WebSocket.

**Step 12, scorer validation.** A gate, not a task.

**Step 13, readiness, deploy, rollback.**

---

## 5. The interface, which is the part the material describes least

Everything else has a specification. The interface has design intent scattered across the flight plan, the product layouts and the synthesis ladder, and it is where Claude Code has the most freedom and therefore the most opportunity to drift.

### 5.1 Give it the product layouts first

`content/product-layouts.json` describes nine real screens: axes, columns, controls, reading order, and the generator contract. **The plot renderers must match those layouts, not an idealised version.** Specifically:

● Waterfall is dense observation scatter, tens of thousands of points, not clean traces
● Residual y-scale is tight, a few hundredths, and departures are subtle
● Light curve is magnitude against solar equatorial phase angle with an **inverted** magnitude axis
● Relative motion panels use **independent per-panel scales**, differing by an order of magnitude
● Neighbourhood carries delta-v, score and days-to-crossing columns, and the filter toggles must be visible in their real state

An idealised renderer produces a trainer that is easier than the job, which is the worst kind of failure because nobody notices it.

### 5.2 The surfaces to build, in order

| Surface | Why this order |
| --- | --- |
| Drill | Smallest complete loop. Proves scoring, scheduling and reveal end to end |
| Plot renderers | Everything else consumes them |
| Debrief | The highest-value feature, and it constrains what the scenario runner must record |
| Dashboard | Cannot be designed until there is something to show |
| Scenario | Largest surface, needs the clock and the transport |
| Argument entry | Tier 3 and above. Distinct enough to be its own piece |
| Authoring | Trace capture mode. Can follow |

### 5.2a Timing: two clocks, not one

**The published standard is two-legged and the interface must render both.**

> 60 minutes from initial indications, or 30 minutes from the last provider product dropped, **whichever is earlier**.

Geosynchronous direct ascent is the exception: 30 minutes flat for the initial warning report, 90 for the tracked object report. Daily crew operations tasks have **no timing standard at all** and latency must not be scored on them.

Implementation requirements:

● Track both clocks concurrently and display both
● Identify and highlight which leg currently governs
● Recompute when a further provider product arrives, because the governing leg can change mid-event
● Scoring evaluates against the governing leg, not against a fixed number
● Never inline these values. They resolve from `report.notso_standard` and the `daasat_geo` block in the local thresholds file

**This is counterintuitive and is why it is drilled.** Fast provider delivery tightens the crew's window rather than relaxing it. An operator watching only the 60 minute leg misses the standard whenever providers are quick, which is the good case.

### 5.2b Report scoring is now implementable

`content/report-detection-patterns.json` carries twenty-one checks and six conditional checks, each with a compiled-and-verified regular expression and **a measured match rate against 3,123 real reports**.

Implement them and verify against the stated rates. A deviation beyond tolerance means the pattern was transcribed wrongly; **do not adjust the expected rate to fit**.

One warning is in that file and deserves repeating. An earlier delta-v pattern placed a negative lookahead after a zero-width match, so it fired on every report and produced a completely false statistic that reached operator-facing content before it was caught. **A pattern that matches everything looks like a working detector until someone computes a percentage from it.** Assert both a floor and a ceiling.

### 5.3 Interface decisions, now closed

All three are now decided in `spec/ENL-SPEC-03-interface.md` sections 5.3 and 7. Summarised:

**Debrief highlight: ink-bright outline plus one brief pulse**, reserved exclusively for debrief signalling. Not copper-amber, because it sits close enough to alert red to read as a warning on a dense plot, and the highlight must say *look here* rather than *danger*. Reversal cost is one token.

**The board: progressive reveal across the tiers**, two panels at tier 1 through to all ten at tier 4, with tier 3 the point where opening a product becomes a choice with a cost. The interface states that this is scaffolding rather than withholding.

**The dual timer.** Specified in 5.2a. Not an open decision, a build requirement.

### 5.4 Accessibility is a code standard here, not polish

Blue 1 at 2.45:1 fails even the graphic floor. Alert red lightened to `#E06C69`. Status never by colour alone. It is a grep gate in the build, not a review item.

---

## 6. The specific things to insist on

Ordered by how expensive they are to retrofit.

| # | Insist | Why |
| --- | --- | --- |
| 1 | **Content is never code, but the engine is.** No hardcoded scenario, no switch over event types, no scoring rule in Python. Product generators, physics, evaluator and scheduler are hand-written classes | The whole architecture rests on the line being in the right place, not on avoiding code |
| 2 | **Scoring is a declarative evaluator.** Adding a rule adds data only | Retrofitting this is a rewrite |
| 3 | **Deterministic replay proven by test** before the debrief is built | The debrief depends on it |
| 4 | **Golden physics tests first** | Everything scores against the physics |
| 5 | **Content version hash on every run record** | Otherwise old results become uninterpretable |
| 6 | **Audit row on every supervisor view of an individual** | Cheap now, expensive later, and it is the control that makes the visibility decision defensible |
| 7 | **Thresholds resolved from a local file, never inlined** | The redaction discipline lives here |
| 8 | **Plot renderers match the real layouts**, enforced by contract tests reading `product-layouts.json` | An idealised trainer is easier than the job |
| 8a | **A generator registry, validated against content references** | Content pointing at an unbuilt product should fail at load, not at runtime |
| 9 | **Both legs of the timing standard implemented**, with the governing leg identified and recomputed on each product arrival | Single-leg scoring is wrong scoring, and the governing leg changes mid-event |
| 10 | **Every score decomposes to a named rule and its evidence** | A scorer that cannot be challenged will not be trusted |

---

## 7. What will go wrong

Predictions, so you recognise them early.

**It will try to make scenarios into code.** The JSON is complex enough that generating a Python class per scenario will look like good engineering. It is the opposite. Watch for it around step 5.

**Or it will over-correct and try to make product generators into data.** Having absorbed that content is not code, it may attempt to express drawing logic in JSON, or propose generating the ten product classes from their definitions. Both are worse than the failure being avoided. Point at section 1.1: the test is whether the count changes when a content author works, and for products it does not.

**It will idealise the plots.** A clean waterfall is easier to write and looks better in a screenshot. Point at the layout file again.

**It will build the scoring engine as a large function.** Cognitive complexity capped at 15 will force refactoring, but into small functions rather than into a declarative evaluator. Those are different things and only one is right.

**It will drift on the accessibility rules** because they are easy to satisfy approximately. The grep gates catch it.

**It will want to use an LLM for report scoring.** The architecture says expert comparison with deterministic checks. Model-assisted scoring is a later swap and it breaks the air gap. Say no.

**Sessions will get long and lose the thread.** One step per session, and re-run the validator at the start of each.

---

## 8. Where the governance pack meets the build

Only two dependencies run from the governance into the code, and they are deliberately narrow.

**Standards are configuration.** Timing bands, accuracy floors, calibration ceilings, concurrent ceilings and ageing callouts all live in the local thresholds file. If a standard changes, no code changes. Check this holds: if Claude Code inlines the 60/30 timing standard anywhere, that is the same error as inlining a scenario.

**Training Objectives are the scoring targets.** The rubric rules trace to TOs in ENL-GOV-03. When a rule is added, it should be traceable to an objective, and a rule that traces to nothing is a rule that measures something nobody asked for.

Everything else in the governance pack describes the requirement and the assurance around it, and should not appear in the codebase at all.

---

## 9. Suggested first three sessions

**Session 1.** Kick-off prompt. Let it produce its own build plan. Compare against yours, resolve divergences, no code.

**Session 2.** Step 1 only. Container contract scaffolded, `simulate-pipeline.sh` passing, nothing else. You should be able to build and run an empty application that satisfies every App Store requirement.

**Session 3.** Step 2. Physics core with the Vallado golden tests. Insist the tests come first.

If those three go cleanly, the pattern is established and the rest is repetition. If session 2 struggles with the container contract, fix that before going further, because every deploy afterwards inherits it.

---

## 10. One thing to hold on to

The content package is the asset. It took a corpus of 3,124 released reports, nine exercise sources, eleven procedures, five product screens and two years of weekly reporting to build, and it is validated, versioned and portable.

The application is the delivery mechanism. If the build goes badly you rebuild the application. If the content is compromised by being absorbed into code, you rebuild everything.

Protect the separation and the rest is recoverable.

---

*Ends.*
