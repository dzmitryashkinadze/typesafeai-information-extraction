import spacy


def run_spacy_ner(text: str) -> list[tuple[str, int]]:
    """Use spaCy to propose unique entities with zero-based token indices."""
    doc = spacy.load("en_core_web_sm")(text)
    found = {}
    for name, index in [(e.text, e.start) for e in doc.ents] + [(t.text, t.i) for t in doc if t.pos_ in {"PROPN", "NOUN", "ADJ"}]:
        found.setdefault(name, index)
    return list(found.items())
