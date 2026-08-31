# ENLIGHTENMENT training system package

Version 2.10.0, 31 August 2026. **Handover release.** Author: Ash Higgins. Review status: draft, pending redaction review.

Content-as-data for the ENLIGHTENMENT orbital warfare trainer. Everything here is loaded at runtime and editable without a code deployment. Validated by `tools/validate_content.py`, which is standard library only and carries a `--self-test` flag.

**Current state: 17 of 17 self-test assertions pass, 0 validation errors.**

## Version 2.10.0: two procedures, two products, and an order that was wrong

Five source documents in one pass: the docked object, breakup, separation and force package procedures, the rank tasking and maintenance procedures, a verified manoeuvre determination screen and an exercise ephemeris file.

**Corrections first, because two of them were load-bearing.** The determination product column order is Initial, Final, Delta. The package had Initial, Delta, Final, which would have put the answer column in the wrong place in every rendered stimulus. The manoeuvre specifics block runs Apogee before Perigee; the package had them the other way round, and that block is scored positionally, so an operator trained on the package order would have been marked down for reproducing it. The synthesised exemplar already held in the quality model had the right order all along, which is exactly the kind of internal disagreement a validator cannot catch.

**A separation opens at Rank 2 for both parent and child.** The package had the new object entering at Rank 1. Rank 1 is the escalation that follows a conversation with the operations centre, not the entry.

**Two new procedures.** Docked object processing, and force package processing held at draft status because its source is draft. Docking carries the sharpest single idea in this pass: the evidence bar is set by prior expectation. Where a docking capability was assessed, the merged appearance has to hold for about six hours to call a possible. Where it was not, the same evidence has to hold for twice as long. The evidence does not change, the prior does, and the operator has to know which case they are in.

**The rank framework becomes quantitative.** The rank card supplies observation cadences: stare, fifteen minutes, forty-five minutes, two hours, twelve hours, twenty-four hours. That turns a rule appearing in three separate procedures, that increased tasking helps little at Rank 2 and a great deal at Ranks 3 to 5, from an oddity into arithmetic. There is almost no headroom above forty-five minutes and a great deal above twenty-four hours. The card also labels Ranks 0 and 1 as temporary tasking in its own words, which converts a package inference into a sourced statement.

**Dedicated collection is a fixed quantity.** Passive radio frequency capacity is contracted in object counts, so an elevation into the tasking band does not create capacity, it creates a trade. Somebody loses custody. The package had nothing on collection as a constrained resource and now has a cue and a drill on exactly that, with the provider identities and contracted quantities left out because the trade is the trainable part and the commercial detail is not.

**The delta column is not the manoeuvre.** On the observed determination screen the right ascension change of about seven degrees is natural nodal regression across a fit interval of a day and a half. Computed against the stated semi-major axis and inclination it reproduces to about one part in two thousand. The manoeuvre is in the small in-plane numbers. This is now a cue and a drill, and the layout carries the instruction to reproduce it deliberately rather than render a clean table.

**The ephemeris is a file, not a picture.** Exercise data, and fitted rather than propagated: specific orbital energy drifts about six per cent across ninety-six minutes, which two-body propagation would not do. A generator emitting a clean propagation would not look like the real thing. The reading rule that matters is that an osculating perigee radius below the Earth's surface separates a ballistic ascent from an orbit, which is the fastest read there is on a direct ascent profile.

**Element set disclosure for proximity reporting.** Included against a red target, withheld against a friendly one, never for a protected object or a well-tracked uncorrelated track. The package held the equivalent ruleset for direct ascent only.

**Placeholders fall from thirteen to eight.** Extremely close proximity distances close at approximately sub five kilometres in geosynchronous orbit and sub one kilometre in low orbit. The breakup handover key is replaced by a rule rather than a number, because the procedure terminates support on request and states no duration. The separation confirmation pass key is deleted: the procedures commit on the initial headcount and reclassify later, so there was never a count to hold. What remains is five items that must never be filled from outside, two scoring decisions for the training requirements authority, and one genuine gap, the series close approach longitude.

**One conflict is recorded rather than resolved.** The Quick Reference Card calls five kilometres merged. The force package definitions call approximately five kilometres extremely close proximity operations. Both cite cross-tagging. Same distance, two labels, two sources, and it is preserved in the thresholds file as unreconciled.

**Two products gain observed layouts.** The determination table and the ephemeris file. Only the Gabbard diagram now lacks one.

## Version 2.5.0: LEO direct ascent and predictive surveillance

Two procedures that close nearly every remaining threshold and add an object class the package did not have.

**Fully closed.** The LEO direct ascent target filter, which was the gap I most wanted shut because a wrong filter produces a target list that is coherent and wrong: perigee and apogee bounds, the five-degree offset below launch latitude that accounts for dogleg profiles, the azimuth band and window pad, one pass before and three after, and closure at headcount one across three passes. Also the whole predictive surveillance filter set: drifting threshold, element set currency, the sixty-day exclusion, close approach criteria and the tasking window either side of closest approach.

**Four things that are new content, not just numbers:**

● **Known Objects.** A tracked object familiar to analysts with no catalogue entry, labelled inconsistently across providers. Treated as friendly, requires a stability assessment, tasking is not raised on it, and it is the explicit exception to the rule that unranked objects are not processed. The package had no representation of this class at all.
● **Do not raise rank on a drifting object's close approaches.** A drifting object crosses the belt and produces close approaches continuously; almost none mean anything. Slowing is the signal, not proximity. Without this the trainer would teach operators to burn collection capacity on geometry.
● **Longitudinal bounds and turn-arounds.** Objects patrolling between established bounds reverse at the limits, and the turn is where proximity opportunities arise because the object slows near whatever is at that longitude. This converts predictive surveillance from monitoring into forecasting, and it is the clearest case in the package where an analyst can be ahead of an event.
● **Anticipated manoeuvre alerts.** A forecast close approach inside the distance at which an object class habitually manoeuvres away triggers an alert predicting the manoeuvre. The most sophisticated move in the procedure, and it sets up a sharper one: if the forecast manoeuvre does not occur, the object has departed from its own pattern, and that is a stronger finding than the manoeuvre would have been.

