# Track A implementation plan

Status: option A selected and implemented as ruleset 1.0.0. This document retains the original design and alternatives. See the [results](track-a-results.md), [annotation guide](annotation-guide.md), and [FHIR mapping policy](fhir-mapping.md) for the delivered baseline. No LLM or TypeSafeAI is used in Track A.

## 1. Objective and boundaries

Build a credible conventional pipeline that extracts clinical facts from varied English notes and maps supported facts into a FHIR Bundle. Explain successes and failures through identifiable rules, source spans, and intermediate results.

The baseline should receive a reasonable vocabulary and context rules. We should measure brittleness rather than construct a deliberately weak implementation or assume every difficult case will fail. Later comparisons should use identical input, annotations, and mapping policies.

Initial scope:

- Conditions and symptoms, including assertion, activity, severity, and experiencer.
- Family history with explicitly stated relatives and conditions.
- Simple numeric observations: laboratory results and vital signs with values and units.
- Medication mentions with explicitly stated action, dose, route, and frequency where available.
- Simple treatment instructions and follow-up intervals.
- Document sections and source evidence.

Start with a curated vocabulary of approximately 30–50 concepts across respiratory, cardiovascular, endocrine, neurologic, and general symptoms, plus 8–12 medications and 6–10 observation types. This bounds coverage without tying the system to one note. Broader terminology integration is a later extension.

Full clinical coverage, unrestricted relation extraction, and general cross-sentence coreference are outside the first version. Include examples of these in the challenge corpus so their impact is visible.

“No LLM” still allows a conventional pretrained POS tagger and dependency parser. The proposed spaCy/scispaCy models below use no transformer component. A completely model-free variation is possible, but would replace dependency matching with token and window rules.

## 2. Core dependency options

Choose one main stack; implement its adapter against a common fact model. These options overlap: scispaCy supplies biomedical linguistic processing, while MedSpaCy supplies clinical rule and context components.

| Option | Proposed core dependencies | Strengths for this experiment | Custom work and tradeoffs |
| --- | --- | --- | --- |
| A — MedSpaCy + spaCy | `medspacy`, compatible `spacy`, non-transformer `en_core_web_sm` | Closest to the intended baseline; target, context, and section components; dependency rules can supplement context rules | Curated vocabulary, relation rules, values, temporal handling, reconciliation, and FHIR mapping remain our responsibility |
| B — spaCy + negspaCy | `spacy`, `negspacy`, `en_core_web_sm` | Smaller clinical abstraction layer; token/phrase/dependency rules are easy to inspect; configurable English negation | Family history, uncertainty, history/activity, sections, and conflict resolution need more custom code |
| C — scispaCy + MedSpaCy | `scispacy`, compatible `spacy`, `en_core_sci_sm`, compatible `medspacy` | Biomedical tokenizer/parser and candidate mention detection combined with clinical context rules | Model compatibility and candidate filtering add complexity; optional terminology linking adds downloads and installation burden |
| D — EDS-NLP rule components | `edsnlp`, matching and qualifier components; parser only if needed | Integrated matching and qualifier components; potentially useful for a later multilingual experiment | Its primary focus is French clinical notes; English cues, sentence behavior, and component support need verification and adaptation |

Option A is my recommendation for this project's first baseline. It matches the proposed `TargetRule`/`DependencyMatcher` design and leaves enough custom logic visible to study maintenance cost. Option B suits a study focused on building and maintaining clinical rules ourselves. Option C suits a study focused on biomedical vocabulary and parser behavior. Option D is less attractive for an English-only first version.

