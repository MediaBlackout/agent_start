"""Natural Language Understanding component."""
from __future__ import annotations

import logging
from enum import Enum, auto
from typing import Dict

import spacy


class Intent(Enum):
    GREET = auto()
    QUERY = auto()
    UNKNOWN = auto()


class NLU:
    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.logger = logger or logging.getLogger(__name__)
        self.nlp = spacy.blank("en")

    def parse(self, text: str) -> tuple[Intent, Dict[str, str]]:
        doc = self.nlp(text)
        intent = Intent.UNKNOWN
        if any(t.lower_ in {"hi", "hello"} for t in doc):
            intent = Intent.GREET
        elif "weather" in text.lower():
            intent = Intent.QUERY
        entities = {ent.label_: ent.text for ent in doc.ents}
        return intent, entities
