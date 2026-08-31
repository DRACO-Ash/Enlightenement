# ENLIGHTENMENT data model

| | |
| --- | --- |
| **Document** | ENL-SPEC-01 |
| **Version** | 1.0 |
| **Date** | 29 August 2026 |
| **Status** | Build specification. Implement as written unless a stated reason to deviate |

---

## 1. Storage decisions, and why

**SQLite on the App Store storage volume.** Confirmed available and writable by uid 10001. Single file, transactional, zero administration, in the standard library. WAL mode for concurrent reads during a write.

**Content is never in the database.** Procedures, cues, drills, scenarios, rubrics, traces and patterns all load from JSON files in the image. The database holds only what is produced at runtime: who did what, when, and what it scored. If you find yourself writing a `drills` table, stop.

**Nothing in browser storage.** Stated requirement, no exceptions.

**Two retention classes.** Run artefacts age out on a schedule; aggregate competence persists while the operator is in role. The schema keeps them in separate tables specifically so a retention job can delete one without touching the other.

---

## 2. Schema

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------
-- Identity. Minimal by design: the shell may later supply identity
-- via header, and this table becomes a shadow record rather than
-- the authority. See the IdentityProvider adapter.
-- ---------------------------------------------------------------
CREATE TABLE operator (
    operator_id      TEXT PRIMARY KEY,          -- opaque, not a name
    display_name     TEXT NOT NULL,
    role_tier        TEXT NOT NULL DEFAULT 'SEA' CHECK (role_tier IN ('SEA','ADVANCED')),
    cell             TEXT,                      -- free text, optional
    created_at       TEXT NOT NULL,             -- ISO 8601 UTC
    last_seen_at     TEXT,
    active           INTEGER NOT NULL DEFAULT 1,
    -- Consent and transparency. The operator is told what a supervisor sees.
    visibility_ack_at TEXT                      -- when they acknowledged the notice
);

CREATE TABLE operator_credential (
    operator_id      TEXT PRIMARY KEY REFERENCES operator(operator_id) ON DELETE CASCADE,
    password_hash    TEXT NOT NULL,             -- bcrypt
    updated_at       TEXT NOT NULL
);

-- ---------------------------------------------------------------
-- Content version pinning. Every run records the exact content it
-- was scored under so a debrief stays interpretable when procedures
-- move on. Without this, old results become uninterpretable.
-- ---------------------------------------------------------------
CREATE TABLE content_version (
    content_hash     TEXT PRIMARY KEY,          -- sha256 over the content tree
    loaded_at        TEXT NOT NULL,
    manifest         TEXT NOT NULL              -- JSON: {file: content_version}
);

-- ---------------------------------------------------------------
-- RUN ARTEFACTS. Retention-limited. Everything needed for exact replay.
-- ---------------------------------------------------------------
CREATE TABLE run (
    run_id           TEXT PRIMARY KEY,
    operator_id      TEXT NOT NULL REFERENCES operator(operator_id) ON DELETE CASCADE,
    content_hash     TEXT NOT NULL REFERENCES content_version(content_hash),
    kind             TEXT NOT NULL CHECK (kind IN ('drill','scenario','synthesis','sandbox','report')),
    ref_id           TEXT NOT NULL,             -- DRL-0001 / SCN-... / tier id
    seed             INTEGER NOT NULL,          -- the PRNG seed. Replay depends on it
    started_at       TEXT NOT NULL,
    completed_at     TEXT,
    outcome          TEXT CHECK (outcome IN ('completed','abandoned','timeout')),
    scored           INTEGER NOT NULL DEFAULT 1,-- sandbox runs are never scored
    total_score      REAL,
    expires_at       TEXT NOT NULL              -- retention. Set on insert
);
CREATE INDEX idx_run_operator ON run(operator_id, started_at DESC);
CREATE INDEX idx_run_expiry   ON run(expires_at);
CREATE INDEX idx_run_ref      ON run(ref_id, started_at DESC);

-- Ordered, append-only. Replaying this against the seed reproduces the run.
CREATE TABLE run_event (
    run_id           TEXT NOT NULL REFERENCES run(run_id) ON DELETE CASCADE,
    seq              INTEGER NOT NULL,
    sim_time_ms      INTEGER NOT NULL,          -- scenario clock, not wall clock
    wall_time        TEXT NOT NULL,
    event_type       TEXT NOT NULL,             -- trigger_fired | product_opened |
                                                -- response_submitted | report_published |
                                                -- notification_made | procedure_entered |
                                                -- thread_actioned | challenge_posed
    payload          TEXT NOT NULL,             -- JSON
    PRIMARY KEY (run_id, seq)
);

