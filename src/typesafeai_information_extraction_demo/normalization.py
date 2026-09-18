"""Deterministic lexical normalization and conservative conflict reconciliation."""

import re
from collections import defaultdict

from .context import add_evidence
from .models import Fact, Note


def normalize(facts: list[Fact], note: Note) -> None:
    for fact in facts:
        if fact.normalization_status != "ambiguous":
            continue
        # Only an explicit, known long-form (SHORT) definition is supported.
        for alternative in fact.alternatives:
            definition = re.search(
                rf"\b{re.escape(alternative)}\s*\(\s*{re.escape(fact.text)}\s*\)",
                note.text,
                re.IGNORECASE,
            )
            if definition:
                fact.concept = alternative
                fact.normalization_status = "matched"
                add_evidence(
                    fact,
                    note,
                    "normalization.explicit_definition",
                    definition.start(),
                    definition.end(),
                )
                break


def reconcile(facts: list[Fact]) -> None:
    groups: dict[tuple[str, str, str], list[Fact]] = defaultdict(list)
    for fact in facts:
        if not fact.hypothetical and fact.kind in {"condition", "symptom"}:
            groups[(fact.concept, fact.experiencer, fact.temporality)].append(fact)
    for group in groups.values():
        polarities = {f.polarity for f in group}
        if "affirmed" in polarities and "negated" in polarities:
            for fact in group:
                fact.conflicts = [other.id for other in group if other.polarity != fact.polarity]


def link_indications(facts: list[Fact], note: Note) -> None:
    for medication in (f for f in facts if f.kind == "medication"):
        for target in facts:
            if target.kind not in {"condition", "symptom"} or target.start < medication.end:
                continue
            if target.sentence_start != medication.sentence_start:
                continue
            between = note.text[medication.end : target.start]
            if re.search(r"\bfor\s*$", between, re.IGNORECASE) and not re.search(r"[;.]", between):
                medication.attributes.setdefault("indication_ids", []).append(target.id)
                target.attributes["mention_role"] = "medication_indication"
                add_evidence(
                    target, note, "relation.medication_indication", medication.start, target.end
                )
