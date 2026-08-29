# Design brief: the ENLIGHTENMENT operator interface

For Claude Design, or any designer picking up this interface. Everything below is fact about a
running application, not aspiration: the tokens are the shipped tokens, the payloads are real
responses, and the contrast figures are measured.

**How to use it.** Paste "The kick-off block" at the bottom into Claude Design, then attach or paste
whichever sections it asks for. The sections are ordered so the first four are the ones it cannot
work without.

---

## 0. Read this before designing anything

**Claude Design's output is a visual direction, not shippable code for this project, and the reason
is a hard constraint rather than a preference.** A published artifact may load scripts from a CDN
allowlist and fonts from Google Fonts. ENLIGHTENMENT may do neither: the flight plan's air-gap
posture is "no CDN, no map tiles, no external calls at runtime", the interface response sets
`script-src 'self'`, and a test fails the build if any shipped asset contains `http://`, `https://`
or a CDN hostname.

So the loop is: Claude Design produces artboards, a human approves the direction, and the direction
is re-implemented in `src/enlightenment/ui/` under the constraints in section 6. Anything an artboard
does that needs a webfont, a charting library or an external request has to survive being rebuilt
without them, or it is not a design this product can adopt.

Two practical consequences for the artboards:

● **Type is a vendored webfont.** Owner decision, 29 August, overriding the system-stack rule this
  section originally carried. The constraint was always "no external request", never "no webfont",
  and the interface already serves `font-src 'self'` - which permits a self-hosted face and forbids
  a content delivery network. So PHOSPHOR ships Saira, Saira Condensed and Azeret Mono as vendored
  woff2, latin subset, six files and 131 kB in total, under the SIL Open Font Licence 1.1 with the
  licence text carried beside them, digests recorded. The artboards load `fonts/fonts.css`, not
  `fonts.googleapis.com`, and `design/check-artboards.mjs` asserts that a loaded artboard fetches
  nothing outside its own directory.
  **The product side is not done.** `src/enlightenment/ui/` still declares no webfont at all - its
  stack is `"Segoe UI", system-ui, -apple-system, sans-serif` and no font file ships - so today the
  mockups render in Saira and the product renders in Segoe UI. That is precisely the defect this
  decision exists to close, and it closes when PHOSPHOR is built into the shipped interface: the
  same six files, served from `/ui/fonts/`, added to the `_UI_FILES` allowlist, with the system
  stack behind them as the fallback because the owner's workstation is Windows. Until then, read
  the artboards as a specification of intent, not as a rendering of what is deployed.
● **Charts are drawn from scratch on a canvas.** No chart library will be available. Design chart
  treatments that a few hundred lines of hand-written canvas code can produce.

---

## 1. The product, in one paragraph

ENLIGHTENMENT is a standalone orbital warfare simulation trainer that turns Joint Commercial
Operations (JCO) Protect and Defend procedures into a game operators want to play, so that when a
real event lands they already know what to do without looking it up. **Single job: build instant,
correct recall of the action required for each event type in the procedure library.** It is a memory
system that happens to render orbits, not a simulator that happens to score.

● **Primary user:** military space domain analysts and Protect and Defend operators. Mixed
  experience, **zero prior knowledge is the floor** - the interface must onboard someone who does not
  know what an element set is, and still stretch someone who has read light curves for years.
● **Context:** shift work, time pressure, shared operations rooms, headphones off, two monitors.
  Motivated by competence and mission readiness. **Highly allergic to anything that feels childish or
  like surveillance.**
● **The one thing the interface must make effortless:** going from "an event is happening" to "I know
  which procedure this is and what step one is" in seconds, repeatedly, without reading a manual.
● **Acceptance line, in the owner's words:** *"It looks like a tool I would leave open on the second
  monitor during a shift, and the drill loop is tight enough that I do one more without deciding
  to."*
