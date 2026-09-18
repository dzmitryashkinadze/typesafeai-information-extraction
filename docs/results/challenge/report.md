# Track A results

Split: `challenge`. Corpus: `1.0.1`.

Author-visible synthetic benchmark; results are not independent clinical validation.

| Layer | Cases | Span F1 | Complete facts / gold | Mapping semantics / gold | Model-valid Bundles |
| --- | ---: | ---: | ---: | ---: | ---: |
| targets | 8 | 0.9333 | 0.0 | 0.0 | 8/8 |
| context | 8 | 0.9333 | 0.125 | 0.125 | 8/8 |
| full | 8 | 0.9677 | 0.6875 | 0.625 | 8/8 |

Complete facts require all annotated semantic fields and attributes to match.
Field scores use strictly matched mentions; complete-fact recall includes missed gold facts.
Mapping scores include missed facts and abstentions. See JSON for denominators and emitted-fact precision.
Profile/terminology/HL7-validator checks were not run; model validation does not establish semantic correctness.

## Error categories

| Category | Count |
| --- | ---: |
| assertion_scope | 2 |
| fhir_mapping | 1 |
| temporal_context | 2 |
| missed_mention | 1 |

## Error examples

| Case | Mention | Category | Differences |
| --- | --- | --- | --- |
| challenge-1 | fever | assertion_scope | {"polarity": {"expected": "negated", "actual": "affirmed"}} |
| challenge-1 | cough | assertion_scope | {"polarity": {"expected": "negated", "actual": "affirmed"}} |
| challenge-3 | cough | fhir_mapping | {} |
| challenge-3 | cough | temporal_context | {"temporality": {"expected": "current", "actual": "unknown"}} |
| challenge-6 | mitral stenosis | missed_mention | {} |
| challenge-7 | metformin | temporal_context | {"temporality": {"expected": "historical", "actual": "future"}, "attributes.dose": {"expected": 1000, "actual": 500.0}} |

Full evidence, rule IDs, case outcomes, runtime versions, and hashes are in `report.json`.