**Two corrections.** Grey is not a third state of behaviour for this processing; a Grey high reportable object is treated as Blue, correcting an assumption I drew from the neighbourhood product display. And the manoeuvre notification criteria carry two qualifiers I had missed: a plane change associated with a RAAN flip station keep is processed as station-keeping despite meeting the criterion, and a friendly asset manoeuvring into red collection range opens a do-not-report thread held for a day. That second one is a class of event the package did not model at all, because the analysis habitually looks outward.

**The validator earned its place again.** Restructuring two threshold blocks orphaned four references from the procedures. It failed the build and named all four rather than letting them reach a runtime lookup.

## Version 2.9.0: changeover, and a gap I did not know existed

The changeover procedure closes the thinnest content in the package. Crew resource management was previously an authored sketch built from continuation training and after action findings. It is now the real procedure with eighteen steps.

**The six-point handover brief standard is the important part.** Why the event was opened, who tasked which object to which rank, which timers affect the next shift, what reporting has been accomplished, next steps, and the current checklist step. The last two are the ones most often dropped, and they are the two that carry forward: an event handed over without them leaves the incoming operator re-deriving position and intent from a thread they have not read, while it is running. The Role Performance Statement carried my description of a good handover; it now carries the published standard, and the handover scenario is scored against it.

**Every tasking change is annotated with reason and expiry.** That supplies the missing mechanism behind the temporary-elevation finding from the standing list. An elevation without an expiry becomes permanent by omission, because nothing prompts the step-down. The expiry in the record is what makes it happen rather than relying on somebody remembering.

**Handover quality is decided hours before handover.** The procedure makes explicit what the exercise records implied: the running record is maintained through the shift, and a brief assembled at changeover is a recollection. A shift briefed as quiet when it was not has happened, and the crew giving that brief could not see the failure because they remembered the shift they had.

**Daily tasks are allocated across cells and weekdays** rather than performed by everyone. That is a coordination failure mode the package did not model, and a sharp one: from inside a single cell, a task owned by another cell and a task nobody did look identical. Only the allocation distinguishes them.

**And a gap I did not know existed.** The daily task table lists a Blue predictive surveillance task alongside the Red one. The package models Red predictive surveillance in full, from a procedure supplied earlier, and has no representation of the Blue equivalent at all. It is recorded in the provenance register as an identified gap. If that procedure exists in the same form, it would close in a single pass as photometry and launch did.

## Version 2.8.0: GEO direct ascent, and graded disclosure

The operational GEO direct ascent procedure closes the last substantial threshold block and adds a concept the package had no representation of at all.

**Closed.** Initial target band of 5 degrees either side of the ascending belt intercept, refined to 2.5 once an initial orbit determination exists. Separation notification and written report both within 10 minutes, which is the tightest deadline anywhere in the package and which the procedure advises preparing in advance. Kill vehicle target radius of 100 km from the initial orbit determination, extending to the closest target within 250 km where none is visible. Tasking at each phase, closure hold, and the search fallback when nothing is found on the posted trajectory.

**One refinement to something I had slightly wrong.** I stated the apogee decision as a hard line at belt altitude. It carries a tolerance of about fifty kilometres, so an apogee marginally above the belt still uses the apogee longitude and only a materially higher one switches to the penetration point. That distinction shifts the entire target list, which is why it is the first analytical decision in the procedure.

**Graded disclosure, which the package could not previously express.**

Two rules, and both are judgements rather than mechanics:

● **Disclosure by channel.** The verbal notification to operations centres carries the affected longitude window and not the individual target names. The written report carries the names. A deliberate asymmetry, because the verbal call travels faster and less controllably.
● **Disclosure by phase.** Before separation, an at-risk object is named in the report and its state is withheld. After separation and an initial orbit determination, the state is included. Naming the object warns its operator; publishing its state while an engagement is still being aimed offers precision to anyone reading who should not have it. Once the kill vehicle has separated the engagement is committed, and the warning value to the operator outweighs what the state gives away.

That second rule is the most interesting piece of tradecraft in any source so far, because it is not a threshold or a checklist step. It is a judgement about what a report gives away weighed against what it buys, made differently at different points in the same event. Four cues and four drills now cover it, and the reasoning is taught rather than the rule.

**Thresholds now stand at 14 placeholders, from 87.** Four of those must never be filled by me: the red threat list, the photometry exclusions, the country set, and the threatened longitude band. Two are the TRA scoring decisions. The remaining eight are small durations and distances that no supplied document has stated.

## Version 2.4.0: the quick reference card

A single reference card closed about thirty outstanding thresholds and revealed four things the package did not have. The most productive document of the whole build relative to its length.

**Closed.** Critical plane matching criteria for both regimes, with range as well as angle. Merge at sub five kilometres. Parking at more than three orbits in the vicinity. The full HRR tasking framework, ranks 0 to 5 with collection cadences, which was the document I had asked for and which closes most outstanding rank references across every procedure.

**Four things the package was missing entirely:**

● **The manoeuvre notification criteria matrix.** Period change thresholds by regime, an order of magnitude apart, plus a plane change criterion that qualifies independently. The package had no key for this and it is the primary discriminator between a manoeuvre of interest and routine station-keeping.
● **Reporting mode set by rank.** The same qualifying event produces a written report and a verbal call, a verbal call alone, or nothing, depending on the object's rank. This is the authoritative basis for the restraint rebalancing that had previously rested on inference.
● **The Protect and Defend event priority order.** Thirteen event types ranked. The surge scenario was scoring triage against my authoring judgement with no authoritative order behind it. It now scores against the published order, which is a material improvement to the highest-difficulty scenario in the package.
● **Passive radio frequency collection is capacity constrained.** Fixed contracted slots across two providers with different band coverage. Adding an object means dropping one. A genuine zero-sum tasking trade the package had never modelled.