● **Tone rule:** errors are learning events, never failures. No punitive mechanics anywhere.
  Operational language throughout - missions and scenarios, never levels-and-loot.
● **Feel reference:** dark mission-control, continuous with the PSIRENS visual language, paced like
  chess.com Puzzle Rush.

---

## 2. The design tokens, as shipped

Copy these verbatim. They are the live values in `src/enlightenment/ui/index.html`.

```css
--navy:       #162646;  /* page ground */
--navy-deep:  #101B33;  /* bars, insets, chart grounds */
--panel:      #1B2C51;  /* card surface */
--structure:  #385FAF;  /* Blue 1: FILL AND BORDER ONLY - see rule 1 */
--label:      #739BCF;  /* Blue 2: labels, axis text, structural text */
--ink:        #E8EDF5;  /* body text */
--ink-dim:    #9FB0CC;  /* secondary text, hints */
--nominal:    #27AE60;  /* green: nominal, correct */
--alert:      #E06C69;  /* red, TEXT-SAFE - see rule 2 */
--alert-fill: #C0504D;  /* red, LARGE FILLS ONLY - see rule 2 */
```

**Measured contrast on `#162646`, computed to WCAG 2.2:**

| Colour | Ratio | Verdict |
|---|---|---|
| Ink `#E8EDF5` | 12.76:1 | Body text, pass |
| Ink dim `#9FB0CC` | 6.83:1 | Body text, pass |
| Blue 2 `#739BCF` | 5.23:1 | Body text, pass |
| Green `#27AE60` | 5.22:1 | Body text, pass |
| Alert `#E06C69` | 4.66:1 | Body text, pass |
| Red `#C0504D` | 3.21:1 | **Body text, FAIL** |
| Blue 1 `#385FAF` | 2.45:1 | **Fails even the 3:1 graphic floor** |

### The five hard rules

These are code standards, enforced by tests that read the shipped markup and the canvas palette. A
design that breaks one cannot be adopted.

1. **Blue 1 `#385FAF` never carries text and never conveys status.** At 2.45:1 it fails the graphic
   floor as well as the text floor. Structural fill and border colour only, behind lighter marks.
   This is the single most likely accessibility defect in a PSIRENS-derived palette.
2. **Alert red is `#E06C69` wherever it carries text or a small mark.** `#C0504D` is retained only
   for large fills where 3:1 suffices. Alert text that fails contrast is the worst possible place to
   fail.
3. **Copper-amber `#C67C00` is excluded from product UI** by house rule. See section 8, question A -
   this is the live open question.
4. **Status is never colour alone.** Red and green as the alert-and-nominal pair is the classic
   deuteranopia trap. Every status carries a shape glyph and a text label as well as a colour: a
   labelled triangle, not a red dot. Currently `▲ correct` and `▼ missed`.
5. **Typography floor is 18px** for body text, per house style. It matters more here than in a
   monitoring tool because operators read procedure text under time pressure rather than glancing at
   glyphs.

### Density varies by mode, palette never does

Cognitive load theory is unambiguous that a novice on a dense display spends attention on the
display rather than the content, and the expertise-reversal effect says the scaffolds that fix that
for a novice actively harm an expert. So:

● **The drill surface strips to almost nothing:** one plot, two inputs, one confidence control.
● **The scenario surface is full operational density.**
● **Same colours, same type, same component grammar throughout,** so it still reads as one tool and
  the transfer to the real console is preserved.

---

## 3. The screens

### Built and running (redesign welcome)

| Screen | Route | Its single job |
|---|---|---|
| **Drill** | `/ui#drill` | Present a cue. Take a produced classification, a produced first action, and a confidence. Nothing else on screen. |
| **Reveal** | same, after commit | Say what was right, name the look-alike if one was picked, show the expert's cue, and decompose the score by rule and evidence. **The highest-value screen in the product.** |
| **Dashboard** | `/ui#dashboard` | Where the operator stands, what has decayed, what is due, and why. |
| **Library** | `/ui#library` | The procedure in full, unscored and never gated. |

