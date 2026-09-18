"""Gold-data validation, one-to-one span matching, semantic and mapping metrics."""

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict
from importlib.resources import files
from time import perf_counter
from typing import Any

from .fhir_mapping import map_fhir
from .models import Extractor, Fact, Note

FIELDS = (
    "concept",
    "polarity",
    "certainty",
    "hypothetical",
    "temporality",
    "activity",
    "experiencer",
    "severity",
    "laterality",
    "normalization_status",
)
ATTRIBUTES = (
    "value",
    "diastolic",
    "unit",
    "action",
    "dose",
    "dose_unit",
    "route",
    "frequency",
    "interval_value",
    "interval_unit",
    "explicit_refutation",
)


def load_corpus() -> dict[str, Any]:
    text = files(__package__).joinpath("resources", "corpus.json").read_text(encoding="utf-8")
    corpus = json.loads(text)
    validate_corpus(corpus)
    corpus["sha256"] = hashlib.sha256(text.encode()).hexdigest()
    return corpus


def validate_corpus(corpus: dict[str, Any]) -> None:
    ids: set[str] = set()
    groups: dict[str, str] = {}
    for case in corpus["cases"]:
        if case["id"] in ids:
            raise ValueError(f"Duplicate case ID: {case['id']}")
        ids.add(case["id"])
        group, split = case["template_group"], case["split"]
        if split not in {"development", "validation", "evaluation", "challenge"}:
            raise ValueError(f"Unknown split: {split}")
        if groups.get(group, split) != split:
            raise ValueError(f"Template group crosses splits: {group}")
        groups[group] = split
        spans = set()
        for gold in case["gold"]:
            start, end = gold["start"], gold["end"]
            if not 0 <= start < end <= len(case["text"]) or case["text"][start:end] != gold["text"]:
                raise ValueError(f"Invalid gold offsets in {case['id']}")
            if not all(field in gold for field in FIELDS):
                raise ValueError(f"Missing semantic annotation in {case['id']}")
            spans.add((start, end))
        for relation in case.get("relations", []):
            for side in ("source", "target"):
                if (relation[f"{side}_start"], relation[f"{side}_end"]) not in spans:
                    raise ValueError(f"Relation has no gold mention in {case['id']}")


def match_spans(
    gold: list[dict[str, Any]], predicted: list[Fact], overlap: bool = False
) -> list[tuple[int, int]]:
    """Deterministic one-to-one matching; overlap is a secondary diagnostic only."""
    candidates = []
    for g, expected in enumerate(gold):
        for p, actual in enumerate(predicted):
            if expected["kind"] != actual.kind:
                continue
            intersection = min(expected["end"], actual.end) - max(expected["start"], actual.start)
            exact = expected["start"] == actual.start and expected["end"] == actual.end
            if exact or (overlap and intersection > 0):
                candidates.append((not exact, -intersection, g, p))
    result = []
    used_gold: set[int] = set()
    used_predicted: set[int] = set()
    for _, _, g, p in sorted(candidates):
        if g not in used_gold and p not in used_predicted:
            result.append((g, p))
            used_gold.add(g)
            used_predicted.add(p)
    return result


def ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def prf(tp: int, fp: int, fn: int) -> dict[str, Any]:
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": ratio(tp, tp + fp),
        "recall": ratio(tp, tp + fn),
        "f1": ratio(2 * tp, 2 * tp + fp + fn),
    }


def differences(expected: dict[str, Any], actual: Fact) -> dict[str, Any]:
    result = {
        field: {"expected": expected[field], "actual": getattr(actual, field)}
        for field in FIELDS
        if expected[field] != getattr(actual, field)
    }
    for field in ATTRIBUTES:
        wanted, got = expected.get("attributes", {}).get(field), actual.attributes.get(field)
        if wanted != got:
            result[f"attributes.{field}"] = {"expected": wanted, "actual": got}
    return result


def relation_keys(relations: list[dict[str, Any]]) -> set[tuple[Any, ...]]:
    return {
        (r["type"], r["source_start"], r["source_end"], r["target_start"], r["target_end"])
        for r in relations
    }


def predicted_relations(facts: list[Fact]) -> set[tuple[Any, ...]]:
    by_id = {f.id: f for f in facts}
    return {
        (
            "medication_indication",
            medication.start,
            medication.end,
            by_id[target].start,
            by_id[target].end,
        )
        for medication in facts
        for target in medication.attributes.get("indication_ids", [])
        if target in by_id
    }


