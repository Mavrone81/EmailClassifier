"""The classification engine: score an email against every category, pick best."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable

from .categories import Category

UNCATEGORISED = "Uncategorised"


@dataclass
class Classification:
    email_id: str
    category: str
    score: float
    subject: str
    sender: str


class Classifier:
    def __init__(self, categories: list[Category], fallback: str = UNCATEGORISED):
        if not categories:
            raise ValueError("Classifier needs at least one category")
        self.categories = categories
        self.fallback = fallback

    def classify_one(self, email: dict[str, Any]) -> Classification:
        best_name = self.fallback
        best_score = 0.0
        for category in self.categories:
            s = category.score(email)
            if s > best_score:
                best_score = s
                best_name = category.name
        return Classification(
            email_id=str(email.get("id", "")),
            category=best_name,
            score=best_score,
            subject=str(email.get("subject", "")),
            sender=str(email.get("from", "")),
        )

    def classify(self, emails: Iterable[dict[str, Any]]) -> list[Classification]:
        return [self.classify_one(e) for e in emails]

    @staticmethod
    def summarise(results: list[Classification]) -> Counter:
        """Return a Counter of category -> number of emails."""
        return Counter(r.category for r in results)