### Not built. Designed here first, then implemented

| Screen | Its single job | Notes |
|---|---|---|
| **First run, zero knowledge** | A 90-second guided worked example: here is a plot, here is the cue, here is what an expert calls it. **Ends with the operator making one correct call themselves.** | The definition of done requires an operator with no prior knowledge to reach a correct unaided classification in under fifteen minutes. This screen carries most of that. |
| **Scenario run** | A full event on a running clock: read the data, classify, identify the governing procedure, execute decision points, produce report content. Threat type withheld by default. | Full operational density. Multiple plot surfaces at once. A visible authoritative clock. |
| **Scenario debrief** | Deterministic replay with the expert's read overlaid: what the expert saw and when, what the operator saw and when, which rule fired and why, what it cost. A self-explanation prompt **before** the reveal. | The hardest screen in the product. Two timelines, one comparison. |
| **Sandbox / free analysis** | Load or fork a scenario, alter parameters, watch what happens. **Never scored, never reported.** | Must LOOK unscored. Operators need somewhere to be wrong in private or they will not explore. |
| **Supervisor view** | Current competence, coverage and decay by axis, for a named operator. | See section 7. What it must NOT show is as designed as what it shows. |
| **Settings** | Reduced motion, audio off by default, the privacy notice in plain words. | |
| **Authoring** | Content author's view of a procedure's validation state, and what went stale. | Version-controlled files first; no in-app WYSIWYG editor in v1. |

### The plot surfaces

**Read `docs/PLOT-REALISM.md` before designing a plot.** Ash supplied five screenshots of live KBR
Space Domain Awareness tooling on 29 August, and judged against them these three surfaces are not
realistic in a structural way: real products are dense gappy multi-source scatter that encode a
second variable in colour, and ours are clean evenly sampled single-series polylines that encode
nothing. That document lists the six idioms every real product uses, what each screenshot gives us,
and the nine changes ranked by training value. A design that ignores it will produce a mockup an
operator recognises as a toy.

Three exist. Each is a canvas drawn from scratch, and each carries an authored text equivalent plus
a "read the data as a table" control.

● **`longitude-drift`** - sub-satellite longitude against time. Reads as a saw (station keeping), a
  break-out to a new held rate (repositioning), or a near-vertical step (a fit artefact).
● **`hill-relative`** - relative position in the along-track and radial plane. A closed repeating
  loop (controlled proximity operations) or an open pass (an uncontrolled drift-by). **The shape
  comes out of the Clohessy-Wiltshire solution, not out of a drawing.**
● **`range-time`** - range from a parent against time, one series per associated object. A couple of
  low-energy pieces one way (deliberate separation) or many pieces both ways with a widening spread
  (fragmentation).

Named in the flight plan and not yet built: light curve, Gabbard diagram, event timeline.

---

## 4. Real data, for every artboard

Build with these. No lorem, no invented figures.

**`GET /api/v1/drill/next`** - carries no answer key, by construction.

```json
{
  "instance_id": "drill-bounded-rpo:0",
  "item_id": "drill-bounded-rpo",
  "item_version": "v1",
  "content_hash": "…",
  "procedure_id": "rpo-response",
  "procedure_title": "Rendezvous and proximity operations response",
  "axis": "event-classification",
  "title": "A relative track that closes",
  "prompt": "Two objects, relative motion in the along-track and radial plane. Name the event, and the first action the governing procedure requires.",
  "difficulty": 1150,
  "operator_rating": 1190,
  "expected_success": 0.557,
  "plot": {
    "kind": "hill-relative",
    "x_label": "Along-track offset, kilometres",
    "y_label": "Radial offset, kilometres",
    "series": [{ "label": "Relative position", "x": [96 floats], "y": [96 floats] }],
    "description": "Relative position of a secondary object about a primary, in the along-track and radial plane. The track is a closed loop that repeats each revolution, staying within a few kilometres and returning to the same place."
  }
}
```

