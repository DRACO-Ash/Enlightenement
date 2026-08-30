# Task evidence: what the job actually is, from the tool operators use

**This is not a training needs analysis.** A Defence Systems Approach to Training (DSAT) needs
analysis is a formal instrument with role analysis, task listing, performance standards and a
training gap. This is the raw material one would be built from, and it is the first thing in this
project traceable to the job rather than inferred from the code.

Source: the Iron Stallion help manual for **Sat Xzibit**, supplied by Ash on 30 August, together
with five screenshots of live products from the same application supplied the day before. Sat
Xzibit is described in its own manual as "a rapid situation-assessment tool for reviewing the
latest available information on a satellite".

Everything below is attributed to that manual so it can be verified against the source or removed
as one block. Where the manual does not say something, this document says so rather than filling
the gap.

## Why this matters more than the plots

`docs/DESIGN-RED-TEAM.md` finding 1 is CRITICAL and reads: *there is no training needs analysis, so
nothing is traceable to the job; the six competency axes were invented.* The flight plan admits it.
DSAT would stop there.

This material does not close that finding. It does something better than another invented axis: it
gives a real tool's own statement of what the operator is trying to answer, in what order, with
which cues. Four things follow from it directly.

## 1. The task, as the tool states it

The manual's own list of what Sat Xzibit helps you answer:

● When the most recent observation, element set, or state vector was received.
● Which providers collected the data, and how the data compares across sources.
● Whether the satellite appears stable, manoeuvring, or changing pattern of life.
● What optical, radar, or radio frequency (RF) data is available for the object.
● When sensors are expected to see the object again.

And its workflow: identify the satellite, set the time window and filters, review the latest state,
open the detailed views, **then plan follow-on collection**.

Read that last step carefully. The job does not end at a classification. It ends at a *tasking
decision*: given what you found, which sensors do you point at it, over what window, and why. That
matters below.

## 2. Residuals are a four-class classification, and we already have the drill format for it

The manual gives four distinct questions to ask of a residual plot, which are four distinct causes
for the data leaving the zero line:

| The question the manual asks | What the answer means |
| --- | --- |
| Is the data staying close to the zero line? | The current state still fits |
| Is a manoeuvre affecting orbit size or orbit plane? | The object moved |
| Is the orbit fit degrading? | The object did not move; the solution is going stale |
| Is the incoming data set showing quality issues? | Neither; the sensor or the association is the problem |

Those last three are the discrimination. "Residuals moved" is the cue; *which of three causes*
is the call. Two of them are not about the satellite at all, which is exactly the kind of confusable
alternative the drill format exists to train, and exactly the kind an invented syllabus would have
missed: a trainee who has only ever been taught "residuals move when there is a manoeuvre" will
report a manoeuvre when the fit is stale.

**And the manual supplies the physical rule that separates the first two:**

● **Beta residuals reveal orbit PLANE change.**
● **Time residuals reveal orbit SIZE change.**

That is a real cue with a physical basis, of the same class as the ones the flight plan names, and
it was not in our vocabulary because nobody here knew it.

## 3. Two of the six axes stop being unmeasurable

`docs/DESIGN-RED-TEAM.md` finding 2 is CRITICAL and says two of the six competency axes, **physical
reasoning** and **reporting**, are structurally unmeasurable by the drill loop as designed. This
material changes that, because it names concrete, scoreable tasks for both.

**Physical reasoning becomes measurable** through the element response question. The orbital plot
product shows period, apogee, perigee and eccentricity stepping together at each burn while
inclination and right ascension of the ascending node (RAAN) ramp smoothly through, untouched,
because both are dominated by natural perturbation. Asking *which elements should have moved, given
this manoeuvre* is a physical-reasoning item that produces a markable answer. The same is true of
the Beta-and-Time rule: plane against size is a physical claim.

**Reporting becomes measurable** through the collection-planning step. The workflow ends at "plan
follow-on collection with ISSP or Manual ISSP", and the manual describes what goes into that: a
time window, an object list, a sensor set, a step rate, and a phenomenology judgement about whether
a sensing type can collect at all given field of view, solar and lunar exclusion angles, day and
night rules and range. That is a produced artefact with right and wrong answers in it, which is
what the reporting axis needed and did not have.

