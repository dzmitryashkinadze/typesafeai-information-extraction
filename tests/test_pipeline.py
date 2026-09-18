from dataclasses import replace

import pytest

from typesafeai_information_extraction_demo.evaluation import differences, load_corpus, match_spans
from typesafeai_information_extraction_demo.fhir_mapping import map_fhir
from typesafeai_information_extraction_demo.models import Note
from typesafeai_information_extraction_demo.pipeline import ClassicPipeline

DEVELOPMENT = [c for c in load_corpus()["cases"] if c["split"] == "development"]


@pytest.mark.parametrize("case", DEVELOPMENT, ids=[c["id"] for c in DEVELOPMENT])
def test_development_gold_semantics_and_mapping(pipeline, case):
    extraction = pipeline.extract(Note(case["text"], note_id=case["id"]))
    pairs = match_spans(case["gold"], extraction.facts)
    assert len(pairs) == len(case["gold"]) == len(extraction.facts)
    mapping = map_fhir(extraction)
    dispositions = {d["fact_id"]: d for d in mapping.dispositions}
    for g, p in pairs:
        gold, actual = case["gold"][g], extraction.facts[p]
        assert not differences(gold, actual)
        ref = dispositions[actual.id]["resource_reference"]
        assert (ref.split("/")[0] if ref else None) == gold["expected_resource"]
    assert mapping.validation["model_validation"]


def test_parser_and_dependency_evidence_are_real(pipeline):
    assert "parser" in pipeline.nlp.pipe_names
    assert "ner" not in pipeline.nlp.pipe_names
    assert "transformer" not in pipeline.nlp.pipe_names
    facts = pipeline.extract(Note("Patient denies cough. Sister has asthma. Mild fatigue.")).facts
    rules = {e.rule_id for f in facts for e in f.evidence}
    assert "dependency.denial" in rules
    assert "dependency.relative_subject" in rules
    assert "dependency.severity" in rules


def test_overlaps_remain_visible(pipeline):
    result = pipeline.extract(Note("Type 2 diabetes mellitus."))
    assert [f.concept for f in result.facts] == ["Type 2 diabetes mellitus"]
    assert result.diagnostics[0]["suppressed"] >= 1


def test_offsets_survive_unicode_and_whitespace(pipeline):
    note = Note("Assessment:\n•  Mild left knee pain.\n\nPatient denies nausea.\n")
    result = pipeline.extract(note)
    for fact in result.facts:
        fact.validate(note)
        assert note.text[fact.start : fact.end] == fact.text
    assert result.facts[0].laterality == "left"
    assert result.facts[1].polarity == "negated"


def test_same_time_conflict_preserves_both_mentions(pipeline):
    result = pipeline.extract(Note("Cough noted. No cough."))
    assert len(result.facts) == 2
    assert all(f.conflicts for f in result.facts)
    assert all(d["reason"] == "conflicting_assertions" for d in map_fhir(result).dispositions)


def test_historical_and_current_mentions_do_not_conflict(pipeline):
    result = pipeline.extract(Note("History of cough. Patient denies cough."))
    assert {f.temporality for f in result.facts} == {"historical", "unknown"}
    assert not any(f.conflicts for f in result.facts)


def test_unknown_unit_is_preserved_without_coding(pipeline):
    result = pipeline.extract(Note("Creatinine 70 umol/L."))
    assert result.facts[0].attributes["unit"] == "umol/L"
    quantity = map_fhir(result).bundle["entry"][1]["resource"]["valueQuantity"]
    assert quantity == {"value": 70.0, "unit": "umol/L"}


def test_past_review_does_not_create_future_plan(pipeline):
    assert not pipeline.extract(Note("Reviewed ten days ago.")).facts


def test_no_birth_date_or_followup_date_is_invented(pipeline):
    mapping = map_fhir(pipeline.extract(Note("Patient is 47 years old. Return in 3 weeks.")))
    assert "birthDate" not in mapping.bundle["entry"][0]["resource"]
    careplan = mapping.bundle["entry"][1]["resource"]
    assert "period" not in careplan


def test_ablations_use_same_targets_but_separate_context():
    note = Note("No cough.")
    assert ClassicPipeline("targets").extract(note).facts[0].polarity == "affirmed"
    assert ClassicPipeline("context").extract(note).facts[0].polarity == "negated"


def test_bad_note_metadata_and_fact_anchor_fail(pipeline):
    with pytest.raises(ValueError):
        Note("hello", reference_date="not-a-date")
    with pytest.raises(ValueError):
        Note("bonjour", language="fr")
    fact = pipeline.extract(Note("Cough.")).facts[0]
    with pytest.raises(ValueError):
        replace(fact, start=-1).validate(Note("Cough."))
    with pytest.raises(ValueError, match="polarity"):
        replace(fact, polarity="invalid")
