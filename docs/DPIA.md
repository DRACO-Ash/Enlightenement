# Data Protection Impact Assessment: ENLIGHTENMENT

**Status:** DRAFT for Data Protection Lead (DPL) review. Not signed. No named-individual
performance record may be written until this is signed.
**Activity:** ENLIGHTENMENT orbital warfare training application, Bluestaq App Store deployment.
**DPL and author:** Ash Higgins, Technical Director and Data Protection Lead.
**Approver:** Managing Director. Name `TBC, re-verify` on entry to REG-003: the role is the one
this project's governance names as approver, and the individual is not corroborated by anything in
this repository, so the unknown marker applies rather than an asserted name.
**Record location:** REG-003 (Data Protection records, DPIA log). This copy travels with the
application source; REG-003 holds the authoritative signed version.
**DPIA reference:** `TBC, re-verify` (allocate on entry to REG-003).
**Drafted:** 20 August 2026.

## Step 1: Screening decision

**Decision: MANDATORY.** A DPIA is required under Article 35 of the United Kingdom General Data
Protection Regulation (UK GDPR). This is not a marginal call.

### The mandatory trigger

**Article 35(3)(a): systematic and extensive evaluation of personal aspects relating to natural
persons, based on automated processing, including profiling.**

Article 4(4) defines profiling as automated processing used to evaluate personal aspects
"in particular to analyse or predict aspects concerning that natural person's **performance at
work**". That is precisely and only what ENLIGHTENMENT does. Specifically:

● Six competency axes scored per operator, each carrying a confidence interval.
● An Elo rating per operator, updated on every drill answer.
● A Brier score on the operator's own stated confidence.
● Free-Spaced Repetition Scheduler (FSRS) state per operator per item, which decides what that
  operator is shown next and when.
● Immutable run artefacts holding the seed, event log, content version hashes, and a full score
  decomposition, retained so a debrief months later is still interpretable.

Systematic: yes, by design, on a fixed timestep with an authoritative server clock. Extensive:
yes, every answer, every timing, every stated confidence, retained per run.

### Also present

● **Behavioural tracking of an identified individual.** Every drill response, response time,
  confidence statement and run is attributed. On the ICO's list.
● **Evaluation or scoring.** The product's entire purpose.
● **Systematic monitoring.** Continuous within the application.
● **Highly personal data in an employment context.** Performance data that can affect a career is
  treated as highly personal by the ICO even though it is not Article 9 special category data.
● **Innovative organisational solution.** Applying spaced repetition, Elo rating and proper
  scoring rules to operator competency is novel in this setting.
● **Power imbalance.** Employer to employee, with supervisor visibility of individual results
  decided by the owner on 16 August 2026.

### Explicitly NOT present

Recorded because their absence narrows the assessment and each is a design decision rather than
an accident.

● **No Article 9 special category data and no Article 10 criminal offence data.**
● **No children's data, no biometrics, no genetic data.**
● **No invisible processing.** The design mandates that operators are told, at first run and in
  the interface, exactly what a supervisor can see, in the same words the supervisor sees it.
● **No large-scale processing.** Ten concurrent operators, one shift crew (owner-confirmed,
  16 August 2026). Scale does not reduce the requirement: the Article 35 threshold is impact on
  individuals, not organisational size.
● **No data matching or combining across sources.** All scenario data is authored or generated
  in-application. The offline Unified Data Library (UDL) characterisation pass emits a noise-model
  parameter file of statistical distributions only, with no records, no object identifiers and
  nothing traceable to a real asset.
● **No Large Language Model (LLM) and no outbound network call at runtime.** The air-gap posture
  is a design requirement, so there is no inference-time data handling, no prompt retention and no
  third-party model provider in scope. Handbook Annex J does not apply.

### Open questions that change the assessment

These must be answered before sign-off, because two of them could escalate the residual risk.

1. **Will readiness output inform shift assignment, console authorisation, task allocation or
   progression?** If yes, Article 22 (automated decision-making) engages and the DPIA must address
   meaningful human review, the right to an explanation, and the right to contest. The declared
   purpose is training development and readiness assurance, which does not; the risk is purpose
   creep, not the current design. **Owner: Ash.**
2. **Can Bluestaq LLC personnel or App Store platform administrators outside the United Kingdom
   access the storage volume or the running pod?** If yes, this is a restricted transfer and needs
   the International Data Transfer Agreement (IDTA), the UK-US Data Bridge where applicable, and a
   Transfer Risk Assessment (TRA). The skill records that a TRA should exist for the parent
   relationship; it must be referenced here rather than repeated, and its existence
   `TBC, re-verify`. **Owner: Ash.**