def error_category(diff: dict[str, Any]) -> str:
    if "concept" in diff or "normalization_status" in diff:
        return "normalization"
    if "experiencer" in diff:
        return "experiencer"
    if "polarity" in diff or "certainty" in diff or "hypothetical" in diff:
        return "assertion_scope"
    if "temporality" in diff or "activity" in diff:
        return "temporal_context"
    return "attribute_attachment"


def evaluate(pipeline: Extractor, cases: list[dict[str, Any]]) -> dict[str, Any]:
    totals: Counter[str] = Counter()
    correct_fields: Counter[str] = Counter()
    field_denominators: Counter[str] = Counter()
    families: dict[str, Counter[str]] = defaultdict(Counter)
    errors: list[dict[str, Any]] = []
    per_case: list[dict[str, Any]] = []
    start_time = perf_counter()
    for case in cases:
        extraction = pipeline.extract(Note(case["text"], note_id=case["id"]))
        mapping = map_fhir(extraction)
        predictions = extraction.facts
        gold = case["gold"]
        pairs = match_spans(gold, predictions)
        matched_gold = {g for g, _ in pairs}
        matched_predicted = {p for _, p in pairs}
        family = families[case["family"]]
        totals.update(gold=len(gold), predicted=len(predictions), matched=len(pairs))
        totals["overlap_matched"] += len(match_spans(gold, predictions, overlap=True))
        family.update(gold=len(gold), matched=len(pairs), predicted=len(predictions), cases=1)
        disposition = {d["fact_id"]: d for d in mapping.dispositions}
        case_complete = 0
        for g, p in pairs:
            expected, actual = gold[g], predictions[p]
            diff = differences(expected, actual)
            for field in FIELDS:
                field_denominators[field] += 1
                correct_fields[field] += int(field not in diff)
            for field in ATTRIBUTES:
                if field in expected["attributes"] or field in actual.attributes:
                    field_denominators[f"attributes.{field}"] += 1
                    correct_fields[f"attributes.{field}"] += int(f"attributes.{field}" not in diff)
            complete = not diff
            case_complete += complete
            wanted_type = expected["expected_resource"]
            actual_ref = disposition[actual.id]["resource_reference"]
            actual_type = actual_ref.split("/")[0] if actual_ref else None
            mapping_correct = wanted_type == actual_type
            totals["mapping_disposition_correct"] += mapping_correct
            totals["semantic_mapping_correct"] += mapping_correct and complete
            totals["correct_emitted_gold"] += bool(actual_type) and mapping_correct and complete
            if wanted_type and actual_type:
                totals["correct_type_when_both_mapped"] += mapping_correct
                totals["both_mapped"] += 1
            totals["mapped_matched_gold"] += bool(actual_type)
            if diff or not mapping_correct:
                errors.append(
                    {
                        "case_id": case["id"],
                        "family": case["family"],
                        "category": error_category(diff) if diff else "fhir_mapping",
                        "text": actual.text,
                        "expected": expected,
                        "actual": asdict(actual),
                        "differences": diff,
                        "mapping": {
                            "expected_type": wanted_type,
                            "actual_type": actual_type,
                            "reason": disposition[actual.id]["reason"],
                        },
                    }
                )
        for g, expected in enumerate(gold):
            if g not in matched_gold:
                errors.append(
                    {
                        "case_id": case["id"],
                        "family": case["family"],
                        "category": "missed_mention",
                        "text": expected["text"],
                        "expected": expected,
                        "actual": None,
                    }
                )
        for p, actual in enumerate(predictions):
            if p not in matched_predicted:
                errors.append(
                    {
                        "case_id": case["id"],
                        "family": case["family"],
                        "category": "extra_mention",
                        "text": actual.text,
                        "expected": None,
                        "actual": asdict(actual),
                    }
                )
        totals["complete"] += case_complete
        family["complete"] += case_complete
        totals["mapped"] += sum(d["status"] == "mapped" for d in mapping.dispositions)
        totals["expected_mappable"] += sum(bool(g["expected_resource"]) for g in gold)
        totals["bundles_valid"] += mapping.validation["model_validation"]
        totals["resource_errors"] += sum(
            d["reason"] == "resource_validation_failed" for d in mapping.dispositions
        )
        wanted_relations, got_relations = (
            relation_keys(case.get("relations", [])),
            predicted_relations(predictions),
        )
        totals["relation_tp"] += len(wanted_relations & got_relations)
        totals["relation_fp"] += len(got_relations - wanted_relations)
        totals["relation_fn"] += len(wanted_relations - got_relations)
        per_case.append(
            {
                "id": case["id"],
                "family": case["family"],
                "gold": len(gold),
                "predicted": len(predictions),
                "complete": case_complete,
                "mapping_dispositions": mapping.dispositions,
                "validation": mapping.validation,
            }
        )
    count = len(cases)
    return {
        "metadata": pipeline.metadata,
        "cases": count,
        "totals": dict(totals),
        "strict_spans": prf(
            totals["matched"],
            totals["predicted"] - totals["matched"],
            totals["gold"] - totals["matched"],
        ),
        "overlap_spans": prf(
            totals["overlap_matched"],
            totals["predicted"] - totals["overlap_matched"],
            totals["gold"] - totals["overlap_matched"],
        ),
        "complete_facts": {
            "correct": totals["complete"],
            "gold": totals["gold"],
            "accuracy_over_gold": ratio(totals["complete"], totals["gold"]),
            "precision_over_predictions": ratio(totals["complete"], totals["predicted"]),
        },
        "fields_on_strict_matches": {
            field: {
                "correct": correct_fields[field],
                "denominator": denominator,
                "accuracy": ratio(correct_fields[field], denominator),
            }
            for field, denominator in sorted(field_denominators.items())
        },
        "relations": prf(totals["relation_tp"], totals["relation_fp"], totals["relation_fn"]),
        "mapping": {
            "emitted_mentions": totals["mapped"],
            "abstained_mentions": totals["predicted"] - totals["mapped"],
            "expected_mappable_gold": totals["expected_mappable"],
            "coverage_over_all_gold": ratio(totals["mapped_matched_gold"], totals["gold"]),
            "disposition_accuracy_over_all_gold": ratio(
                totals["mapping_disposition_correct"], totals["gold"]
            ),
            "semantic_mapping_accuracy_over_all_gold": ratio(
                totals["semantic_mapping_correct"], totals["gold"]
            ),
            "correctness_among_emitted_mentions": ratio(
                totals["correct_emitted_gold"], totals["mapped"]
            ),
            "resource_construction_failures": totals["resource_errors"],
        },
        "validation": {
            "bundles_model_valid": totals["bundles_valid"],
            "bundles": count,
            "profile_validation": "not_run",
            "terminology_validation": "not_run",
            "hl7_validator": "not_run",
        },
        "families": {k: dict(v) for k, v in sorted(families.items())},
        "error_categories": dict(Counter(e["category"] for e in errors)),
        "errors": errors,
        "case_results": per_case,
        "extraction_mapping_seconds": round(perf_counter() - start_time, 4),
    }