**And one corroboration worth noting.** The behaviour library's distance-maintaining avoidance archetype was generalised from weekly reporting and stated a floor of roughly thirty kilometres. The card independently records three separate objects manoeuvring to increase distance below that same figure. The archetype was authored before the corroborating reference was seen and the number matched, which is a useful check that the library is not drifting into invention.

## Version 2.2.0: handover release, and what the final audit found

A deliberate defect hunt before handover. It found four things, two of which would have shipped as live faults.

**1. The timing standard in the content was wrong.** The package scored latency against a flat 30 minutes, inferred from exercise commentary. The published standard is two-legged: **60 minutes from initial indications, or 30 minutes from the last provider product dropped, whichever is earlier**, with geosynchronous direct ascent initial warning at 30 flat. Three live scoring rules, two drill explanations and the headline finding in the recurrence register all carried the wrong figure. All corrected.

The correction also surfaced a competence the package did not train: the crew tracks two clocks and must know which governs, and the governing leg flips depending on provider speed, which they do not control. Fast delivery tightens the window rather than relaxing it. CUE-103 and DRL-0114 now cover it, and the interface must render both clocks.

The headline claim is retracted and restated honestly. Against the 60 minute leg, five of six recorded events were Qualified and one Partial. The exercise assessors recorded them as late at the time, which indicates they judged against the tighter leg. **That is consistent with the second leg being routinely missed but cannot be confirmed without provider product drop timestamps**, which are now an outstanding request. The finding is qualitative, supported by contemporaneous assessment, and the quantification is not currently defensible.

**2. Fifty-eight generator names for twelve generators.** Drill authoring accumulated ad-hoc generator names, one per stimulus shape. An engineer reading the drill bank would have tried to build 58 renderers. Consolidated to ten product renderers and two composition modes, declared canonically in the `_generator_contract` block at the top of `drills.json`. Originals preserved as `_legacy_generator` in params for traceability and marked do-not-implement. **This was the single biggest handover risk in the package.**

**3. Four response formats in live use and absent from the schema.** `cross_product_reconciliation`, `reasoned_argument`, `anatomy_question` and `no_action_correct` were all being used and none were declared. The validator passed because it never checked, which is exactly the blind spot a validator exists to prevent.

**4. No provenance trail for numeric claims.** Operator-facing content carries no confidence markers, and should not. But it makes numeric claims, and their sourcing lived only in my head. `content/provenance-register.json` now traces every claim to a source and a confidence level, including the ones marked judgement rather than evidence, and lists what the package deliberately does not claim.

**The validator now has 16 assertions rather than 14.** The two new ones, `generators_canonical` and `response_formats_declared`, exist specifically because they would have caught defects 2 and 3. They run on every session start.

## Version 2.1.0: the synthesis ladder

Synthesis is now the progression spine rather than a drill type. Twenty multi-product drills across five tiers, from a pair of products to the full board with some of it lying to you.

**The end state, stated as the owner put it:** an advanced operator looks at everything available at the time and produces an informed decision with a reasoned, defensible argument for why. Six components make an argument defensible: a conclusion stated plainly, an evidence chain naming which product carries which part, at least one alternative eliminated with its evidence, confidence pegged to the weakest link, a falsifier named in advance, and the gaps stated.

**The falsifier is the component I would defend hardest.** An assessment that cannot be wrong is not an assessment. Naming in advance what would overturn it forces the analyst to test their own reasoning, tells the recipient what to watch for, and protects the analyst when the picture changes, because a revised assessment flagged as provisional is analysis working correctly rather than an error.

**The five tiers.** Pair, two products. Triangulate, three, where no two settle it. Board, four or five, and part of the skill is knowing which not to open. Full board, everything, all eight anatomy questions answered from evidence. Contested board, everything plus degradation, contradiction and a challenge to your argument afterwards.

**The sharpest lesson in the whole ladder sits at tier two.** Optical merging, photometric merging and element set convergence all agreeing does not mean three confirmations. They agree because they share a failure mode: all three degrade the same way when objects become unresolvable. Agreement between products with a common limitation is one indicator, not three, and that judgement now carries the highest single award in the argument rubric.

**Gamification that suits this audience.** The board is the visible progression, filling as the operator advances. A fusion rating tracked separately from the drill rating, because an operator can be excellent at reading a residual plot and poor at building an argument, and averaging hides exactly the thing that matters. Chain length as a personal best. A clean-board award for using everything you opened, because economy is what experienced analysts have that novices do not.

Deliberately not gamified: no streaks on synthesis, since these are long-form and a missed day is normal; no leaderboard on fusion rating, since it is the measure most likely to be read as a judgement of someone's worth; and no time pressure below tier three, because rushing an argument is the failure being trained out rather than in.

**The challenge mechanic is where the calibration lesson lands.** At tier five the debrief poses the strongest available counter-argument. Revising correctly under challenge scores higher than defending a weak position. That is deliberate: an analyst who cannot change their mind on good evidence is a liability regardless of how often they are right.

**Two new progression stages.** Fusion, where an operator stops answering and starts assessing. Advanced operator, which is not simply harder but trains a different thing: producing a defensible argument where a single correct answer may not exist. That is the actual work of a senior analyst and it is not reachable by making earlier drills harder. It is also natural material for site leads and mission area leads, who spend most of their time assessing other people's arguments rather than building their own.

The Elo ceiling rose from 1800 to 2200 to give that band real headroom.

## Version 2.0.0: red team findings implemented

A structured red team of v1.8.1 found the package strong at teaching what to notice and what to do, and weak at teaching what is actually happening and why. A keyword audit put numbers on it: 437 hits for procedural content against 15 for mission and platform knowledge. Against the aim, that was inverted. Five decisions from the owner and the launch procedure closed it.

**The platform library is the largest single addition and closes the largest gap.** Fifteen platform archetypes from public sources only, describing what each class is built to do, how that shows up in observable behaviour, and critically what each class cannot do. The cannot list does more analytical work than the can list because it eliminates hypotheses outright: an object that manoeuvres is not a derelict whatever the catalogue says. This is the knowledge an operator needs to write the mission paragraph every report carries, and to assess intent at all.