3. **Retention period for detailed run artefacts.** Open in the flight plan. **Owner: Ash as DPL.**
4. **Staff consultation route.** Open in the flight plan. **Owner: Ash as DPL.**

**Next step:** proceed to Step 2. Screening decision to be recorded in REG-003 whatever the
outcome, per the rule that the absence of a DPIA is itself evidence.

## Step 2: The assessment (Article 35(7))

### 1. Description of processing

**Nature.** ENLIGHTENMENT presents a military space domain analyst with short, rated training
scenarios and drills, scores their response against the governing procedure's own expected
response, and retains the result. It computes and stores a competency estimate per axis, a
difficulty rating, a calibration score, and a spaced-repetition schedule that determines what that
operator sees next. It replays a scored run from its seed and event log so the operator and a
supervisor can see what was missed and why.

**Scope.**

| | |
|---|---|
| Data subjects | Military space domain analysts and Protect and Defend operators in the Joint Commercial Operations (JCO) cell and adjacent UK Space Command roles; content authors and instructors; supervisors |
| Volume | Up to ten concurrent operators, one shift crew (owner-confirmed, 16 August 2026) |
| Data categories | Ordinary personal data only: identity (name or username), authentication credential material, competency estimates per axis with confidence intervals, response accuracy and timing, stated confidence, drill and scenario history, FSRS scheduling state, immutable run artefacts, supervisor access audit records |
| Special category | None |
| Geography | United Kingdom. Bluestaq App Store, `enlightenment.apps.bluestaq.com`. Transfer position at screening question 2 |
| Duration | Detailed run artefacts: retention `TBC, re-verify`. Aggregate competence: for the duration of the operator's role |
| Classification | Not classified (owner-confirmed, 16 August 2026), for both this work and the source procedures |

**Context.** The relationship is employer to employee, so there is an inherent power imbalance and
consent is not an available lawful basis. Operators work shift patterns in shared operations rooms
under time pressure. The flight plan records that this user group is "highly allergic to anything
that feels childish or like surveillance", and that Self-Determination Theory evidence says
perceived surveillance erodes the intrinsic motivation the product depends on to work at all. That
is not only a design risk: it is the reason the transparency controls below are load-bearing rather
than decorative.

**Purpose.** Build instant, correct recall of the action required for each event type in the
procedure library, so that when a real event occurs the operator already knows what to do without
looking it up. The benefit to the individual is direct and substantial: demonstrable competence,
and a safe place to be wrong in private before being wrong on shift.

**The declared purpose is training development and readiness assurance.** It is not performance
management and it is not discipline. If the data is later used for either, that is a new purpose
requiring a new privacy notice and a revision of this DPIA.

### 2. Necessity and proportionality

**Lawful basis (Article 6).** Recommendation: **Article 6(1)(f), legitimate interests**, supported
by a documented Legitimate Interests Assessment (LIA), with Article 6(1)(e) public task considered
if the processing is later carried out under a specific statutory function. `TBC, re-verify: DPL to
confirm and complete the LIA.`

**Consent is not available.** In an employment relationship the imbalance of power means consent
cannot be freely given, so it cannot be the basis. This is stated explicitly because "the operator
agreed to use the trainer" is the intuitive and wrong answer.

**No Article 9 condition is required.** No special category data is processed.

**Less intrusive alternatives considered.**

● **Anonymous or pseudonymous scoring with no persistent identity.** Rejected: the spacing
  scheduler and the competency estimate are per-person by construction, and a trainer that cannot
  remember what an individual has forgotten cannot do the one job it exists for.
● **Aggregate-only reporting with no individual record.** Rejected for the same reason. Retained
  in part: supervisor views surface current competence, coverage and decay, not raw failures.
● **Self-reported competence.** Rejected: the product exists because the gap between stated and
  actual recall is what causes confident errors.
● **Local-only storage in the browser.** Rejected: the design forbids browser storage, and it
  would prevent the operator from moving between consoles.

**Data minimisation applied.**

● No special category data, no biometrics, no location, no free-text about people.
● **Sandbox and free analysis are never scored and never reported.** Operators need a place to be
  wrong in private or they will not explore.
