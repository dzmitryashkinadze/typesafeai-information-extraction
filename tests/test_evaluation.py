from copy import deepcopy
from dataclasses import replace

import pytest

from typesafeai_information_extraction_demo.evaluation import (
    evaluate,
    load_corpus,
    match_spans,
    prf,
    validate_corpus,
)
from typesafeai_information_extraction_demo.models import Extraction, Note


def test_corpus_has_varied_cases_and_no_template_leakage():
    corpus = load_corpus()
    assert len(corpus["cases"]) >= 120
    assert len({c["family"] for c in corpus["cases"]}) >= 18
    assert len([c for c in corpus["cases"] if c.get("note_type") == "multi_section"]) >= 12
    validate_corpus(corpus)


def test_wrong_offsets_and_template_leakage_fail():
    corpus = load_corpus()
    broken = deepcopy(corpus)
    broken["cases"][0]["gold"][0]["start"] += 1
    with pytest.raises(ValueError, match="offsets"):
        validate_corpus(broken)
    broken = deepcopy(corpus)
    broken["cases"][1]["split"] = "evaluation"
    with pytest.raises(ValueError, match="crosses splits"):
        validate_corpus(broken)


def test_span_matching_is_one_to_one(pipeline):
    actual = pipeline.extract(Note("Patient reports cough.")).facts[0]
    gold = [{"start": actual.start, "end": actual.end, "kind": "symptom"}]
    assert len(match_spans(gold, [actual, replace(actual)])) == 1
    assert match_spans(gold, [replace(actual, start=actual.start - 1)]) == []
    assert len(match_spans(gold, [replace(actual, start=actual.start - 1)], overlap=True)) == 1


def test_wrong_semantics_cannot_hide_behind_valid_fhir(pipeline):
    case = next(c for c in load_corpus()["cases"] if c["id"] == "negation-1")

    class WrongPolarity:
        metadata = pipeline.metadata

        def extract(self, note):
            result = pipeline.extract(note)
            result.facts[0].polarity = "affirmed"
            return result

    result = evaluate(WrongPolarity(), [case])
    assert result["strict_spans"]["f1"] == 1.0
    assert result["validation"]["bundles_model_valid"] == 1
    assert result["complete_facts"]["accuracy_over_gold"] == 0.0
    assert result["mapping"]["semantic_mapping_accuracy_over_all_gold"] == 0.0


def test_empty_predictions_do_not_score_as_correct_extraction(pipeline):
    case = next(c for c in load_corpus()["cases"] if c["id"] == "affirmed-1")

    class Empty:
        metadata = pipeline.metadata

        def extract(self, note):
            return Extraction(note, [], self.metadata)

    result = evaluate(Empty(), [case])
    assert result["validation"]["bundles_model_valid"] == 1
    assert result["strict_spans"]["recall"] == 0.0
    assert result["complete_facts"]["accuracy_over_gold"] == 0.0
    assert result["mapping"]["coverage_over_all_gold"] == 0.0
    assert result["strict_spans"]["precision"] is None


def test_undefined_metrics_are_null():
    assert prf(0, 0, 0)["f1"] is None
