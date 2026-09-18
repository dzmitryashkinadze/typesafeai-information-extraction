# Track A baseline results

Option A is implemented with Python 3.12.14, MedSpaCy 1.3.1, spaCy 3.8.2, `en_core_web_sm` 3.8.0, and `fhir.resources` 8.3.0 using its R4B namespace. Runtime dependencies and the parser model are pinned in `uv.lock`.

The pipeline has 61 concepts: 40 condition/symptom concepts, 3 ambiguous abbreviations, 10 medications, and 8 observation types. It uses 89 target rules, 123 ConText rules including MedSpaCy's 102 English defaults, 8 section headings, 4 dependency patterns, and explicit token/regex fallback logic.

## Evaluation

There are 134 author-visible synthetic cases across 19 clinical case families, plus multi-section and challenge groupings. Twelve are longer notes. The full pipeline matches 114/114 development facts and 21/22 validation facts. Evaluation contains 42 cases and 68 gold facts.

| Layer | Strict span F1 | Complete facts | Semantically correct mapping dispositions | Model-valid Bundles |
| --- | ---: | ---: | ---: | ---: |
| Targets only | 92.91% | 10/68 (14.71%) | 7/68 (10.29%) | 42/42 |
| Targets + ConText | 92.91% | 17/68 (25.00%) | 14/68 (20.59%) | 42/42 |
| Full pipeline | 94.57% | 40/68 (58.82%) | 38/68 (55.88%) | 42/42 |

Complete-fact scoring requires canonical concept, polarity, certainty, hypothetical status, time, activity, subject, severity, laterality, normalization, and applicable attributes to agree with gold. It includes missed mentions in the denominator. Correct mapping dispositions also require the expected resource type or intended abstention. They are not a score for complete FHIR profile/terminology validation.

The full pipeline detects 61 mentions with no span false positives and misses 7 gold mentions. It maps 52 mentions and abstains on 9. Among emitted mentions, 34/52 (65.38%) have the complete expected semantics and resource type. A type-correct Bundle can therefore still carry an incorrect clinical claim.

## Measured brittle moments

| Trigger | Observed behavior | Main limitation |
| --- | --- | --- |
| “Stroke cannot be excluded” | Uncertainty remains unknown | Cue coverage and ordering |
| “Should dizziness develop, call…” | Hypothetical finding becomes a patient Condition | Conditional construction not covered |
| “Dizziness is not necessarily absent” | Ambiguous polarity becomes affirmed | Composite assertion semantics |
| “Creatinine measured at 1.4 mg/dL” | Concept detected, value missed; resource withheld | Numeric attachment grammar |
| “Pain in the left knee is mild” | Gold finding missed | Discontinuous/reordered lexical pattern |
| “Chest pain, described as severe” | Severity missed | Postnominal attachment |
| “To manage hypertension, start…” | Indication becomes an independent Condition | Reversed relation direction |
| “Schedule a review after a fortnight” | Follow-up missed | Temporal expression coverage |
| “Patient is dyspneic” / “nausia” | Mentions missed | Unseen synonym and spelling coverage |
| Relative followed by pronoun within family-history section | Generic section experiencer overrides unknown pronoun | Section/local subject precedence |

Challenge cases add neither/nor negation, contradictory reports, explicit refutation, unknown units, abbreviation definitions, and dose changes. In the dose-change case, the first dose (500 mg) is extracted instead of the new dose (1000 mg), and a past change is classified as future. Differently classified current/unknown time contexts also allow a contradiction to escape reconciliation.

Validation found another rule collision: MedSpaCy's default forward `resolved` cue wins the modifier overlap pruning against the project's backward activity cue. “Anemia resolved” therefore leaves activity unknown. During development, a different heading/cue collision was corrected: “history” in “Family history:” is now interpreted through the Sectionizer rather than as a historical-time cue.

These results identify lexical, context, relation, and mapping work for later experiments. Structural validation alone cannot correct them. Track B should be measured against the same facts and shared mapper rather than receiving a different annotation policy.

## Reproducibility and disclosure

[Evaluation report](results/evaluation/report.md) and [JSON](results/evaluation/report.json) contain ablations, per-field denominators, relation metrics, dispositions, evidence, and hashes. [Challenge report](results/challenge/report.md) and [JSON](results/challenge/report.json) are separate from the headline evaluation.

Ruleset 1.0.0 was frozen before evaluation/challenge extraction. Two challenge timing labels were subsequently corrected in corpus 1.0.1: the first defined MS alias is current, and “was increased” is historical. No extraction rules were changed after these runs. The [freeze manifest](track-a-freeze.json) records source/lock/rule hashes, initial/final corpus hashes, and the corrections. Reports use the corrected corpus; evaluation results are unchanged.

These small, authored templates do not establish general clinical performance. Shared vocabulary and composed familiar cues are disclosed in the annotation guide. Future changes prompted by these reports should use a new ruleset version and a fresh independently authored evaluation set.

## Verification

The implementation passes 103 tests, Ruff lint/format checks, and mypy checks. The wheel and source distribution build successfully. An isolated installation of the wheel, run from `/tmp`, loads packaged rule/corpus data and completes extraction and validation-split evaluation. Implemented R4B model/reference checks pass; official HL7/profile/terminology checks are not run.
