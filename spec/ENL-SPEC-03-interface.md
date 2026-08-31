# ENLIGHTENMENT interface specification

| | |
| --- | --- |
| **Document** | ENL-SPEC-03 |
| **Version** | 1.0 |
| **Date** | 29 August 2026 |
| **Status** | Build specification. Design decisions taken; deviations need a reason |

---

## 1. What this document is for

The product layouts specify nine provider screens precisely. Everything around them was design intent rather than specification, which meant Claude Code would have designed the application shell, navigation, state model and interaction patterns unaided. This closes that.

**The acceptance line, from the flight plan:** *it looks like a tool I would leave open on the second monitor during a shift, and the drill loop is tight enough that I do one more without deciding to.*

---

## 2. Shell

Single page application, no framework, no CDN, all assets vendored. Desktop, two-monitor context. No mobile layout.

```
┌──────────────────────────────────────────────────────────────┐
│ ENLIGHTENMENT      Drill  Scenarios  Synthesis  Library  Me  │  ← rail, 48px
├──────────────────────────────────────────────────────────────┤
│                                                              │
│                      SURFACE                                 │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│ status: content v2.2.0 · offline · [build stamp]             │  ← 24px
└──────────────────────────────────────────────────────────────┘
```

The build stamp in the footer is not decoration. An operator reporting a problem should be able to name the build without being asked.

**Navigation is flat.** Five destinations, no nesting, no hamburger, no breadcrumbs. An operator under time pressure should never be more than one click from anything.

---

## 3. Visual system

Locked. From the flight plan and the measured contrast audit.

| Token | Value | Use |
| --- | --- | --- |
| `--ground` | `#162646` | Page background |
| `--ground-2` | `#0f1b33` | Panel background |
| `--structure` | `#385FAF` | **Borders and fills only. Never text, never status.** 2.45:1, fails every floor |
| `--label` | `#739BCF` | Labels and secondary text. 5.23:1 |
| `--ink` | `#E8EDF5` | Primary text. 12.76:1 |
| `--ink-dim` | `#9FB0CC` | Tertiary text. 6.83:1 |
| `--nominal` | `#27AE60` | Nominal status. 5.22:1 |
| `--alert` | `#E06C69` | Alert text and small marks. 4.66:1 |
| `--alert-fill` | `#C0504D` | Large alert fills only. 3.21:1 |
| `--signal` | `#E8EDF5` + pulse | **Debrief highlight only. See section 7** |

**Enforced by grep gate:** `#385FAF` must not appear as a `color` or in any status class. `#C0504D` must not carry text.

Type floor 18px. Status never by colour alone: every status carries a shape and a text label. `prefers-reduced-motion` honoured throughout. Audio optional, off by default, because this runs in a shared operations room.

---

## 4. Client state model

One state object, no framework state management, `requestAnimationFrame` coalescing for high-frequency redraws.

```js
const state = {
  session:   { operator, roleTier, stages, ratings },
  surface:   'drill' | 'scenario' | 'synthesis' | 'library' | 'me' | 'debrief',
  drill:     { runId, item, response, confidence, submitted, result },
  scenario:  { runId, simTimeMs, clockState, products, triggers,
               timing: { legIndication, legProduct, governing, remainingMs },
               openThreads, draftReport },
  synthesis: { runId, tier, products, argument, challenge },
  debrief:   { runId, timeline, expertTrace, highlights, cursor },
  ui:        { reducedMotion, audio, density }
};
```

**Rules.** Server state is never mutated client-side; the client re-renders from what arrives. The scenario clock is never extrapolated across a disconnect. Nothing persists to browser storage, ever.

---

## 5. Surfaces

### 5.1 Drill

The highest-frequency surface. Everything about it optimises for one more without deciding to.

```
┌──────────────────────────────────────────────┐
│  [ stimulus, full width, product-accurate ]  │
│                                              │
├──────────────────────────────────────────────┤
│  What has happened, and what is your first   │
│  action?                                     │
│  ┌────────────────────────────────────────┐  │
│  │ response entry                         │  │
│  └────────────────────────────────────────┘  │
│  Confidence  ○ low  ○ medium  ○ high         │
│                              [ Submit ⏎ ]    │
└──────────────────────────────────────────────┘
```

