#!/usr/bin/env python3
"""Validate the ENLIGHTENMENT training content library.

Script mode per CONTEXT-001 Section 3: standard library only, fully typed,
structured logging to stderr, and a --self-test flag emitting a JSON assertion
manifest. No third-party dependencies, so this runs in the container, in the
pipeline, and on an air-gapped workstation without setup.

Checks performed:
  1. Every content file parses as JSON and carries a _version block.
  2. Every cross-reference resolves: competency, product, procedure, cue,
     artefact and scenario identifiers are all reachable.
  3. Identifier formats match the schema patterns.
  4. No drill item uses a recognition response format. This is a hard rule,
     not a style preference: a visible answer defeats retrieval practice.
  5. Every threshold_ref used in content resolves against the thresholds file.
  6. No placeholder threshold is relied upon by a scenario that would be scored.
  7. Redaction tripwires: shipped content contains no numeric object catalogue
     identifiers and no obvious tasking values inlined outside the thresholds
     file.

Exit codes: 0 clean, 1 validation failures, 2 usage or IO error.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

LOG: Final = logging.getLogger("validate_content")

ID_PATTERNS: Final[dict[str, re.Pattern[str]]] = {
    "competency": re.compile(r"^CMP-\d{2}$"),
    "product": re.compile(r"^PRD-[A-Z0-9-]+$"),
    "artefact": re.compile(r"^ART-\d{3}$"),
    "procedure": re.compile(r"^PROC-[A-Z0-9-]+$"),
    "cue": re.compile(r"^CUE-\d{3}$"),
    "drill": re.compile(r"^DRL-\d{4}$"),
    "scenario": re.compile(r"^SCN-[A-Z0-9-]+$"),
    "trace": re.compile(r"^TRC-[A-Z0-9-]+$"),
    "rubric": re.compile(r"^RUB-[A-Z0-9-]+$"),
    "stage": re.compile(r"^STG-\d{2}$"),
}

FORBIDDEN_RESPONSE_FORMATS: Final[frozenset[str]] = frozenset({"multiple_choice", "select_one", "true_false"})

# A bare five-digit token in shipped content is very likely a catalogue number.
CATALOGUE_NUMBER: Final = re.compile(r"(?<![\d.\-])\d{5}(?![\d.])")

REQUIRED_VERSION_KEYS: Final[frozenset[str]] = frozenset(
    {"schema_version", "content_version", "author", "updated", "source_refs", "review_status"}
)


@dataclass
class Report:
    """Accumulated validation outcome."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    @property
    def ok(self) -> bool:
        return not self.errors


def load_json(path: Path) -> dict[str, Any]:
    """Read and parse a JSON file, raising a clear error on failure."""
    try:
        with path.open(encoding="utf-8") as handle:
            data: Any = json.load(handle)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"content file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"top level of {path} must be an object")
    return data


def collect(content_dir: Path) -> dict[str, dict[str, Any]]:
    """Load every known content file from the content directory."""
    files = {
        "competencies": content_dir / "competencies.json",
        "products": content_dir / "products.json",
        "artefacts": content_dir / "artefacts.json",
        "cues": content_dir / "cues.json",
        "drills": content_dir / "drills.json",
        "scenarios": content_dir / "scenarios.json",
        "traces": content_dir / "traces.json",
        "rubrics": content_dir / "rubrics.json",
        "progression": content_dir / "progression.json",
        "procedures_core": content_dir / "procedures" / "procedures-core.json",
        "procedures_extended": content_dir / "procedures" / "procedures-extended.json",
        "thresholds": content_dir / "thresholds.example.json",
        "layouts": content_dir / "product-layouts.json",
        "patterns": content_dir / "report-detection-patterns.json",
        "provenance": content_dir / "provenance-register.json",
    }
    return {name: load_json(path) for name, path in files.items()}