● **Supervisor views surface competence, coverage and decay by axis. They do not surface raw
  failed attempts, sandbox activity, or drill misses.** A drill miss is the mechanism by which the
  product works; reporting it would destroy the loop it measures.
● No analytics, no telemetry, no third-party processor at runtime.

**Accuracy measures, all of them REQUIRED and none of them yet built.** The tense matters and an
earlier version of this paragraph got it wrong, describing every one of these as though it existed.
Nothing here scores anything today.

● Every run must record the exact content version hash it was scored under, so a score stays
  interpretable against the procedure that produced it.
● The scoring engine must decompose every score into which rule fired, on which evidence, against
  which procedure version, so an operator can see and challenge the basis of a result.
● Competency estimates must carry confidence intervals and must never be presented as a bare
  number.

A DPIA that credits a control it wants rather than a control it has is worse than one that admits
the gap, because the gap is what the conditions in Section 6 exist to close.

**A material control, stated plainly: the scorer must be validated against expert human raters on a
held-out set before any operator is scored by it.** An unvalidated automated scorer producing
personal data about someone's professional competence is an accuracy risk to the individual, not
only a product-quality issue. The flight plan makes this a gate rather than a task.

**Retention justification.** Two tiers. Detailed run artefacts age out on a defined schedule;
aggregate competence persists for the duration of the role. Rationale: the debrief value of a run
artefact decays quickly, whereas the coverage and decay picture is the readiness record.
**Period `TBC, re-verify`. Recommendation: 12 months for detailed run artefacts, reviewed
annually.** The recommendation is the DPL's to accept or change.

**How individuals will be informed.** A privacy notice at first run, before any scored interaction,
plus a persistent statement in the interface. It must state, in the same words the supervisor sees:
what is collected, what the supervisor can see, what the supervisor cannot see, the declared
purpose, the retention period, and how to exercise rights. Per POL-002 Section 09.

**Data subject rights.**

| Right | How it is met |
|---|---|
| Access | Export of the operator's own record: competency estimates, history, run artefacts |
| Rectification | Score decomposition names the rule and the evidence, so a disputed score is challengeable and correctable |
| Erasure | Deletion of identity and detailed artefacts. Aggregate readiness figures may be retained anonymised where the legitimate interest survives; to be settled in the LIA |
| Restriction | Suspension of scoring for an individual without loss of access to practice |
| Portability | Not engaged: the basis is legitimate interests, not consent or contract. Export is provided anyway under access |
| Objection | Absolute in relation to any later use for performance management, and a trigger for revising this DPIA |

**International transfers.** United Kingdom deployment. See screening question 2. Where the parent
relationship is engaged, the IDTA and the UK-US Data Bridge apply, supported by the existing TRA
for the parent relationship, which is referenced rather than repeated and whose existence is
`TBC, re-verify`.

### 3. Consultation

| Party | Status |
|---|---|
| Ash Higgins, DPL | Author of this assessment |
| Managing Director (name `TBC, re-verify`) | Approver. Not yet consulted on this draft |
| Affected staff (operators) | **Not yet consulted. Required before sign-off.** Route `TBC, re-verify` |
| Supervisors | Not yet consulted. Should see the notice text they are described by |
| Processors and suppliers | None at runtime. Bluestaq App Store is the hosting platform; access boundary at screening question 2 |

**Data subject consultation is not optional here and should not be waived.** The processing is
about professional competence, in an employment relationship, with supervisor visibility. The ICO
expects consultation where individuals' interests are engaged this directly, and the flight plan
identifies voluntary return rate as the early-warning metric for exactly the trust this
consultation protects. A single point of failure is noted: Ash owns product, classification,
redaction sign-off, expert-trace authoring, the deploy decision and the DPL role.

### 4. Risk identification

Risks to the rights and freedoms of individuals, not to the organisation.