The hardest entry in it is servicing against co-orbital attack, where no geometric discriminator exists. The package now teaches the honest position: report the observation, report the demonstrated capability, and state that intent is not observable from geometry. That is a more useful product than a confident guess in either direction.

**The event anatomy framework is the spine the package lacked.** Eight questions applied identically to every event type, with a worked anatomy for each of the seven main types. Questions five and six, what this enables next and who is affected, were the weakest in both the package and four years of released reports, and they carry the heaviest weighting in the new drill class and the highest-value rubric rule. An event matters because of the options it creates, and a report that stops at the event has stopped one step short of the point.

**Synthesis training now exists.** The red team found zero of 81 drills referencing more than one product, which meant the package trained every component of an assessment and never assembled them. A new response format requires reconciling two or more products, including the case where a solve and the geometry disagree and the operator must prefer the one closer to the observations.

**The over-reporting imbalance is corrected.** Twenty no-action drills now, against three before. Knowing when not to report is a competency, and an explicit no-impact statement scores fully because it demonstrates the question was asked.

**Free-text scoring is decided: expert comparison.** The operator writes unconstrained prose; deterministic offline checks detect required elements, anatomy questions, ambiguity failures and register consistency; the debrief then places the operator's report beside the expert's with three specific self-assessment prompts. It cannot mark prose quality and the interface says so rather than implying a judgement it cannot make. The upgrade path to model-assisted scoring is specified as a component swap, and the cost of taking it is recorded: it breaks the air-gap posture and the deterministic replay guarantee.

**Launch is closed.** The last procedure with no cues, no drills and no scenario now has seven cues, four drills, a full rewrite from the real document and its own scenario. It also contains the most explicit latency instruction in any procedure in the package: publish as soon as a candidate track is obtained, even before payload separation.

Coverage after the change: 102 cues, 98 drills, 11 scenarios, 45 general rubric rules. Physical reasoning went from 2 scoring rules to 5, event classification from 5 to 8.

## Version 1.8.0: two years of behaviour, and the sharpest insight yet

76 weekly activity reports spanning 2023 to 2026, plus the advanced direct ascent module.

**The weekly reports solve a problem I could not solve from physics.** Scenario templates said what varies; nothing said what the variation should look like. Without behavioural norms a generator produces events that are physically valid and behaviourally implausible, and an experienced operator notices within one scenario. `content/behaviour-library.json` now holds ten archetypes with their quantified norms, generalised from the corpus so the numbers survive and the object identities do not.

The most instructive is **distance-maintaining avoidance**: objects of interest that manoeuvre specifically to keep close approaches above a consistent floor, repeatedly, over years. Entirely benign in intent and correctly assessed as within pattern of life. An operator who treats every manoeuvre by such an object as significant will over-report constantly, and the genuinely anomalous one will then not stand out.

Also captured: deploy-then-sustained-proximity where the deployed child rather than the parent does the manoeuvring across months; coordinated inclination changes across a launch group where the first mover is the indicator and the rest are confirmation; drift-stop-and-park where the parked longitude and its plane relationships are the event rather than the park; and first-ever behaviour from a known object, where a slight change on an object that has never done it outranks a large routine one. That last archetype directly counters weighting significance by magnitude.

**The tempo finding matters as much as the archetypes.** Events routinely span weeks or months, and a typical week carries several running events alongside new ones. A trainer composed entirely of fresh events teaches a tempo that does not exist, so seeds now carry history.

**The advanced direct ascent module contains the sharpest single analytical insight in any source so far, and it inverts an instinct.** Assuming an electro-optical seeker, the target must be illuminated while the launch site is not, which constrains when a combat engagement is plausible and can be checked before any tracking exists. And the ascending vehicle may receive in-flight trajectory updates, which means **a threatened asset that manoeuvres too early is simply retargeted**. Every operator arrives with conjunction-avoidance instincts where earlier is always better. Debris does not retarget; a guided vehicle does. Warning time exists so the asset can prepare rather than act, and movement has effect once the intercept path is committed and divert capability is limited. Both are now procedure steps, cues and drills, and the retargeting drill is the highest-rated item in the bank.

**One apparent gap, now closed.** Electromagnetic interference appears prominently across two years of weekly reporting and nowhere in this package. Verified with the owner on 29 August 2026: it is carried by a different mission area and is out of scope. Recorded as a scope boundary rather than deleted, so a future reader does not mistake the absence for an oversight and re-open it.

**That exchange produced a method correction worth more than the answer.** The weekly reports aggregate across three regional cells and several mission areas, so frequency within them does not indicate scope for this audience. The released notification corpus is the output of the operators being trained and is the better guide to what they actually produce. Where the two disagree, the notification corpus wins. That rule is now written into the register, because I would otherwise have made the same inference again on the next source.

## Version 1.7.0: the product standard, with its pictures

The vendor product standard again, but the real Word file rather than the text extraction that was in project knowledge. The extraction dropped **11 embedded images**, and those images are annotated worked examples of compliant products. I had built the product definitions from prose alone.

**Four real fields were missing, and one of them is the most operationally direct thing in the package.**

● **Sustained close approach possible.** A true or false column on the coplanar product answering whether a pairing could linger near the primary rather than merely pass it. Lingering is what enables collection, inspection and everything beyond, so this is a direct answer where every other column is an input. It should be the first thing an operator reads, and I had not modelled it at all.
● **The association status taxonomy.** Same, close, nearby and none, each defined by four thresholds set in the tool header. Not a coplanarity flag but a banding of continuous quantities against configurable limits, so the same pair can be close under one configuration and none under another. It is also independent of sustained close approach possible, which is a discrimination worth training.
● **Days to right ascension zero.** The product's own name for the countdown to natural plane alignment, and zero in that column can mean aligned now or no convergence at all. Only the rate separates the two readings.
● **Light curve display modes.** Colour by interval, by sensor hemisphere, or by sensor. This means two of the three photometric scepticism checks are a selector away on the plot already open, rather than products to request. That makes skipping them much harder to justify, and the drill has a correspondingly short time target.

