# Red team: does PHOSPHOR meet the standards for a training system?

**Verdict up front: the interface is strong and the instructional design underneath it has three
serious gaps. None of them is a visual problem, and none of them is fixed by better screens.** The
prettiest drill loop in the world still fails an assessor who asks "where is your training needs
analysis?"

Scope: the PHOSPHOR direction (`design/phosphor/`) and the shipped drill layer it would replace,
tested against instructional-design and defence training standards. Written adversarially. Findings
are ranked by what would actually stop this being accepted or being effective, not by how easy they
are to fix.

---

## The standards this is tested against

Marked by how confident I am, because a red team that overstates its own authority is worth less
than one that does not.

**Confident, and directly applicable**

● **Gagné's Nine Events of Instruction.** The oldest and bluntest checklist for whether a piece of
  instruction is complete.
● **Merrill's First Principles of Instruction.** Problem-centred, activation, demonstration,
  application, integration.
● **Van Merriënboer's Four-Component Instructional Design (4C/ID).** The model built specifically
  for complex cognitive skills: whole learning tasks, supportive information, procedural
  information, part-task practice. This is the most relevant single framework to what
  ENLIGHTENMENT is trying to do.
● **Cognitive Load Theory (Sweller).** Intrinsic, extraneous and germane load; the worked-example
  effect; the expertise-reversal effect.
● **Kirkpatrick's four levels of evaluation.** Reaction, learning, behaviour, results.
● **Deliberate practice (Ericsson).** Specific goals, immediate informative feedback, repetition
  with refinement, a coach or model.
● **Recognition-Primed Decision making (Klein).** How experts actually decide under time pressure,
  and the mental-simulation step that classification-only training misses.
● **Transfer of training (Baldwin and Ford).** Near and far transfer; conditions of practice;
  identical elements.
● **WCAG 2.2 AA.** Already a code standard in this project.

**Applicable, but the edition needs checking before anyone cites it externally**

● **Defence Systems Approach to Training (DSAT)**, the UK MOD training methodology, with the
  governing policy in the JSP 822 series. The phase structure (training needs analysis, design,
  delivery, assurance, with internal and external validation) is what an MOD training authority
  would expect to see. **TBC, re-verify the current JSP 822 edition and its exact requirements
  before quoting it in anything customer-facing.** I cannot check it from here and will not invent
  clause numbers.
● **xAPI (the Experience API) and SCORM** as learning-record interoperability standards, if this
  ever has to feed a wider learning management system.

**Deliberately not claimed.** I have not cited a NATO STANAG, an ISO number, or a specific JSP
clause, because I cannot verify one from here and a fabricated reference in a defence training
document is worse than no reference at all.

---

## Findings, ranked

### 1. CRITICAL. There is no training needs analysis, so nothing is traceable to the job

Every standard above starts in the same place: what does the job actually require, and what is the
gap? DSAT begins with a training needs analysis producing a formal statement of training
requirement. Merrill and 4C/ID both start from real whole tasks. ENLIGHTENMENT starts from a
procedure list and six competency axes that **the flight plan itself says were invented**: "no
external framework applies; six axes invented here, confirmed with owner".

Invented is not the same as wrong. The six axes are sensible and the plan is honest about their
provenance, which is more than many training products manage. But the consequence is real:

● No task inventory, and no Difficulty-Importance-Frequency analysis to say which tasks are worth
  training at all.
● No traceability from a training objective back to a job task, so the coverage claim on the
  dashboard means "coverage of the content we happened to author", not "coverage of the role".
● **The three v1 procedures were chosen by the owner, not derived from an analysis.** They are
  plausible choices. They are not defensible ones under DSAT until something upstream says so.

**Severity:** this is the finding that would stop an MOD training authority accepting the system,
and it is invisible in every screenshot.

**What closes it:** a short, honest TNA. Even a two-page one, naming the tasks, their DIF ratings
and the objectives derived from them, with the analysis method stated. It also retro-justifies the
six axes or replaces them.

### 2. CRITICAL. It is entirely part-task practice, and a part-task trainer produces operators who cannot run an event

4C/ID is unambiguous that complex skills need **whole learning tasks** in a simple-to-complex
sequence, with part-task practice used only to automate the recurrent bits. ENLIGHTENMENT v1 ships
the part-task half and nothing else: scenario mode is flight plan step 11 and is not built.

Drills train cue recognition and first-action recall. They do not train:

● Holding a developing picture across time while evidence accumulates.
● Revising a call as new data arrives, which is where the debrief's whole lesson lives.
● Sequencing the rest of the procedure after step one.
● Producing report content at the right threshold at the right time - one of the six axes, and
  currently **unmeasurable**, which is why the dashboard shows it as "not measured" forever.

