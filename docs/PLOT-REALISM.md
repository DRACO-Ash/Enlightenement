# Plot realism: what real operational products look like, and what ours do not

Five screenshots of live KBR Space Domain Awareness (SDA) tooling, supplied by Ash on 29 August as
design reference. Publicly catalogued objects throughout (SHIYAN 12 01, GAOFEN 13, BANGABANDHU,
TJS-10). This document records what they show, judges the drill surfaces against them, and lists
what changes.

**Verdict: the plots this application generates are not realistic, and the gap is structural
rather than cosmetic.** It is not a matter of adding noise or picking better colours. Every one of
the five real products is a dense, gappy, multi-source scatter that encodes a second variable in
colour. Every one of ours is a clean, evenly sampled, single-series polyline that encodes nothing.

The illustrative plot generator (`training/plots.py`, retired in V0.24.0 when the real content
package landed) already carried the warning in its own module docstring: "a
shaped series presented as measured data is the clean-training-data-is-negative-training failure
the plan warns about". That warning was correct and its scope was too small. It described the
noise amplitude. The problem is the sampling, the clumping, the second dimension, the marker, the
provenance and the number of sources.

## The six idioms every real product uses and ours use none of

**1. Colour carries a variable, and it is usually THE variable.** Not one of these five plots uses
colour decoratively. The light curve colours by interval (a red pass against a blue ramp against
white). The residual plot colours by association type. TRIC runs a continuous blue-cyan-yellow-red
ramp along the trajectory to encode time. The waterfall colours by object across hundreds of hues.
The orbital plot colours by data source. In an operational tool the colour IS the analysis: it is
how an analyst separates one pass from another, one sensor from another, one source from another.
Our surfaces draw one cyan line.

**2. Data arrives in passes, not in a continuous sweep.** Every real time series is clumped: a
dense burst of observations while a sensor has the object, then hours of nothing. The residual plot
shows seven distinct clumps across seven days. The waterfall is mostly empty space with vertical
bands where coverage exists. Our generators emit `SERIES_POINTS = 96` points at a fixed interval
with no gaps at all. An operator trained on evenly sampled data has never had to ask "is that a
real change or the edge of a pass?", which is one of the first questions the job requires.

**3. The marker is a plus-cross, and the plot is a scatter.** Real products draw thousands of
small `+` glyphs. They do not draw a connecting line, because a line asserts continuity between
observations that are not continuous. We draw polylines. That is a claim about the data that the
data does not support, and it hides the pass structure in point 2.

**4. Two sources are overlaid, and the comparison is the point.** The orbital plot shows
`58204-KBR` in red squares against `58204-SPACE_TRACK` in blue-grey crosses on the same axes. That
comparison - your own solution against the public catalogue - is itself an analytical act, and
where they disagree is where the interesting question lives. We have no notion of a second source.

**5. Discrete state changes are drawn as steps, not as curves.** TRIC's Right Ascension delta is a
staircase. The orbital plot's period sits on flat levels and jumps between them. Our
`longitude-drift` artefact case draws "a near-vertical jump", which is closer, but the rest of our
shapes are smooth where the real thing is piecewise.

**6. The frame carries provenance and a clock.** The waterfall footer reads "Latest Execution
2026-08-28T22:27:20.5387 | Latest Ob Ct: 20000". The residual plot draws a red vertical line at the
current epoch and a hover box giving the exact timestamp with the fitted deltas. The TRIC header
names both objects, both element-set sources, and a count of others. Our plots carry a title and
two axis labels.

## What each product gives us

### 1. Vis Mag light curve, 50321 SHIYAN 12 01

Visual magnitude against solar equatorial phase angle, minus 80 to plus 80 degrees. **The
magnitude axis is inverted** - 9 at the top, 15 at the bottom - because brighter is a smaller
number and an analyst reads brightness upward. Points are `+` glyphs coloured by an "Interval"
legend running 0 to 7, rendered as a vertical list of coloured dots down the left edge: interval 0
in red, 1 to 6 in a sequential blue ramp, 7 in white. Several thousand points, arranged in vertical
stripes that are individual passes.

The feature an analyst is looking at is unmistakable once seen: a sharp brightening to magnitude
9.3 in a narrow band just past zero phase angle, standing four magnitudes above the surrounding
trend. That is a specular glint, and the whole shape of the curve either side of it is the
photometric signature.

**We have no light-curve surface at all.** `PlotKind` carries three values and none of them is
photometric. This is why "Photometric cues" appears in the Progress artboard's decay list as
"never" trained, and why "Specular glint" and "Tumble period" sit in the vocabulary chips as
uncollected. The surface those items would need does not exist.

### 2. Residual against observation time, 46610 GAOFEN 13

Residual on a tight vertical scale, minus 0.08 to plus 0.08, against a seven-day window. Legend on
the left: ASTAT Assoc., Beta Assoc., Time Assoc., V Mag Assoc., each a coloured dot. The data sits
in seven clumps, overwhelmingly one association type.

