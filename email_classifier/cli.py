"""Command-line interface for EmailClassifier.

Commands:
    demo                 Classify the bundled sample inbox (no network/credentials).
    classify             Fetch live Gmail messages and print a category summary.
    clean                Plan (and optionally apply) cleaning actions on Gmail.

Run `python -m email_classifier <command> --help` for options.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .categories import DEFAULT_CONFIG_PATH, load_categories
from .classifier import Classifier
from .cleaner import Cleaner, CleanPlan

SAMPLE_PATH = Path(__file__).resolve().parent.parent / "tests" / "sample_emails.json"


def _print_summary(summary, total: int) -> None:
    width = max((len(k) for k in summary), default=10)
    print(f"\n  Classified {total} message(s):\n")
    for name, count in summary.most_common():
        bar = "█" * count
        print(f"  {name.ljust(width)}  {str(count).rjust(4)}  {bar}")
    print()


def _print_plan(plan: CleanPlan, dry_run: bool) -> None:
    if not plan.actions:
        print("  Nothing to clean under the current policy.\n")
        return
    mode = "DRY-RUN (no changes made)" if dry_run else "APPLIED"
    print(f"\n  Cleaning plan — {mode}\n")
    for a in plan.actions[:50]:
        subj = (a.subject[:60] + "…") if len(a.subject) > 60 else a.subject
        print(f"  [{a.action:>9}] {a.category:<14} {subj}")
    if len(plan.actions) > 50:
        print(f"  … and {len(plan.actions) - 50} more")
    print(f"\n  Totals: {plan.counts()}\n")


def cmd_demo(args: argparse.Namespace) -> int:
    categories = load_categories(args.config)
    emails = json.loads(Path(args.sample).read_text(encoding="utf-8"))
    classifier = Classifier(categories)
    results = classifier.classify(emails)
    _print_summary(classifier.summarise(results), len(results))

    print("  Per-message:")
    for r in results:
        print(f"    • [{r.category:<14}] {r.subject}  ⟵ {r.sender}")

    plan = Cleaner(categories).plan(emails, results)
    _print_plan(plan, dry_run=True)
    return 0


def _live(args: argparse.Namespace):
    from .gmail_client import GmailClient

    client = GmailClient(args.credentials, args.token)
    emails = client.fetch_many(query=args.query, limit=args.limit)
    return client, emails


def cmd_classify(args: argparse.Namespace) -> int:
    categories = load_categories(args.config)
    _client, emails = _live(args)
    classifier = Classifier(categories)
    results = classifier.classify(emails)
    _print_summary(classifier.summarise(results), len(results))
    return 0


def cmd_clean(args: argparse.Namespace) -> int:
    categories = load_categories(args.config)
    client, emails = _live(args)
    classifier = Classifier(categories)
    results = classifier.classify(emails)
    plan = Cleaner(categories).plan(
        emails,
        results,
        category_override=args.category,
        action_override=args.action,
        min_age_days=args.older_than,
    )
    dry_run = not args.apply
    _print_plan(plan, dry_run=dry_run)
    if not dry_run:
        applied = Cleaner(categories).execute(plan, client, dry_run=False)
        print(f"  Applied to Gmail: {applied}\n")
    else:
        print("  Re-run with --apply to perform these actions.\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="email_classifier", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="category rules JSON")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("demo", help="classify bundled sample inbox (offline)")
    d.add_argument("--sample", default=str(SAMPLE_PATH))
    d.set_defaults(func=cmd_demo)

    def add_live(sp):
        sp.add_argument("--credentials", default="credentials.json")
        sp.add_argument("--token", default="token.json")
        sp.add_argument("--query", default="", help="Gmail search query, e.g. 'in:inbox'")
        sp.add_argument("--limit", type=int, default=100)

    c = sub.add_parser("classify", help="classify live Gmail messages")
    add_live(c)
    c.set_defaults(func=cmd_classify)

    cl = sub.add_parser("clean", help="plan/apply cleaning on live Gmail")
    add_live(cl)
    cl.add_argument("--apply", action="store_true", help="actually perform actions (default: dry-run)")
    cl.add_argument("--category", help="only act on this category")
    cl.add_argument("--action", choices=["archive", "trash", "mark_read", "spam"], help="force an action")
    cl.add_argument("--older-than", type=int, dest="older_than", help="age threshold in days")
    cl.set_defaults(func=cmd_clean)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, ImportError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