Two of six competency axes (physical reasoning, reporting) are structurally unreachable by the
drill layer as built. That is not a content gap, it is an architecture gap.

**Severity:** the product as shipped can only ever measure four of its own six axes.

**What closes it:** scenario mode, which is already planned. The finding is that it is not optional
polish - it is the half of the model that makes the other half legitimate.

### 3. CRITICAL. No scaffolding fade. It goes from one worked example to unsupported problems

The worked-example effect is one of the most replicated findings in the field: novices learn
substantially more from studying worked examples than from solving equivalent problems, and the
advantage reverses as expertise grows. The standard progression is **worked example → completion
problem → independent problem**, with support fading as competence rises.

PHOSPHOR has the first rung (First Contact, a genuine worked example) and the third rung (the
drill). There is no middle rung. A true novice - and the plan says "assume zero prior knowledge as
the floor" - gets ninety seconds of guidance and is then producing unaided answers with no
intermediate support.

The Elo rating fades *difficulty*. It does not fade *support*, and those are different axes.

**Severity:** this is the finding most likely to make a novice bounce off the product in the first
session, which is precisely the outcome the engagement design exists to prevent.

**What closes it:** completion problems. Same signal, but the classification is given and the
operator supplies the first action; or the cue is circled and they name it. A "guided" mode that
the scheduler retires per cue class once the operator has landed it unaided twice.

### 4. MAJOR. "Reach" is a relative rating being read as a competence claim

This one is mine, and it is a conceptual error in the design I built rather than a rough edge.

Elo is a pairwise-comparison rating. It is excellent at what the drill uses it for - choosing an
item near the edge of someone's ability. It is **not** a criterion-referenced competence measure,
and defence training assessment is criterion-referenced: can this person perform this task to this
standard, yes or no.

PHOSPHOR makes "Reach 1241" the hero number on three screens. A supervisor reading that number will
read it as competence. It cannot support that, for two reasons: it is relative to a content set
that is itself being rated, and it says nothing about which tasks the person can actually do.

**What closes it:** keep Elo where it belongs, in item selection, and demote it visually. Promote
the criterion-referenced statement that already exists in the data - "current on 3 of 3 wired
procedures, decayed on 1" - to the hero position. The dashboard already computes this; the design
put the wrong number first.

### 5. MAJOR. Assessment validity rests on one author with no second marker

Ash authors and validates the expert traces, and the flight plan records the *availability* risk of
that single-point dependency, with sensible mitigations. It does not address the *validity* risk,
which is a different thing: a scoring key with one author and no inter-rater agreement has no
established reliability.

The plan already names the right gate - "the automated scorer must be checked for agreement with
expert human raters on a validation set before any operator is scored by it" (step 12) - and that
gate has not run. Until it does, every number this product shows an operator is unvalidated.

**What closes it:** a second subject-matter expert scoring a held-out set, and a reported agreement
statistic. The content model already carries `authored_by` and `authored_on` on every item, so the
data structure supports it today.

### 6. MAJOR. Gagné's checklist: four events strong, three weak, one absent

Run the drill loop against the nine events honestly:

| Event | Verdict |
|---|---|
| 1. Gain attention | **Strong.** The inbound signal, the sweep, the open loop. |
| 2. Inform the learner of the objective | **ABSENT.** The drill never says what it is training. |
| 3. Stimulate recall of prior learning | **Weak.** Spacing does it implicitly; nothing surfaces "you have met this cue class before". |
| 4. Present the content | **Strong.** |
| 5. Provide learning guidance | **Weak by design** (retrieval practice), and see finding 3. |
| 6. Elicit performance | **Strong.** Production, not recognition, is the best thing in the product. |
| 7. Provide feedback | **Strong.** The reveal is exemplary: named rule, evidence, expert cue. |
| 8. Assess performance | **Strong**, subject to finding 4. |
| 9. Enhance retention and transfer | **Partial.** Spacing is there; transfer is untested. |

Event 2 is the cheap fix and the one with real payoff: a novice who does not know what they are
being asked to get better at cannot direct their own effort, which undercuts the autonomy leg of
the motivation design.

### 7. MAJOR. Kirkpatrick levels 3 and 4 have no mechanism at all

The plan optimises for Level 2 (learning) and says so. Levels 3 (behaviour on the job) and 4
(results) have no instrumentation and no route to any. DSAT's external validation asks exactly this
question: did the training improve performance in the role?

