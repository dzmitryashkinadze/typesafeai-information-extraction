"""Small, inspectable dependency and bounded-token rules supplementing ConText."""

import re
from typing import Any

from spacy.matcher import DependencyMatcher
from spacy.tokens import Doc, Span

from .models import Evidence, Fact, Note

RELATIVES = {
    "mother",
    "father",
    "sister",
    "brother",
    "daughter",
    "son",
    "grandmother",
    "grandfather",
}
SEVERITIES = {"mild", "moderate", "severe"}
ACTIONS = {"take", "start", "stop", "continue", "increase", "decrease", "consider"}
NUMBER = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|twelve)"
FOLLOW_UP = re.compile(
    rf"\b(?:return|follow[ -]up|review|recheck)\s+in\s+({NUMBER})\s+(days?|weeks?|months?)\b",
    re.IGNORECASE,
)
INSTRUCTION = re.compile(
    r"\b(?:maintain|continue)\s+(?:the\s+|a\s+|current\s+)?"
    r"(?:dietary plan|low-salt diet|diet|exercise|hydration)\b",
    re.IGNORECASE,
)
WORD_NUMBERS = dict(
    zip("one two three four five six seven eight nine ten".split(), range(1, 11), strict=True)
)
WORD_NUMBERS["twelve"] = 12


def add_evidence(fact: Fact, note: Note, rule: str, start: int, end: int) -> None:
    evidence = Evidence.at(note, rule, start, end)
    if evidence not in fact.evidence:
        fact.evidence.append(evidence)


def clause(span: Span) -> Span:
    """Conservative local scope: semicolons, contrast, and line breaks terminate it."""
    doc = span.doc
    left, right = span.sent.start, span.sent.end
    for token in doc[left : span.start]:
        if token.text == ";" or token.lower_ in {"but", "however"} or "\n" in token.text:
            left = token.i + 1
    for token in doc[span.end : right]:
        if token.text == ";" or token.lower_ in {"but", "however"} or "\n" in token.text:
            right = token.i
            break
    return doc[left:right]


class DependencyRules:
    def __init__(self, vocab: Any) -> None:
        self.matcher = DependencyMatcher(vocab, validate=True)
        self.matcher.add(
            "dependency.denial",
            [
                [
                    {"RIGHT_ID": "cue", "RIGHT_ATTRS": {"LEMMA": "deny"}},
                    {
                        "LEFT_ID": "cue",
                        "REL_OP": ">>",
                        "RIGHT_ID": "target",
                        "RIGHT_ATTRS": {"POS": {"IN": ["NOUN", "PROPN"]}},
                    },
                ]
            ],
        )
        self.matcher.add(
            "dependency.relative_subject",
            [
                [
                    {"RIGHT_ID": "verb", "RIGHT_ATTRS": {"POS": {"IN": ["VERB", "AUX"]}}},
                    {
                        "LEFT_ID": "verb",
                        "REL_OP": ">",
                        "RIGHT_ID": "relative",
                        "RIGHT_ATTRS": {
                            "LOWER": {"IN": sorted(RELATIVES)},
                            "DEP": {"IN": ["nsubj", "nsubjpass"]},
                        },
                    },
                    {
                        "LEFT_ID": "verb",
                        "REL_OP": ">>",
                        "RIGHT_ID": "target",
                        "RIGHT_ATTRS": {"POS": {"IN": ["NOUN", "PROPN"]}},
                    },
                ]
            ],
        )
        self.matcher.add(
            "dependency.severity",
            [
                [
                    {"RIGHT_ID": "target", "RIGHT_ATTRS": {"POS": {"IN": ["NOUN", "PROPN"]}}},
                    {
                        "LEFT_ID": "target",
                        "REL_OP": ">",
                        "RIGHT_ID": "severity",
                        "RIGHT_ATTRS": {"LOWER": {"IN": sorted(SEVERITIES)}, "DEP": "amod"},
                    },
                ]
            ],
        )
        self.matcher.add(
            "dependency.medication_action",
            [
                [
                    {"RIGHT_ID": "action", "RIGHT_ATTRS": {"LEMMA": {"IN": sorted(ACTIONS)}}},
                    {
                        "LEFT_ID": "action",
                        "REL_OP": ">>",
                        "RIGHT_ID": "target",
                        "RIGHT_ATTRS": {"POS": {"IN": ["NOUN", "PROPN"]}},
                    },
                ]
            ],
        )

    def apply(self, doc: Doc, spans: list[Span], facts: list[Fact], note: Note) -> None:
        for match_id, indices in self.matcher(doc):
            rule = doc.vocab.strings[match_id]
            target_index = indices[0] if rule == "dependency.severity" else indices[-1]
            for span, fact in zip(spans, facts, strict=True):
                if not span.start <= target_index < span.end:
                    continue
                cue_index = (
                    indices[1]
                    if rule in {"dependency.relative_subject", "dependency.severity"}
                    else indices[0]
                )
                cue = doc[cue_index]
                local = clause(span)
                if not local.start <= cue_index < local.end:
                    continue
                if rule == "dependency.denial":
                    fact.polarity = "negated"
                elif rule == "dependency.relative_subject":
                    fact.experiencer = cue.lower_
                elif rule == "dependency.severity":
                    fact.severity = cue.lower_
                elif fact.kind == "medication":
                    fact.attributes["action"] = cue.lemma_
                else:
                    continue
                add_evidence(fact, note, rule, cue.idx, cue.idx + len(cue))