**`POST /api/v1/drill/answer`** - request, then the reveal. This is a real response to a
confidently wrong answer on the hardest separation item.

```json
// request
{ "item_id": "drill-early-ambiguity", "classification": "fragmentation",
  "first_action": "count the associated objects", "confidence": 4 }

// response
{
  "correct": false, "action_correct": true, "confused_with": "fragmentation",
  "points": 43.75, "brier": 0.5625,
  "calibration": "confident and wrong, which is the costliest combination on a real watch",
  "rating_before": 1214, "rating_after": 1207, "rating_delta": -7,
  "next_due_in_days": 1,
  "accepted_classifications": ["indeterminate", "insufficient data", "cannot determine",
                               "unknown", "not enough data", "inconclusive", "undetermined"],
  "accepted_first_actions": ["count the associated objects", "characterise how the count is growing",
                             "count the associated objects and characterise the growth",
                             "wait for the next revisit"],
  "expert_cue": "Opposite directions is weak evidence for fragmentation and two pieces is weak evidence for separation. In the first hour the count has not had time to stop growing, so the honest answer is indeterminate.",
  "procedure_id": "separation-versus-breakup",
  "procedure_title": "Separation versus breakup discrimination",
  "first_step": "Count the associated objects and characterise how the count is growing over time.",
  "lines": [
    { "rule": "event-named", "axis": "event-classification", "awarded": 0.0, "available": 45.0,
      "fired": false,
      "evidence": "answer matched 'fragmentation', which is the look-alike this item discriminates against" },
    { "rule": "first-action-named", "axis": "procedure-recall", "awarded": 35.0, "available": 35.0,
      "fired": true, "evidence": "first action matched 'count the associated objects'" },
    { "rule": "confidence-calibrated", "axis": "uncertainty-calibration", "awarded": 8.75,
      "available": 20.0, "fired": true,
      "evidence": "stated confidence 75%, outcome incorrect: confident and wrong, which is the costliest combination on a real watch" },
    { "rule": "expert-cue", "axis": "cue-detection", "awarded": 0.0, "available": 0.0,
      "fired": false, "evidence": "Opposite directions is weak evidence for fragmentation…" }
  ]
}
```

**`GET /api/v1/dashboard`**

```json
{
  "operator_id": "synthetic-operator", "rating": 1214, "runs_total": 7,
  "items_total": 12, "due_now": ["drill-bounded-rpo", "…"],
  "axes": [
    { "axis": "cue-detection", "attempts": 0, "accuracy": null, "interval": null, "mean_brier": null },
    { "axis": "event-classification", "attempts": 7, "accuracy": 0.714,
      "interval": [0.359, 0.975], "mean_brier": 0.0 }
  ],
  "coverage": [
    { "procedure_id": "manoeuvre-detection", "items": 4, "attempted": 3, "demonstrated": 3 }
  ],
  "recent": [
    { "item_id": "drill-drift-by", "answered_at": "2026-08-27T22:49:11+00:00",
      "correct": false, "points": 37.7, "confidence": 5, "rating_after": 1214 }
  ]
}
```

The six axes, in order, always: `cue-detection`, `event-classification`, `procedure-recall`,
`physical-reasoning`, `uncertainty-calibration`, `reporting`.

**`GET /api/v1/library/{procedure_id}`** returns `id`, `version`, `title`, `status`, `authored_by`,
`authored_on`, `change_reason`, `purpose`, `entry_conditions[]`, `roles[]`,
`steps[{ordinal, action, responsible_role, note, warning}]`,
`threshold_criteria[{name, condition}]`, `reporting_requirements[]`,
`transition_rules[{when, to_procedure_id}]`, `closure_criteria[]`.