**One connection I had missed entirely.** The pass schedule identifies sensor sites geographically, which makes it the product that shows how much independent hemisphere coverage exists over a period. That links it straight to the photometry procedure's scepticism checks, and until now the package gave an operator no reason to open it during a photometric assessment. Density is not diversity: nine sensors in one hemisphere is one failure mode wearing nine names.

**The lesson for the rest of the package.** A text extraction of a document about visual products loses exactly the part that matters. Worth checking whether any other source in project knowledge is a lossy extraction of something richer.

## Version 1.6.0: the photometry gap, closed

The photometric change procedure. This closes the largest scope gap in the package: photometric change is the third most common report type at 15 per cent of real reporting volume, scores second worst for quality, and until now had no procedure here at all.

**It also resolves an open standards question.** The Pacific report recorded alpha-numeric and numeric identifiers used inconsistently across provider products, with a common standard still being agreed. This procedure states it: where a catalogue number exceeds the five-digit range the object carries both a numeric identifier and an Alpha-5 designator, with the leading digit replaced by an alphanumeric character and the remaining four unchanged, and reports provide both together so they can be cross-referenced. Both forms, not a choice between them. The register and the cue are updated, and the recognition skill remains because provider products will vary until the convention propagates.

**The procedure supplies something no other source has: an explicit scepticism protocol.** Five signatures to look for, being a sharp change with hard angles, a new feature, a complete change to an existing feature, a stable curve becoming a diffuse trend, and a total trend change in a single period. Three reasons to be sceptical, being a single-sensor abnormality, a source that saw the object before and does not see this, and a hemisphere difference. That third set corroborates three artefacts I had already built from other evidence, which is the first time this package has had a procedure confirm an artefact rather than the other way round.

**Two suppression rules now sit before analysis rather than after it.** An exclusion list of objects for which no event is opened at all, and friendly high rate revisit photometry which is not reported unless higher headquarters directs. Both are checked first, because analysis cannot change the answer and doing it first only creates the temptation to publish. The exclusion list itself is externalised and never ships; the package teaches that the check exists.

**And a report type the package did not previously model: cancellation.** Where an event proves not to have met criteria, it is cancelled with a report saying so, not closed quietly. Analysts avoid this because it feels like admitting error. It is the opposite, and everyone who received the original is still holding it.

## Version 1.5.0: the newest exercise, and what junior operators actually do

Advanced-operator observations from the most recent exercise. The most behaviourally specific source in the package, and the one that gets closest to what an individual analyst does at the keyboard.

**Three failures here are new, common, and precisely drillable.**

● **Acting on the latest post without reading the thread.** One provider post carried both a verification of a previously reported possible manoeuvre and a new possible one. The analyst reported only the new item and did not understand that the earlier one also needed verifying. The report had to be corrected before release. A verification is a reportable fact in its own right, because leaving it unstated leaves the recipient holding a possible that is no longer possible.
● **Requesting products that have already been provided.** Recorded as happening almost invariably: the standard product request pasted into a thread, in one case directly beneath the products it was requesting, and one thread left twenty minutes waiting on products already posted elsewhere. The procedural step is request the products you need, not paste the request. It was always a judgement.
● **Generic requests to providers.** Asking for an update without naming a product, without saying what it would resolve, and without tagging a provider tracking twenty concurrent threads. Assessed as signalling proactivity without knowing what to ask for. Product request is now scored on specificity, and a generic request scores zero even though it is technically an action.

**The strongest corroboration is on procedure currency.** A late switch in expected data format plus a pivot to a new procedure for a major event type, with senior instructors and leads still unfamiliar and report timings affected. That is a third instance across two cells and two exercises, so what was recorded as a regional observation is now the most corroborated pattern in the register. A separate observation extends it: an experienced lead returning after several months away started already behind on instructions and procedure changes. The procedure-change policy now covers absence as well as change, because it is the same problem seen from the operator's side.

**One observation is the clearest possible statement of the why gap.** An analyst declined to attach debris states to a breakup notification because the debris came from a friendly object. That delayed the report by about an hour. Debris is tracked for what it will hit, not for what it came from. Every procedure step in this package already carries its purpose; that field now drives a drill rather than only sitting in the authoring.

**And a third instance of one specific class of failure.** Pre- and post-manoeuvre plot colours vary between deliveries. Added to waterfall time direction and identifier representation, that is three conventions recorded as unstable. They are now drilled as one habit rather than three facts: read the legend, the axes and the field definitions before reading the data, including on a product you have read a hundred times. Confidence is what makes this one dangerous.

**Also new: a provider-side artefact with an analyst-side consequence.** Two manoeuvres solved as one, described by the provider themselves as what happens when burns sum faster than the filter can resolve. It produces an inaccurate proximity picture and incorrect categorisation. The discriminator is whether any single burn direction explains the element signature.

## Version 1.4.0: 3,124 real reports, graded

Four years of released NOTSOs, April 2022 to March 2026, across 1,089 event threads. Every one scored against a rubric derived from the standard. This is the only part of the package built on a large sample rather than a handful of documents, and it settles several things that were previously judgement.

**Reporting quality has improved continuously and substantially.** Median completeness rose from 6 of 21 checks in 2022 to 14 in 2026; median length from 102 words to 618. That is real institutional learning, and it has two consequences. The trainer should target the current standard rather than the four-year average. And any claim about this application's effect must be measured against the existing trend, or it will be credited with improvement that was already happening.

**The largest gap, on the largest sample available, is observation without consequence.** Only 38 per cent of released reports contain any impact statement and only 35 per cent assess against pattern of life. Most reports describe. The good ones assess. A report that says what happened without saying what it means transfers the analytical burden to a recipient with less context than the author.

**The second gap is uncertainty signalled but not sized.** 1,899 reports hedge; only 24 per cent of those state a confidence level. Confidence appears in 17 per cent of reports overall and collection limitations in 4 per cent. The possible-versus-verified register is being used as though it were a full confidence statement, and it is a coarse two-state signal.

**A four-level quality ladder** now sits in `content/notso-quality-model.json`, graded from the corpus: bare observation, structured observation, assessed, calibrated. Almost nothing reaches level four. The important caveat is that level four is not always the target: a holding report is a deliberate level one and is correct at that moment, because latency dominates on a first release. The trainer scores against the level the moment warrants.