-- One row per scoring rule that fired. This is what makes a score
-- challengeable: every point traces to a named rule and its evidence.
CREATE TABLE run_score_component (
    run_id           TEXT NOT NULL REFERENCES run(run_id) ON DELETE CASCADE,
    seq              INTEGER NOT NULL,
    rubric_id        TEXT NOT NULL,
    rule_id          TEXT NOT NULL,
    competency_id    TEXT NOT NULL,
    award            REAL NOT NULL,
    evidence         TEXT NOT NULL,             -- JSON: which event(s) fired it
    explain          TEXT NOT NULL,             -- operator-facing, verbatim from the rubric
    PRIMARY KEY (run_id, seq)
);
CREATE INDEX idx_score_competency ON run_score_component(competency_id);

-- Free-text reports, kept separate because they are the richest personal data.
CREATE TABLE run_report (
    run_id           TEXT NOT NULL REFERENCES run(run_id) ON DELETE CASCADE,
    seq              INTEGER NOT NULL,
    report_kind      TEXT NOT NULL,             -- holding | possible | verified | update | cancellation
    body             TEXT NOT NULL,
    submitted_at     TEXT NOT NULL,
    latency_from_indication_s INTEGER,
    latency_from_last_product_s INTEGER,
    governing_leg    TEXT CHECK (governing_leg IN ('indication','product')),
    detection_results TEXT NOT NULL,            -- JSON: {CHK-01: true, CND-03: false, ...}
    anatomy_results  TEXT NOT NULL,             -- JSON: {1: answered, 5: absent, ...}
    PRIMARY KEY (run_id, seq)
);

-- ---------------------------------------------------------------
-- AGGREGATE COMPETENCE. Persists while the operator is in role.
-- ---------------------------------------------------------------
CREATE TABLE competency_state (
    operator_id      TEXT NOT NULL REFERENCES operator(operator_id) ON DELETE CASCADE,
    competency_id    TEXT NOT NULL,             -- CMP-01..CMP-08
    estimate         REAL NOT NULL,             -- 0..1
    ci_low           REAL NOT NULL,             -- never display an estimate without these
    ci_high          REAL NOT NULL,
    observations     INTEGER NOT NULL DEFAULT 0,
    updated_at       TEXT NOT NULL,
    PRIMARY KEY (operator_id, competency_id)
);

-- Two ratings, deliberately separate. An operator can read a residual
-- plot excellently and build an argument poorly; averaging hides it.
CREATE TABLE rating (
    operator_id      TEXT NOT NULL REFERENCES operator(operator_id) ON DELETE CASCADE,
    rating_kind      TEXT NOT NULL CHECK (rating_kind IN ('drill','fusion')),
    value            REAL NOT NULL,
    games            INTEGER NOT NULL DEFAULT 0,
    best_chain_length INTEGER NOT NULL DEFAULT 0, -- fusion only
    updated_at       TEXT NOT NULL,
    PRIMARY KEY (operator_id, rating_kind)
);

-- FSRS scheduling. One row per operator per cue.
CREATE TABLE cue_schedule (
    operator_id      TEXT NOT NULL REFERENCES operator(operator_id) ON DELETE CASCADE,
    cue_id           TEXT NOT NULL,
    stability        REAL NOT NULL,
    difficulty       REAL NOT NULL,
    last_review_at   TEXT,
    due_at           TEXT NOT NULL,
    reps             INTEGER NOT NULL DEFAULT 0,
    lapses           INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (operator_id, cue_id)
);
CREATE INDEX idx_schedule_due ON cue_schedule(operator_id, due_at);

-- Item difficulty, updated from observed performance. Authored seeds
-- are provisional until enough attempts exist.
CREATE TABLE item_rating (
    item_id          TEXT PRIMARY KEY,          -- DRL-nnnn
    elo              REAL NOT NULL,
    attempts         INTEGER NOT NULL DEFAULT 0,
    provisional      INTEGER NOT NULL DEFAULT 1,-- clears past a threshold
    updated_at       TEXT NOT NULL
);

CREATE TABLE stage_progress (
    operator_id      TEXT NOT NULL REFERENCES operator(operator_id) ON DELETE CASCADE,
    stage_id         TEXT NOT NULL,             -- STG-01..STG-07
    status           TEXT NOT NULL CHECK (status IN ('locked','available','met','tested_out')),
    met_at           TEXT,
    PRIMARY KEY (operator_id, stage_id)
);