**`GET /api/v1/content`** returns `ok`, `version`, `counts`, `errors[]`, `procedures[]`,
`confidence_steps`, `operator_id`, `identity`, `content_provenance`.

**The confidence scale is five fixed steps**, and the percentages are the probabilities a proper
scoring rule is applied to: `1: 15%`, `2: 35%`, `3: 55%`, `4: 75%`, `5: 93%`. Current labels:
Guessing, Leaning, Fairly sure, Confident, Certain. **No step asserts certainty** - the top is 93%,
because an operator who is certain is not certain, and a rule that can return an infinite penalty
stops being readable.

---

## 5. Interaction, and what the design must not break

● **The answer is never on screen before the operator commits.** No options list, no autocomplete
  against the answer key, no hint that narrows the field. Two free-text fields. This is the
  product's central design choice and it is not negotiable.
● **Cue to feedback under 100 ms.** The muscle-memory loop. A reveal that animates in over 400 ms
  has broken the product as a memory system. Motion is welcome ON the reveal moment; it must not sit
  between the commit and the answer.
● **The reveal is the reward moment.** It is where the product earns its "one more" feeling, so it
  gets real motion design - and a non-motion equivalent that still MARKS the moment rather than
  removing the signal.
● **Reading the procedure is never penalised**, and must not look like it is. No "you used a hint"
  badge, ever.
● **Scenario start under one second, first meaningful paint under two seconds** on the dashboard,
  cold.
● **Ten concurrent operators**, one shift crew. Desktop, two-monitor. **No mobile layout in v1.**

### Accessibility floors, which are code standards here

WCAG 2.2 AA throughout. Specifically: contrast met on charts as well as text; colour-blind-safe
pairs; status never encoded by colour alone; **keyboard operability of every plot surface**; focus
management in overlays; live regions used sparingly and at a controlled cadence;
`prefers-reduced-motion` honoured completely. Audio optional and **off by default** - this runs in a
shared operations room.

Every plot needs its text equivalent designed, not bolted on. Currently: an authored
`plot.description` always visible below the canvas, plus a "read the data as a table" disclosure that
lists the points (every eighth point when the series is dense, because a 96-row table read aloud is
complete rather than accessible).

---

## 6. Implementation constraints the direction has to survive

● Single-page application, **no framework, no build step, no CDN, no external request of any kind.**
● Currently two files: `src/enlightenment/ui/index.html` (markup plus inline stylesheet) and
  `app.js`. The script is a sibling rather than inline because the response sets
  `script-src 'self'`.
● Response headers: `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';
  img-src 'self' data:; connect-src 'self'; font-src 'self'; base-uri 'none'; form-action 'none';
  frame-ancestors 'none'`.
● **No markup-parsing sink and no dynamic-code sink in the client.** Every value from the content
  tree is written with `textContent`. Content is edited without a code deployment, so an authoring
  mistake must not become a scripting bug. A test greps for the sinks by name.
● Charts: hand-written canvas. Icons: inline SVG or a Unicode glyph. Images: none currently, and any
  addition must be a `data:` URI.
● The interface is served at `/ui`, not `/`. `/` belongs to the App Store health contract.

---

## 7. Privacy, which is a design constraint and not a legal footnote

The owner has decided that **supervisors see individual results.** That is a legitimate call in a
readiness context, and it is not cost-free: Self-Determination Theory evidence says perceived
surveillance erodes intrinsic motivation, which is the engine this product runs on. Four controls
are part of the design rather than optional extras.

● **No covert observation.** Operators are told, at first run and in the interface, exactly what
  their supervisor can see, **in the same words the supervisor sees it.** Surprise is what destroys
  trust in a tool like this, not visibility. This needs designing, not a link to a policy.
● **Purpose limitation, stated on screen.** The declared purpose is training development and
  readiness assurance.
● **Show competence, not failure.** Supervisor views surface current competence, coverage and decay
  by axis. They do **not** surface raw failed attempts, sandbox activity, or drill misses - a drill
  miss is the mechanism by which the product works, and penalising the practice loop would destroy
  the loop.
