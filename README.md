# Clinical Information Extraction: brittle rules vs. TypeSafeAI

This project is a small, reproducible experiment in extracting structured medical information from a clinical note and representing the result as [FHIR](https://hl7.org/fhir/). It deliberately compares two approaches:

1. a conventional NLP pipeline built from MedSpaCy/spaCy rules; and
2. a planned TypeSafeAI pipeline to evaluate whether typed schemas and validation improve brittle detection logic and make ambiguity, negation, temporality, and mapping errors visible.

The goal is to demonstrate, with a varied corpus and the same expected facts for both tracks, where a rule-based implementation becomes brittle and how a typed extraction contract can address those failure modes.

## Experiment design

### Track A: classic MedSpaCy/spaCy baseline

Option A is implemented: MedSpaCy 1.3.1, spaCy 3.8.2 with the non-transformer `en_core_web_sm` 3.8.0 parser, Python 3.12, and FHIR R4B 4.3.0. Dependency versions and the model URL are recorded in `uv.lock`.

The baseline uses:

- `medspacy.ner.TargetRule` for a curated vocabulary spanning multiple clinical domains;
- `spacy.matcher.DependencyMatcher` for selected assertion, experiencer, attribute, and plan relations;
- MedSpaCy's standard English ConText rules plus project qualifiers and section detection;
- bounded token/regex rules for observations, medication details, and plans;
- separate normalization, reconciliation, and FHIR mapping modules.

Every mention retains original offsets, evidence spans, and rule IDs. Ambiguous abbreviations and conflicting assertions remain inspectable. The Bundle uses text-coded concepts; it does not invent terminology codes.

See the [implementation plan](docs/track-a-plan.md), [annotation guide](docs/annotation-guide.md), [FHIR mapping policy](docs/fhir-mapping.md), and [measured results](docs/track-a-results.md).

## Run Track A

```bash
uv sync --locked
uv run --locked typesafeai-information-extraction-demo extract \
  --input examples/respiratory.txt --patient-id demo-001 --output-dir output/respiratory
```

Setup downloads the pinned Python/parser dependencies. Extraction runs offline afterward. Other examples are `examples/endocrine.txt` and `examples/family_history.txt`; the corpus covers many more note styles.

Each extraction writes:

- `facts.json`: exact note, mention-level facts, attributes, and evidence;
- `bundle.json`: FHIR R4B collection Bundle with a Patient and supported clinical resources;
- `diagnostics.json`: source/version hashes, candidate overlaps, mapping dispositions, and validation results.

Use `--note-id` and `--reference-date YYYY-MM-DD` for metadata. Relative follow-up intervals are preserved without inventing dates or appointments. Running into an existing output directory replaces these generated files.

## Evaluate Track A

The packaged corpus contains 134 cases: 70 development, 14 validation, 42 evaluation, and 8 challenge cases. It includes 12 longer notes and 19 clinical case families. Gold annotations are authored separately from extractor output, with template groups kept within one split. This is an author-visible synthetic benchmark.

```bash
uv run --locked typesafeai-information-extraction-demo evaluate \
  --split evaluation --layer all --output-dir reports/evaluation
uv run --locked typesafeai-information-extraction-demo evaluate \
  --split challenge --output-dir reports/challenge
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked mypy src
```

`--layer all` compares targets only, targets plus ConText, and the complete pipeline. Reports contain semantic field scores, relation scores, mapping coverage, validation levels, and error evidence.

The first evaluation illustrates the gap between identifying mentions and interpreting them:

| Layer | Strict span F1 | Complete facts / 68 gold facts | Model-valid Bundles |
| --- | ---: | ---: | ---: |
| Targets only | 92.9% | 14.7% | 42/42 |
| Targets + ConText | 92.9% | 25.0% | 42/42 |
| Full pipeline | 94.6% | 58.8% | 42/42 |

Model validation and internal reference checks passed, while clinical semantics still failed on unfamiliar phrasing and rule scope. Full profile, terminology, and HL7-validator checks have not been run. The [result report](docs/track-a-results.md) describes the failures and the disclosed gold-label corrections; extractor rules were not tuned on these evaluation results.

### Track B: TypeSafeAI pipeline

Track A already provides a library-independent fact contract. Track B should use the same semantic dimensions and FHIR mapper so the comparison measures extraction behavior:

- concept and optional terminology code;
- original text and character span;
- subject/experiencer (`patient`, `father`, etc.);
- polarity, certainty, and hypothetical status as separate fields;
- temporality and clinical activity as separate fields;
- severity;
- source sentence, ambiguity, and conflicts;
- relations and mapping dispositions.

TypeSafeAI integration is the next track. Both tracks will receive the same corpus and be evaluated against the same annotations. Structural typing alone does not establish clinical correctness; improvements need to be measured.

## Planned milestones

1. **Document the contract** — complete for Track A.
2. **Build the baseline** — complete; extraction CLI and FHIR R4B mapper are available.
3. **Create adversarial fixtures** — complete; varied corpus and split manifest are packaged.
4. **Measure brittleness** — complete; baseline reports and source freeze are recorded.
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

Track A is implemented and verified with tests, formatting/lint checks, type checks, a built wheel, and an extraction/evaluation run from an isolated installation outside the repository. Track B is pending validation of the actual TypeSafeAI API and its extraction approach.
