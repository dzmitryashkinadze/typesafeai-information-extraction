"""Explicit text-coded FHIR R4B mappings; no clinical inference from resource shape."""

import json
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from fhir.resources.R4B import get_fhir_model_class
from pydantic import ValidationError

from .models import Extraction, Fact, MappingResult


def stable_id(value: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"clinical-extraction-demo:{value}"))


def concept(text: str) -> dict[str, str]:
    return {"text": text}


def status(system: str, value: str) -> dict[str, Any]:
    return {
        "coding": [{"system": f"http://terminology.hl7.org/CodeSystem/{system}", "code": value}]
    }


def plan(fact: Fact, subject: dict[str, str], text: str) -> dict[str, Any]:
    return {
        "resourceType": "CarePlan",
        "status": "unknown",
        "intent": "proposal" if fact.certainty == "possible" else "plan",
        "subject": subject,
        "description": text,
        "activity": [{"detail": {"status": "unknown", "description": text}}],
    }


def resource_for(
    fact: Fact, extraction: Extraction, subject: dict[str, str]
) -> tuple[dict[str, Any] | None, str]:
    if fact.normalization_status != "matched":
        return None, "ambiguous_concept"
    if fact.conflicts:
        return None, "conflicting_assertions"
    if fact.hypothetical:
        return None, "hypothetical_finding"
    if fact.experiencer in {"unknown", "other"}:
        return None, "unresolved_experiencer"
    if fact.polarity == "unknown":
        return None, "unknown_polarity"
    if (
        fact.kind in {"medication", "plan"}
        and fact.polarity == "negated"
        and fact.temporality == "future"
    ):
        return None, "negated_plan"
    sentence = extraction.note.text[fact.sentence_start : fact.sentence_end].strip()
    role = fact.attributes.get("mention_role")
    if role == "medication_indication":
        return None, "indication_is_not_independent_diagnosis"
    if role == "diagnostic_evaluation":
        return plan(fact, subject, sentence), "planned_evaluation"
    if role == "plan_context":
        return None, "plan_mention_is_not_independent_diagnosis"
    if fact.experiencer != "patient":
        if fact.kind not in {"condition", "symptom"}:
            return None, "unsupported_non_patient_fact"
        if fact.polarity != "affirmed" or fact.certainty == "possible":
            return None, "unsupported_family_assertion"
        return {
            "resourceType": "FamilyMemberHistory",
            "status": "partial",
            "patient": subject,
            "relationship": concept(fact.experiencer.replace("_", " ")),
            "condition": [{"code": concept(fact.concept)}],
        }, "family_history"
    if fact.kind in {"condition", "symptom"}:
        if fact.attributes.get("explicit_refutation"):
            return {
                "resourceType": "Condition",
                "subject": subject,
                "code": concept(fact.concept),
                "verificationStatus": status("condition-ver-status", "refuted"),
            }, "explicit_refutation"
        if fact.polarity == "negated":
            return {
                "resourceType": "Observation",
                "status": "unknown",
                "subject": subject,
                "code": concept(f"Presence of {fact.concept}"),
                "valueBoolean": False,
            }, "negative_finding"
        result: dict[str, Any] = {
            "resourceType": "Condition",
            "subject": subject,
            "code": concept(fact.concept),
        }
        if fact.activity != "unknown":
            result["clinicalStatus"] = status("condition-clinical", fact.activity)
        if fact.certainty == "possible":
            result["verificationStatus"] = status("condition-ver-status", "provisional")
        if fact.severity:
            result["severity"] = concept(fact.severity)
        if fact.temporality == "historical":
            result["note"] = [{"text": "Historical mention; current activity is not inferred."}]
        if fact.laterality:
            result.setdefault("note", []).append({"text": f"Laterality: {fact.laterality}"})
        return result, "patient_finding"
    if fact.kind == "observation":
        if "value" not in fact.attributes or fact.polarity != "affirmed":
            return None, "missing_or_negated_numeric_value"
        unit = fact.attributes.get("unit")
        quantity: dict[str, Any] = {"value": fact.attributes["value"]}
        if unit:
            quantity["unit"] = unit
        # Units remain display text. UCUM coding has not been verified.
        result = {
            "resourceType": "Observation",
            "status": "unknown",
            "subject": subject,
            "code": concept(fact.concept),
        }
        if "diastolic" in fact.attributes:
            if fact.concept != "Blood pressure":
                return None, "unsupported_ratio_value"
            diastolic = {**quantity, "value": fact.attributes["diastolic"]}
            result["component"] = [
                {"code": concept("Systolic blood pressure"), "valueQuantity": quantity},
                {"code": concept("Diastolic blood pressure"), "valueQuantity": diastolic},
            ]
        else:
            result["valueQuantity"] = quantity
        return result, "numeric_observation"
    if fact.kind == "medication":
        action = fact.attributes.get("action", "unspecified")
        dosage = fact.attributes.get("dosage_text")
        if action == "start" and dosage and "dose" in fact.attributes:
            result = {
                "resourceType": "MedicationRequest",
                "status": "draft",
                "intent": "order",
                "subject": subject,
                "medicationCodeableConcept": concept(fact.concept),
                "dosageInstruction": [{"text": dosage}],
            }
            return result, "explicit_medication_order"
        if action in {"start", "stop", "increase", "decrease", "consider"}:
            return plan(fact, subject, sentence), "medication_plan"
        result = {
            "resourceType": "MedicationStatement",
            "status": "not-taken"
            if fact.polarity == "negated"
            else "active"
            if action in {"take", "continue"}
            else "unknown",
            "subject": subject,
            "medicationCodeableConcept": concept(fact.concept),
        }
        if dosage:
            result["dosage"] = [{"text": dosage}]
        return result, "reported_medication"
    if fact.kind == "plan":
        return plan(fact, subject, fact.text), "instruction_or_follow_up"
    return None, "unsupported_fact_kind"


