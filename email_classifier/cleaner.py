"""Turn classifications into cleaning actions.

The cleaner is deliberately conservative:
  * It NEVER deletes anything itself — it builds a plan and (optionally) hands
    each action to a Gmail client that performs reversible operations.
  * "trash" moves to Gmail Trash (recoverable for 30 days), it is not a permanent
    delete.
  * Dry-run is the default everywhere; the caller must explicitly opt into apply.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .categories import Category
from .classifier import Classification

VALID_ACTIONS = {"none", "archive", "trash", "mark_read", "spam"}


@dataclass
class CleanAction:
    email_id: str
    action: str          # archive | trash | mark_read
    category: str
    reason: str
    subject: str


@dataclass
class CleanPlan:
    actions: list[CleanAction]

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for a in self.actions:
            out[a.action] = out.get(a.action, 0) + 1
        return out


def _age_days(email: dict[str, Any], now: datetime) -> float | None:
    """Best-effort age in days from an email's `internal_date` (epoch ms) or `date`."""
    ms = email.get("internal_date")
    if ms is not None:
        try:
            sent = datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)
            return (now - sent).total_seconds() / 86400.0
        except (ValueError, TypeError):
            pass
    return None


class Cleaner:
    def __init__(self, categories: list[Category]):
        self.by_name = {c.name: c for c in categories}
        for c in categories:
            if c.clean_action not in VALID_ACTIONS:
                raise ValueError(f"Category {c.name} has invalid clean_action {c.clean_action!r}")

    def plan(
        self,
        emails: list[dict[str, Any]],
        classifications: list[Classification],
        now: datetime | None = None,
        category_override: str | None = None,
        action_override: str | None = None,
        min_age_days: int | None = None,
    ) -> CleanPlan:
        """Build a list of actions to take.

        category_override: only act on this category.
        action_override:   force this action regardless of category policy.
        min_age_days:      override the per-category age threshold.
        """
        now = now or datetime.now(timezone.utc)
        by_id = {str(e.get("id", "")): e for e in emails}
        actions: list[CleanAction] = []

        for c in classifications:
            if category_override and c.category != category_override:
                continue
            cat = self.by_name.get(c.category)
            if cat is None:
                continue

            action = action_override or cat.clean_action
            if action == "none":
                continue

            threshold = min_age_days if min_age_days is not None else cat.clean_older_than_days
            email = by_id.get(c.email_id, {})
            age = _age_days(email, now)

            if threshold and threshold > 0:
                if age is None:
                    # Unknown age + an age policy => skip to stay safe.
                    continue
                if age < threshold:
                    continue
                reason = f"{c.category}: {action} (age {age:.0f}d ≥ {threshold}d)"
            else:
                reason = f"{c.category}: {action}"

            actions.append(
                CleanAction(
                    email_id=c.email_id,
                    action=action,
                    category=c.category,
                    reason=reason,
                    subject=c.subject,
                )
            )
        return CleanPlan(actions=actions)

    @staticmethod
    def execute(plan: CleanPlan, gmail_client, dry_run: bool = True) -> dict[str, int]:
        """Execute a plan against a Gmail client.

        With dry_run=True (default) nothing is sent to Gmail — returns the counts
        that *would* be applied. The gmail_client must expose: archive(id),
        trash(id), mark_read(id).
        """
        # Map plan action -> Gmail client method name.
        method = {"archive": "archive", "trash": "trash",
                  "mark_read": "mark_read", "spam": "mark_spam"}
        applied = {"archive": 0, "trash": 0, "mark_read": 0, "spam": 0}
        for a in plan.actions:
            if not dry_run:
                getattr(gmail_client, method[a.action])(a.email_id)
            applied[a.action] += 1
        return applied