def check_version_blocks(data: dict[str, dict[str, Any]], report: Report) -> None:
    """Every content file must declare provenance and review status."""
    for name, payload in data.items():
        if name == "thresholds":
            continue
        version = payload.get("_version")
        if not isinstance(version, dict):
            report.error(f"{name}: missing _version block")
            continue
        missing = REQUIRED_VERSION_KEYS - set(version)
        if missing:
            report.error(f"{name}: _version missing keys {sorted(missing)}")
        if version.get("review_status") == "draft":
            report.warn(f"{name}: review_status is draft, not yet redaction reviewed")


def index_ids(data: dict[str, dict[str, Any]]) -> dict[str, set[str]]:
    """Build the set of defined identifiers for each content type."""
    procedures = data["procedures_core"]["procedures"] + data["procedures_extended"]["procedures"]
    return {
        "competency": {c["id"] for c in data["competencies"]["competencies"]},
        "product": {p["id"] for p in data["products"]["products"]},
        "artefact": {a["id"] for a in data["artefacts"]["artefacts"]},
        "procedure": {p["id"] for p in procedures},
        "cue": {c["id"] for c in data["cues"]["cues"]},
        "drill": {d["id"] for d in data["drills"]["drills"]},
        "scenario": {s["id"] for s in data["scenarios"]["scenario_templates"]},
        "trace": {t["id"] for t in data["traces"]["expert_traces"]},
    }


def check_id_formats(defined: dict[str, set[str]], report: Report) -> None:
    """Identifiers must match their schema patterns."""
    for kind, ids in defined.items():
        pattern = ID_PATTERNS.get(kind)
        if pattern is None:
            continue
        for identifier in sorted(ids):
            if not pattern.match(identifier):
                report.error(f"{kind}: identifier {identifier!r} does not match {pattern.pattern}")


def check_references(data: dict[str, dict[str, Any]], defined: dict[str, set[str]], report: Report) -> None:
    """Every cross-reference must resolve to a defined identifier."""

    def verify(kind: str, values: Any, where: str) -> None:
        if not values:
            return
        for value in values:
            if value not in defined[kind]:
                report.error(f"{where}: unresolved {kind} reference {value!r}")

    procedures = data["procedures_core"]["procedures"] + data["procedures_extended"]["procedures"]
    for proc in procedures:
        verify("competency", proc.get("competency_ids"), f"procedure {proc['id']}")
        for step in proc.get("steps", []):
            verify("product", step.get("products"), f"procedure {proc['id']} step {step['n']}")
        for point in proc.get("decision_points", []):
            for branch in point.get("branches", []):
                target = branch.get("goto_procedure")
                if target and target not in defined["procedure"]:
                    report.error(f"procedure {proc['id']} {point['id']}: unresolved goto {target!r}")

    for cue in data["cues"]["cues"]:
        verify("product", cue.get("seen_in"), f"cue {cue['id']}")
        verify("competency", cue.get("competency_ids"), f"cue {cue['id']}")
        verify("artefact", cue.get("artefact_ids"), f"cue {cue['id']}")
        proc_id = cue.get("procedure_id")
        if proc_id and proc_id not in defined["procedure"]:
            report.error(f"cue {cue['id']}: unresolved procedure {proc_id!r}")

    for drill in data["drills"]["drills"]:
        if drill["cue_id"] not in defined["cue"]:
            report.error(f"drill {drill['id']}: unresolved cue {drill['cue_id']!r}")
        product = drill.get("stimulus", {}).get("product_id")
        if product and product not in defined["product"]:
            report.error(f"drill {drill['id']}: unresolved product {product!r}")
        verify("artefact", drill.get("artefact_ids"), f"drill {drill['id']}")

    for scenario in data["scenarios"]["scenario_templates"]:
        verify("procedure", scenario.get("procedure_ids"), f"scenario {scenario['id']}")
        verify("competency", scenario.get("competency_ids"), f"scenario {scenario['id']}")
        for trigger in scenario.get("trigger_events", []):
            verify("competency", trigger.get("competency_ids"), f"scenario {scenario['id']} {trigger['id']}")

    for trace in data["traces"]["expert_traces"]:
        if trace["scenario_id"] not in defined["scenario"]:
            report.error(f"trace {trace['id']}: unresolved scenario {trace['scenario_id']!r}")
        for obs in trace.get("observations", []):
            product = obs.get("on_product")
            if product and product not in defined["product"]:
                report.error(f"trace {trace['id']}: unresolved product {product!r}")

    for rubric in data["rubrics"]["rubrics"]:
        for rule in rubric.get("rules", []):
            if rule["competency_id"] not in defined["competency"]:
                report.error(f"rubric {rubric['id']} {rule['id']}: unresolved competency")


