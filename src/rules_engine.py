"""Rules engine for matching and executing actions on emails."""

import re
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from typing import Optional

from .database import Database, Rule, LogEntry, RuleField, RuleOperator, RuleAction
from .gmail_client import GmailClient, EmailMessage
from .config import (
    DRY_RUN, LOG_PATH, LOG_LEVEL, LOG_MAX_SIZE, LOG_BACKUP_COUNT,
    EXCLUDE_TRASH, EXCLUDE_SPAM, EXCLUDE_DRAFTS, EXCLUDE_SENT
)

# Setup logging with rotation (file only, no stdout to avoid TUI conflicts)
logger = logging.getLogger(__name__)
logger.setLevel(getattr(logging, LOG_LEVEL))
_handler = RotatingFileHandler(
    f"{LOG_PATH}/cleaner.log",
    maxBytes=LOG_MAX_SIZE,
    backupCount=LOG_BACKUP_COUNT
)
_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(_handler)


class RulesEngine:
    def __init__(self, db: Database, gmail: GmailClient, on_log: Optional[callable] = None, is_cancelled: Optional[callable] = None):
        self.db = db
        self.gmail = gmail
        self.on_log = on_log
        self.is_cancelled = is_cancelled

    def _log(self, message: str, level: str = "info"):
        """Log message to file and optional callback."""
        if level == "error":
            logger.error(message)
        else:
            logger.info(message)
        if self.on_log:
            self.on_log(message, level)

    def _get_field_value(self, message: EmailMessage, field: RuleField) -> str:
        """Extract the field value from a message."""
        if field == RuleField.LABEL:
            # Return labels as comma-separated string for matching
            return ",".join(message.labels)
        mapping = {
            RuleField.SUBJECT: message.subject,
            RuleField.FROM: message.sender,
            RuleField.TO: message.to,
            RuleField.BODY: message.body_preview,
        }
        return mapping.get(field, "")

    def _match_operator(self, value: str, operator: RuleOperator, pattern: str) -> bool:
        """Check if value matches the pattern using the operator."""
        value_lower = value.lower()
        pattern_lower = pattern.lower()

        if operator == RuleOperator.CONTAINS:
            return pattern_lower in value_lower
        elif operator == RuleOperator.CONTAINS_EXACT:
            return pattern in value  # Case-sensitive
        elif operator == RuleOperator.EQUALS:
            return value_lower == pattern_lower
        elif operator == RuleOperator.STARTS_WITH:
            return value_lower.startswith(pattern_lower)
        elif operator == RuleOperator.ENDS_WITH:
            return value_lower.endswith(pattern_lower)
        elif operator == RuleOperator.REGEX:
            try:
                return bool(re.search(pattern, value, re.IGNORECASE))
            except re.error:
                logger.error(f"Invalid regex pattern: {pattern}")
                return False

        return False

    def matches_rule(self, message: EmailMessage, rule: Rule) -> bool:
        """Check if a message matches a rule."""
        # Check age requirement
        if rule.older_than_days > 0 and message.age_days < rule.older_than_days:
            return False

        # For LABEL field, trust Gmail's query (label names vs IDs issue)
        if rule.field == RuleField.LABEL:
            return True

        # Check field match
        field_value = self._get_field_value(message, rule.field)
        return self._match_operator(field_value, rule.operator, rule.value)

    def execute_action(self, message: EmailMessage, rule: Rule) -> tuple[bool, Optional[str]]:
        """Execute the rule action on a message."""
        labels_str = ", ".join(message.labels) if message.labels else "no labels"
        if DRY_RUN:
            self._log(f"[DRY RUN] Would {rule.action.value} message: [{message.subject}] in [{labels_str}]")
            return True, None

        try:
            if rule.action == RuleAction.DELETE:
                success = self.gmail.delete_message(message.id)
            elif rule.action == RuleAction.ARCHIVE:
                success = self.gmail.archive_message(message.id)
            elif rule.action == RuleAction.MARK_READ:
                success = self.gmail.mark_as_read(message.id)
            elif rule.action == RuleAction.LABEL:
                if not rule.action_param:
                    return False, "Label name not specified"
                label_id = self.gmail.get_or_create_label(rule.action_param)
                if not label_id:
                    return False, f"Could not create/find label: {rule.action_param}"
                success = self.gmail.add_label(message.id, label_id)
            else:
                return False, f"Unknown action: {rule.action}"

            if success:
                date_str = message.date.strftime("%Y-%m-%d")
                self._log(
                    f"Action '{rule.action.value}' on: [{message.subject}] from [{message.sender}] ({date_str}) in [{labels_str}]"
                )
                return True, None
            else:
                return False, "Gmail API returned failure"

        except Exception as e:
            error_msg = str(e)
            self._log(f"Error executing action: {error_msg}", "error")
            return False, error_msg

    def process_rule(self, rule: Rule) -> dict:
        """Process a single rule against all matching messages."""
        stats = {"matched": 0, "success": 0, "failed": 0}

        self._log(f"Processing rule: {rule.name}")

        # Build search query based on rule field
        query_parts = []
        if rule.field == RuleField.SUBJECT:
            query_parts.append(f"subject:{rule.value}")
        elif rule.field == RuleField.FROM:
            query_parts.append(f"from:{rule.value}")
        elif rule.field == RuleField.TO:
            query_parts.append(f"to:{rule.value}")
        elif rule.field == RuleField.BODY:
            # Gmail searches body content by default with plain text
            query_parts.append(f'"{rule.value}"')
        elif rule.field == RuleField.LABEL:
            # Quote label name if it contains spaces or special chars
            label_value = rule.value
            if " " in label_value or "-" in label_value:
                query_parts.append(f'label:"{label_value}"')
            else:
                query_parts.append(f"label:{label_value}")

        # Add folder exclusions
        if EXCLUDE_TRASH:
            query_parts.append("-in:trash")
        if EXCLUDE_SPAM:
            query_parts.append("-in:spam")
        if EXCLUDE_DRAFTS:
            query_parts.append("-in:drafts")
        if EXCLUDE_SENT:
            query_parts.append("-in:sent")

        query = " ".join(query_parts)

        # Get messages with timeout handling
        try:
            messages = self.gmail.search_messages(
                query=query,
                older_than_days=rule.older_than_days if rule.older_than_days > 0 else None
            )
        except (TimeoutError, Exception) as e:
            self._log(f"Error searching messages for rule '{rule.name}': {e}", "error")
            return stats

        for message in messages:
            # Check for cancellation
            if self.is_cancelled and self.is_cancelled():
                self._log("Cancelled by user", "error")
                break

            # Double-check with our matcher (Gmail search is approximate)
            try:
                if not self.matches_rule(message, rule):
                    continue

                stats["matched"] += 1
                success, error = self.execute_action(message, rule)

                # Log the action
                log_entry = LogEntry(
                    id=None,
                    rule_id=rule.id,
                    rule_name=rule.name,
                    message_id=message.id,
                    message_subject=message.subject[:200],
                    message_from=message.sender[:200],
                    action=rule.action,
                    success=success,
                    error_message=error,
                    executed_at=datetime.now(),
                )
                self.db.add_log(log_entry)

                if success:
                    stats["success"] += 1
                else:
                    stats["failed"] += 1

            except (TimeoutError, Exception) as e:
                self._log(f"Error processing message: {e}", "error")
                stats["failed"] += 1
                continue

        self._log(
            f"Rule '{rule.name}' complete: {stats['matched']} matched, "
            f"{stats['success']} success, {stats['failed']} failed"
        )

        # Update last run timestamp
        self.db.update_rule_last_run(rule.id)

        return stats

    def run_all_rules(self) -> dict:
        """Run all enabled rules."""
        rules = self.db.get_rules(enabled_only=True)
        total_stats = {"rules_processed": 0, "matched": 0, "success": 0, "failed": 0}

        self._log(f"Starting cleanup with {len(rules)} active rules")

        for rule in rules:
            # Check for cancellation between rules
            if self.is_cancelled and self.is_cancelled():
                self._log("Cancelled by user", "error")
                break

            stats = self.process_rule(rule)
            total_stats["rules_processed"] += 1
            total_stats["matched"] += stats["matched"]
            total_stats["success"] += stats["success"]
            total_stats["failed"] += stats["failed"]

        self._log(
            f"Cleanup complete: {total_stats['rules_processed']} rules, "
            f"{total_stats['matched']} messages matched, "
            f"{total_stats['success']} actions successful"
        )

        return total_stats
