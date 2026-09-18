# Track A results

Split: `evaluation`. Corpus: `1.0.1`.

Author-visible synthetic benchmark; results are not independent clinical validation.

| Layer | Cases | Span F1 | Complete facts / gold | Mapping semantics / gold | Model-valid Bundles |
| --- | ---: | ---: | ---: | ---: | ---: |
| targets | 42 | 0.9291 | 0.1471 | 0.1029 | 42/42 |
| context | 42 | 0.9291 | 0.25 | 0.2059 | 42/42 |
| full | 42 | 0.9457 | 0.5882 | 0.5588 | 42/42 |

Complete facts require all annotated semantic fields and attributes to match.
Field scores use strictly matched mentions; complete-fact recall includes missed gold facts.
Mapping scores include missed facts and abstentions. See JSON for denominators and emitted-fact precision.
Profile/terminology/HL7-validator checks were not run; model validation does not establish semantic correctness.

## Error categories

| Category | Count |
| --- | ---: |
| temporal_context | 7 |
| assertion_scope | 8 |
| missed_mention | 7 |
| attribute_attachment | 5 |
| fhir_mapping | 2 |
| experiencer | 1 |

## Error examples

| Case | Mention | Category | Differences |
| --- | --- | --- | --- |
| affirmed-5 | dizziness | temporal_context | {"temporality": {"expected": "current", "actual": "unknown"}} |
| affirmed-6 | palpitations | temporal_context | {"temporality": {"expected": "current", "actual": "unknown"}} |
| pseudo-5 | dizziness | assertion_scope | {"polarity": {"expected": "unknown", "actual": "affirmed"}, "certainty": {"expected": "possible", "actual": "unknown"}} |
| pseudo-6 | palpitations | assertion_scope | {"polarity": {"expected": "unknown", "actual": "affirmed"}, "certainty": {"expected": "possible", "actual": "unknown"}} |
| uncertainty-5 | stroke | assertion_scope | {"certainty": {"expected": "possible", "actual": "unknown"}} |
| uncertainty-6 | epilepsy | assertion_scope | {"certainty": {"expected": "possible", "actual": "unknown"}} |
| history-5 | stroke | temporal_context | {"temporality": {"expected": "historical", "actual": "unknown"}} |
| history-6 | epilepsy | temporal_context | {"temporality": {"expected": "historical", "actual": "unknown"}} |
| hypothetical-5 | dizziness | assertion_scope | {"hypothetical": {"expected": true, "actual": false}, "temporality": {"expected": "future", "actual": "unknown"}} |
| hypothetical-6 | palpitations | assertion_scope | {"hypothetical": {"expected": true, "actual": false}, "temporality": {"expected": "future", "actual": "unknown"}} |
| attribute-5 | Pain in the left knee | missed_mention | {} |
| attribute-6 | chest pain | attribute_attachment | {"severity": {"expected": "severe", "actual": null}} |
| value-5 | Creatinine | attribute_attachment | {"attributes.value": {"expected": 1.4, "actual": null}, "attributes.unit": {"expected": "mg/dL", "actual": null}} |
| value-6 | Heart rate | attribute_attachment | {"attributes.value": {"expected": 88, "actual": null}, "attributes.unit": {"expected": "bpm", "actual": null}} |
| follow-up-6 | Schedule a review after a fortnight | missed_mention | {} |
| repeat-5 | dizziness | temporal_context | {"temporality": {"expected": "current", "actual": "unknown"}} |
| repeat-6 | palpitations | temporal_context | {"temporality": {"expected": "current", "actual": "unknown"}} |
| coverage-5 | dyspneic | missed_mention | {} |
| coverage-6 | nausia | missed_mention | {} |
| relation-5 | hypertension | fhir_mapping | {} |

Full evidence, rule IDs, case outcomes, runtime versions, and hashes are in `report.json`.