● **Sandbox and free analysis are never scored and never reported**, and the interface should make
  that visible at a glance.

Every axis is reported **with a confidence interval, never a bare number.** An axis with no attempts
reports "not measured", which is a different fact from "measured at zero" - collapsing them is how a
dashboard lies about coverage, and a supervisor would read three zeroes as three weaknesses.

Current state: one synthetic operator id, `synthetic-operator`, everywhere. No named-individual
record is written until the Data Protection Impact Assessment is signed.

---

## 8. Open design questions. Propose on these

**A. The pedagogical highlight, and this one shapes the highest-value screen.** The debrief's central
move is highlighting the cue the operator missed, on the actual data they were looking at, and it
must not read as an alarm. Red is alert, green is nominal, Blue 2 is structure, and copper-amber is
excluded from product UI by house rule - so **nothing in the palette is free to mean "attention, but
not an alarm".**

Two candidates:
1. An ink-bright `#E8EDF5` outline plus a brief pulse, reserved exclusively to debrief signalling and
   used nowhere else. **Currently implemented so it can be judged on screen.**
2. A narrow house-rule exception admitting copper-amber `#C67C00` for this one pedagogical use.

A third option is welcome if there is one. Owner decides.

**B. Progressive density.** The drill is deliberately sparse and the scenario surface is
deliberately dense. How does an operator move between them without the tool feeling like two tools?
Untouched so far.

**C. The scenario debrief's two timelines.** What the expert saw and when, against what the operator
saw and when, with the rule that fired and its cost. This is the hardest information-design problem
in the product and nothing has been designed for it yet.

**D. Making "unscored" visible.** The sandbox must feel safe at a glance, without a childish
treatment.

**E. The first-run worked example.** Ninety seconds, zero prior knowledge, ending in one correct
unaided call. Pacing and scaffolding are the whole design.

---

## 9. What to hand back

● Artboards for the four built screens, if the direction changes them, and for the seven unbuilt
  ones in section 3.
● A recommendation on each open question in section 8, with the reasoning.
● Any token the direction adds, with its **measured** contrast on `#162646` and on `#101B33`. Measured
  rather than estimated: this project has already had a palette rule set by measurement overturning
  an assumption.
● Component grammar: what a card, a control, a status, a disclosure and an overlay look like, so the
  seven new screens can be built without re-deciding.

It lands as a change to `src/enlightenment/ui/`, which then runs the verification loop and both
binding gates like anything else.

---

## The kick-off block

Paste this into Claude Design, then attach this document.

> I need artboards for ENLIGHTENMENT, a dark mission-control training application for military space
> domain analysts. It is a memory system that happens to render orbits: short timed drills that build
> instant recall of Protect and Defend procedures. Four screens exist and run; seven more need
> designing.
>
> The design system is fixed and measured - I will give you the tokens, the contrast figures and five
> hard rules that tests enforce. Do not introduce a chart library or any external request: the
> application is air-gapped and serves `script-src 'self'`, so charts are hand-written canvas. Type
> is a webfont, but a vendored one - name the faces and I will bring the files into the repository;
> nothing may be fetched at runtime. Density varies by mode; the palette never does.
>
> Build every artboard with the real payloads I supply, not placeholder content.
>
> The highest-value screen is the reveal, where an operator finds out they were confidently wrong and
> is shown the cue they missed on the data they were looking at. The open question that shapes it: red
> is alert, green is nominal, blue is structure and amber is excluded by house rule, so nothing is
> free to mean "attention, but not an alarm". I need a recommendation.
>
> Errors are learning events. No punitive mechanics, no leaderboards, nothing that feels childish or
> like surveillance. The acceptance line is: "It looks like a tool I would leave open on the second
> monitor during a shift, and the drill loop is tight enough that I do one more without deciding to."
