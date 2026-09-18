# Clinical Information Extraction: brittle rules vs. TypeSafeAI

This project is a small, reproducible experiment in extracting structured medical information from a clinical note and representing the result as [FHIR](https://hl7.org/fhir/). It deliberately compares two approaches:

1. a conventional NLP pipeline built from MedSpaCy/spaCy rules; and
2. a TypeSafeAI pipeline whose typed schema and validation addresses brittle detection logic and make ambiguity, negation, temporality, and mapping errors visible.

The goal is not to build a production clinical system or to make clinical decisions. The goal is to demonstrate, with the same note and the same expected facts, where a rule-based implementation becomes brittle and how a typed extraction contract can address those failure modes.

## Experiment design

### Track A: classic MedSpaCy/spaCy baseline

Implement a deliberately understandable baseline using:

- `medspacy.ner.TargetRule` for terms such as `HTN`, `Type 2 Diabetes`, `fatigue`, `HF`, `migraines`, and `pneumonia`;
- `spacy.matcher.DependencyMatcher` for patterns such as `denies` + symptom, family-member + cancer, and plan/follow-up constructions;
- sentence-level context rules for negation, historical status, and experiencer;
- a hand-written normalization layer that converts entities into FHIR resources.

The baseline should be deterministic and testable, but its limitations should be visible rather than hidden. We will record false positives/negatives and show how small wording changes break token, dependency, abbreviation, or scope assumptions.

### Track B: TypeSafeAI pipeline

Define a typed extraction schema first, then have the extraction pipeline produce validated instances of that schema. The schema should make these fields explicit:

- concept and optional terminology code;
- original text and character span;
- subject/experiencer (`patient`, `father`, etc.);
- assertion (`present`, `absent`, `refuted`, `possible`, `planned`);
- temporality (`current`, `historical`, `recent`, `future`);
- severity;
- source sentence and confidence/ambiguity;
- target FHIR resource type and mapping status.

TypeSafeAI-specific integration should be added only after the schema and baseline are working. This keeps the comparison fair: both tracks receive the same note and are evaluated against the same typed expected output.

## Planned milestones

1. **Document the contract** — finish the expected facts, ambiguity policy, FHIR profile assumptions, and evaluation criteria.
2. **Build the baseline** — add dependencies, a MedSpaCy pipeline, rule definitions, normalization, and a JSON/FHIR output example.
3. **Create adversarial fixtures** — vary negation scope, family history, capitalization, abbreviations, tense, and sentence order.
4. **Measure brittleness** — add tests and a small error table showing what the baseline misses or misclassifies.
5. **Add TypeSafeAI** — implement the typed schema and validated extraction/mapping flow using the project’s actual TypeSafeAI API.
6. **Compare outputs** — evaluate semantic correctness, FHIR validation, traceability to source spans, and behavior on the adversarial fixtures.
7. **Polish the demo** — provide a runnable command, readable intermediate output, final FHIR `Bundle`, and a short conclusions section.

## Evaluation criteria

The demo should compare more than entity recognition. For each fact, check:

- concept normalization;
- assertion and negation;
- temporality and activity status;
- experiencer/family history;
- severity;
- plan versus diagnosis;
- preservation of ambiguity;
- source-span traceability;
- FHIR resource shape and validation.

Success means that the output is safe to inspect and explain: unsupported inferences are not silently promoted to patient facts, and invalid or incomplete mappings are reported as such.

## Development status

The repository currently contains the Python package scaffold only. The next implementation step is the classic baseline and its fixtures. TypeSafeAI API details, terminology choices, and the precise FHIR version/profile should be pinned in the implementation documentation once confirmed.
