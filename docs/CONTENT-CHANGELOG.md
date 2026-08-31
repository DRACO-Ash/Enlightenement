# ENLIGHTENMENT content package v2.10.0

**Date:** 31 August 2026
**From:** v2.9.0
**Validator:** 17 assertions, 17 passing, 0 errors, both before and after.

## Sources consumed

● JCO Docked Object procedure
● JCO Force Package procedure (DRAFT)
● JCO HRR Object Tasking and HRR Maintenance procedures
● JCO Breakup procedure
● JCO Separation procedure
● Fusion provider verified manoeuvre determination screen, observed 31 Aug 2026
● Exercise ephemeris file, STK .e format, observed 31 Aug 2026, confirmed by the owner as exercise data and fitted

## Corrections

| Was | Now | Where |
| --- | --- | --- |
| Determination product columns Initial, Delta, Final | Initial, Final, Delta | `drills.json` generator contract, `products.json`, new layout |
| Manoeuvre specifics block Perigee before Apogee | Apogee before Perigee | `notso-templates.json` TPL-VERIFIED-MANOEUVRE |
| Separated object enters at Rank 1 | Parent and child both enter at Rank 2, discretion higher; Rank 1 is the escalation | `thresholds.example.json` separation.tasking_ranks |
| Breakup handover expectation declared in days, with an unsourced days to weeks estimate | Request terminated, not time bound, with a 30 day final closure leg | `thresholds.example.json` breakup.handover_expectation |
| Separation notification unconditional on establishing the headcount | Gated on the top three ranks; the same gate appears in docking and force package; breakup remains unconditional | thresholds, PROC-DOCK, PROC-FP |
| `separation.confirmation_passes` awaiting a value | Key deleted. The procedures commit on the initial headcount and reclassify later | `thresholds.example.json` |
| `breakup.coverage_duration` a single under-specified key | Split into four durations the procedure actually states | `thresholds.example.json` |

## Placeholders: 13 to 8

Closed: `rpo.type_distances.extremely_close_geo` at approximately 5 km, `extremely_close_leo` at approximately 1 km, `breakup.handover_expectation` as a rule, `breakup.coverage_duration` split and populated, `separation.confirmation_passes` deleted.

Remaining eight: the five that must never be filled from outside, the two scoring decisions for the training requirements authority, and `rpo.type_distances.series_close_approach_longitude`, which is now the only operational threshold genuinely still owed.

## Unreconciled, preserved not resolved

`rpo.type_distances._unreconciled`. The Quick Reference Card holds 5 km as merged. The force package definitions hold approximately 5 km as extremely close proximity operations. Both cite cross-tagging. Owner to decide which term the operator should use.

## Additions

● **PROC-DOCK**, docked object processing, ten steps, three decision points, status active.
● **PROC-FP**, force package processing, eleven steps, three decision points, status draft to match its source, with a status note against use in scored assessment until the source is issued.
● **Observed layouts** for `PRD-DC-TABLE` and `PRD-EPHEMERIS`. Only `PRD-GABBARD` now lacks one.
● **CUE-125** delta column carrying natural drift, **CUE-126** elevation with no spare collection capacity, **CUE-127** target element set in a proximity report. Each has a drill, so the undrilled cue count is unchanged at 15.
● **DRL-0138 to DRL-0140.** DRL-0139 uses the `threshold_call` response format, which was declared in the schema and previously unused.
● **Threshold groups** `docking`, `force_package` and `hrr`, plus breakup and separation close approach screening ladders and the missing non-threat rocket body launch profile.
● **Nineteen provenance claims**, marked fact, derived or inference, including the two computed findings and one explicit unknown.

## Computed findings, marked

**Derived.** On the observed determination screen the right ascension delta is natural nodal regression across the fit interval, reproducing to about one part in two thousand against the stated semi-major axis and inclination. The manoeuvre is in the small in-plane numbers. Argument of perigee behaves the same way but is poorly conditioned at near-circular eccentricity and no crisp rule is claimed for it.

**Derived.** The exercise ephemeris is not Keplerian-consistent. Specific orbital energy drifts about six per cent across 96 minutes. A generator emitting a clean two-body propagation will not resemble the real product.

**Inference, with an explicit unknown.** The stated delta-v on the determination screen does not reconcile with the element changes, by roughly a factor of two to three. Whether the field is operator entered or computed by another route is unresolved and sits with the owner. No generator should derive that field from the table until it is.

## Redaction

The force package source carries protected object catalogue numbers. They are not in the package. The determination screen carries a live catalogue identifier and it is not in the package. Provider identities, contracted object counts and named tools remain excluded, consistent with the existing abstraction to cataloguing authority, operations centre and higher headquarters. The five-digit tripwire fired zero times across the whole content directory after the change.

## Warning delta

Two warnings cleared, being the unused response format and two of the three missing layouts. One warning gained: `PROC-DOCK` and `PROC-FP` have no scenario yet. Total unchanged at 19.

## Still open

● Seven scenarios untraced, five existing traces unvalidated.
● Blue predictive surveillance procedure not supplied.
● Two new procedures need scenarios.
● The merged versus extremely close conflict.
● The delta-v field question above.