MedSpaCy provides target matching, ConText, section detection, and postprocessing; it can extend an existing spaCy pipeline. Its default pipeline must not be assumed to provide dependency parses. See the [MedSpaCy repository](https://github.com/medspacy/medspacy). spaCy's `DependencyMatcher` requires dependency annotations from a parser or equivalent component; see its [API documentation](https://spacy.io/api/dependencymatcher).

negspaCy implements NegEx and supports configurable cue sets, pseudo-negations, and termination phrases. It addresses negation rather than the entire clinical context model. See the [negspaCy repository](https://github.com/jenojp/negspacy).

scispaCy offers biomedical models, an abbreviation detector, and optional linking. Its abbreviation detector handles explicit long-form/short-form pairs; it is not a general disambiguator for standalone abbreviations. Use `en_core_sci_sm`, avoiding transformer models. See the [scispaCy repository](https://github.com/allenai/scispacy). EDS-NLP's primary focus is French clinical notes; see its [documentation](https://aphp.github.io/edsnlp/latest/).

### Runtime and compatibility gate

The planning scaffold specified Python `>=3.14` and had no NLP dependencies. The implementation now uses Python `>=3.12,<3.13`, with the exact NLP/model combination resolved in `uv.lock`. Package and model versions must be selected together.

Proposed starting point: Python 3.12, with 3.11 as a fallback if native dependencies cause problems. This is a candidate to verify, not an established compatibility guarantee. If retaining Python 3.14 is preferred, first investigate the selected stack's installability rather than promising support.

The currently published scispaCy metadata requires Python `>=3.9,<3.13`, so option C cannot use the current project requirement unchanged. MedSpaCy's minimum Python metadata alone does not establish support for 3.14 across its dependencies. See [scispaCy package metadata](https://pypi.org/project/scispacy/) and [MedSpaCy package metadata](https://pypi.org/project/medspacy/).

After selection, perform a short compatibility check: install in an isolated environment, load the exact model, confirm pipeline ordering and dependency annotations, run one target/context/relation example, then pin working versions and model artifacts in the lockfile. Record versions in evaluation output. Runtime changes belong to that implementation step.

### Shared dependencies and alternatives

| Concern | Proposed choice | Alternatives and rationale |
| --- | --- | --- |
| Intermediate facts | Standard-library `dataclasses` and `Enum`, explicit validation functions | Pydantic for richer runtime validation; `TypedDict` for a lighter JSON contract but fewer runtime guarantees |
| FHIR construction | `fhir.resources` with an explicit release namespace | Plain dictionaries plus release-matched validation for a transparent mapping; another generated FHIR model library if strict R4 is required |
| Evaluation | `pytest`, standard-library metric calculations | Avoid a general ML evaluation dependency for a small corpus |
| Development checks | `ruff`, one type checker (`mypy` or `pyright`) | Select one checker; avoid duplicate toolchains |
| Dates and intervals | Explicit rules plus `datetime` for the initial supported grammar | Add a date parsing library only if broader expressions become necessary; control locale and reference date |
| Terminology | Versioned local concept/synonym table | Optional QuickUMLS or scispaCy linker later; evaluate installation, terminology access, and candidate ambiguity separately |

Ordinary dataclasses or Pydantic do not introduce TypeSafeAI. A common intermediate representation is needed to evaluate Track A and later reuse its FHIR mapping.

## 3. Data contract

Accept a note with an external `note_id`, `patient_id`, language, and optional encounter/reference date. Preserve the exact input text and its character offsets. Unknown metadata stays unknown: age does not produce an invented date of birth, and an unanchored interval does not produce an invented calendar date.

Produce three outputs:

1. Mention-level facts, including conflicting and unresolved evidence.
2. Reconciled facts eligible for mapping, plus explicit mapping dispositions.
3. FHIR Bundle and an evaluation/diagnostic report.

Separate context dimensions rather than putting everything into one assertion enum:

| Field group | Proposed content |
| --- | --- |
| Identity/evidence | Stable mention ID, note ID, exact text, `[start, end)` offsets, sentence/section ID, evidence spans |
| Concept | Kind, canonical name, optional verified code/system, alternatives, normalization status |
| Assertion | Polarity (`affirmed`, `negated`, `unknown`); certainty (`certain`, `possible`, `unknown`); conditional/hypothetical flag |
| Time/activity | Current/historical/future/unknown, explicit time expression, active/inactive/resolved/unknown |
| Experiencer | Patient, identified relative, other, unknown |
| Attributes | Severity, laterality, numeric value/unit, medication attributes, follow-up duration as applicable |
| Relations | Relative-has-condition, medication-for-condition, observation-has-value, plan-targets-concept |
| Explanation | Matched rule IDs, cue spans, parser/model version, conflicts, abstention reason |

A historical condition is not automatically inactive. A negated symptom is not automatically a refuted diagnosis. An instruction to “rule out” a condition is not a completed exclusion. A hypothetical warning is not an active symptom.

Use `matched`, `ambiguous`, `unresolved`, and `conflicting` statuses rather than inventing confidence probabilities for hand-written rules. If scores are added, label them as heuristics or linker similarity, not calibrated clinical certainty.

## 4. Pipeline stages

```text
Exact note text + metadata
  → tokenization / sentence boundaries / sections / dependency parse
  → candidate mentions and numeric expressions
  → assertion, experiencer, time, severity, and relation rules
  → normalization and conflict reconciliation
  → facts + evidence + mapping dispositions
  → FHIR resources and Bundle
  → semantic metrics + structural validation + error report
```

### Stage 1 — Document processing

- Load the selected tokenizer and conventional parser; disable unrelated pretrained NER in options A/B to keep concept coverage explicit.
- Detect section headings such as history, family history, examination, assessment, and plan.
- Check behavior on lists, fragments, abbreviations, and missing punctuation.
- Preserve original offsets. If text normalization is necessary, maintain an offset map or normalize token attributes without rewriting input.
- Choose one authoritative sentence-boundary strategy. Verify its interaction with the parser instead of stacking competing sentence components by default.

### Stage 2 — Candidate detection

- For option A, use MedSpaCy `TargetRule`; for B, use spaCy phrase/token matchers; for C, combine curated targets with filtered biomedical candidates.
- Keep concepts, synonyms, capitalization policy, and ambiguous abbreviations in versioned data files.
- Apply exact/token matching first. Avoid fuzzy matching initially so failure causes remain attributable.
- Extract numeric candidates and units without prematurely attaching them to the nearest clinical term.
- Retain overlapping candidate spans in a span group or intermediate collection before resolving overlaps. Do not let `doc.ents` silently discard nested candidates.

### Stage 3 — Clinical context

- Apply supported ConText/NegEx/qualifier rules, including preceding/following cues, pseudo-negations, termination cues, and section context.
- Determine polarity, certainty, hypothetical status, historical context, and experiencer independently.
- Treat a section as evidence, not an absolute label: “Mother has diabetes; patient does not” needs clause-level subjects.
- Use dependency rules for selected constructions where syntactic attachment matters. Keep token/window fallbacks explicit and separately measurable.
- Record competing rules and resolve them using documented specificity/precedence. Leave incompatible results flagged when precedence cannot resolve them.

### Stage 4 — Attributes and relations

- Attach severity and laterality through bounded syntactic or token rules.
- Bind observation values/units using local patterns, punctuation boundaries, and competing-candidate checks.
- Recognize medication actions (`taking`, `start`, `stop`, `increase`, `consider`) separately from the drug mention. Extract dose/route/frequency only when supported by explicit text.
- Extract follow-up intervals and treatment instructions. Preserve a text plan when detailed resource mapping is unsupported.
- Restrict first-version subject resolution to explicit relatives and documented local constructions. Flag unsupported cross-sentence pronouns.

### Stage 5 — Normalization and reconciliation

- Normalize known synonyms using the curated table; preserve original wording.
- Resolve abbreviations only through explicit definitions or a documented local policy. Retain alternatives for ambiguous short forms.
- Verify terminology codes before including them. Text-only `CodeableConcept` is preferable to a guessed code; a UMLS CUI is not automatically a SNOMED CT code.
- Keep repeated mentions and evidence, then aggregate only compatible facts. Contradictory statements or changing time contexts must remain inspectable.
- Never infer a diagnosis solely from an observation value or a medication indication.

### Stage 6 — FHIR mapping

Selected default: FHIR R4B 4.3.0 with a collection Bundle. R4 4.0.1 and R5 5.0.0 remain possible future alternatives if interoperability requirements favor them. The delivered mapper uses R4B throughout construction, examples, and validation.

The current `fhir.resources` library defaults to R5 and offers an R4B namespace; these must not be labeled interchangeably as R4. See the [library documentation](https://github.com/nazrulworld/fhir.resources).

| Fact | Proposed mapping policy |
| --- | --- |
| Patient identity | Minimal `Patient` based on external ID; demographic fields only when explicit and semantically compatible |
| Affirmed patient condition | `Condition`, with supported certainty/activity/severity and temporal fields |
| Negated symptom/finding | A negative `Observation` when the chosen concept/value representation supports it; otherwise retain as an unmapped fact |
| Explicitly refuted prior diagnosis | `Condition.verificationStatus=refuted` under a documented policy; distinguish this from generic negation and planned evaluation |
| Relative's condition | `FamilyMemberHistory`; do not create a patient Condition |
| Numeric laboratory/vital finding | `Observation` with value, unit, and explicit timing; preserve unrecognized units rather than inventing UCUM codes |
| Medication actually reported | `MedicationStatement` in R4B when context and required fields support it |
| Explicit medication order | `MedicationRequest` only for a sufficiently specified ordering statement |
| Advice, vague medication change, follow-up | `CarePlan` with textual activity details when appropriate; do not fabricate an appointment or a specific order |
| Ambiguous/conflicting fact | Explicit `unmapped`/`needs_review` disposition with reason; retain evidence in the fact output |

FHIR distinguishes clinical status from verification status and provides specific guidance for refuted conditions; see [Condition](https://hl7.org/fhir/R4B/condition.html). Planned activity can be represented through [CarePlan](https://hl7.org/fhir/R4B/careplan.html).

Use deterministic IDs and internally consistent references. Maintain a sidecar mapping from resources to mention/evidence IDs; define a source-span extension only if evidence must travel inside FHIR. A sidecar is enough for the first demo.

Validate resource construction, Bundle references, and release-specific constraints. Add the HL7 validator as a separate integration check where practical; Python model construction is not complete profile or terminology validation. Report these levels separately, following [FHIR validation guidance](https://hl7.org/fhir/R4B/validation.html).

## 5. Corpus and annotation plan

Create a corpus before tuning extraction rules. Target approximately 100 short cases plus 12–20 multi-section notes. Short cases isolate a feature; longer notes exercise interactions and reconciliation. These counts are practical targets rather than statistical evidence of general clinical performance.

Use varied concepts, authors' phrasing, section layouts, sentence lengths, and punctuation. Keep a bounded vocabulary but evaluate unseen synonyms separately from unseen context constructions.

| Case family | Example contrasts | What to annotate/check |
| --- | --- | --- |
| Affirmed findings | “Reports wheezing” / “Wheezing noted on exam” | Mention boundaries and patient assertion |
| Negation | “Denies nausea” / “Nausea was not observed” | Preceding/following scope |
| Coordination | “No fever or cough, but has wheezing” | Shared negation and termination |
| Pseudo-negation | “Not only cough but also fever” / “No change in tremor” | Prevent false polarity changes |
| Uncertainty/exclusion | “Possible appendicitis” / “Rule out appendicitis” / “Appendicitis was excluded” | Possible, planned evaluation, completed exclusion |
| Historical/activity | “History of epilepsy” / “Seizures resolved” / “Epilepsy remains active” | History separate from activity |
| Experiencer | “Sister has asthma; patient denies asthma” | Relative and patient clauses |
| Hypothetical | “Call if rash develops” / “Rash developed yesterday” | Advice versus actual finding |
| Abbreviations | Explicit expansion pair / standalone “MS” / lowercase “ms” in a unit | Ambiguity and lexical collisions |
| Section boundaries | Finding under family history / same finding under assessment | Section evidence and clause overrides |
| Severity/laterality | “Mild left knee pain and severe right ankle pain” | Correct attribute attachment |
| Values/units | “Na 132 mmol/L; K 4.2 mmol/L” / “BP 128/76” | Values attach to correct observations |
| Medications | “Takes metformin” / “Stop metformin” / “Consider metformin” | Report, order, discontinued action, possibility |
| Follow-up/time | “Review in ten days” / “Reviewed ten days ago” | Future interval versus past event |
| Repetition/conflict | Earlier denial followed by later positive report | Evidence and temporal reconciliation |
| Note mechanics | Bullet lists, fragments, Unicode, headings, blank lines | Segmentation and exact offsets |
| Coverage limits | Unseen synonym, misspelling, unusual word order | Lexical versus contextual failure |
| Cross-sentence subject | “Her mother has lupus. She takes steroids.” | Unsupported pronoun ambiguity |

Each case contains input metadata, gold mentions/spans, semantic fields, relationships, expected ambiguity/abstention, and expected mapping disposition. Validate the annotation files themselves, including substring/offset consistency.

Separate expected semantics from exact resource serialization. An absent optional field is not the same as a wrong clinical assertion. Document acceptable alternatives where the text genuinely permits more than one interpretation.

Split by note/template family, not random individual paraphrases. Suggested split: 50% development, 20% validation, 30% frozen evaluation. Keep closely related contrast pairs together; reserve some entire wording templates for evaluation. Rules may be tuned on development and selected on validation. Changes prompted by evaluation require a new ruleset version and disclosure of test exposure.

Add a clearly labeled challenge set for unsupported phenomena. Do not fold challenge-set failures into a headline score without stating coverage. Having inspected all authored fixtures limits claims about independence; later evaluation can add newly authored, independently reviewed notes.

## 6. Evaluation and brittleness analysis

Report separate extraction and mapping results:

- Strict span precision/recall/F1 and a secondary overlap score.
- Concept accuracy on matched mentions, plus lexical coverage/missed mentions.
- Per-field accuracy for polarity, certainty, experiencer, temporality, activity, and severity; state denominators and unknown/unannotated handling.
- Relation and attribute attachment precision/recall.
- Complete-fact accuracy: concept and all required semantic fields correct together.
- Ambiguity/abstention rate, correctness among emitted facts, and incorrect unsupported claims.
- Mapping coverage across all gold facts, semantic mapping correctness, and structural validation success among emitted resources.
- Contrast-pair consistency: irrelevant formatting should preserve facts, while a polarity/subject change should change the relevant field.
- Runtime and number of rules, with short notes and longer notes measured separately.

Avoid rewarding empty Bundles for passing validation. A structurally valid but semantically wrong Condition is an extraction/mapping failure. Report both and preserve the facts-to-resource link.

For each observed error record the case ID, expected/actual fact, pipeline stage, relevant rules/cues, root cause, and correction cost. Useful categories are missing vocabulary, segmentation, scope, parser attachment, experiencer, temporal ambiguity, normalization, reconciliation, and FHIR mapping.

Run small ablations where the stack permits them: targets only; targets plus context; full pipeline with dependency rules. This establishes what each layer contributes. Keep a record of a few rule changes that fix development cases and cause regressions elsewhere. Failure examples should come from measured output.

Record limitations honestly: type validation catches shape/invariant errors, while clinical context mistakes require semantic evidence or a different extraction method. Track A results should establish which brittle moments Track B actually needs to address.

## 7. Proposed repository structure

```text
src/typesafeai_information_extraction_demo/
  models.py                 # facts, evidence, relations, dispositions
  pipeline.py               # orchestration for the selected stack
  extractors/classic.py      # MedSpaCy/spaCy or chosen alternative
  context.py                # custom context and relation logic
  normalization.py          # concept lookup and reconciliation
  fhir_mapping.py           # release-specific fact-to-resource policy
  evaluation.py             # matching, metrics, error categories
  cli.py                    # extract/evaluate commands
  resources/                # versioned targets, cues, concepts, sections
tests/
  fixtures/development/
  fixtures/validation/
  fixtures/evaluation/
  fixtures/challenge/
  test_context.py
  test_relations.py
  test_normalization.py
  test_fhir_mapping.py
  test_evaluation.py
docs/
  track-a-plan.md
  annotation-guide.md
  fhir-mapping.md
```

Exact module names can evolve. Keep extraction, normalization, and FHIR mapping independently callable. Ship resource files as package data and avoid requiring a repository-relative working directory.

Proposed commands after implementation:

```text
uv run typesafeai-information-extraction-demo extract --input note.txt --patient-id demo-001 --output-dir output/
uv run typesafeai-information-extraction-demo evaluate --split evaluation --output-dir reports/
uv run pytest
uv run ruff check .
```

These commands are implemented. Extraction runs offline after package/model setup. Output includes `facts.json`, `bundle.json`, and `diagnostics.json`; evaluation also produces a machine-readable report and a readable error table.

## 8. Implementation milestones and review artifacts

| Milestone | Work | Completion evidence |
| --- | --- | --- |
| 0. Stack selection | Choose option, runtime, FHIR release, initial scope | Short decision record and verified dependency/model combination |
| 1. Contract and corpus | Fact model, annotation guide, fixture format, initial diverse cases, split manifest | Reviewed gold annotations; offsets and schema validated; evaluation split fixed |
| 2. Candidate baseline | Tokenization, sections, curated targets, source spans | Targets-only results and documented vocabulary coverage |
| 3. Context and relations | Assertion, subject, time/activity, attributes, medications, values, plans | Field-level tests and context/dependency ablations on development/validation |
| 4. Normalization and FHIR | Concept mapping, conflict handling, resource construction, references | Supported resource examples, mapping dispositions, validation report |
| 5. Frozen evaluation | Run selected ruleset, compute metrics, categorize failures | Reproducible report with denominators, coverage, failures, and rule/version manifest |
| 6. Demo handoff | CLI, examples spanning multiple note types, README commands | Fresh-environment run, selected checks passing, documented limitations and Track B targets |

Initial corpus and implementation can grow together, but define annotation semantics and split policy before context tuning. Commit corpus/ruleset versions with reports so results can be reproduced.

Completion does not require perfect extraction or a preselected score. It requires a functioning selected stack, traceable results across the agreed case families, honest frozen-set evaluation, and valid release-specific FHIR output for supported mappings. No benchmark numbers should be promised before the corpus exists.

## 9. Decisions for review

The delivered selection is A + Python 3.12 + FHIR R4B + curated text-only concepts. The alternatives below are retained for future review.

1. Core stack: A (recommended), B, C, or D.
2. Runtime: test Python 3.12 first (recommended), or investigate preserving 3.14.
3. FHIR release: R4B 4.3.0 (proposed), strict R4 4.0.1, or R5 5.0.0.
4. Scope: conditions/symptoms, family history, observations, medication actions, and simple plans (proposed); alternatively deliver conditions/family history first and add the other types in a second increment.
5. Terminology: curated verified local mapping first (recommended), or include a terminology linker from the start.

The recommendation is A + a verified Python 3.12 environment + explicit R4B mapping + curated terminology, delivered in the milestones above. Dependency feasibility and your selections may change that combination before implementation.
