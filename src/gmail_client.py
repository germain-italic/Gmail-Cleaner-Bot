"""Gmail API client with Service Account authentication."""

import base64
import re
import time
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Optional
from email.utils import parsedate_to_datetime

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .config import GOOGLE_CREDENTIALS_PATH, GMAIL_USER_EMAIL, GMAIL_SCOPES, MAX_SEARCH_RESULTS

# Rate limiting: 15,000 quota units/min, ~5 units per call = 3000 calls/min = 50/sec
# Be conservative: 40 calls/sec = 0.025s between calls
API_RATE_LIMIT_DELAY = 0.025


@dataclass
class EmailMessage:
    id: str
    thread_id: str
    subject: str
    sender: str
    to: str
    date: datetime
    snippet: str
    labels: list[str]
    body_preview: str = ""

    @property
    def age_days(self) -> int:
        now = datetime.now(timezone.utc)
        # Ensure date is timezone-aware
        date = self.date if self.date.tzinfo else self.date.replace(tzinfo=timezone.utc)
        return (now - date).days


class GmailClient:
    def __init__(self, user_email: str = GMAIL_USER_EMAIL):
        self.user_email = user_email
        self._service = None
        self._last_api_call = 0

    def _rate_limit(self):
        """Enforce rate limiting between API calls."""
        elapsed = time.time() - self._last_api_call
        if elapsed < API_RATE_LIMIT_DELAY:
            time.sleep(API_RATE_LIMIT_DELAY - elapsed)
        self._last_api_call = time.time()

    @property
    def service(self):
        if self._service is None:
            credentials = service_account.Credentials.from_service_account_file(
                GOOGLE_CREDENTIALS_PATH, scopes=GMAIL_SCOPES
            )
            delegated_credentials = credentials.with_subject(self.user_email)
            self._service = build("gmail", "v1", credentials=delegated_credentials)
        return self._service

    def _get_header(self, headers: list[dict], name: str) -> str:
        for header in headers:
            if header["name"].lower() == name.lower():
                return header["value"]
        return ""

    def _parse_date(self, date_str: str) -> datetime:
        try:
            return parsedate_to_datetime(date_str)
        except (ValueError, TypeError):
            return datetime.now(timezone.utc)

    def _decode_body(self, payload: dict) -> str:
        """Extract text body from message payload."""
        body = ""

        if "body" in payload and payload["body"].get("data"):
            body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="ignore")
        elif "parts" in payload:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                    body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="ignore")
                    break
                elif "parts" in part:
                    body = self._decode_body(part)
                    if body:
                        break

        return body[:1000]  # Limit preview size

    def search_messages(
        self,
        query: str = "",
        max_results: int = MAX_SEARCH_RESULTS,
        older_than_days: Optional[int] = None,
        on_progress: Optional[callable] = None
    ) -> list[EmailMessage]:
        """Search for messages matching the query with pagination."""
        if older_than_days:
            date_threshold = (datetime.now() - timedelta(days=older_than_days)).strftime("%Y/%m/%d")
            query = f"{query} before:{date_threshold}".strip()

        messages = []
        page_token = None

        try:
            while True:
                # Fetch page of message IDs (max 100 per page)
                self._rate_limit()
                request = self.service.users().messages().list(
                    userId="me",
                    q=query,
                    maxResults=min(100, max_results - len(messages)),
                    pageToken=page_token
                )
                result = request.execute()

                message_ids = result.get("messages", [])

                for msg_ref in message_ids:
                    msg = self.get_message(msg_ref["id"])
                    if msg:
                        messages.append(msg)
                        if on_progress:
                            on_progress(len(messages))

                    # Stop if we've reached max_results
                    if len(messages) >= max_results:
                        return messages

                # Check for next page
                page_token = result.get("nextPageToken")
                if not page_token:
                    break

        except HttpError as e:
            raise Exception(f"Gmail API error: {e}")

        return messages

    def get_message(self, message_id: str) -> Optional[EmailMessage]:
        """Get a single message by ID."""
        try:
            self._rate_limit()
            msg = self.service.users().messages().get(
                userId="me",
                id=message_id,
                format="full"
            ).execute()

            payload = msg.get("payload", {})
            headers = payload.get("headers", [])

            return EmailMessage(
                id=msg["id"],
                thread_id=msg["threadId"],
                subject=self._get_header(headers, "Subject"),
                sender=self._get_header(headers, "From"),
                to=self._get_header(headers, "To"),
                date=self._parse_date(self._get_header(headers, "Date")),
                snippet=msg.get("snippet", ""),
                labels=msg.get("labelIds", []),
                body_preview=self._decode_body(payload),
            )

        except HttpError:
            return None

    def delete_message(self, message_id: str, permanent: bool = False) -> bool:
        """Delete a message (move to trash or permanent delete)."""
        try:
            self._rate_limit()
            if permanent:
                self.service.users().messages().delete(
                    userId="me", id=message_id
                ).execute()
            else:
                self.service.users().messages().trash(
                    userId="me", id=message_id
                ).execute()
            return True
        except HttpError:
            return False

    def archive_message(self, message_id: str) -> bool:
        """Archive a message (remove INBOX label)."""
        try:
            self._rate_limit()
            self.service.users().messages().modify(
                userId="me",
                id=message_id,
                body={"removeLabelIds": ["INBOX"]}
            ).execute()
            return True
        except HttpError:
            return False

    def mark_as_read(self, message_id: str) -> bool:
        """Mark a message as read."""
        try:
            self._rate_limit()
            self.service.users().messages().modify(
                userId="me",
                id=message_id,
                body={"removeLabelIds": ["UNREAD"]}
            ).execute()
            return True
        except HttpError:
            return False

    def add_label(self, message_id: str, label_id: str) -> bool:
        """Add a label to a message."""
        try:
            self._rate_limit()
            self.service.users().messages().modify(
                userId="me",
                id=message_id,
                body={"addLabelIds": [label_id]}
            ).execute()
            return True
        except HttpError:
            return False

    def get_labels(self) -> list[dict]:
        """Get all labels."""
        try:
            self._rate_limit()
            result = self.service.users().labels().list(userId="me").execute()
            return result.get("labels", [])
        except HttpError:
            return []

    def get_or_create_label(self, label_name: str) -> Optional[str]:
        """Get label ID by name, create if doesn't exist."""
        labels = self.get_labels()
        for label in labels:
            if label["name"].lower() == label_name.lower():
                return label["id"]

        try:
            self._rate_limit()
            result = self.service.users().labels().create(
                userId="me",
                body={
                    "name": label_name,
                    "labelListVisibility": "labelShow",
                    "messageListVisibility": "show"
                }
            ).execute()
            return result["id"]
        except HttpError:
            return None

    def test_connection(self) -> tuple[bool, str]:
        """Test the Gmail API connection."""
        try:
            profile = self.service.users().getProfile(userId="me").execute()
            return True, f"Connected as {profile['emailAddress']}"
        except HttpError as e:
            return False, f"Connection failed: {e}"
        except Exception as e:
            return False, f"Error: {e}"
