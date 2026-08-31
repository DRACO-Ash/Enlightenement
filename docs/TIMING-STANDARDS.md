# Timing Standards

| | |
| --- | --- |
| **Document** | ENL-GOV-07 |
| **Version** | 1.0 |
| **Date** | 29 August 2026 |
| **Status** | **AUTHORITATIVE.** Transcribed from the JCO Timing Standards document |
| **Classification** | Not Classified |
| **Supersedes** | All inferred timing standards in ENL-GOV-02 v0.1 and v0.2 |

---

## 1. Correction notice

Earlier versions of this pack used a flat 30 minute first-report standard, **inferred from exercise commentary and not from an authoritative source**. That inference was wrong and it was load-bearing: it drove the headline gap statement, the assessment latency bands, and the scoring rubric.

The published standard is two-legged and materially more sophisticated, because it accounts for provider latency rather than holding the crew accountable for it.

---

## 2. The standard

### 2.1 General rule, all NOTSO operations except GEO direct ascent

> **60 minutes from the initial indications, or 30 minutes from the last provider product dropped, whichever is earlier.**

Worked example from the source: on notification of a possible manoeuvre, providers have up to 30 minutes to drop the indicating products, being a waterfall and a residual plot, and the crew then has 30 minutes from that point to produce a report. Where providers deliver in 10 minutes, the 30 minute timer takes precedence.

**The consequence that matters for training.** Fast provider delivery tightens the crew's window rather than relaxing it. A crew that waits for the 60 minute leg when products arrived at 10 minutes has already missed the standard by 20 minutes. **The crew does not control which leg governs, and must therefore track both.**

### 2.2 Rating bands

| Task | Qualified | Partial | Unqualified |
| --- | --- | --- | --- |
| Manoeuvre | 60/30 | 90/60 | >90/60 |
| Rendezvous and proximity operations | 60/30 | 90/60 | >90/60 |
| Photometric change | 60/30 | 90/60 | >90/60 |
| Multiple headcount | 60/30 | 90/60 | >90/60 |
| Separation | 60/30 | 90/60 | >90/60 |
| Breakup | 60/30 | 90/60 | >90/60 |
| Reentry | 60/30 | 90/60 | >90/60 |
| LEO direct ascent | 60/30 | 90/60 | >90/60 |
| LEO launch | 60/30 | 90/60 | >90/60 |
| Geosynchronous and deep space launch | 60/30 | 90/60 | >90/60 |
| On-orbit ASAT | 60/30 | 90/60 | >90/60 |

### 2.3 GEO direct ascent, the exception

Two separate products with two separate clocks.

| Product | Qualified | Partial | Unqualified |
| --- | --- | --- | --- |
| Initial warning report | 30 | 60 | >60 |
| Tracked object report | 90 | 120 | >120 |

The initial warning standard is 30 minutes flat, and it is the tightest standard in the whole framework. That is consistent with the procedure: this is the event where warning time is the entire product, and where the asset needs hours to act.

### 2.4 Daily crew operations

No official timing standards for changeover, logging, tasking, predictive surveillance, state update search, geosynchronous wide search or spectrum tasks.

**Training consequence.** Latency must not be scored on these tasks. Doing so would invent a standard that does not exist. Predictive surveillance is scored on completeness and correctness only.

---

## 3. What this changes

### 3.1 In the Role Performance Statement
Task T5.1 standard is replaced. See ENL-GOV-02 v0.3.

### 3.2 In the Assessment Strategy
Latency bands are replaced by the published Qualified, Partial and Unqualified bands. They are no longer derived from observed performance and no longer need defending as fair, because they are the standard the operator is held to anyway.

### 3.3 In the training design
**A genuinely new training requirement falls out of this and the package does not currently cover it.**

The crew must track two clocks concurrently and know which one governs. The governing leg changes depending on provider behaviour, which the crew does not control and cannot predict. An operator who tracks only the 60 minute leg will systematically miss the standard whenever providers are fast, and providers being fast is the good case.

That is a discrete, trainable, currently untrained competence. Proposed additions:

● A cue for recognising which leg governs
● A drill on computing the deadline from a provider drop time
● Scenario seeds that vary provider delivery speed so the governing leg changes between runs
● A visible dual timer in the scenario interface, since the real environment has one

### 3.4 In the evidence base
The gap statement is corrected. Against the 60 minute leg, five of six observed events were Qualified and one Partial. The AAR authors assessed those same events as late, which indicates they were judging against the 30 minute leg. **That is consistent with the second leg being the one routinely missed, but it cannot be confirmed without provider product drop timestamps.**

**Open item.** Obtain provider drop times for the recorded events so the gap can be quantified against the correct leg. Until then, latency is a qualitative finding supported by contemporaneous assessment rather than a quantified one.

---

## 4. Note on the source

The source table contains two entries numbered 3.1, being Perform Manoeuvre and Perform Multiple Headcount. Assumed a typographical error with no effect on the standards. **[Inference]**

---

*Ends.*