**Non-negotiable:** no answer, no options, no hint of the accept values anywhere in the DOM before submission. Response entry differs by `response_format` but is always production. There is no multiple-choice component in this application and none should be written.

On submit, the panel expands downward to reveal verdict, explanation and the rules that fired. **Reveal is a downward expansion, not a page change**, so the stimulus stays visible while the operator reads why. Next is a single keypress.

Round trip target under 100 ms. Pre-fetch the next item during reveal.

### 5.2 Scenario

```
┌───────────────┬──────────────────────────────┐
│ CLOCK         │                              │
│ T+00:14:22    │      product panels          │
│               │      (from the board)        │
│ DEADLINES     │                              │
│ ▸ product     │                              │
│   00:15:38    │                              │
│   indication  │                              │
│   00:45:38    ├──────────────────────────────┤
│               │  actions │ draft report      │
│ THREADS   [3] │                              │
│ ▸ active      │                              │
│   monitoring  │                              │
│   ready       │                              │
└───────────────┴──────────────────────────────┘
```

**The dual timer is the distinctive element and it must be right.** Both deadlines shown, the governing one marked with `▸` and rendered in `--ink` while the other sits in `--ink-dim`. When a product arrives and the governing leg changes, the marker moves and there is a brief pulse. Under five minutes remaining the governing figure moves to `--alert`. Where the procedure is a daily crew operations task the whole deadline block is absent, because no standard exists.

Thread triage uses three lanes: active, monitoring, ready to close. The count badge turns to `--alert` past the concurrent ceiling. Untouched threads past the ageing window carry a marker.

### 5.3 Synthesis, the board

The visible progression. Panels appear as tiers advance.

| Tier | Board |
| --- | --- |
| 1 | Two panels, side by side, both open |
| 2 | Three panels |
| 3 | Four or five, **collapsed by default, operator chooses what to open** |
| 4 | All ten as collapsed tabs, all openable |
| 5 | All ten, some marked degraded or stale |

Tier 3 is where the interaction changes: opening a product becomes a choice with a cost, and the clean-board award depends on every opened panel contributing. Which panels were opened is recorded and shown in the debrief.

The interface states plainly that early tiers present a curated set for training reasons. **Scaffolding, not withholding**, and saying so avoids the impression that the tool is hiding things.

### 5.4 Argument entry, tier 3 and above

Six labelled fields, in order, matching the argument components:

```
Conclusion        [ one line, plain ]
Evidence chain    [ + add: claim → product ]
Ruled out         [ + add: alternative → evidence ]
Confidence        [ low / medium / high ]  ← "peg to your weakest link"
Falsifier         [ what would prove this wrong ]
Gaps              [ what you did not have ]
```

Fields are labelled, not pre-filled and not validated into shape. The hint against Confidence is deliberate: setting it by the strongest evidence rather than the weakest is the most common argument failure and the most heavily penalised.

**No time pressure below tier 3.** Rushing an argument is the failure being trained out.

### 5.5 Debrief

Two columns. Operator's run left, expert right, aligned by scenario time.

```
┌────────────────────────┬────────────────────────┐
│ YOU              T+04:12│ EXPERT           T+02:50│
│ opened residual        │ checked epoch age      │
│ called manoeuvre       │ ruled out: stale state │
│                        │ ruled out: starved fit │
├────────────────────────┴────────────────────────┤
│  ANATOMY   1 ✓  2 ✓  3 ✓  4 ~  5 ✗  6 ✗  7 ✓  8 ✓ │
├─────────────────────────────────────────────────┤
│  [ replay ◀ ▮▶ ]  with highlight overlay        │
└─────────────────────────────────────────────────┘
```

The anatomy strip is the fastest read in the whole application: answered, implied, absent. Questions 5 and 6 are weighted and, where absent, the debrief expands them by default rather than leaving the operator to notice.

Replay renders the operator's own products with the expert's highlight overlaid at the moment they noticed. **The ruled-out column is the highest-value element** and should never be collapsed by default: novices rarely generate alternatives at all, and seeing which ones an expert discarded is the fastest route to generating them.