Two frame elements matter. A vertical crosshair with a hover box reading `2026-08-26 23:42:03 /
ΔPer: -5.5099(s)  ΔInc: -0.2002` - so the tooltip carries the fitted consequence, not just the
coordinate under the cursor. And a red vertical line at the right edge marking the present.

The plot furniture is a standard interactive chart toolbar: zoom, pan, box select, lasso,
autoscale, reset. Our plots are static images with a "read the data as a table" control.

### 3. TRIC results, 43463 BANGABANDHU against 46610 GAOFEN 13

Six panels: Cross-Track over In-Track, Distance, Solar Aspect Angle, Radial over Cross-Track,
Radial over In-Track, and Right Ascension delta. **Three of the six are Hill-frame projections of
the same relative motion**, which is the surface our `hill-relative` generator produces - and the
real one shows all three projections at once, because a single projection of a three-dimensional
relative track is ambiguous.

The trajectory is drawn as a continuous colour ramp encoding time, with three marker classes
called out in a horizontal legend above the grid: a red dot at minimum distance, yellow `+` at each
non-reference state change, cyan squares at each reference state change. Axis labels carry units in
parentheses: "Cross-Track (km)". The distance panel is a smooth descent to a marked minimum and back.

Our `hill-relative` draws one closed ellipse in one projection with no time encoding, no minimum
marker, and no state changes.

### 4. Waterfall, observation time against longitude

Three days of observation time down the vertical axis against longitude across the horizontal, with
several thousand `+` glyphs coloured per object across a large categorical palette. No legend, and
correctly so: the cardinality is far past what a legend can serve.

The structure is the content. Dense vertical bands where coverage is continuous, diagonal streaks
where an object is drifting in longitude over time, and large empty regions. A drifting object
reads as a diagonal, a stationkeeping object as a vertical line, and a manoeuvre as a change in
the slope of a streak - the same discrimination our `longitude-drift` surface trains, in the frame
an operator actually meets it in, surrounded by hundreds of other objects.

**Ours shows one object alone on an empty axis.** Finding the signal in a crowded field is a
distinct skill and we do not train it.

### 5. Orbital plot results, 58204 TJS-10

Six panels of orbital elements over six months: inclination, period, RAAN, eccentricity, apogee,
perigee. Two sources overlaid, KBR in red squares and SPACE_TRACK in blue-grey crosses.

**This one is a manoeuvre-detection drill as it exists in the real world**, and it specifies the
discrimination our `drill-repositioning` item is trying to teach:

● Period sits on flat levels and steps between them: roughly 1436 minutes, then 1443.5, then 1433,
  then back to 1436. Each transition carries one or two isolated outlier points off the level.
● Apogee, perigee and eccentricity all step at the same epochs, in the directions the period change
  implies.
● Inclination ramps smoothly upward across the whole window, and RAAN declines smoothly. **Neither
  responds to the manoeuvres at all**, because both are dominated by natural perturbation.

That last point is the teaching content and we do not have it. The discrimination is not "spot a
step". It is "know which elements a burn moves and which it does not, and read the step in the ones
that respond against the ones that do not". A single-panel longitude plot cannot pose that
question. A six-panel element grid poses it on its own.

## What changes

Ranked by how much it improves the training, not by effort.

1. **Add the element-grid surface.** Six panels, two sources, steps in the responsive elements
   against smooth ramps in the unresponsive ones. This is the single highest-value addition,
   because product 5 shows the real discrimination is cross-element and no current surface can pose
   it.
2. **Sample in passes, not continuously.** Replace the fixed-interval loop with a pass schedule:
   bursts of observations with realistic gaps. This changes every existing surface and adds the
   "is that a change or a gap edge?" question that the job actually asks.
3. **Draw scatter with `+` glyphs; stop drawing polylines through gaps.** A connecting line asserts
   continuity we do not have.
4. **Give colour a job.** Pass index, association type, source, or time-along-track, depending on
   the surface. Every real product does this and it is how an analyst decomposes a dense plot.
5. **Overlay a second source.** Even one alternative element set turns a plot into a comparison,
   and the disagreement is analytically load-bearing.
6. **Add the light-curve surface**, magnitude axis inverted, with the glint band. It unlocks the
   photometric vocabulary that is currently marked "never trained".
7. **Three Hill projections, not one**, with a minimum-distance marker and state-change markers.
8. **Add the crowded-field surface**, a waterfall with the target among many, so finding the object
   is part of the task.
9. **Frame furniture**: units in parentheses on every axis label, a present-epoch marker on any time
   axis, and a provenance footer naming the seed and the generation time. We already carry the seed
   in the debrief; it belongs on the plot.

Items 2, 3, 4 and 9 apply to the three surfaces that already exist and are largely independent of
new content. Items 1, 6 and 8 are new surfaces and need authored items behind them.

## The limitation this does not remove

