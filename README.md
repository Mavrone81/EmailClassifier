# EmailClassifier

A small, dependency-light tool that **categorises** your Gmail inbox into useful
buckets (Promotions, Social, Finance, Travel, Updates, Newsletters, Work,
Spam-suspect) and then **cleans** it by archiving, marking-read or trashing
messages according to a configurable, per-category policy.

Designed to be safe:

- The core engine is **pure Python standard library** — no dependencies to run
  classification or the offline demo.
- Cleaning is **dry-run by default**. Nothing changes until you pass `--apply`.
- "Trash" uses Gmail's Trash (recoverable for ~30 days). The tool **never**
  requests permanent-delete permission.

## Quick start (offline demo — no Gmail needed)

```bash
python -m email_classifier demo
```

This classifies the bundled sample inbox (`tests/sample_emails.json`) and prints
a category breakdown plus the cleaning plan it *would* run.

## Run the tests

```bash
python tests/test_classifier.py      # zero-dependency runner
# or, if you have pytest:
python -m pytest
```

## Use it on your real Gmail

1. Create an OAuth client:
   - Go to the [Google Cloud Console](https://console.cloud.google.com/), create
     a project, enable the **Gmail API**.
   - Create credentials → **OAuth client ID** → application type **Desktop app**.
   - Download the JSON and save it next to the code as `credentials.json`.
2. Install the Gmail extras:
   ```bash
   pip install -r requirements.txt
   ```
3. Classify your inbox (read-only):
   ```bash
   python -m email_classifier classify --query "in:inbox" --limit 200
   ```
   The first run opens a browser for consent and writes `token.json`.
4. Preview a clean-up (dry-run), then apply:
   ```bash
   python -m email_classifier clean --query "in:inbox" --limit 500          # preview
   python -m email_classifier clean --query "in:inbox" --limit 500 --apply  # execute
   ```

Useful `clean` flags:

| Flag | Effect |
|------|--------|
| `--apply` | Actually perform the actions (otherwise dry-run) |
| `--category Promotions` | Only act on one category |
| `--action archive` | Force an action, overriding category policy |
| `--older-than 120` | Override the age threshold (days) |

> `credentials.json` and `token.json` are git-ignored — keep them private.

## How categorisation works

Each category in [`config/categories.json`](config/categories.json) has a list
of **rules**. A rule matches on sender domain/substring, subject or body
keywords, the presence of a `List-Unsubscribe` header, or Gmail's own category
labels — and contributes a weight. The highest-scoring category wins; anything
that scores zero is `Uncategorised`. Edit the JSON to tune it to your mail — no
code changes required.

Per-category cleaning policy fields:

```jsonc
{
  "name": "Promotions",
  "clean_action": "trash",          // none | archive | trash | mark_read
  "clean_older_than_days": 90        // only act once a message is this old
}
```

## Project layout

```
email_classifier/
  categories.py   rule + category model, JSON loader
  classifier.py   scoring engine
  cleaner.py      builds & executes cleaning plans (dry-run aware)
  gmail_client.py Gmail API wrapper (lazy google imports; modify scope only)
  cli.py          demo / classify / clean commands
config/categories.json   editable rules + policy
tests/                   sample inbox + unit tests
```

## License

MIT — see [LICENSE](LICENSE).
