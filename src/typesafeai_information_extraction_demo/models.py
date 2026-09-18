"""Library-independent facts shared by extraction, evaluation, and FHIR mapping."""

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Literal, Protocol

Polarity = Literal["affirmed", "negated", "unknown"]
Certainty = Literal["certain", "possible", "unknown"]
Temporality = Literal["current", "historical", "recent", "future", "unknown"]
Activity = Literal["active", "inactive", "resolved", "unknown"]


@dataclass(frozen=True)
class Note:
    text: str
    note_id: str = "note-001"
    patient_id: str = "demo-001"
    reference_date: str | None = None
    language: str = "en"

    def __post_init__(self) -> None:
        if not self.note_id or not self.patient_id:
            raise ValueError("note_id and patient_id must be nonempty")
        if self.language != "en":
            raise ValueError("Track A currently supports English only")
        if self.reference_date:
            date.fromisoformat(self.reference_date)


@dataclass(frozen=True)
class Evidence:
    rule_id: str
    text: str
    start: int
    end: int

    @classmethod
    def at(cls, note: Note, rule_id: str, start: int, end: int) -> "Evidence":
        if not 0 <= start < end <= len(note.text):
            raise ValueError(f"Invalid evidence offsets: {start}:{end}")
        return cls(rule_id, note.text[start:end], start, end)


@dataclass
class Fact:
    id: str
    note_id: str
    kind: str
    concept: str
    text: str
    start: int
    end: int
    sentence_start: int
    sentence_end: int
    section: str | None = None
    polarity: Polarity = "affirmed"
    certainty: Certainty = "unknown"
    hypothetical: bool = False
    temporality: Temporality = "unknown"
    activity: Activity = "unknown"
    experiencer: str = "patient"
    severity: str | None = None
    laterality: str | None = None
    normalization_status: str = "matched"
    alternatives: list[str] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        choices = {
            "kind": {"condition", "symptom", "observation", "medication", "plan"},
            "polarity": {"affirmed", "negated", "unknown"},
            "certainty": {"certain", "possible", "unknown"},
            "temporality": {"current", "historical", "recent", "future", "unknown"},
            "activity": {"active", "inactive", "resolved", "unknown"},
            "normalization_status": {"matched", "ambiguous", "unresolved"},
        }
        for name, allowed in choices.items():
            if getattr(self, name) not in allowed:
                raise ValueError(f"Invalid {name}: {getattr(self, name)}")

    def validate(self, note: Note) -> None:
        self.__post_init__()
        if self.note_id != note.note_id or note.text[self.start : self.end] != self.text:
            raise ValueError(f"Fact {self.id} is not anchored to its note")
        if (
            not 0
            <= self.sentence_start
            <= self.start
            < self.end
            <= self.sentence_end
            <= len(note.text)
        ):
            raise ValueError(f"Fact {self.id} has invalid sentence bounds")
        for evidence in self.evidence:
            if note.text[evidence.start : evidence.end] != evidence.text:
                raise ValueError(f"Fact {self.id} has invalid evidence")


@dataclass
class Extraction:
    note: Note
    facts: list[Fact]
    metadata: dict[str, Any]
    diagnostics: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MappingResult:
    bundle: dict[str, Any]
    dispositions: list[dict[str, Any]]
    validation: dict[str, Any]


class Extractor(Protocol):
    metadata: dict[str, Any]

    def extract(self, note: Note) -> Extraction: ...