def validate_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """Model/primitive/choice-field validation plus local reference checks, not profiles."""
    errors: list[str] = []
    try:
        get_fhir_model_class("Bundle").model_validate(bundle)
    except ValidationError as exc:
        errors.append(str(exc))
    entries = bundle.get("entry", [])
    references = {f"{e['resource']['resourceType']}/{e['resource']['id']}" for e in entries} | {
        e["fullUrl"] for e in entries
    }
    ids = [e["fullUrl"] for e in entries]
    if len(ids) != len(set(ids)):
        errors.append("Duplicate Bundle fullUrl")

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            ref = value.get("reference")
            if ref and ref not in references:
                errors.append(f"Unresolved internal reference: {ref}")
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(bundle)
    return {
        "fhir_release": "4.3.0",
        "model_validation": not errors,
        "internal_references": not any("reference" in e for e in errors),
        "errors": errors,
        "profile_validation": "not_run",
        "terminology_validation": "not_run",
        "hl7_validator": "not_run",
    }


def map_fhir(extraction: Extraction) -> MappingResult:
    patient_id = stable_id(f"patient:{extraction.note.patient_id}")
    patient = {
        "resourceType": "Patient",
        "id": patient_id,
        "identifier": [
            {"system": "urn:clinical-extraction-demo:patient", "value": extraction.note.patient_id}
        ],
    }
    subject = {"reference": f"Patient/{patient_id}"}
    entries = [{"fullUrl": f"urn:uuid:{patient_id}", "resource": patient}]
    dispositions: list[dict[str, Any]] = []
    emitted: dict[str, str] = {}
    for fact in extraction.facts:
        resource, reason = resource_for(fact, extraction, subject)
        disposition: dict[str, Any] = {
            "fact_id": fact.id,
            "status": "mapped" if resource else "unmapped",
            "reason": reason,
            "resource_reference": None,
        }
        if resource:
            # Dedupe only identical resource payloads; all mentions retain dispositions.
            fingerprint = json.dumps(resource, sort_keys=True)
            resource_id = emitted.get(fingerprint)
            if resource_id is None:
                resource_id = stable_id(
                    f"{extraction.note.note_id}:{extraction.note.patient_id}:{fingerprint}"
                )
                resource["id"] = resource_id
                try:
                    validated = get_fhir_model_class(resource["resourceType"]).model_validate(
                        resource
                    )
                    resource = validated.model_dump(mode="json", exclude_none=True)
                except ValidationError as exc:
                    disposition.update(
                        status="unmapped", reason="resource_validation_failed", errors=str(exc)
                    )
                    dispositions.append(disposition)
                    continue
                emitted[fingerprint] = resource_id
                entries.append({"fullUrl": f"urn:uuid:{resource_id}", "resource": resource})
            disposition["resource_reference"] = f"{resource['resourceType']}/{resource_id}"
        dispositions.append(disposition)
    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "id": stable_id(f"bundle:{extraction.note.patient_id}:{extraction.note.note_id}"),
        "entry": entries,
    }
    return MappingResult(bundle, dispositions, validate_bundle(bundle))