def bounded_attributes(span: Span, fact: Fact, note: Note, spans: list[Span]) -> None:
    """Explicit fallbacks; their limited scope is deliberately recorded in evidence."""
    local = clause(span)
    prefix = span.doc[local.start : span.start]
    # A relative or explicit patient mention nearest to the target wins in this local clause.
    subjects = [t for t in prefix if t.lower_ in RELATIVES | {"patient"}]
    if subjects:
        subject = subjects[-1]
        fact.experiencer = subject.lower_
        add_evidence(fact, note, "token.explicit_subject", subject.idx, subject.idx + len(subject))
    elif fact.section == "family_history":
        fact.experiencer = "relative_unspecified"
    elif prefix and prefix[0].lower_ in {"she", "he", "they"} and span.sent.start > 0:
        # No general coreference: retain the uncertainty instead of choosing a person.
        fact.experiencer = "unknown"
        add_evidence(
            fact, note, "token.unresolved_pronoun", prefix[0].idx, prefix[0].idx + len(prefix[0])
        )

    for token in span.doc[max(local.start, span.start - 3) : span.start]:
        if token.lower_ in SEVERITIES and fact.severity is None:
            fact.severity = token.lower_
            add_evidence(fact, note, "token.local_severity", token.idx, token.idx + len(token))
        if token.lower_ in {"left", "right", "bilateral"}:
            fact.laterality = token.lower_
            add_evidence(fact, note, "token.local_laterality", token.idx, token.idx + len(token))

    if fact.section in {"past_medical_history", "history"} and fact.temporality == "unknown":
        fact.temporality = "historical"
    if fact.section == "plan" and fact.kind in {"condition", "symptom"}:
        fact.attributes["mention_role"] = "plan_context"

    before = prefix.text.lower()
    if re.search(r"\b(?:reports?|has|experiencing|presents? with)\b", before):
        if fact.temporality == "unknown":
            fact.temporality = "current"
    local_text = local.text.lower()
    if re.search(r"\b(?:yesterday|recently)\b", local_text):
        fact.temporality = "recent"
    if "rule out" in before:
        fact.attributes["mention_role"] = "diagnostic_evaluation"
        fact.temporality = "future"
    if fact.hypothetical:
        fact.temporality = "future"
    if re.search(r"\b(?:previous|prior) diagnosis\b", before) and re.search(
        r"\b(?:excluded|ruled out|refuted)\b", local_text
    ):
        fact.attributes["explicit_refutation"] = True

    next_target = min(
        (other.start_char for other in spans if span.end <= other.start < local.end),
        default=local.end_char,
    )
    suffix = note.text[span.end_char : next_target]
    if fact.kind == "observation":
        value = re.match(
            r"\s*(?:(?:is|was)\s+|[:=]\s*)?(-?\d+(?:\.\d+)?)"
            r"(?:\s*/\s*(\d+(?:\.\d+)?))?(?:\s*([A-Za-zµ]+(?:/[A-Za-z]+)?|%))?",
            suffix,
            re.IGNORECASE,
        )
        if value:
            fact.attributes["value"] = float(value[1])
            if value[2]:
                fact.attributes["diastolic"] = float(value[2])
            if value[3] and value[3].lower() not in {
                "today",
                "yesterday",
                "recently",
                "was",
                "is",
                "and",
                "but",
            }:
                fact.attributes["unit"] = value[3]
            add_evidence(
                fact,
                note,
                "regex.observation_value",
                span.end_char + value.start(),
                span.end_char + value.end(),
            )
        return

    if fact.kind == "medication":
        if "action" not in fact.attributes:
            actions = [t for t in prefix if t.lemma_ in ACTIONS]
            if actions:
                token = actions[-1]
                fact.attributes["action"] = token.lemma_
                add_evidence(
                    fact, note, "token.medication_action", token.idx, token.idx + len(token)
                )
        action = fact.attributes.get("action", "unspecified")
        if action in {"start", "increase", "decrease", "stop", "consider"}:
            fact.temporality = "future"
        if action == "consider":
            fact.certainty = "possible"
        dose = re.search(r"\b(\d+(?:\.\d+)?)\s*(mg|mcg|units)\b", suffix, re.IGNORECASE)
        if dose:
            fact.attributes.update(dose=float(dose[1]), dose_unit=dose[2].lower())
        route = re.search(r"\b(oral|orally|PO|subcutaneous|intravenous)\b", suffix, re.IGNORECASE)
        frequency = re.search(
            r"\b(twice daily|once daily|daily|weekly|BID|QD)\b", suffix, re.IGNORECASE
        )
        if route:
            fact.attributes["route"] = route[1].lower()
        if frequency:
            fact.attributes["frequency"] = frequency[1].lower()
        if dose or route or frequency:
            fact.attributes["dosage_text"] = re.sub(r"\bfor\s*$", "", suffix).strip().rstrip(".")
            for rule, match in [
                ("regex.dose", dose),
                ("regex.route", route),
                ("regex.frequency", frequency),
            ]:
                if match:
                    add_evidence(
                        fact, note, rule, span.end_char + match.start(), span.end_char + match.end()
                    )


def plan_facts(doc: Doc, note: Note) -> list[Fact]:
    result: list[Fact] = []
    for pattern, concept in [(FOLLOW_UP, "Follow-up"), (INSTRUCTION, "Treatment instruction")]:
        for match in pattern.finditer(note.text):
            span = doc.char_span(match.start(), match.end(), alignment_mode="expand")
            if span is None:
                continue
            fact = Fact(
                id=f"{note.note_id}:{match.start()}:{match.end()}:plan",
                note_id=note.note_id,
                kind="plan",
                concept=concept,
                text=match[0],
                start=match.start(),
                end=match.end(),
                sentence_start=span.sent.start_char,
                sentence_end=span.sent.end_char,
                temporality="future",
            )
            if pattern is FOLLOW_UP:
                number = match[1].lower()
                fact.attributes.update(
                    interval_value=int(number) if number.isdigit() else WORD_NUMBERS[number],
                    interval_unit=match[2].lower().rstrip("s"),
                )
            add_evidence(
                fact,
                note,
                "regex.follow_up" if pattern is FOLLOW_UP else "regex.instruction",
                match.start(),
                match.end(),
            )
            result.append(fact)
    return result