-- Calibration, tracked separately because it is a competence in its own right.
CREATE TABLE calibration_sample (
    operator_id      TEXT NOT NULL REFERENCES operator(operator_id) ON DELETE CASCADE,
    run_id           TEXT NOT NULL REFERENCES run(run_id) ON DELETE CASCADE,
    seq              INTEGER NOT NULL,
    stated_confidence REAL NOT NULL,            -- 0..1
    was_correct      INTEGER NOT NULL,
    brier            REAL NOT NULL,
    recorded_at      TEXT NOT NULL,
    PRIMARY KEY (run_id, seq)
);
CREATE INDEX idx_calibration_op ON calibration_sample(operator_id, recorded_at DESC);

-- Retention probe results. The primary evidence of skill gain, and
-- separate from ordinary runs because in-session improvement is not evidence.
CREATE TABLE retention_probe (
    probe_id         TEXT PRIMARY KEY,
    operator_id      TEXT NOT NULL REFERENCES operator(operator_id) ON DELETE CASCADE,
    cue_id           TEXT NOT NULL,
    days_since_last_exposure INTEGER NOT NULL,
    correct          INTEGER NOT NULL,
    latency_ms       INTEGER,
    probed_at        TEXT NOT NULL
);
CREATE INDEX idx_probe_op ON retention_probe(operator_id, probed_at DESC);

-- ---------------------------------------------------------------
-- AUDIT. Never deleted by the retention job. This is the control that
-- makes supervisor visibility defensible.
-- ---------------------------------------------------------------
CREATE TABLE access_audit (
    audit_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id         TEXT NOT NULL,             -- who looked
    subject_id       TEXT NOT NULL,             -- whose record
    view             TEXT NOT NULL,             -- which view
    occurred_at      TEXT NOT NULL
);
CREATE INDEX idx_audit_subject ON access_audit(subject_id, occurred_at DESC);

-- Content edits, attributed. Required by the content-as-data model.
CREATE TABLE content_audit (
    audit_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id         TEXT NOT NULL,
    file             TEXT NOT NULL,
    from_version     TEXT,
    to_version       TEXT NOT NULL,
    reason           TEXT,
    occurred_at      TEXT NOT NULL
);

-- Expert traces authored in-app. Fixes the single-author dependency.
CREATE TABLE authored_trace (
    trace_id         TEXT PRIMARY KEY,
    scenario_id      TEXT NOT NULL,
    author_id        TEXT NOT NULL REFERENCES operator(operator_id),
    validated_by_id  TEXT REFERENCES operator(operator_id),
    validated_at     TEXT,
    body             TEXT NOT NULL,             -- JSON, conforming to the expertTrace schema
    status           TEXT NOT NULL CHECK (status IN ('draft','validated','superseded')),
    created_at       TEXT NOT NULL
);
```

---

## 3. Rules the schema does not enforce

Stated because they matter and SQLite will not police them.

**Retention.** A job deletes `run`, and cascades handle `run_event`, `run_score_component`, `run_report` and `calibration_sample`, where `expires_at` has passed. It **must not** touch `competency_state`, `rating`, `cue_schedule`, `stage_progress`, `retention_probe`, `access_audit` or `content_audit`. Retention period from `thresholds.local.json`; if unset, refuse to write named-individual records at all.

**Sandbox runs are never scored and never reported.** `scored = 0`, no score components written, excluded from every aggregate. Operators need somewhere to be wrong in private.

**Every read of another operator's individual data writes an audit row.** No exceptions, including for administrators. An audit trail with holes is worse than none because it implies completeness.

**Competency estimates are never displayed without confidence intervals.** `ci_low` and `ci_high` are NOT NULL for that reason. A radar chart of bare point estimates is false precision and is prohibited.

**Content hash on every run.** If content changed mid-session, the run records the hash it started under.

---

## 4. What deliberately has no table

| Not stored | Why |
| --- | --- |
| Drills, cues, scenarios, rubrics, procedures | Content. Loads from JSON |
| Thresholds | Local configuration file |
| Product definitions and layouts | Content |
| Generated stimuli | Reproduced from seed plus content hash. Storing them would be storing derived data |
| Raw failed attempts as a supervisor-visible artefact | Exists in `run_event`, and is excluded from supervisor views by policy |

**On generated stimuli:** determinism makes storage unnecessary. Seed plus content hash reproduces any stimulus exactly. Storing them would multiply the data volume for no gain and would create a second source of truth.

---

## 5. Migration

Content versions change constantly; the schema should not. Use `PRAGMA user_version`, one numbered migration per change, forward-only, applied on startup before serving. A migration that cannot run means the application does not start rather than serving against a schema it does not understand.
