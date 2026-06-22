"""Thin wrapper over the Gmail API.

Google libraries are imported lazily inside __init__ so that the classifier,
cleaner and the offline `demo` command work without any third-party packages
installed. Install extras with:  pip install -r requirements.txt
"""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

# Read + modify (archive/trash/labels). We do NOT request permanent-delete scope.
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


class GmailClient:
    def __init__(
        self,
        credentials_path: str = "credentials.json",
        token_path: str = "token.json",
    ):
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError as exc:  # pragma: no cover - depends on optional extras
            raise ImportError(
                "Gmail features need extra packages. Run:\n"
                "    pip install -r requirements.txt"
            ) from exc

        creds = None
        if Path(token_path).exists():
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not Path(credentials_path).exists():
                    raise FileNotFoundError(
                        f"{credentials_path} not found. Download an OAuth client ID "
                        "(Desktop app) from Google Cloud Console — see README."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)
            Path(token_path).write_text(creds.to_json(), encoding="utf-8")

        self.service = build("gmail", "v1", credentials=creds)
        self._label_cache: dict[str, str] = {}

    # ---- reading -----------------------------------------------------------
    def list_message_ids(self, query: str = "", limit: int = 100) -> list[str]:
        ids: list[str] = []
        page_token = None
        while len(ids) < limit:
            resp = (
                self.service.users()
                .messages()
                .list(userId="me", q=query, maxResults=min(100, limit - len(ids)), pageToken=page_token)
                .execute()
            )
            ids.extend(m["id"] for m in resp.get("messages", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return ids[:limit]

    def fetch(self, message_id: str) -> dict[str, Any]:
        """Return a normalised email dict the classifier understands."""
        msg = (
            self.service.users()
            .messages()
            .get(userId="me", id=message_id, format="metadata",
                 metadataHeaders=["From", "Subject", "List-Unsubscribe", "Date"])
            .execute()
        )
        headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
        return {
            "id": msg["id"],
            "from": headers.get("from", ""),
            "subject": headers.get("subject", ""),
            "snippet": msg.get("snippet", ""),
            "labels": msg.get("labelIds", []),
            "list_unsubscribe": headers.get("list-unsubscribe", ""),
            "internal_date": msg.get("internalDate"),
        }

    def fetch_many(self, query: str = "", limit: int = 100) -> list[dict[str, Any]]:
        return [self.fetch(mid) for mid in self.list_message_ids(query, limit)]

    # ---- writing (all reversible) -----------------------------------------
    def archive(self, message_id: str) -> None:
        self.service.users().messages().modify(
            userId="me", id=message_id, body={"removeLabelIds": ["INBOX"]}
        ).execute()

    def trash(self, message_id: str) -> None:
        # Moves to Trash (recoverable ~30 days), not a permanent delete.
        self.service.users().messages().trash(userId="me", id=message_id).execute()

    def mark_spam(self, message_id: str) -> None:
        # Moves the message to Gmail's Spam/Junk folder (adds SPAM, leaves INBOX).
        # Reversible: the user can "Not spam" it back from the Spam folder.
        self.service.users().messages().modify(
            userId="me", id=message_id,
            body={"addLabelIds": ["SPAM"], "removeLabelIds": ["INBOX"]},
        ).execute()

    def mark_read(self, message_id: str) -> None:
        self.service.users().messages().modify(
            userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}
        ).execute()

    def apply_label(self, message_id: str, label: str) -> None:
        self.service.users().messages().modify(
            userId="me", id=message_id, body={"addLabelIds": [self._label_id(label)]}
        ).execute()

    def set_category(self, message_id: str, keep: str, managed_labels: list[str]) -> None:
        """Apply exactly one category label: add `keep`, remove any other managed
        category labels the message currently carries (one API call). Leaves the
        user's own non-managed labels untouched."""
        keep_id = self._label_id(keep)               # create if needed
        remove_ids = [
            lid for n in managed_labels if n != keep
            for lid in (self._existing_label_id(n),) if lid
        ]
        body: dict[str, Any] = {"addLabelIds": [keep_id]}
        if remove_ids:
            body["removeLabelIds"] = remove_ids
        self.service.users().messages().modify(userId="me", id=message_id, body=body).execute()

    def _existing_label_id(self, name: str) -> str | None:
        if not self._label_cache:
            self._label_id(name)  # populates the cache (and creates `name` if missing)
        return self._label_cache.get(name)

    def _label_id(self, name: str) -> str:
        if not self._label_cache:
            resp = self.service.users().labels().list(userId="me").execute()
            self._label_cache = {l["name"]: l["id"] for l in resp.get("labels", [])}
        if name not in self._label_cache:
            created = (
                self.service.users()
                .labels()
                .create(userId="me", body={"name": name})
                .execute()
            )
            self._label_cache[name] = created["id"]
        return self._label_cache[name]