def report_markdown(report: dict[str, Any]) -> str:
    layers = report["layers"]
    lines = [
        "# Track A results",
        "",
        f"Split: `{report['split']}`. Corpus: `{report['corpus_version']}`.",
        "",
        "Author-visible synthetic benchmark; results are not independent clinical validation.",
        "",
        "| Layer | Cases | Span F1 | Complete facts / gold | "
        "Mapping semantics / gold | Model-valid Bundles |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for layer, result in layers.items():
        lines.append(
            f"| {layer} | {result['cases']} | {result['strict_spans']['f1']} | "
            f"{result['complete_facts']['accuracy_over_gold']} | "
            f"{result['mapping']['semantic_mapping_accuracy_over_all_gold']} | "
            f"{result['validation']['bundles_model_valid']}/{result['cases']} |"
        )
    full = layers.get("full", next(iter(layers.values())))
    lines += [
        "",
        "Complete facts require all annotated semantic fields and attributes to match.",
        "Field scores use strictly matched mentions; "
        "complete-fact recall includes missed gold facts.",
        "Mapping scores include missed facts and abstentions. "
        "See JSON for denominators and emitted-fact precision.",
        "Profile/terminology/HL7-validator checks were not run; "
        "model validation does not establish semantic correctness.",
        "",
        "## Error categories",
        "",
        "| Category | Count |",
        "| --- | ---: |",
    ]
    lines += [f"| {k} | {v} |" for k, v in full["error_categories"].items()]
    lines += [
        "",
        "## Error examples",
        "",
        "| Case | Mention | Category | Differences |",
        "| --- | --- | --- | --- |",
    ]
    for error in full["errors"][:20]:
        diff = json.dumps(error.get("differences", error.get("mapping", {})), ensure_ascii=False)
        lines.append(
            f"| {error['case_id']} | {error['text']} | "
            f"{error['category']} | {diff.replace('|', '/')} |"
        )
    lines += [
        "",
        "Full evidence, rule IDs, case outcomes, runtime versions, "
        "and hashes are in `report.json`.",
        "",
    ]
    return "\n".join(lines)