Both need authoring, and neither is free. But the flight plan's claim that the axes are measurable
is now defensible for four of six instead of four with two hopes attached.

## 4. The manual contains a procedure we did not write

Its "recommended operator checks", verbatim in substance:

1. Compare the latest timestamps for the observation, element set and state vector lists.
2. **Look for agreement across providers before assuming a trend is real.**
3. Use Run Residuals to test how well a specific source state explains the current observation set.
4. Cross-check any suspected manoeuvre against the manoeuvre list, the residual plots, and the
   downstream views.

Step 2 is a discipline, not a technique, and it is the one most likely to be skipped under time
pressure. It also answers a question I raised in `docs/PLOT-REALISM.md` from the other direction:
overlaying two sources is not a nice visual idiom, it is a required check, and a training surface
that shows one source cannot ask the operator to perform it.

Step 4 is the same shape: no single view is sufficient, and the call is made where several agree.

## 5. Other operational content worth authoring against

Taken from the manual, ranked by how usable it is as training material.

● **Adjust ACDC span.** When a manoeuvre or a bad data period is corrupting a multi-day fit, the
  operator moves the fit start to after the event and re-runs. This is a decision with a real
  trade-off and a wrong version: re-fitting to hide a manoeuvre rather than to measure it.
  ("ACDC" is not expanded anywhere in the supplied material. `TBC, re-verify`.)
● **Display Mode regrouping.** The same residual data regrouped by satellite, sensor, source, or
  residual type. Knowing which grouping answers which question is a skill, and it is cheap to
  train: same data, four views, one question.
● **Time difference of arrival (TDOA) reading.** Each point is a *pair* of sensors, not one; the
  legend identifies site pairs or clusters; larger-magnitude changes align with manoeuvre periods;
  a cluster falling silent is a coverage gap rather than a signal. The "each point is a pair" part
  is a genuine misconception trap.
● **The observation heat map** overlays multiple days to expose recurring coverage patterns and
  gaps by time of day, which is how pattern-of-life change is seen. Colour is date-based.
● **Phenomenology availability.** Whether a sensor type can collect at all, given field of view,
  solar and lunar exclusion, day or night rules and range. An operator who tasks a sensor that
  physically cannot see the object has made a specific, markable error.
● **Association status (ASTAT).** ASTAT 1 fully associated, ASTAT 2 closely associated. Vocabulary.

## 6. One thing to decide before this is designed against

The manual is explicit that **red means the most recent data**, in the heat map, in the LAT/LON
view and in the light curves, with a red line marking the present. That convention is consistent
across at least three views in the tool the operator uses every day.

PHOSPHOR uses red-pink for *your call was wrong*. Those are two unrelated meanings on the same
colour, and transfer of training turns on the surface features of the practice environment matching
the job's. `docs/PLOT-REALISM.md` sets out three options and recommends confining red to recency on
plot surfaces and never using it for verdicts. **It is a design decision and it is Ash's.**

## What is not here

● The Web Waterfall help guide did not come through; only the one-line description inside the Sat
  Xzibit manual, which says it shows observations from objects within 50 km of the queried
  satellite as longitude over time.
● No performance standard. The manual says what an operator looks at, never how fast or how
  accurately they are expected to do it. Every scoring threshold in this product remains a number
  we chose.
● No role or task hierarchy, no criticality rating, no error consequence analysis. A DSAT needs
  analysis has all three and this has none of them.
● Nothing about the Joint Counter-small Unmanned Aircraft Systems Office (JCO) Global Operations
  context specifically. This is a Space Domain Awareness tool; the mapping to the intended
  audience is an assumption, not evidence.

## Handling

Tool documentation and product screenshots for publicly catalogued objects. What has been taken is
procedure, vocabulary and visual idiom. No data has been taken: no residual value, object pairing,
timestamp, sensor identity, provider name or site characteristic from the source material appears
in content or code, and the generated series stay synthetic and seeded. Nothing in this document
should be treated as an authored training artefact until a subject-matter expert has confirmed it,
which is the same bar `content/` already sits behind.
