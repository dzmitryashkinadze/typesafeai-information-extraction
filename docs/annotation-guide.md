# Track A annotation contract

The corpus is package data in `src/typesafeai_information_extraction_demo/resources/corpus.json`. Cases are authored with expected semantics; offsets are calculated from explicitly supplied surface strings, not extractor predictions. They are not independently blinded clinical annotations.

## Case format

Each case has an ID, clinical case family, template group, split, exact input text, gold mentions, and optional relations. Longer notes additionally have `note_type=multi_section`. Repeated surfaces have distinct offsets. Spans use Python Unicode character indices and an exclusive end: `text[start:end]` must equal the annotated surface.

`validate_corpus` checks IDs, offset consistency, required semantic fields, relation endpoints, and template-group separation. Every mention includes an expected FHIR resource type or `null` for intended abstention. That mapping expectation is separate from extraction semantics.

## Semantic labels

| Dimension | Policy |
| --- | --- |
| Concept | Canonical text name; missed synonyms/misspellings are annotated as their intended concepts and evaluated as coverage failures |
| Polarity | Affirmed mention, negated presence, or unknown; ambiguous constructions such as “not necessarily absent” remain unknown |
| Certainty | `possible` for an explicit uncertainty cue; otherwise `unknown` unless certainty is explicitly supported; affirmation is not diagnostic confirmation |
| Hypothetical | Conditional warnings and possible future symptoms are marked independently from certainty |
| Time | Explicit positive present-condition reports use `current`; history/childhood use `historical`; yesterday/recently use `recent`; instructions/evaluation plans use `future`; unqualified or untimed negative mentions use `unknown` |
| Medication time | A planned action uses `future`; explicitly past changes use `historical`; an unqualified reported regimen has unknown event timing, with taking status represented separately by its action |
| Activity | Only explicit active/inactive/resolved wording supports activity; history alone does not imply inactive |
| Experiencer | Patient, named relative, unspecified relative, or unknown; general pronoun coreference is not annotated as resolved |
| Severity/laterality | Attach to the relevant concept, including wording outside the mention span |
| Normalization | Known canonical names use `matched`; standalone ambiguous abbreviations use `ambiguous`; an explicit known expansion supports normalization |
| Attributes | Observation values/units, medication action/dose/route/frequency, follow-up intervals, and explicit refutation where stated |

These are operational POC conventions. In particular, time labels are coarse context labels, not invented onset dates. The contract should be reviewed before using a different corpus, and both tracks must use the same conventions.

## Mapping expectations

Affirmed patient findings typically map to Condition; absent findings map to a presence Observation with `valueBoolean=false`. Refutation of a prior diagnosis is a separate case. Family conditions map to FamilyMemberHistory. Numeric findings require correctly attached values. Medication indications and vague plan mentions do not establish an independent patient diagnosis.

Explicit medication orders with dose details map to draft MedicationRequest; reported use maps to MedicationStatement; vague changes map to CarePlan. Ambiguity, unknown experiencers, hypothetical findings, and same-time conflicts can require abstention.

The relation annotations cover medication-to-indication links with mention offsets as endpoints. Observation/attribute attachment is scored separately through attributes. Annotation of an indication concept does not authorize mapping it as a diagnosis.

## Splits and versioning

The delivered corpus has 70 development, 14 validation, 42 evaluation, and 8 challenge cases. Groups with the same authored template stay in one split. Counts differ from the initial percentage targets because template grouping takes priority. Longer notes combine multiple case families. They may reuse vocabulary/cues from development while holding out the full note composition.

Development cases are regression tests; validation is used for inspection, and evaluation/challenge report remaining failures. Author-visible templates limit claims of generalization. Future work should add independently authored notes and a fresh evaluation set if rules are tuned after seeing results.

Corpus 1.0.1 corrects two challenge timing annotations after the first run: the first explicitly defined `MS` mention inherits its current finding context, and “was increased” is a historical medication change. Ruleset 1.0.0 is unchanged. Original/final corpus hashes and corrections are disclosed in `docs/track-a-freeze.json`.