This is not a v1 feature request. It is a decision that needs taking consciously, because retro-
fitting a route to job-performance data is far harder than designing a hook for it now.

**What closes it:** decide whether external validation will ever be attempted. If yes, the minimum
is a stable operator identifier that can be correlated with watch-floor performance data by someone
who holds both - which has data-protection consequences that belong in the DPIA before, not after.

### 8. MODERATE. Recognition-primed decision making: no mental-simulation step

Klein's model of expert decision-making under time pressure has two halves: recognise the
situation, then **mentally simulate** the chosen course of action to check it works before
committing. ENLIGHTENMENT trains the first half thoroughly and the second half not at all.

The drill asks for a classification and a first action. It never asks "and what do you expect to
happen next?" - which is the question that separates an expert from someone who has memorised a
lookup table.

**What closes it:** a third field on some items, or better, a scenario-mode prompt: "what do you
expect the next revisit to show?" That is also a cheap, high-value engagement mechanism, because
being right about a prediction is more satisfying than being right about a label.

### 9. MODERATE. The vocabulary mechanism has no mastery rule behind it

"11 of 34 signatures" is the strongest engagement idea in the design and it currently means
nothing precise. Collected on what basis - one correct answer? Under any assessment standard a
single correct response is not evidence of mastery, and a vocabulary count that inflates on a lucky
guess will be noticed and discounted by exactly the audience this product is for.

**What closes it:** a stated rule. Landed unaided at two different spacings is defensible and the
scheduler already has the data to know it.

### 10. MODERATE, and mine. Text at 8.5 to 10.5 pixels is carrying the lesson

I measured contrast carefully and then undermined it with size. The SVG annotations in the
artboards run at 8.5 to 10.5 px, and they are not decoration: "SENSOR REVISIT · COUNT STOPS", "THE
COUNT HAD NOT STOPPED GROWING YET" and the whole debrief timeline carry the instructional content.

The house floor is 18 px for body text and this project treats accessibility floors as code
standards. Small-caps furniture at 11 px is arguable. **Text carrying the teaching point at 9.5 px
is not.**

**What closes it, and what actually happened.** I stopped estimating and measured. A headless
Chromium harness loads each artboard at two window widths, and for every `<text>` in every plot it
computes the *rendered* size (the declared size times the ratio of the drawn width to the viewBox
width), then compares each label's bounding box against the frame and against every other label.
It lives at `design/check-artboards.mjs`. It needs Node and Playwright, so it is not a leg of
`scripts/verify.sh`; it is run by hand when an artboard changes. The numbers it produced are these.

The rendered sizes were worse than the declared ones, because a plot inside a 1.55fr column is
drawn *smaller* than its own coordinate system:

| Artboard | scale | worst declared | worst rendered |
| --- | --- | --- | --- |
| Main | 0.77 to 0.95 | 9.5 | **9.0 px** |
| Reveal | 0.77 to 0.95 | 9.5 | **9.0 px** |
| Progress | 1.09 | 8.5 | **9.3 px** |
| Debrief | 1.09 | 9.5 | **10.4 px** |
| FirstContact | 1.08 | 9.5 | **10.2 px** |

Two further defects fell out of the same measurement, neither of which I had noticed by eye:

● **Progress clipped its own radar labels.** "PROCEDURE RECALL" ran past the right edge of a 440
  unit viewBox and was cut off by the frame. It had been wrong since the artboard was drawn.
● **The debrief timeline overlapped six of its own labels.** "spread narrow, one way" and
  "separation · 70%" occupied the same strip of pixels, as did two more pairs. The screen that
  carries the single most important teaching moment in the product was partly unreadable.

So the fix was not a font-size change. Every plot now sits inside a bounded measure so its render
scale is a known quantity rather than whatever the window happens to be; in-plot text is sized
against that measured scale, not against its own coordinate system; the debrief timeline's label
layer was rebuilt on two staggered rows per track with hairline leaders back to each marker; and
the radar frame gained the margin its labels always needed.

The harness now asserts, at both a 1440 px and an 1180 px window, that **no text inside any plot
renders below 12 px, none is clipped by its frame, and no two labels overlap.** All six artboards
pass. That is a standing check, not a one-off: it is how the next artboard gets caught.

### 11. MODERATE, and also mine. The contrast figures were measured without the scanline

The palette figures in the canvas (10.4 to 13.0 : 1) were computed against the flat ground colours.
The artboards then composite a scanline overlay at `rgba(255,255,255,0.018)` over the plot area,
and the glow spreads a wide low-opacity stroke under every trace. Neither was in the measurement.

