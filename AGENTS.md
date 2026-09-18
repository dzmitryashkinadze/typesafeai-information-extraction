# Contributor guidance

## Project objective

Maintain a small comparison demo for clinical-note information extraction:

1. a transparent MedSpaCy/spaCy rule-based baseline; and
2. a typed, validated TypeSafeAI pipeline producing equivalent structured facts and FHIR output.

The comparison is the product. Keep both implementations understandable and evaluate them against the same fixtures and expected facts.

## Working principles

- Treat all clinical text in this repository as synthetic.
- Never silently turn a mention into a patient diagnosis. Preserve assertion, temporality, experiencer, severity, and uncertainty.
- Preserve source text and spans for every extracted item where practical.
- Preserve ambiguity. For example, do not expand `HF` or `COLD` without an explicit documented policy or confidence result.
- Keep FHIR mapping separate from extraction and normalization so each layer can be tested independently.
- Prefer small deterministic fixtures over hidden magic or one-off notebook behavior.
- Pin or record dependency versions when adding MedSpaCy, spaCy, TypeSafeAI, FHIR libraries, or terminology packages.

## Expected implementation shape

The eventual package should have clear modules for:

- synthetic note fixtures and expected semantic facts;
- the classic MedSpaCy/spaCy extractor;
- the TypeSafeAI extractor;
- normalization and assertion/temporality handling;
- FHIR resource/Bundle mapping;
- evaluation and regression tests.

Names may evolve, but the boundary between these responsibilities should remain explicit.

## Testing requirements

Every new extraction rule or schema field should include tests covering the positive case and at least one nearby failure mode. Important cases include:

- negated symptoms and diagnoses;
- family-member experiencer versus patient experiencer;
- historical/inactive conditions;
- future plans and follow-up intervals;
- ambiguous abbreviations and capitalization;
- severity such as `mild`;
- source-span and sentence traceability;
- valid and incomplete FHIR mappings.

Run the project’s formatter, type checker, and test suite when they exist. Do not claim FHIR compliance without validating the generated resources against the selected FHIR version/profile or clearly labeling validation as pending.

## Documentation requirements

Update `README.md` when the input note, expected facts, FHIR mapping policy, commands, or comparison conclusions change. Document any TypeSafeAI-specific assumptions near the integration code, including schema versions and failure behavior.