**The type mix changes the v1 scope question.** Manoeuvre 42 per cent, Launch 24 per cent, Photometric 15 per cent, RPO 8 per cent, Separation 7 per cent. The confirmed v1 scope covers 57 per cent of volume, but Launch and Photometric are the second and third most common types and score in the bottom three for quality. Photometric has no dedicated procedure in the package at all. That is now a recommendation in the model file and question 11 below.

**Length is not quality.** Breakup reports average around 5,000 words at only moderate completeness, while the best manoeuvre reports reach high completeness in 300 to 400. The model states what earns its place and what to cut.

## Version 1.3.0: a second cell, and what that makes possible

An after action report from a different JCO region. With one cell I could only record failures. With two I can separate systemic from cell-specific, which changes how the training is weighted: a systemic pattern is drilled for everyone, a cell-specific one is offered but weighted by the operator's own performance. Telling an operator in one region that they hesitate on reports, when that evidence came from another region, would be both wrong and insulting.

**The finding that matters most is a chain neither report shows on its own.** One cell records that a new force-package procedure was issued to them on the weekend before an exercise with no difference, continuation or gap training, and that the exercise consequently tested initial understanding rather than application. The other cell records that a combined force-package thread handed over to them caused processing uncertainty. Same procedure, two ends of one failure, two continents. The problem was never operator understanding. The procedure entered service faster than the training did.

**That is the observation this application most directly answers**, and `content/progression.json` now carries a procedure-change policy in response. Because a procedure is content here rather than code, a new or changed procedure can be loaded and drilled before it enters service. On a version increment the loader diffs against the previous version, the drill layer re-prioritises the cues attached to changed steps only, and competence is flagged stale for what changed rather than for the whole procedure. A draft procedure can be rehearsed unscored before anyone decides to adopt it. Difference training on demand, in the days before, rather than in the exercise that discovers the gap.

**Four patterns are now confirmed in both cells and are therefore systemic:** object identifier handling, notification discipline, non-routine and newly introduced procedures, and the separation branch. One corroborates a design decision: operators were observed going straight to discovery processing for objects separating from a red asset, which is the branch already carrying the highest classification weight in the package. The sequencing nuance is now explicit in both procedures, because the training decks do not state it plainly: separation first, discovery subsequently if the object remains unidentified. They are sequential stages of one event, not alternative paths.

**One observation changed how the package scores notifications.** Notifications were being simulated by posting in a thread rather than exercising the real process, assessed as removing the chance to build or assess the skill at all. Every mandatory notification step now requires produced wording scored against the must-state list, rather than a completion flag. A notification you can satisfy by clicking done teaches exactly the wrong habit.

## Version 1.2.0: targeted at what this cell actually gets wrong

Eight Live Fly after action reports across two exercises six months apart, with different crews. They change what the trainer is for.

**The headline finding is that the dominant failure is not error, it is latency.** Across six recorded direct ascent events, first report latency against a thirty minute standard ran to 37, 49, 55, 56, 60 and 61 minutes, averaging 53. The analysis was generally sound and target identification generally correct. What was missing was willingness to publish before the picture was complete.

**And then, on the final day of the second exercise, the same cell delivered six first reports in 16 to 30 minutes, most in the 20 to 25 band.** Nothing about the events was easier. What changed was that the crew had done enough of them that the response had become the norm. One report states the mechanism outright: education improves confidence, confidence improves situational awareness, and that reduces report times.

That is the strongest available argument for this application, and it was written by an exercise observer rather than by a designer. The gap is not knowledge and it is not capability. It is repetition. Scoring targets are now calibrated to the cell's own demonstrated performance rather than to an imposed standard.

`content/recurrence-register.json` holds eighteen patterns with their evidence trails, root causes and the mechanism that trains each one out. Two new competency axes were added because the existing six could not carry these failures: **CMP-07 decision commitment under time pressure** and **CMP-08 event lifecycle ownership**. Sixteen cues, twelve drills, three scenarios, sixteen rubric rules and one artefact followed.

The three new scenarios target the register directly: a surge scenario where load deliberately exceeds capacity and triage is scored, an out-of-order scenario where the consequence arrives before the cause, and a handover scenario where the brief omits threads that are then the operator's problem.

**The mirror-image finding matters too.** On time-critical events the failure is hesitation; on ambiguous proximity events it is assessments running ahead of the evidence, particularly on docking judgements. Both are now trained, and they pull in opposite directions, which is why a single "be more decisive" message would have been wrong.

## Version 1.1.0: corrected against real products

Version 1.0.0 was authored from the training decks, the AARs and the written product standard. Version 1.1.0 corrects it against five real provider screens and a seven-report operational NOTSO thread. Five things were wrong, and they were wrong in the same direction: the written standard describes what a product must contain, not what an operator looks at.

● **The light curve is plotted against solar equatorial phase angle, not time.** This was the largest error. Plotting against phase angle is how the geometry effect is designed out, so the artefact I built a drill around is partly handled by the product itself. The real skill is comparing intervals at matched phase angle. The magnitude axis is also inverted, and a generator that renders brighter downward would train the wrong reflex outright.
● **The waterfall is dense observation scatter, not clean traces.** Tens of thousands of observations, and extracting one drifting object from that density is itself the trained skill. A generator producing a handful of tidy lines would make the drill far easier than the real product, which is the worst kind of training failure because it is invisible.
● **Residual departures are small.** The vertical scale runs to a few hundredths. My description implied a visible excursion. The product also annotates candidate manoeuvre times with period and inclination deltas in a tooltip, which hands the operator the burn direction directly and changes the workflow.
● **The neighbourhood carries delta-v and a provider score as columns.** Assessing closure cost is reading a column, not performing a calculation. The score is a provider heuristic and is now modelled as an artefact, because treating it as the answer is a real failure mode.
● **TRIC state change markers are not manoeuvres.** They indicate the solution was refitted. Counting them as burns is now the highest-difficulty discrimination drill in the bank.