| # | Risk | Likelihood | Severity | Rating |
|---|---|---|---|---|
| R1 | **Purpose creep into performance management.** Competency data collected for training is used for appraisal, progression or discipline without a new notice or basis | Medium: the data is exactly what a manager would want, and the request will be reasonable-sounding | High: career consequences from data the individual believed was for practice | **High** |
| R2 | **An unvalidated scorer produces an inaccurate competence record.** The operator is recorded as weak on an axis because the rubric, not the operator, was wrong | Medium if the validation gate is skipped; Low if enforced | High: an inaccurate professional competence record that a supervisor sees | **High** (Medium with the gate enforced) |
| R3 | **Perceived surveillance erodes trust and use.** Operators experience the trainer as monitoring, stop using it voluntarily, or game it | Medium: the flight plan records this user group as strongly averse | Medium: loss of a readiness capability, and a chilling effect on honest practice | **Medium** |
| R4 | **Unauthorised disclosure of the performance record** through a defect, a shared credential or an over-broad access grant | Low: server-side controls, private team visibility, no egress | High: professional embarrassment and career impact from competence data | **Medium** |
| R5 | **Supervisor access without accountability.** A supervisor views an individual's record and no record of that viewing exists | Low once the audit control is built; **High today, because it is not built** | Medium: the operator cannot know who has looked at their competence record | **Medium** |
| R6 | **Loss of the individual's own data** (integrity or availability) so the operator cannot see or correct their own record | Low | Medium | **Low** |
| R7 | **Re-identification from aggregate readiness reporting** in a cohort of ten. A single-axis coverage figure across one shift crew can identify an individual | Medium: ten is a small denominator | Medium | **Medium** |
| R8 | **Retention beyond necessity.** Detailed run artefacts accumulate indefinitely because no ageing mechanism exists | **High today: no retention mechanism is implemented and no period is set** | Medium | **Medium** |
| R9 | **Restricted transfer without a completed assessment**, if platform administration or parent-company access reaches the volume | `TBC` pending screening question 2 | Medium | `TBC` |

### 5. Measures to address risk

Controls are named specifically. Where a control is **not yet built**, that is stated: this
assessment must not credit a control that does not exist.

| # | Existing controls | Additional controls proposed | Residual |
|---|---|---|---|
| R1 | Declared purpose recorded in the flight plan and in this DPIA | ■ Purpose limitation written into the privacy notice and the interface, not only this document. ■ Any use for performance management is a new purpose requiring a new notice and a DPIA revision, recorded as a change trigger in Section 7. ■ Supervisor views technically constrained to competence, coverage and decay, so the raw material for appraisal is not available to surface. **Not yet built.** | **Medium.** Cannot be driven lower by technical means alone; it is a governance commitment |
| R2 | **None.** An earlier version of this row credited score decomposition and a content version hash as EXISTING. Neither exists: the stored record is identity, title, scenario and notes only, and the same row already said "no scoring engine exists", so the table contradicted itself against its own preamble. Corrected on review | ■ **Scorer validation against expert human raters on a held-out set, as a gate before any operator is scored.** ■ Score decomposition recording which rule fired on which evidence against which procedure version. ■ A content version hash on every run. ■ Confidence intervals never dropped in presentation. ■ Challenge route in the interface. **None built; no scoring engine exists.** | **Medium** with the gate enforced; **High** without it |
| R3 | Design commitment to no covert observation; sandbox never scored | ■ First-run notice in the supervisor's own words. ■ Sandbox and free analysis excluded from scoring and reporting by construction. ■ Voluntary return rate monitored as the early-warning metric. **Not yet built.** | **Low to Medium** |
| R4 | Writes fail closed (HTTP 401 without a token). Team token compared in constant time behind a length guard. Two-tier rate limiting. Cross-Origin Resource Sharing (CORS) refuses to start on `*` or `null`. Request body capped. Every request body validated with unknown keys rejected. `O_NOFOLLOW` on every file open, backups at mode 0600. Non-root numeric user 10001, flattened single-layer image with no package manager and no setuid or setgid bits. Structured audit line per privileged action carrying no secret and no performance figure. Physics core provably unreachable from any HTTP route | ■ **Per-operator identity replacing the shared team token**, so a record is attributable and access is individual. **Not built.** ■ Storage volume group ownership via `securityContext.fsGroup`. **Operations request outstanding.** | **Low** once identity exists; **Medium** today |
| R5 | None | ■ **A structured one-line audit record for every supervisor view of an individual's results: who viewed, whose record, when, which view.** Cheap now, expensive to retrofit. **Not built.** ■ Operator-visible access log, so the individual can see who looked | **Low** once built |
| R6 | Atomic write via temporary file and rename, flock serialisation across load-merge-rename, monotonic revision with compare-and-set and HTTP 409 on a stale write, anti-shrink merge so a dataset never silently loses records, backups on every destructive write | ■ Export of the operator's own record. **Not built.** | **Low** |
| R7 | None | ■ Minimum cohort size before any aggregate figure is shown, or individual-only reporting with no cohort view. ■ Explicit statement in the notice that the cohort is small and aggregates are not anonymous. **Not built.** | **Low to Medium** |
| R8 | Two CAPACITY caps, which are not retention periods and are named as partial: the store prunes the oldest session records beyond a fixed count, and prunes backups to the five most recent. Neither is time-based and neither applies to run artefacts, which do not exist yet | ■ **A defined retention period and an implemented ageing job** for detailed run artefacts, with aggregate competence retained separately. **Neither set nor built.** A capacity cap bounds how much is held; a retention period bounds how LONG, and only the second discharges the storage-limitation principle | **Low** once set and built |
| R9 | United Kingdom deployment; no runtime egress; no third-party processor | ■ Confirm the platform administration access boundary. ■ Where the parent relationship is engaged, reference the IDTA, the UK-US Data Bridge and the existing parent TRA | `TBC` |

