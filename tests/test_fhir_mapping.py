from typesafeai_information_extraction_demo.fhir_mapping import map_fhir, validate_bundle
from typesafeai_information_extraction_demo.models import Note


def resources(mapping, kind):
    return [e["resource"] for e in mapping.bundle["entry"] if e["resource"]["resourceType"] == kind]


def test_absence_is_not_refuted_condition(pipeline):
    mapping = map_fhir(pipeline.extract(Note("Patient denies chest pain.")))
    assert not resources(mapping, "Condition")
    assert resources(mapping, "Observation")[0]["valueBoolean"] is False


def test_explicit_refutation_uses_verification_not_activity(pipeline):
    result = pipeline.extract(Note("The previous diagnosis of pneumonia was ruled out."))
    condition = resources(map_fhir(result), "Condition")[0]
    assert condition["verificationStatus"]["coding"][0]["code"] == "refuted"
    assert "clinicalStatus" not in condition


def test_history_alone_does_not_mean_inactive(pipeline):
    condition = resources(map_fhir(pipeline.extract(Note("History of asthma."))), "Condition")[0]
    assert "clinicalStatus" not in condition
    assert condition["note"]


def test_ambiguity_and_hypothetical_are_retained_unmapped(pipeline):
    mapping = map_fhir(pipeline.extract(Note("HF noted. Call if rash develops.")))
    assert {d["reason"] for d in mapping.dispositions} == {
        "ambiguous_concept",
        "hypothetical_finding",
    }
    assert len(mapping.bundle["entry"]) == 1


def test_rule_out_is_evaluation_plan(pipeline):
    mapping = map_fhir(pipeline.extract(Note("Rule out appendicitis.")))
    assert resources(mapping, "CarePlan")
    assert not resources(mapping, "Condition")


def test_family_condition_never_becomes_patient_condition(pipeline):
    mapping = map_fhir(pipeline.extract(Note("Father has prostate cancer.")))
    assert resources(mapping, "FamilyMemberHistory")[0]["relationship"]["text"] == "father"
    assert not resources(mapping, "Condition")


def test_unresolved_subject_and_family_medication_are_not_mapped(pipeline):
    mapping = map_fhir(pipeline.extract(Note("Mother has lupus. She takes aspirin.")))
    assert mapping.dispositions[-1]["reason"] == "unresolved_experiencer"
    family_med = map_fhir(pipeline.extract(Note("Mother takes aspirin.")))
    assert family_med.dispositions[0]["reason"] == "unsupported_non_patient_fact"


def test_indication_is_not_independent_diagnosis(pipeline):
    mapping = map_fhir(pipeline.extract(Note("Patient takes metformin for diabetes.")))
    assert resources(mapping, "MedicationStatement")
    assert not resources(mapping, "Condition")
    assert mapping.dispositions[-1]["reason"] == "indication_is_not_independent_diagnosis"


def test_vague_medication_plan_does_not_fabricate_order(pipeline):
    mapping = map_fhir(pipeline.extract(Note("Start aspirin.")))
    assert resources(mapping, "CarePlan")
    assert not resources(mapping, "MedicationRequest")


def test_explicit_medication_dose_is_preserved(pipeline):
    mapping = map_fhir(pipeline.extract(Note("Start lisinopril 10 mg oral daily.")))
    request = resources(mapping, "MedicationRequest")[0]
    assert request["dosageInstruction"][0]["text"] == "10 mg oral daily"
    assert request["status"] == "draft"
    assert request["intent"] == "order"


def test_negated_future_order_is_not_emitted(pipeline):
    result = pipeline.extract(Note("Start metformin 500 mg daily."))
    result.facts[0].polarity = "negated"
    mapping = map_fhir(result)
    assert mapping.dispositions[0]["reason"] == "negated_plan"
    assert not resources(mapping, "MedicationRequest")


def test_blood_pressure_uses_components(pipeline):
    observation = resources(map_fhir(pipeline.extract(Note("BP 128/76 mmHg."))), "Observation")[0]
    assert "valueQuantity" not in observation
    assert [c["valueQuantity"]["value"] for c in observation["component"]] == [128, 76]


def test_identical_resources_dedupe_with_all_source_links(pipeline):
    extraction = pipeline.extract(Note("Patient reports cough. Patient reports cough."))
    first, second = map_fhir(extraction), map_fhir(extraction)
    assert first.bundle == second.bundle
    assert len(resources(first, "Condition")) == 1
    assert len(first.dispositions) == 2
    assert (
        first.dispositions[0]["resource_reference"] == first.dispositions[1]["resource_reference"]
    )


def test_missing_reference_is_rejected(pipeline):
    mapping = map_fhir(pipeline.extract(Note("Cough noted.")))
    condition = resources(mapping, "Condition")[0]
    condition["subject"]["reference"] = "Patient/nonexistent"
    assert not validate_bundle(mapping.bundle)["internal_references"]


def test_choice_field_violation_is_rejected(pipeline):
    mapping = map_fhir(pipeline.extract(Note("No cough.")))
    observation = resources(mapping, "Observation")[0]
    observation["valueQuantity"] = {"value": 5}
    assert not validate_bundle(mapping.bundle)["model_validation"]