Two new content files carry this: `content/product-layouts.json` holds the observed structure of each screen and the generator contract derived from it, and `content/notso-templates.json` holds report structure, register conventions and scoring hooks taken from the real thread. Ten cues, ten drills and three artefacts were added.

## What is in the package

| File | Holds | Count |
| --- | --- | --- |
| `schemas/enlightenment.schema.json` | Every content type, as JSON Schema `$defs` | 10 types |
| `content/competencies.json` | The scoring axes | 8 |
| `content/products.json` | Provider products: what they must contain, how to read them, how they are misread | 10 |
| `content/product-layouts.json` | Observed screen structure, axes, columns, controls, generator contract | 9 screens |
| `content/notso-templates.json` | Report templates, register conventions, scoring hooks | 4 templates |
| `content/notso-quality-model.json` | Four-level quality ladder graded from 3,124 real reports | 4 levels |
| `content/behaviour-library.json` | Behaviour archetypes with quantified norms, for scenario realism | 10 archetypes |
| `content/platform-library.json` | What each class of object is for and what it cannot do | 15 archetypes |
| `content/event-anatomy.json` | The eight questions that constitute understanding an event | 8 questions |
| `content/synthesis-ladder.json` | Five-tier fusion progression, gamification and argument scoring | 5 tiers |
| `content/provenance-register.json` | Source and confidence for every claim made to operators | 27 claims |
| `content/recurrence-register.json` | What these cells repeatedly get wrong, with cross-cell analysis | 40 patterns |
| `content/artefacts.json` | Data artefacts that mimic real signals | 22 |
| `content/procedures/procedures-core.json` | Manoeuvre, RPO, Separation, Breakup, UCT Discovery, Photometry | 6 |
| `content/procedures/procedures-extended.json` | DA-ASAT LEO and GEO, Predictive Surveillance, Launch, CRM | 5 |
| `content/cues.json` | Atomic recognisable patterns, each with its discrimination pairs | 103 |
| `content/drills.json` | Rated production-format drill items | 114 |
| `content/scenarios.json` | Parameterised scenario templates with EBAT trigger events | 12 |
| `content/traces.json` | Expert traces for the debrief overlay | 5 |
| `content/rubrics.json` | Scoring as declarative decision tables | 3 |
| `content/progression.json` | Mastery gates, spacing, adaptive and procedure-change policy | 7 stages |
| `content/thresholds.example.json` | Externalised operational thresholds, placeholders only | 27 refs |
| `tools/validate_content.py` | Validator with self-test | |

## The five decisions that shape everything

**1. The answer is never on screen.** No drill uses a multiple-choice format and the schema does not permit one, enforced by the validator as a hard error. If the answer is visible the operator is pattern-matching rather than retrieving, and the retention benefit largely evaporates. Distractors live in the `reject` list and are used only after the operator has committed, to teach in the explanation.

**2. Cues are the unit, not procedures.** The spacing scheduler tracks individual cues. A miss on a cue schedules that cue to return sooner, and it returns inside a full scenario rather than as an isolated card. That is what keeps the spacing invisible and stops the app feeling like flashcards.

**3. Every scenario carries a distractor.** A scenario in which every anomaly is real trains over-reporting, which is a real operational failure mode. The artefact library exists so that synthetic data can be wrong in the ways real data is wrong. Escalating a distractor is penalised less than missing a real event, because over-caution is the safer failure.

**4. Discrimination is authored explicitly.** Every procedure has a `not_this_procedure_when` field and every cue has `confusable_with` entries with named discriminators. Expert perception is discrimination between look-alikes, not association with labels, so the look-alikes are first-class content rather than an afterthought.

**5. Operational thresholds are externalised.** Every number that could change with a procedure revision lives behind a `threshold_ref` key resolved from `thresholds.local.json`, which does not ship. Three benefits: tasking values and distance criteria stay out of the repository, a threshold revision is a config change rather than a content release, and the app stays honest that the numbers belong to the procedure rather than to the app.

## Source traceability

Authored from the continuation training decks (RPO, Space Warfare and Separation, Orbital Elements and Manoeuvres, Crew Resource Management and Breakup, Predictive Surveillance, Launch and xGEO, Space Weather and Orbital Laws), the DA-ASAT theory and procedure deck, the vendor product standardisation draft, and six after action reports. Every content file names its sources in its `_version.source_refs` block.

The AARs earned their place. They supply what the training decks cannot: what actually goes wrong. Cross-tagging onset distances, the neighbourhood filter that hid the objects that mattered, observations published without states, the ambiguity of a merged optical picture, and the value of a pattern-of-life comparison nobody had made. Nine of the fifteen artefacts come from AAR findings rather than from doctrine.

## How to run the validator

```bash
python3 tools/validate_content.py --content-dir content
python3 tools/validate_content.py --content-dir content --self-test
```

Exit codes: 0 clean, 1 validation failures, 2 usage or IO error. Wire the self-test into `simulate-pipeline.sh` so malformed content fails before upload rather than at runtime.

The validator checks cross-references, identifier formats, production-format compliance, threshold resolution, and coverage. It also runs a redaction tripwire that warns on any bare five-digit token in shipped content, on the basis that it is probably an object catalogue number.

## Loader requirements

Three behaviours the runtime must implement, which are content decisions rather than engineering ones:

● **Refuse to serve a scored scenario when a required threshold is still a placeholder.** An operator seeing `PLACEHOLDER` in the interface is a bug. Unscored sandbox use may proceed.
● **Reject a seed that fails its solvability check** rather than serving it. An unsolvable scenario is a scoring injustice and will be recognised as one.
● **Record the content version hash on every run**, so a debrief months later is still interpretable against the procedure version it was scored under.

## What is deliberately not here

● **Real object identifiers.** Scenarios use synthetic objects. Historical basis fields reference publicly reported events in generalised terms.
● **Watchlist membership, tasking values and distance criteria.** All externalised.
● **Slide content.** Being handled separately.
● **Generator implementations.** The `stimulus.generator` fields name generators the physics core must provide. The contract is here; the code is a build task.

## Gaps, stated plainly

