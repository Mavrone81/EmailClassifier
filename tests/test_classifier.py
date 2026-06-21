"""Unit tests — run with:  python -m pytest   (or)   python tests/test_classifier.py"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from email_classifier import Category, Classifier, Cleaner, Rule, load_categories  # noqa: E402

CATS = load_categories()
EMAILS = json.loads((Path(__file__).parent / "sample_emails.json").read_text(encoding="utf-8"))


def _classify():
    return Classifier(CATS).classify(EMAILS)


def test_promotion_detected():
    by_id = {c.email_id: c for c in _classify()}
    assert by_id["1"].category == "Promotions"
    assert by_id["9"].category == "Promotions"


def test_social_and_finance_and_travel():
    by_id = {c.email_id: c for c in _classify()}
    assert by_id["2"].category == "Social"
    assert by_id["3"].category == "Finance"
    assert by_id["4"].category == "Travel"


def test_work_and_spam():
    by_id = {c.email_id: c for c in _classify()}
    assert by_id["7"].category == "Work"
    assert by_id["8"].category == "Spam-suspect"


def test_personal_is_uncategorised():
    by_id = {c.email_id: c for c in _classify()}
    assert by_id["10"].category == "Uncategorised"


def test_cleaner_respects_age_threshold():
    # Self-contained policy so the test is independent of the shipped config:
    # Promotions trashes once older than 90 days.
    cats = [Category(
        name="Promotions",
        clean_action="trash",
        clean_older_than_days=90,
        rules=[Rule(weight=4, subject_keywords=["sale", "% off", "save", "discount"])],
    )]
    now = datetime(2026, 6, 21, tzinfo=timezone.utc)
    results = Classifier(cats).classify(EMAILS)
    plan = Cleaner(cats).plan(EMAILS, results, now=now)
    acted_ids = {a.email_id for a in plan.actions}
    # Old promo (#1, ~385d) trashed; recent promo (#9, ~1d) below 90d threshold -> skipped.
    assert "1" in acted_ids
    assert "9" not in acted_ids


def test_spam_pushed_to_junk():
    now = datetime(2026, 6, 21, tzinfo=timezone.utc)
    results = _classify()
    plan = Cleaner(CATS).plan(EMAILS, results, now=now)
    spam_actions = {a.email_id: a.action for a in plan.actions if a.action == "spam"}
    # The phishing/"you won" email (#8) must be sent to Junk regardless of age.
    assert spam_actions.get("8") == "spam"


def test_execute_dry_run_changes_nothing():
    results = _classify()
    plan = Cleaner(CATS).plan(EMAILS, results, now=datetime(2026, 6, 21, tzinfo=timezone.utc))

    class Boom:
        def archive(self, _): raise AssertionError("must not call in dry-run")
        def trash(self, _): raise AssertionError("must not call in dry-run")
        def mark_read(self, _): raise AssertionError("must not call in dry-run")

    applied = Cleaner(CATS).execute(plan, Boom(), dry_run=True)
    assert sum(applied.values()) == len(plan.actions)


if __name__ == "__main__":
    funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in funcs:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {fn.__name__}: {e}")
    print(f"\n{len(funcs) - failed}/{len(funcs)} tests passed")
    sys.exit(1 if failed else 0)