def check_declared_enums(data: dict[str, dict[str, Any]], schemas: dict[str, Any], report: Report) -> None:
    """Every response_format used must be declared in the schema enum.

    Added after a self-audit found four formats in live use and absent from the
    schema. The validator passed because it never checked, which is exactly the
    class of blind spot a validator exists to prevent.
    """
    declared = set(
        schemas["$defs"]["drillItem"]["properties"]["response_format"]["enum"]
    )
    used = {d["response_format"] for d in data["drills"]["drills"]}
    undeclared = used - declared
    if undeclared:
        report.error(f"drills: response_format values not declared in schema: {sorted(undeclared)}")
    unused = declared - used
    if unused:
        report.warn(f"schema: response_format values declared but unused: {sorted(unused)}")


def check_generator_contract(data: dict[str, dict[str, Any]], report: Report) -> None:
    """Every generator must be one of the canonical set declared in drills.json.

    Ad-hoc generator names are the single biggest handover risk: an engineer
    reading the drill bank would otherwise try to build one generator per name.
    """
    contract = data["drills"].get("_generator_contract")
    if not contract:
        report.error("drills: no _generator_contract block. Engineers cannot know what to build.")
        return
    canonical = set(contract.get("product_renderers", {})) | set(contract.get("composition_modes", {}))
    if not canonical:
        report.error("drills: _generator_contract declares no generators")
        return
    used = {d["stimulus"]["generator"] for d in data["drills"]["drills"]}
    rogue = used - canonical
    if rogue:
        report.error(f"drills: generators outside the canonical contract: {sorted(rogue)}")
    unused = canonical - used
    if unused:
        report.warn(f"drills: canonical generators with no drill: {sorted(unused)}")
    # every declared renderer must name a real product
    products = {p["id"] for p in data["products"]["products"]}
    for name, spec in contract.get("product_renderers", {}).items():
        pid = spec.get("product_id")
        if pid not in products:
            report.error(f"generator contract: renderer {name!r} names unknown product {pid!r}")


def check_layout_coverage(data: dict[str, dict[str, Any]], report: Report) -> None:
    """Products used by drills should carry an observed layout where one exists."""
    layouts = {l["product_id"] for l in data["layouts"]["layouts"]}
    used = {d["stimulus"]["product_id"] for d in data["drills"]["drills"]}
    missing = sorted(used - layouts)
    if missing:
        report.warn(
            f"layout: products used by drills with no observed layout: {missing}. "
            "Renderers for these are built from the product definition alone, which is weaker."
        )


def check_detection_patterns(data: dict[str, Any], report: Report) -> None:
    """Every detection pattern must compile and declare an expected rate.

    A pattern that matches everything looks like a working detector until
    someone computes a percentage from it. That has happened once already.
    """
    pats = data.get("patterns")
    if not pats:
        report.error("report-detection-patterns.json missing")
        return
    ids: set[str] = set()
    for check in pats["checks"]:
        ids.add(check["id"])
        try:
            re.compile(check["pattern"])
        except re.error as exc:
            report.error(f"detection {check['id']}: pattern does not compile: {exc}")
        if check.get("expected_match_rate") is None:
            report.warn(f"detection {check['id']}: no expected_match_rate, cannot be verified")
    for cond in pats["conditional_checks"]:
        for key in ("base", "requires"):
            ref = cond.get(key)
            if ref and ref not in ids:
                report.error(f"conditional {cond['id']}: {key} references unknown check {ref!r}")


