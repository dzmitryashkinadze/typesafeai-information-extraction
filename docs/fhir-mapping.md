# Track A FHIR mapping policy

The mapper uses `fhir.resources.R4B` and FHIR 4.3.0. Bundles are collections, not transaction requests or full document Bundles. Text-only clinical CodeableConcepts avoid unverified terminology codes. HL7 status systems are coded explicitly; observation units remain display strings without inferred UCUM codes.

## Eligibility and resources

Every fact gets a mapping disposition containing its fact ID, mapped/unmapped status, reason, and optional resource reference. Facts/evidence are retained even when no resource is emitted.

| Evidence | Mapping |
| --- | --- |
| External patient ID | Minimal Patient with a deterministic UUID ID and identifier; demographic extraction is not implemented |
| Affirmed patient condition/symptom | Condition; explicit activity, severity, possible verification, and historical/laterality notes where supported |
| Negated patient condition/symptom | Observation whose text code is “Presence of …” and whose boolean value is false |
| Explicit refutation of prior diagnosis | Condition with verification status `refuted`; no invented clinical activity |
| Planned exclusion/evaluation | CarePlan containing the source sentence, rather than a refuted Condition |
| Relative's affirmed condition | FamilyMemberHistory with a text relationship and partial status |
| Numeric finding | Observation with valueQuantity; blood pressure uses systolic/diastolic components |
| Reported medication | MedicationStatement; explicitly taking/continuing supports active status; otherwise unknown; negative reports support not-taken |
| Start instruction with explicit dose | Draft MedicationRequest with intent order and source dosage text; it is not an authenticated prescription |
| Vague change, stop/increase/decrease/consider instruction | CarePlan with source sentence; possible plans use proposal intent |
| Diet/hydration/exercise instruction or follow-up interval | CarePlan with textual activity, preserving the interval in the fact sidecar |

Ambiguous normalization, contradictions, hypothetical findings, unknown subjects, negative future plans, and unsupported non-patient facts are not mapped. A medication indication alone and a condition mentioned only in a plan do not establish a patient Condition. Missing numeric values require abstention. Possible numeric/family cases outside supported rules remain limitations.

Unknown clinical activity is omitted, not changed to active. Bare affirmed mentions do not receive confirmed verification status. A historical mention does not produce an invented onset date. Patient age does not produce a birth date. Follow-up advice does not produce a booked appointment or a dated event.

See the specification's [Condition guidance](https://hl7.org/fhir/R4B/condition.html) and [CarePlan definition](https://hl7.org/fhir/R4B/careplan.html).

## Evidence, deduplication, and IDs

Resource IDs use deterministic UUIDs scoped to note/patient and payload. All resources reference the Patient in the same Bundle. Identical resource payloads are emitted once, with each source mention retaining its own disposition/reference. Conflicting polarities at the same normalized concept, subject, and temporal context are flagged before mapping; differently classified or unknown time contexts can escape reconciliation, as measured in the challenge set.

Source spans, context cues, rule IDs, and medication-indication relations travel in `facts.json`. `diagnostics.json` links mention IDs to resources and records mapping reasons. The mapper does not add an undocumented FHIR extension for character offsets.

## Validation levels

Implemented checks cover Python FHIR model construction, primitive/choice-field rules provided by the library, unique Bundle fullUrls, and internal references. Resource-construction failures become explicit unmapped dispositions and are counted in evaluation; they cannot vanish silently from metrics.

Profile, complete FHIRPath invariant, external terminology, and official HL7 validator checks are not implemented. Model-valid output is not a claim of complete FHIR compliance or semantic correctness. This distinction is measured directly: all evaluation Bundles pass implemented checks while many extracted facts have incorrect meanings. See [FHIR validation guidance](https://hl7.org/fhir/R4B/validation.html).
