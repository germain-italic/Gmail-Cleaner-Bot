"""Rule suggester: scan the mailbox for recurring messages that no rule covers yet.

Groups recent messages by sender address and by recurring subject phrase, drops
anything already handled by an existing rule, and proposes ready-to-create
deletion rules ranked by frequency. Suggestion only — nothing is created here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from email.utils import parseaddr
from typing import Optional, Callable, TYPE_CHECKING

from .database import Rule, RuleField, RuleOperator, RuleAction

if TYPE_CHECKING:  # GmailClient pulls in google-api; only needed for type hints
    from .gmail_client import GmailClient

# A word is "stable" (usable to cluster subjects) if it is alphabetic and not a
# hostname/date/id fragment. Variable parts (hostnames, numbers, dates) don't
# recur, so the frequency threshold filters them out on its own — but stripping
# the obvious ones up front makes the cluster signatures cleaner.
_WORD_RE = re.compile(r"[0-9a-zà-öø-ÿ]+", re.IGNORECASE)
_BRACKET_RE = re.compile(r"\[[^\]]*\]")
_STRIP_EDGES = " \t-–—:|·.,"


@dataclass
class Record:
    subject: str
    sender: str       # normalized email address (lowercased)
    sender_raw: str   # full From header (decoded)


@dataclass
class Suggestion:
    dimension: str            # "sender" | "subject"
    field: RuleField
    operator: RuleOperator
    value: str
    count: int
    older_than_days: int
    action: RuleAction
    sample_subject: str
    sample_sender: str

    def suggested_name(self) -> str:
        if self.dimension == "sender":
            return f"Auto: from {self.value}"
        v = self.value if len(self.value) <= 40 else self.value[:37] + "..."
        return f"Auto: subject '{v}'"

    def to_rule(self, name: Optional[str] = None) -> Rule:
        now = datetime.now()
        return Rule(
            id=None,
            name=name or self.suggested_name(),
            field=self.field,
            operator=self.operator,
            value=self.value,
            action=self.action,
            action_param=None,
            older_than_days=self.older_than_days,
            enabled=True,
            created_at=now,
            updated_at=now,
        )


# --------------------------------------------------------------------------- #
# Scan
# --------------------------------------------------------------------------- #
def _header(gmail: GmailClient, headers: list, name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return gmail._decode_mime_header(h.get("value", ""))
    return ""


def scan(
    gmail: GmailClient,
    months: int = 6,
    max_messages: int = 3000,
    on_progress: Optional[Callable[[int], None]] = None,
) -> list[Record]:
    """Fetch lightweight (Subject, From) metadata for recent messages."""
    svc = gmail.service
    after = (datetime.now() - timedelta(days=30 * months)).strftime("%Y/%m/%d")
    query = f"after:{after}"

    records: list[Record] = []
    page_token = None
    while len(records) < max_messages:
        gmail._rate_limit()
        resp = svc.users().messages().list(
            userId="me", q=query,
            maxResults=min(500, max_messages - len(records)),
            pageToken=page_token,
        ).execute()
        refs = resp.get("messages", [])
        if not refs:
            break
        for ref in refs:
            gmail._rate_limit()
            msg = svc.users().messages().get(
                userId="me", id=ref["id"], format="metadata",
                metadataHeaders=["From", "Subject"],
            ).execute()
            headers = msg.get("payload", {}).get("headers", [])
            subject = _header(gmail, headers, "Subject")
            from_raw = _header(gmail, headers, "From")
            email_addr = parseaddr(from_raw)[1].lower()
            records.append(Record(subject=subject, sender=email_addr, sender_raw=from_raw))
            if on_progress and len(records) % 100 == 0:
                on_progress(len(records))
            if len(records) >= max_messages:
                break
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    if on_progress:
        on_progress(len(records))
    return records


# --------------------------------------------------------------------------- #
# Clustering
# --------------------------------------------------------------------------- #
def _signature(subject: str) -> tuple:
    """Cluster key: first stable words of a subject (brackets/numbers dropped)."""
    s = _BRACKET_RE.sub(" ", subject.lower())
    words = _WORD_RE.findall(s)
    stable = [w for w in words if len(w) >= 2 and not any(c.isdigit() for c in w)]
    return tuple(stable[:4])


def _lcs_tokens(a: list, b: list) -> list:
    """Longest common *contiguous* token run between two token lists."""
    if not a or not b:
        return []
    best_len, best_end = 0, 0
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        ai = a[i - 1]
        for j in range(1, len(b) + 1):
            if ai == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best_len:
                    best_len, best_end = cur[j], i
        prev = cur
    return a[best_end - best_len:best_end]


def _common_phrase(subjects: list, sample_size: int = 40) -> str:
    """Longest verbatim phrase shared by a sample of subjects (→ safe `contains`)."""
    token_lists = [s.lower().split() for s in subjects[:sample_size] if s.strip()]
    if not token_lists:
        return ""
    common = token_lists[0]
    for toks in token_lists[1:]:
        common = _lcs_tokens(common, toks)
        if not common:
            break
    return " ".join(common).strip(_STRIP_EDGES)


def _sender_suggestions(records, min_count, older_than_days) -> list[Suggestion]:
    counts = Counter(r.sender for r in records if r.sender)
    sample: dict[str, Record] = {}
    for r in records:
        if r.sender:
            sample.setdefault(r.sender, r)
    out = []
    for addr, n in counts.items():
        if n < min_count:
            continue
        s = sample[addr]
        out.append(Suggestion(
            dimension="sender", field=RuleField.FROM, operator=RuleOperator.CONTAINS,
            value=addr, count=n, older_than_days=older_than_days,
            action=RuleAction.DELETE, sample_subject=s.subject, sample_sender=s.sender_raw,
        ))
    return out


def _subject_suggestions(records, min_count, older_than_days) -> list[Suggestion]:
    clusters: dict[tuple, list] = defaultdict(list)
    for r in records:
        sig = _signature(r.subject)
        if len(sig) >= 2:
            clusters[sig].append(r)

    out, seen_values = [], set()
    for recs in clusters.values():
        if len(recs) < min_count:
            continue
        value = _common_phrase([r.subject for r in recs])
        # Need a specific phrase: at least 2 words and a few characters.
        if len(value) < 8 or len(value.split()) < 2:
            continue
        key = value.lower()
        if key in seen_values:
            continue
        seen_values.add(key)
        out.append(Suggestion(
            dimension="subject", field=RuleField.SUBJECT, operator=RuleOperator.CONTAINS,
            value=value, count=len(recs), older_than_days=older_than_days,
            action=RuleAction.DELETE, sample_subject=recs[0].subject, sample_sender=recs[0].sender_raw,
        ))
    return out


# --------------------------------------------------------------------------- #
# Coverage filter (skip what existing rules already handle)
# --------------------------------------------------------------------------- #
def _match(value: str, operator: RuleOperator, pattern: str) -> bool:
    v, p = value.lower(), pattern.lower()
    if operator == RuleOperator.CONTAINS:
        return p in v
    if operator == RuleOperator.CONTAINS_EXACT:
        return pattern in value
    if operator == RuleOperator.EQUALS:
        return v == p
    if operator == RuleOperator.STARTS_WITH:
        return v.startswith(p)
    if operator == RuleOperator.ENDS_WITH:
        return v.endswith(p)
    if operator == RuleOperator.REGEX:
        try:
            return bool(re.search(pattern, value, re.IGNORECASE))
        except re.error:
            return False
    return False


def _sample_field(s: Suggestion, field: RuleField) -> Optional[str]:
    if field == RuleField.SUBJECT:
        return s.sample_subject
    if field == RuleField.FROM:
        return s.sample_sender
    return None  # TO / BODY / LABEL not scanned → can't judge


def _is_covered(s: Suggestion, existing_rules: list[Rule]) -> bool:
    for rule in existing_rules:
        # Exact duplicate (same field+value), regardless of enabled state.
        if rule.field == s.field and rule.value.strip().lower() == s.value.strip().lower():
            return True
        if not rule.enabled or rule.field == RuleField.LABEL:
            continue
        fv = _sample_field(s, rule.field)
        if fv and _match(fv, rule.operator, rule.value):
            return True
    return False


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def generate_suggestions(
    gmail: GmailClient,
    existing_rules: list[Rule],
    months: int = 6,
    max_messages: int = 3000,
    min_count: int = 5,
    older_than_days: int = 3,
    max_suggestions: int = 40,
    on_progress: Optional[Callable[[int], None]] = None,
) -> list[Suggestion]:
    records = scan(gmail, months=months, max_messages=max_messages, on_progress=on_progress)
    suggestions = _sender_suggestions(records, min_count, older_than_days)
    suggestions += _subject_suggestions(records, min_count, older_than_days)
    suggestions = [s for s in suggestions if not _is_covered(s, existing_rules)]
    suggestions.sort(key=lambda s: s.count, reverse=True)
    return suggestions[:max_suggestions]