The effect is small - the overlay is under 2% white - and it *raises* the ground luminance slightly,
which lowers contrast against light text. It is almost certainly still comfortably over 4.5:1. But
"almost certainly" is not the standard this project holds itself to elsewhere.

**What closes it:** re-measure with the overlay composited, and drop the scanline if any figure
lands under 7:1. Done in this pass - figures below.

### 12. MINOR. No learning-record interoperability

No xAPI, no SCORM, no export of a training record in any standard shape. If JCO or UK Space Command
ever want this to feed a wider training management system, that is a retrofit.

Not a v1 need, and possibly never a need for an air-gapped internal tool. Worth an explicit
decision rather than a silent omission.

### 13. MINOR. Stress exposure is present but not designed

Real watch floors are stressful and mild time pressure in training is well supported. But there is
no progression from low- to high-pressure conditions and no explicit design for coping transfer.
The sweep is atmosphere rather than a stress-inoculation curriculum.

Low priority, and honestly it may be the right call for v1 - but it should be a call.

---

## What PHOSPHOR gets right, tested rather than asserted

Being adversarial does not mean being ungenerous. Against the same standards:

● **Deliberate practice (Ericsson) is properly implemented.** Specific goals, immediate informative
  feedback, repetition with refinement, and a model to imitate. Most training products claim this
  and deliver a quiz. The named-rule, named-evidence reveal is the real thing.
● **Retrieval practice and spacing are the architecture, not a feature.** Production over
  recognition, and a scheduler that puts a miss at the front. This is the strongest evidence base
  in the whole field and the product is built on it rather than decorated with it.
● **Feedback quality is genuinely excellent.** Naming the look-alike the operator chose - "you
  called it fragmentation, and that is the look-alike this signal exists to separate" - is
  discriminative feedback of a kind most systems never attempt.
● **Calibration training is rare and correct.** A proper scoring rule on stated confidence, with
  plain-language verdicts. Confident-and-wrong is the failure mode that kills people in
  operational settings and almost nothing trains it directly.
● **Cognitive load is handled deliberately** at the density level, with the expertise-reversal
  effect explicitly reasoned about rather than stumbled into.
● **The motivation design is evidence-led and restrained.** Refusing streaks and badges on
  overjustification grounds, and building relatedness from a named expert instead of a leaderboard,
  is a better-reasoned position than most commercial training products hold.
● **Transfer is designed for.** Same palette, same component grammar, same vocabulary across drill
  and scenario, which is the identical-elements route to transfer.

**On the "well designed training system" question specifically: the learning science is above
industry standard. The instructional systems engineering around it is below it.** Those are
different disciplines and the second one is mostly paperwork and sequencing, not screens.

---

## Re-measured, with the overlay composited

Every accent, against the plot ground **with** the scanline overlay applied, since the original
figures did not include it:

| Token | Flat ground | With scanline | Verdict |
|---|---|---|---|
| amber `#FFBB55` | 11.77 | 11.63 | pass |
| cyan `#00E6FA` | 12.90 | 12.75 | pass |
| green `#7CE79C` | 12.97 | 12.82 | pass |
| coral `#FFA4A1` | 10.43 | 10.31 | pass |
| violet `#DBB5FF` | 11.37 | 11.24 | pass |
| ink `#F2F0F4` | 17.47 | 17.26 | pass |
| ink-2 `#B9B6C2` | 9.92 | 9.81 | pass |
| ink-3 `#807D8C` | 4.93 | 4.87 | pass, and it is the floor |

The overlay costs about 1% of contrast ratio. Nothing crosses a threshold, so the scanline stays.
`ink-3` at 4.87:1 remains the only token close to the 4.5:1 line, and it is used for axis numerals
and secondary labels only.

---

## Recommended order of work

1. **The training needs analysis** (finding 1). Nothing else is defensible without it, and it is
   days of thinking rather than weeks of building.
2. **Scenario mode** (finding 2). Already planned as step 11. It unlocks two of the six axes.
3. **The scaffolding fade** (finding 3). Completion problems between the worked example and the
   unaided drill.
4. **Demote "Reach", promote criterion-referenced currency** (finding 4). A design change, not an
   engineering one, and it is an afternoon.
5. **Scorer validation** (finding 5). Already a named gate; needs a second expert.
6. **State the objective in the drill** (finding 6, event 2). Cheapest fix on the list.
7. **A mastery rule for the vocabulary** (finding 9).
8. **Decide on Kirkpatrick 3 and 4, and on xAPI** (findings 7 and 12). Decisions, not builds, but
   both get more expensive the longer they wait.