### 6. Sign-off and conclusion

**Recommendation: PROCEED WITH CONDITIONS.**

The processing is necessary and proportionate to a legitimate readiness purpose, and the design
already carries unusually strong transparency and minimisation commitments. No residual high risk
is identified that cannot be mitigated, so **Article 36 prior consultation with the Information
Commissioner's Office is not required** on the current facts.

**The conditions are binding, and they precede the first named-individual record rather than
following it.**

1. **No named-individual performance record is written until this DPIA is signed.** Development
   proceeds against synthetic accounts. This is already the design position: the identity layer
   will be built and exercised without real operators.
2. **The lawful basis is confirmed and the Legitimate Interests Assessment completed.**
3. **Operators are consulted**, and the privacy notice is in place at first run before any scored
   interaction.
4. **The retention period is set and the ageing mechanism implemented.** R8 is the only risk that
   is currently unmitigated by anything at all.
5. **The supervisor-access audit record is built** before any supervisor view exists. R5 is cheap
   now and expensive later, and it is the control that makes the visibility decision defensible to
   the operator and to an assessor.
6. **The scorer is validated against expert human raters** before any operator is scored by it.
7. **The transfer position is confirmed** (screening question 2), and the Article 22 question
   answered (screening question 1).

**Residual high risks after conditions:** none, provided conditions 4, 5 and 6 are met. R1 remains
Medium and is a governance commitment rather than a technical control, which is the honest
characterisation.

| | |
|---|---|
| Prepared by | Ash Higgins, Technical Director and Data Protection Lead |
| Approved by | Managing Director, name `TBC, re-verify`. **Not yet signed** |
| Date approved | `TBC, re-verify` |
| Review cadence | On any change trigger below, and at minimum annually |

### 7. Review and update

**Owner:** Ash Higgins as DPL. **Record location:** REG-003.

**Change triggers requiring revision before the change takes effect:**

● Any use of the data for performance management, appraisal, progression or discipline. This is a
  new purpose, not a change of scope.
● Any change to what a supervisor can see.
● Any change to the data categories collected, including any new competency axis.
● Introduction of any Large Language Model, any outbound network call at runtime, or any live
  Unified Data Library connectivity.
● Any change to the transfer position, including platform administration access.
● Any move from synthetic accounts to named individuals, if this DPIA was signed before that step.
● A material change to the scoring engine after scorer validation.
● Any personal data breach engaging this processing (see the incident triage and breach assessment
  routes).
● Regulatory change, including new ICO guidance on employment monitoring or on automated decisions.

**Scheduled review date:** twelve months from approval, or on the first change trigger, whichever
is sooner.

## Related records

**Provenance note.** The record identifiers below (POL-002, REG-003, the Employee Handbook and its
Annex J, IASME Theme 4) are cited from the company's own document set and are not verifiable from
this repository. They are named so the DPIA can be filed against them; if any identifier has
changed, the reference is the thing to correct, not the assessment.

● POL-002 Data Protection and Privacy Policy
● REG-003 Data Protection records (DPIA log)
● Employee Handbook v2.0 Part 15, Annex J (Artificial Intelligence tools). **Not engaged:** no LLM
  and no outbound call at runtime
● Transfer Risk Assessment for the Bluestaq Ltd to Bluestaq LLC relationship, `TBC, re-verify`
● `docs/SECURITY.md` and `docs/DEPLOYMENT.md` in this repository, for the technical controls named
  in Section 5
● UK GDPR Articles 6, 22, 35 and 36; Data Protection Act 2018; current ICO DPIA guidance and the
  ICO list of processing operations requiring a DPIA; IASME Theme 4; ISO/IEC 27001:2022 Annex
  A.5.34