Everything above makes a generated surface look and behave like a real one. It does not make it a
real one. The flight plan puts the noise model behind an offline UDL characterisation pass (step
4) that has not run, so the amplitude, the pass cadence, the sensor bias and the outlier rate are
all still parameters we chose rather than figures we measured. Making the plots look convincing
before that pass runs makes the shortfall harder to see, not smaller, so the provisional marker
stays on every one of them until real figures replace it.

## The questions, answered

Ash supplied the Sat Xzibit help manual on 30 August. It closes four of the five and changes two
things I had written above.

### The association types are a diagnostic rule, not a legend

**ASTAT is association status**: how strongly an observation matches an element set. ASTAT 1 is
fully associated, ASTAT 2 closely associated. And the other two are not categories at all, they are
a discrimination:

● **Beta residuals reveal orbit PLANE change.**
● **Time residuals reveal orbit SIZE change.**

That is a teachable rule with a physical basis, and it is the residual plot's whole reason for
existing. The manual also gives four distinct causes for residuals leaving the zero line, which
between them make a four-class classification task of exactly the shape our drill format already
serves: the state no longer fits, a manoeuvre has changed orbit size or plane, the orbit fit is
degrading, or the incoming data has a quality problem. Recorded in `docs/TASK-EVIDENCE.md`.

`V Mag Assoc.` is not defined in the manual. By position it is the visual-magnitude residual;
marked as inference, `TBC, re-verify`.

### Interval is a recency bin, and red means "now" across the whole toolset

The light-curve display uses multiple days of observations "with the most recent data shown in
red". The heat map is explicit: colours are date-based, red is the most recent data, blue the
oldest in the range, and a red line marks the current time. LAT/LON uses the same convention. So
the interval legend running 0 to 7 down the left edge of the light curve is a time bin, interval 0
being the most recent, and the blue-to-white ramp is age.

**This is a transfer-of-training problem for PHOSPHOR and I would rather raise it than let it
ship.** In the operator's real tools red means *most recent*, consistently, in at least three
views. In PHOSPHOR red-pink (`--no`, #FFA4A1) means *your call was wrong*. An operator moving
between the two reads the same colour as two unrelated things. Baldwin and Ford's identical-elements
account of transfer says the training environment's surface features should match the job's where
they can, and colour semantics are about as surface as it gets. Options: adopt red-equals-recent
and find another channel for wrongness, keep the PHOSPHOR meaning and accept the collision
knowingly, or use red only for recency on plot surfaces and never for verdicts. **My
recommendation is the third**, because it keeps the two meanings in separate parts of the screen
where they cannot be confused, but it is a design decision and it is Ash's.

### Pass cadence, which is the number change 2 needed

From Ash directly:

| Regime and phenomenology | Cadence |
| --- | --- |
| Low Earth orbit (LEO) | 8 passes per day, split into 2 periods |
| Geostationary (GEO), electro-optical | Consistent coverage, except solar exclusion |
| Passive radio frequency (RF) | Essentially constant |

So a LEO series is roughly four passes in a window, one revolution apart, then a long gap, then a
second window: two dense clusters a day, not an even sweep. The residual product corroborates it,
showing seven clumps across the seven days of the GAOFEN 13 window. GEO optical is near-continuous
through local night with a daylight gap and a solar-exclusion outage; RF has no meaningful gaps,
which makes it the phenomenology an operator turns to when the optical picture goes quiet. That
contrast is itself trainable.

### The waterfall is neighbours, not the catalogue

I had this wrong. Web Waterfall shows "observations from objects within 50 km of the queried
satellite, displayed as longitude over time". It is not a whole-sky view with the target somewhere
in it, it is the target and its close neighbourhood. That makes it a far better fit for the product
than the crowded-field task I proposed: it is a co-location and proximity surface, which is the
rendezvous and proximity operations (RPO) discrimination the flight plan already names.

Change 8 above is therefore rewritten: **not "find the target in a crowded field" but "read the
neighbourhood"**, the target's longitude track among the objects sharing its 50 km, over time.

### Still open

● The Web Waterfall help guide itself did not come through, only the one-line description inside
  the Sat Xzibit manual. If there is more on how the 50 km neighbourhood is selected and drawn, it
  would sharpen the surface.
● ACDC, in "Adjust ACDC Span", is not expanded anywhere in the supplied material. `TBC, re-verify`
  rather than guessed at.
● The manual's RCS section calls the axis "Solar Equinox Phase Angle" while the light-curve
  screenshot's axis reads "Solar Equatorial Phase Angle". The screenshot is the artefact, so the
  plots follow it, but one of the two is wrong and it would be worth knowing which.

## Handling

These are live operational products and tool documentation for publicly catalogued objects. What
has been taken is procedure and visual idiom, not data: no residual value, object pairing,
timestamp, sensor identity or provider characteristic from the screenshots has been copied into
content or code, and the generated series stay synthetic and seeded. Everything sourced from the
manual is attributed in `docs/TASK-EVIDENCE.md` so it can be verified or removed as one block. Say
if any of that needs to be tighter.