These are real and are warnings in the validator output, not oversights:

● **14 of 91 cues have no drill item.** Listed in the validator output. Roughly three hours of authoring.
● **5 of 10 scenarios have no expert trace**, so they cannot be debriefed and must not be scored until they have one. The three v1 scenarios are traced.
● **Every expert trace needs second-expert validation.** The `validated_by` field reads TBC on all five. An unvalidated scorer is a wrong answer delivered with confidence, which is the exact failure this application exists to prevent.
 Procedures are authored; scenarios are not.
● **All thresholds are placeholders.** Nothing can be scored until `thresholds.local.json` is populated.
● **All content is `draft` status**, not `redaction_reviewed`.

## Redaction note on the weekly activity reports

76 reports naming hundreds of specific objects with catalogue numbers, longitudes, report links and named personnel across three regional cells. None of it is here. Every archetype is generalised to a behaviour class with its quantified norms retained, because the numbers are what make a generated scenario feel real and the identities are what must not travel. An operator trained on the archetypes recognises the behaviour anywhere; one trained on the identities only recognises those objects, which is worse training as well as worse practice.

## Redaction note on the photometry procedure

The source carries an explicit do-not-open object exclusion list by catalogue number, a notification tool address, and internal tool click-paths. All excluded. The exclusion list is externalised to the local thresholds file and never ships. The procedure in this package teaches that the check exists and must be performed before any analysis; it does not carry the list, and it never will.

## Redaction note on the advanced-operator observations

**The most sensitive document in the package by a clear margin, and it deserves a direct flag rather than a footnote.** It names approximately a dozen individuals, pairs each with their nationality, and attaches adverse performance judgements including complacency, laziness and apathy. It also identifies specific named people as struggling, overwhelmed, or held back by language.

None of that is in the package. Every name, nationality and individual judgement was excluded and each observation is recorded impersonally as a behaviour pattern.

Separately from this build: that document contains adverse personal data about identifiable individuals from several allied nations, written in terms that would be difficult to defend if the subject read it. It is worth deciding deliberately how it is stored, who receives it, and whether the individual-level judgements need to be separated from the pattern-level observations before it circulates further.

## Redaction note on the NOTSO corpus

The strongest redaction case yet, and the largest source. 3,124 real released notifications containing live object names, catalogue numbers, element sets, longitudes, provider names, analyst names and operational assessments. None of it is in the package. **Every exemplar in the quality model is synthesised to preserve a structural pattern; nothing is quoted from the corpus and no object in any exemplar is real.** All statistics are aggregate and non-attributable.

## Redaction note on the exercise after action reports

The second-region source additionally names internal procedures, a controlling instruction reference, fusion provider organisations and a specific object with both its identifiers. All excluded. The identifier issue is recorded as a format pattern rather than by example, which loses nothing instructionally.

The strongest redaction case in the package. The source reports name individual operators, national contingents, satellite designators, thread identifiers, internal tool names, provider names and email addresses. None of it is here.

Two categories were excluded on principle rather than merely omitted:

● **Individual and nationality-linked performance criticism.** Several reports assess named operators and one assesses the participation of a national contingent. That is personal data about identifiable people, some of it adverse, and it has no place in a distributable training artefact whatever the marking on the source. **Flagging it specifically because it also warrants a look at how those reports themselves are stored and shared.**
● **Internal tool names and click-paths.** The register describes what operators do, never which button.

What remains is behaviour patterns, root causes and timings.

## Redaction note on the version 1.1.0 sources

The NOTSO thread supplied is operational. It contains live object names, catalogue numbers, element sets, assessments and provider attributions. **None of that is in this package.** What was extracted is sentence structure, field order, register conventions and cadence. The validator's catalogue-number tripwire runs over every shipped file and is now refined to suppress legitimate count fields, so it reports signal rather than noise.

The same applies to the product screens. Layouts, axes, column names, control names and reading rules were taken. Object names, longitudes, threshold values and provider identities were not.

## Questions needing a steer

1. **Threshold population.** Who populates `thresholds.local.json`, and does it live in a config store or on the storage volume?
2. **Trace validation.** Who is the second expert? This blocks scoring, not building.
3. **Historical events by name.** Scenarios currently generalise. Naming the SJ-21 and SJ-25 sequence or the Intelsat 33E event explicitly would improve engagement and recognition, and all three are publicly reported. Is naming them acceptable?
4. **Accuracy floor.** The gates use 0.8, matching the continuation training testing standard. Confirm that is the right bar for a trainer where the pass condition is retention rather than a single assessment.
5. **Product list completeness.** Ten products are modelled. Are there others crews routinely request?
6. **Waterfall density target.** Real products carry observation counts in the tens of thousands. Is that the density the trainer should reproduce from the outset, or should foundation-stage drills use a reduced density that increases as the operator advances? My inclination is to reduce it early and ramp it, but that is a training judgement rather than a technical one.
7. **Two new competency axes.** CMP-07 and CMP-08 are mine, derived from the exercise evidence rather than from any framework. Eight axes risks false precision on a skill radar. Confirm you want both, or whether lifecycle ownership should fold into procedure recall.
8. **Cross-cell weighting.** Systemic patterns are drilled for everyone; cell-specific ones are weighted by the operator's own performance rather than by their cell. Confirm that is right, and whether operators should see which patterns came from which region.
9. **Procedure-change mode.** Needs a procedure-diff implementation and a decision on who authors the change summary. Strongest capability claim in the evidence base, currently a build item rather than a solved problem.
10. **Scope, again.** Photometry is now covered. Launch remains: 24 per cent of real reporting volume, bottom three for quality, and no scenario. If you have the launch procedure to hand it is the last gap of any size.
11. **Latency targets.** Scoring uses green at or inside 25 minutes, amber to 30, red beyond, calibrated from the cell's own demonstrated performance. Confirm that is fair rather than punitive for a trainer.
9. **Provider score.** Should the trainer reproduce the score column at all? Modelling it teaches operators to treat it as an input rather than an answer. Omitting it means they meet it for the first time on the real product. I have modelled it, and it is reversible.
