"""Option A: spaCy parser → MedSpaCy targets, sections, ConText → custom rules."""

import hashlib
import json
from importlib.metadata import version
from importlib.resources import files
from typing import Any, Literal, cast

import medspacy  # noqa: F401 — registers MedSpaCy factories with spaCy
import spacy
from medspacy.context import ConText, ConTextRule
from medspacy.ner import TargetMatcher, TargetRule
from medspacy.section_detection import Sectionizer, SectionRule
from spacy.tokens import Span

from .context import DependencyRules, add_evidence, bounded_attributes, plan_facts
from .models import Extraction, Fact, Note
from .normalization import link_indications, normalize, reconcile

Layer = Literal["targets", "context", "full"]


def resource(name: str) -> dict[str, Any]:
    return json.loads(files(__package__).joinpath("resources", name).read_text(encoding="utf-8"))


class ClassicPipeline:
    def __init__(self, layer: Layer = "full") -> None:
        if layer not in {"targets", "context", "full"}:
            raise ValueError(f"Unknown layer: {layer}")
        self.layer = layer
        try:
            self.nlp = spacy.load("en_core_web_sm", disable=["ner"])
        except OSError as exc:
            raise RuntimeError(
                "Missing pinned spaCy parser model. Run `uv sync --locked`."
            ) from exc
        if "parser" not in self.nlp.pipe_names:
            raise RuntimeError("DependencyMatcher requires a dependency parser")
        concepts = resource("concepts.json")
        context = resource("context.json")
        self.concepts = {c["id"]: c for c in concepts["concepts"]}
        matcher = cast(
            TargetMatcher,
            self.nlp.add_pipe(
                "medspacy_target_matcher",
                config={"result_type": "group", "span_group_name": "candidates", "prune": False},
            ),
        )
        targets = []
        for concept in self.concepts.values():
            for term in concept["terms"]:
                pattern = None
                if concept.get("case_sensitive"):
                    pattern = [{"ORTH": t.text} for t in self.nlp.make_doc(term)]
                targets.append(TargetRule(term, concept["id"], pattern=pattern))
        matcher.add(targets)
        sectionizer = cast(
            Sectionizer,
            self.nlp.add_pipe(
                "medspacy_sectionizer",
                config={
                    "rules": None,
                    "input_span_type": "group",
                    "span_group_name": "candidates",
                    "span_attrs": None,
                    "require_start_line": True,
                },
            ),
        )
        sectionizer.add(
            [
                SectionRule(
                    **r, pattern=[{"LOWER": t.lower_} for t in self.nlp.make_doc(r["literal"])]
                )
                for r in context["sections"]
            ]
        )
        context_rules: list[dict[str, Any]] = []
        default_context_count = 0
        if layer != "targets":
            component = cast(
                ConText,
                self.nlp.add_pipe(
                    "medspacy_context",
                    config={
                        "rules": "default",
                        "input_span_type": "group",
                        "span_group_name": "candidates",
                        "span_attrs": None,
                    },
                ),
            )
            default_context_count = len(component.rules)
            existing = {(r.literal.lower(), r.category, r.direction) for r in component.rules}
            component.add(
                [
                    ConTextRule(**r)
                    for r in context["rules"]
                    if (r["literal"].lower(), r["category"], r["direction"]) not in existing
                ]
            )
            context_rules = [r.to_dict() for r in component.rules]
        self.dependencies = DependencyRules(self.nlp.vocab)
        fingerprint = hashlib.sha256(
            json.dumps([concepts, context], sort_keys=True).encode()
        ).hexdigest()
        source = b"".join(
            files(__package__).joinpath(name).read_bytes()
            for name in [
                "models.py",
                "pipeline.py",
                "context.py",
                "normalization.py",
                "fhir_mapping.py",
                "evaluation.py",
            ]
        )
        self.metadata = {
            "track": "A",
            "layer": layer,
            "ruleset_version": "1.0.0",
            "resource_sha256": fingerprint,
            "fhir_release": "4.3.0",
            "implementation_sha256": hashlib.sha256(source).hexdigest(),
            "context_rule_sha256": hashlib.sha256(
                json.dumps(context_rules, sort_keys=True).encode()
            ).hexdigest(),
            "versions": {
                p: version(p)
                for p in [
                    "medspacy",
                    "spacy",
                    "en-core-web-sm",
                    "fhir-resources",
                    "typesafeai-information-extraction-demo",
                ]
            },
            "pipes": self.nlp.pipe_names,
            "concepts": len(self.concepts),
            "target_rules": len(targets),
            "context_rules": len(context_rules),
            "default_context_rules": default_context_count,
            "dependency_rules": len(self.dependencies.matcher),
        }

    def extract(self, note: Note) -> Extraction:
        doc = self.nlp(note.text)
        candidates = list(doc.spans["candidates"])
        # Preserve all candidates in diagnostics, then choose longest overlapping spans.
        selected: list[Span] = []
        for span in sorted(candidates, key=lambda s: (-(s.end - s.start), s.start, s.label_)):
            if not any(span.start < other.end and other.start < span.end for other in selected):
                selected.append(span)
        spans = sorted(selected, key=lambda s: (s.start, s.end))
        facts: list[Fact] = []
        for span in spans:
            concept = self.concepts[span.label_]
            fact = Fact(
                id=f"{note.note_id}:{span.start_char}:{span.end_char}:{span.label_}",
                note_id=note.note_id,
                kind=concept["kind"],
                concept=concept["name"],
                text=span.text,
                start=span.start_char,
                end=span.end_char,
                sentence_start=span.sent.start_char,
                sentence_end=span.sent.end_char,
                section=span._.section_category,
                normalization_status="ambiguous" if concept.get("alternatives") else "matched",
                alternatives=concept.get("alternatives", []).copy(),
            )
            add_evidence(fact, note, f"target.{span.label_}", span.start_char, span.end_char)
            title = span._.section_title
            if title is not None and len(title):
                add_evidence(
                    fact, note, f"section.{fact.section}", title.start_char, title.end_char
                )
            if self.layer != "targets":
                for modifier in span._.modifiers:
                    cue = doc[slice(*modifier.modifier_span)]
                    # Heading semantics come from the Sectionizer. In particular,
                    # "history" inside "Family history:" does not establish past time.
                    if any(
                        section.title_start <= cue.start and cue.end <= section.title_end
                        for section in doc._.sections
                    ):
                        continue
                    add_evidence(
                        fact,
                        note,
                        f"context.{modifier.category}.{modifier.rule.literal}",
                        cue.start_char,
                        cue.end_char,
                    )
                    match modifier.category:
                        case "NEGATED_EXISTENCE":
                            fact.polarity = "negated"
                        case "POSSIBLE_EXISTENCE":
                            fact.certainty = "possible"
                        case "HISTORICAL":
                            fact.temporality = "historical"
                        case "HYPOTHETICAL":
                            fact.hypothetical = True
                        case "FAMILY":
                            fact.experiencer = "relative_unspecified"
                        case "INACTIVE":
                            fact.activity = "inactive"
                        case "RESOLVED":
                            fact.activity = "resolved"
                        case "ACTIVE":
                            fact.activity = "active"
                if fact.section == "family_history":
                    fact.experiencer = "relative_unspecified"
                if (
                    fact.section in {"past_medical_history", "history"}
                    and fact.temporality == "unknown"
                ):
                    fact.temporality = "historical"
            facts.append(fact)
        if self.layer == "full":
            self.dependencies.apply(doc, spans, facts, note)
            for span, fact in zip(spans, facts, strict=True):
                bounded_attributes(span, fact, note, spans)
            facts.extend(plan_facts(doc, note))
            normalize(facts, note)
            link_indications(facts, note)
            reconcile(facts)
        facts.sort(key=lambda f: (f.start, f.end))
        for fact in facts:
            fact.validate(note)
        diagnostics = [
            {
                "stage": "candidates",
                "all_spans": [
                    {"start": s.start_char, "end": s.end_char, "label": s.label_}
                    for s in candidates
                ],
                "overlap_policy": "longest_span_then_position_then_label",
                "suppressed": len(candidates) - len(spans),
            }
        ]
        return Extraction(note, facts, self.metadata.copy(), diagnostics)