Where no expert trace exists the right column says so plainly.

### 5.6 Dashboard

Competence by axis **with confidence intervals rendered as bands, never as points**. Decay per procedure as information, never as a nag. Two ratings shown separately, never averaged. Chain length as a personal best. What is due, and why.

No streaks. No leaderboard.

### 5.7 Library

Procedures, products, artefacts, platform archetypes, browsable and searchable. Reference, not assessment. Available during scenarios, because in the real environment the procedure is available.

---

## 6. Onboarding, first fifteen minutes

The acceptance test is that an operator with no prior knowledge reaches a correct unaided classification in under fifteen minutes.

1. **Sign in.** Visibility notice shown and acknowledged. Exactly what a supervisor can see, in the same words the supervisor sees.
2. **One product, no task.** A residual plot with the informative region marked. What it is, what the axes are, what the zero line means. No question asked.
3. **Worked example.** An expert reads a departure aloud in text. What they looked at, in what order, what they concluded.
4. **Completion problem.** Same product, one step removed. The operator names the departure type.
5. **First unaided call.** New instance, no scaffold. Correct or not, the reveal teaches.
6. **Straight into the drill loop.**

Cognitive load theory in sequence: worked example, then completion, then problem. Scaffolds fade automatically; an operator who tests out of a stage never sees them.

---

## 7. The debrief highlight, decided

This was open question 13 and it needs deciding before the debrief is built.

**Decision: ink-bright outline plus a single brief pulse, reserved exclusively for debrief signalling.**

```css
--signal-outline: #E8EDF5;
--signal-width: 2px;
--signal-pulse: 600ms ease-out, once, respects prefers-reduced-motion;
```

**Why this and not copper-amber.** Amber is barred from product UI by house rule, and taking an exception for one purpose creates a precedent that erodes the rule. More importantly, amber sits close enough to alert red that on a dense plot under time pressure it would read as a warning. The debrief highlight must not say *danger*, it must say *look here*.

**Why ink-bright works.** It is already the highest-contrast token at 12.76:1, it carries no operational meaning anywhere else in the system, and on a dark plot an outline reads as emphasis rather than as status.

**The rules that make it safe.** Used only in the debrief, never in a live scenario. Never on more than one feature at a time. Pulse fires once on reveal, not continuously. Under `prefers-reduced-motion` the outline appears without the pulse and persists half a second longer.

**Reversal cost is low.** One token, one component. If the TRA or an operator cohort finds it insufficiently distinct, changing it is a token edit rather than a rendering change.

---

## 8. Accessibility, as code standards

| Requirement | Enforcement |
| --- | --- |
| WCAG 2.2 AA contrast | Grep gate on forbidden colour uses, plus a contrast test over the token set |
| Status never by colour alone | Every status component carries shape and text |
| Keyboard operability of every plot | Focus, arrow traversal of features, Enter to inspect |
| Live regions used sparingly | Clock ticks are **not** announced. Trigger events, deadline changes and reveals are |
| Focus management | Focus moves to the reveal on submit, returns to entry on next |
| `prefers-reduced-motion` | All motion has a non-motion equivalent that still marks the moment |
| Type floor | 18px, no exceptions |

The live-region rule matters more than it looks. Announcing a 1 Hz clock would make the application unusable with a screen reader, and it is the obvious naive implementation.

---

## 9. Build order for the interface

| Order | Surface | Why |
| --- | --- | --- |
| 1 | Shell, rail, tokens, state object | Everything sits in it |
| 2 | Plot renderers | Everything consumes them |
| 3 | Drill | Smallest complete loop. Proves scoring end to end |
| 4 | Debrief | Constrains what the scenario runner must record |
| 5 | Dashboard | Needs something to show |
| 6 | Scenario | Largest. Needs clock, transport, dual timer |
| 7 | Synthesis and argument entry | Distinct enough to be its own piece |
| 8 | Library | Reference, low risk |
| 9 | Authoring | Fixes the trace dependency |

Debrief before dashboard is deliberate. The debrief determines what must be recorded during a run, and discovering that after the scenario runner is built means changing both.