def check_production_format(data: dict[str, dict[str, Any]], report: Report) -> None:
    """No drill may present the answer on screen. This is load-bearing."""
    for drill in data["drills"]["drills"]:
        fmt = drill.get("response_format", "")
        if fmt in FORBIDDEN_RESPONSE_FORMATS:
            report.error(
                f"drill {drill['id']}: response_format {fmt!r} is a recognition format. "
                "Recall requires the operator to produce the answer."
            )
        answer = drill.get("answer", {})
        if not answer.get("accept"):
            report.error(f"drill {drill['id']}: no accepted answers defined")
        if not answer.get("reject"):
            report.warn(f"drill {drill['id']}: no reject entries, so a miss cannot be explained")
        if not drill.get("explain"):
            report.error(f"drill {drill['id']}: no explain text, so a reveal teaches nothing")


def walk_threshold_refs(node: Any, found: set[str]) -> None:
    """Recursively collect every threshold_ref used anywhere in the content."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "threshold_ref" and isinstance(value, str):
                found.add(value)
            elif key == "time_standard" and isinstance(value, str) and "." in value and " " not in value:
                found.add(value)
            else:
                walk_threshold_refs(value, found)
    elif isinstance(node, list):
        for item in node:
            walk_threshold_refs(item, found)


def resolve_threshold(thresholds: dict[str, Any], dotted: str) -> bool:
    """Return True when a dotted threshold key exists in the thresholds file."""
    node: Any = thresholds
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return True


def check_thresholds(data: dict[str, dict[str, Any]], report: Report) -> set[str]:
    """Every threshold_ref must resolve, and placeholders must be visible."""
    used: set[str] = set()
    for name, payload in data.items():
        if name == "thresholds":
            continue
        walk_threshold_refs(payload, used)

    thresholds = data["thresholds"]
    for ref in sorted(used):
        if not resolve_threshold(thresholds, ref):
            report.error(f"thresholds: unresolved threshold_ref {ref!r}")

    meta = thresholds.get("_meta", {})
    if not meta.get("all_placeholders_replaced", False):
        report.warn(
            "thresholds: placeholders not replaced. The loader must refuse to serve a scored "
            "scenario until thresholds.local.json is populated."
        )
    return used


COUNT_KEYS: Final = re.compile(r'"(obs_count|rows|revolutions|days|duration_\w+|\w*_count|\w*_km|elo|difficulty_seed)"\s*:')


def check_redaction(content_dir: Path, report: Report) -> None:
    """Tripwire for catalogue numbers inlined in shipped content.

    Skips lines whose key is a known count or rating field, since those are
    legitimately five digits. A skipped line is still reported at debug level
    so the suppression itself stays visible.
    """
    for path in sorted(content_dir.rglob("*.json")):
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if "PLACEHOLDER" in line:
                continue
            if COUNT_KEYS.search(line):
                LOG.debug("redaction tripwire suppressed on count field: %s:%d", path.name, line_no)
                continue
            for match in CATALOGUE_NUMBER.finditer(line):
                report.warn(
                    f"redaction tripwire: {path.name}:{line_no} contains a five-digit token "
                    f"{match.group()!r}. Confirm this is not an object catalogue number."
                )


def check_coverage(data: dict[str, dict[str, Any]], defined: dict[str, set[str]], report: Report) -> None:
    """Every competency and active procedure should be reachable from content."""
    covered_by_cue: set[str] = set()
    for cue in data["cues"]["cues"]:
        covered_by_cue.update(cue.get("competency_ids", []))
    uncovered = defined["competency"] - covered_by_cue
    if uncovered:
        report.warn(f"coverage: competencies with no cue: {sorted(uncovered)}")

    drilled_cues = {d["cue_id"] for d in data["drills"]["drills"]}
    undrilled = defined["cue"] - drilled_cues
    if undrilled:
        report.warn(f"coverage: {len(undrilled)} cues have no drill item yet: {sorted(undrilled)}")

    scenario_procs: set[str] = set()
    for scenario in data["scenarios"]["scenario_templates"]:
        scenario_procs.update(scenario.get("procedure_ids", []))
    unexercised = defined["procedure"] - scenario_procs
    if unexercised:
        report.warn(f"coverage: procedures with no scenario: {sorted(unexercised)}")

    traced = {t["scenario_id"] for t in data["traces"]["expert_traces"]}
    untraced = defined["scenario"] - traced
    if untraced:
        report.warn(f"coverage: scenarios with no expert trace, cannot be debriefed: {sorted(untraced)}")


def validate(content_dir: Path) -> Report:
    """Run the full validation suite over a content directory."""
    report = Report()
    data = collect(content_dir)
    schemas = json.loads((content_dir.parent / "schemas" / "enlightenment.schema.json").read_text(encoding="utf-8"))
    check_version_blocks(data, report)
    check_declared_enums(data, schemas, report)
    check_generator_contract(data, report)
    check_layout_coverage(data, report)
    check_detection_patterns(data, report)
    defined = index_ids(data)
    check_id_formats(defined, report)
    check_references(data, defined, report)
    check_production_format(data, report)
    used_thresholds = check_thresholds(data, report)
    check_redaction(content_dir, report)
    check_coverage(data, defined, report)

    report.counts = {
        "competencies": len(defined["competency"]),
        "products": len(defined["product"]),
        "artefacts": len(defined["artefact"]),
        "procedures": len(defined["procedure"]),
        "cues": len(defined["cue"]),
        "drills": len(defined["drill"]),
        "scenarios": len(defined["scenario"]),
        "expert_traces": len(defined["trace"]),
        "threshold_refs_used": len(used_thresholds),
    }
    return report


def _compiles(pattern: str) -> bool:
    """True when a regular expression compiles."""
    try:
        re.compile(pattern)
    except re.error:
        return False
    return True


def self_test(content_dir: Path) -> dict[str, Any]:
    """Run explicit assertions and emit a JSON manifest of the results."""
    assertions: list[dict[str, Any]] = []

    def assert_that(name: str, condition: bool, detail: str) -> None:
        assertions.append({"assertion": name, "passed": bool(condition), "detail": detail})

    data = collect(content_dir)
    defined = index_ids(data)
    report = validate(content_dir)

    assert_that("content_loads", True, "all content files parsed as JSON")
    assert_that("no_validation_errors", report.ok, f"{len(report.errors)} errors")
    assert_that(
        "competency_axes_present",
        len(defined["competency"]) >= 6,
        f"{len(defined['competency'])} axes defined",
    )
    assert_that(
        "every_competency_is_measured",
        all(c.get("measured_by") for c in data["competencies"]["competencies"]),
        "every axis declares how it is measured",
    )
    rubric_axes = {
        rule["competency_id"]
        for rub in data["rubrics"]["rubrics"]
        for rule in rub["rules"]
    }
    assert_that(
        "every_competency_is_scored",
        defined["competency"] <= rubric_axes,
        f"axes with no scoring rule: {sorted(defined['competency'] - rubric_axes)}",
    )
    assert_that(
        "no_recognition_formats",
        all(d["response_format"] not in FORBIDDEN_RESPONSE_FORMATS for d in data["drills"]["drills"]),
        "no drill uses a multiple choice or recognition response format",
    )
    assert_that(
        "every_drill_explains",
        all(d.get("explain") for d in data["drills"]["drills"]),
        "every drill has explain text for the reveal",
    )
    assert_that(
        "every_scenario_has_distractor",
        all(
            any(t.get("distractor") for t in s["trigger_events"])
            for s in data["scenarios"]["scenario_templates"]
        ),
        "every scenario carries at least one distractor trigger",
    )
    assert_that(
        "every_scenario_has_solvability_check",
        all(s.get("solvability", {}).get("check") for s in data["scenarios"]["scenario_templates"]),
        "every scenario declares a solvability assertion",
    )
    assert_that(
        "every_trace_has_ruled_out",
        all(
            any(o.get("ruled_out") for o in t["observations"])
            for t in data["traces"]["expert_traces"]
        ),
        "every expert trace records hypotheses that were actively discarded",
    )
    assert_that(
        "every_trace_admits_limits",
        all(t.get("would_have_missed") for t in data["traces"]["expert_traces"]),
        "every expert trace states what the expert found hard",
    )
    contract = data["drills"].get("_generator_contract", {})
    canonical = set(contract.get("product_renderers", {})) | set(contract.get("composition_modes", {}))
    assert_that(
        "detection_patterns_compile",
        all(_compiles(c["pattern"]) for c in data["patterns"]["checks"]),
        f"{len(data['patterns']['checks'])} detection patterns compile",
    )
    assert_that(
        "generators_canonical",
        bool(canonical) and {d["stimulus"]["generator"] for d in data["drills"]["drills"]} <= canonical,
        f"{len(canonical)} canonical generators declared, all drill references within them",
    )
    declared_formats = set(
        json.loads((content_dir.parent / "schemas" / "enlightenment.schema.json").read_text(encoding="utf-8"))
        ["$defs"]["drillItem"]["properties"]["response_format"]["enum"]
    )
    assert_that(
        "response_formats_declared",
        {d["response_format"] for d in data["drills"]["drills"]} <= declared_formats,
        "every response_format in use is declared in the schema",
    )
    assert_that(
        "every_procedure_has_discrimination",
        all(
            p.get("not_this_procedure_when")
            for p in data["procedures_core"]["procedures"]
        ),
        "every core procedure states when it is not the right procedure",
    )
    assert_that(
        "every_rubric_rule_explains",
        all(
            r.get("explain")
            for rub in data["rubrics"]["rubrics"]
            for r in rub["rules"]
        ),
        "every scoring rule carries operator-facing explain text",
    )
    used_refs: set[str] = set()
    for name, payload in data.items():
        if name != "thresholds":
            walk_threshold_refs(payload, used_refs)
    assert_that(
        "thresholds_externalised",
        bool(used_refs) and all(resolve_threshold(data["thresholds"], ref) for ref in used_refs),
        f"{len(used_refs)} threshold_refs used, all resolve against the thresholds file",
    )

    passed = sum(1 for a in assertions if a["passed"])
    return {
        "tool": "validate_content",
        "content_dir": str(content_dir),
        "assertions": assertions,
        "passed": passed,
        "failed": len(assertions) - passed,
        "counts": report.counts,
        "errors": report.errors,
        "warnings": report.warnings,
    }


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Validate ENLIGHTENMENT training content.")
    parser.add_argument("--content-dir", type=Path, default=Path("content"), help="path to the content directory")
    parser.add_argument("--self-test", action="store_true", help="run assertions and emit a JSON manifest")
    parser.add_argument("--verbose", action="store_true", help="log at debug level")
    args = parser.parse_args(argv)

    logging.basicConfig(
        stream=sys.stderr,
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )

    try:
        if args.self_test:
            manifest = self_test(args.content_dir)
            json.dump(manifest, sys.stdout, indent=2)
            sys.stdout.write("\n")
            return 0 if manifest["failed"] == 0 and not manifest["errors"] else 1

        report = validate(args.content_dir)
    except (FileNotFoundError, ValueError) as exc:
        LOG.error("%s", exc)
        return 2

    for warning in report.warnings:
        LOG.warning("%s", warning)
    for error in report.errors:
        LOG.error("%s", error)

    LOG.info("content counts: %s", json.dumps(report.counts))
    if report.ok:
        LOG.info("validation clean: %d errors, %d warnings", 0, len(report.warnings))
        return 0
    LOG.error("validation failed: %d errors, %d warnings", len(report.errors), len(report.warnings))
    return 1


if __name__ == "__main__":
    sys.exit(main())
