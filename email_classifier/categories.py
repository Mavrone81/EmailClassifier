"""Category definitions and the rule-matching primitives.

A category is a named bucket with a list of rules. Each rule inspects an email
(a plain dict) and contributes a weight to the category's score when it matches.
The classifier picks the highest-scoring category. Everything here is pure
Python with no third-party dependencies so it can run and be unit-tested
without Gmail credentials.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "categories.json"


def _text(email: dict[str, Any], key: str) -> str:
    return str(email.get(key, "") or "").lower()


@dataclass
class Rule:
    """A single matcher. Any non-empty condition that matches adds `weight`.

    Conditions are OR-ed within a rule; a rule matches if ANY of its populated
    conditions match. Use several rules on a category to express AND-like intent.
    """

    weight: float = 1.0
    from_domains: list[str] = field(default_factory=list)
    from_contains: list[str] = field(default_factory=list)
    subject_keywords: list[str] = field(default_factory=list)
    body_keywords: list[str] = field(default_factory=list)
    gmail_labels: list[str] = field(default_factory=list)
    has_list_unsubscribe: bool | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Rule":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"Unknown rule keys: {sorted(unknown)}")
        return cls(**data)

    def score(self, email: dict[str, Any]) -> float:
        """Return this rule's weight if it matches the email, else 0."""
        sender = _text(email, "from")
        subject = _text(email, "subject")
        body = _text(email, "snippet") or _text(email, "body")
        labels = [str(x).upper() for x in email.get("labels", [])]

        if self.from_domains and any(sender.endswith("@" + d.lower()) or ("@" + d.lower()) in sender or d.lower() in sender for d in self.from_domains):
            return self.weight
        if self.from_contains and any(s.lower() in sender for s in self.from_contains):
            return self.weight
        if self.subject_keywords and any(k.lower() in subject for k in self.subject_keywords):
            return self.weight
        if self.body_keywords and any(k.lower() in body for k in self.body_keywords):
            return self.weight
        if self.gmail_labels and any(l.upper() in labels for l in self.gmail_labels):
            return self.weight
        if self.has_list_unsubscribe is not None:
            present = bool(email.get("list_unsubscribe"))
            if present == self.has_list_unsubscribe:
                return self.weight
        return 0.0


@dataclass
class Category:
    name: str
    description: str = ""
    rules: list[Rule] = field(default_factory=list)
    # Default cleaning policy for this category (consumed by cleaner.py).
    clean_action: str = "none"   # none | archive | trash | mark_read
    clean_older_than_days: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Category":
        rules = [Rule.from_dict(r) for r in data.get("rules", [])]
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            rules=rules,
            clean_action=data.get("clean_action", "none"),
            clean_older_than_days=int(data.get("clean_older_than_days", 0)),
        )

    def score(self, email: dict[str, Any]) -> float:
        return sum(rule.score(email) for rule in self.rules)


def load_categories(path: str | os.PathLike[str] | None = None) -> list[Category]:
    """Load category definitions from a JSON config file."""
    cfg = Path(path) if path else DEFAULT_CONFIG_PATH
    with open(cfg, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return [Category.from_dict(c) for c in data["categories"]]
