#!/usr/bin/env python3
"""Terminal User Interface for Gmail Cleaner Bot."""
from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

from textual.app import App, ComposeResult
from textual.worker import Worker
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import (
    Header, Footer, Static, Button, DataTable, Input, Select, Switch, Label, TabbedContent, TabPane
)
from textual.screen import Screen, ModalScreen
from textual.binding import Binding
from rich.text import Text

from src.config import validate_config, DRY_RUN
from src.database import Database, Rule, RuleField, RuleOperator, RuleAction
from src.gmail_client import GmailClient
from src.rules_engine import RulesEngine


class RuleFormScreen(ModalScreen[Rule | None]):
    """Modal screen for creating/editing a rule."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    CSS = """
    RuleFormScreen {
        align: center middle;
    }

    #form-container {
        width: 70;
        height: auto;
        max-height: 80%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }

    .form-row {
        height: 3;
        margin-bottom: 1;
    }

    .form-label {
        width: 20;
        height: 3;
        content-align: left middle;
    }

    .form-input {
        width: 1fr;
    }

    #buttons {
        height: 3;
        margin-top: 1;
        align: center middle;
    }

    #buttons Button {
        margin: 0 1;
    }
    """

    def __init__(self, rule: Rule | None = None):
        super().__init__()
        self.rule = rule

    def compose(self) -> ComposeResult:
        with Container(id="form-container"):
            yield Static("New Rule" if not self.rule else "Edit Rule", id="form-title")

            with Horizontal(classes="form-row"):
                yield Label("Name:", classes="form-label")
                yield Input(
                    value=self.rule.name if self.rule else "",
                    placeholder="Rule name",
                    id="name",
                    classes="form-input"
                )

            with Horizontal(classes="form-row"):
                yield Label("Field:", classes="form-label")
                yield Select(
                    [(f.value.title(), f.value) for f in RuleField],
                    value=self.rule.field.value if self.rule else RuleField.SUBJECT.value,
                    id="field",
                    classes="form-input"
                )

            with Horizontal(classes="form-row"):
                yield Label("Operator:", classes="form-label")
                # Exclude REGEX from dropdown (controlled by checkbox)
                operators = [o for o in RuleOperator if o != RuleOperator.REGEX]
                default_op = self.rule.operator if self.rule and self.rule.operator != RuleOperator.REGEX else RuleOperator.CONTAINS
                yield Select(
                    [(o.value.replace("_", " ").title(), o.value) for o in operators],
                    value=default_op.value,
                    id="operator",
                    classes="form-input"
                )

            with Horizontal(classes="form-row"):
                yield Label("Value:", classes="form-label")
                yield Input(
                    value=self.rule.value if self.rule else "",
                    placeholder="Value to match",
                    id="value",
                    classes="form-input"
                )

            with Horizontal(classes="form-row"):
                yield Label("Regex:", classes="form-label")
                yield Switch(
                    value=self.rule.operator == RuleOperator.REGEX if self.rule else False,
                    id="use_regex"
                )

            with Horizontal(classes="form-row"):
                yield Label("Older than (days):", classes="form-label")
                yield Input(
                    value=str(self.rule.older_than_days) if self.rule else "0",
                    placeholder="0",
                    id="older_than",
                    classes="form-input"
                )

            with Horizontal(classes="form-row"):
                yield Label("Action:", classes="form-label")
                yield Select(
                    [(a.value.replace("_", " ").title(), a.value) for a in RuleAction],
                    value=self.rule.action.value if self.rule else RuleAction.DELETE.value,
                    id="action",
                    classes="form-input"
                )

            with Horizontal(classes="form-row"):
                yield Label("Label (if action=label):", classes="form-label")
                yield Input(
                    value=self.rule.action_param if self.rule and self.rule.action_param else "",
                    placeholder="Label name",
                    id="action_param",
                    classes="form-input"
                )

            with Horizontal(classes="form-row"):
                yield Label("Enabled:", classes="form-label")
                yield Switch(value=self.rule.enabled if self.rule else True, id="enabled")

            with Horizontal(id="buttons"):
                yield Button("Save", variant="primary", id="save")
                yield Button("Cancel", variant="default", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
        elif event.button.id == "save":
            self._save_rule()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _save_rule(self) -> None:
        name = self.query_one("#name", Input).value.strip()
        if not name:
            self.notify("Name is required", severity="error")
            return

        value = self.query_one("#value", Input).value.strip()
        if not value:
            self.notify("Value is required", severity="error")
            return

        try:
            older_than = int(self.query_one("#older_than", Input).value or "0")
        except ValueError:
            older_than = 0

        # Use REGEX operator if checkbox is checked
        use_regex = self.query_one("#use_regex", Switch).value
        if use_regex:
            operator = RuleOperator.REGEX
        else:
            operator = RuleOperator(self.query_one("#operator", Select).value)

        rule = Rule(
            id=self.rule.id if self.rule else None,
            name=name,
            field=RuleField(self.query_one("#field", Select).value),
            operator=operator,
            value=value,
            action=RuleAction(self.query_one("#action", Select).value),
            action_param=self.query_one("#action_param", Input).value.strip() or None,
            older_than_days=older_than,
            enabled=self.query_one("#enabled", Switch).value,
            created_at=self.rule.created_at if self.rule else datetime.now(),
            updated_at=datetime.now(),
        )

        self.dismiss(rule)


class ConfirmScreen(ModalScreen[bool]):
    """Confirmation dialog."""

    CSS = """
    ConfirmScreen {
        align: center middle;
    }

    #confirm-container {
        width: 50;
        height: auto;
        background: $surface;
        border: thick $error;
        padding: 1 2;
    }

    #confirm-message {
        margin-bottom: 1;
    }

    #confirm-buttons {
        height: 3;
        align: center middle;
    }
    """

    def __init__(self, message: str):
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Container(id="confirm-container"):
            yield Static(self.message, id="confirm-message")
            with Horizontal(id="confirm-buttons"):
                yield Button("Yes", variant="error", id="yes")
                yield Button("No", variant="default", id="no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")


class RunLogScreen(ModalScreen[dict]):
    """Modal screen showing execution logs."""

    BINDINGS = [
        Binding("escape", "close", "Close"),
    ]

    CSS = """
    RunLogScreen {
        align: center middle;
    }

    #log-container {
        width: 90%;
        height: 80%;
        background: $surface;
        border: thick $primary;
        padding: 1;
    }

    #log-title {
        dock: top;
        height: 1;
        background: $primary;
        color: $text;
        text-align: center;
        padding: 0 1;
    }

    #log-content {
        height: 1fr;
        margin: 1 0;
        background: $background;
        padding: 1;
    }

    #log-buttons {
        dock: bottom;
        height: 3;
        align: center middle;
    }

    .log-info {
        color: $text;
    }

    .log-error {
        color: $error;
    }

    .log-success {
        color: $success;
    }
    """

    def __init__(self):
        super().__init__()
        self.logs: list[tuple[str, str]] = []
        self.stats: dict = {}
        self.running = True

    def compose(self) -> ComposeResult:
        with Container(id="log-container"):
            yield Static("Execution Log", id="log-title")
            yield ScrollableContainer(Static("", id="log-text"), id="log-content")
            with Horizontal(id="log-buttons"):
                yield Button("Close", variant="primary", id="close", disabled=True)

    def add_log(self, message: str, level: str = "info"):
        self.logs.append((message, level))
        self._update_display()

    def _update_display(self):
        log_text = self.query_one("#log-text", Static)
        # Build Rich Text object to avoid markup parsing issues
        output = Text()
        for i, (msg, level) in enumerate(self.logs):
            if i > 0:
                output.append("\n")
            if level == "error":
                output.append(msg, style="red")
            elif "complete" in msg.lower() or "success" in msg.lower():
                output.append(msg, style="green")
            else:
                output.append(msg)
        log_text.update(output)
        # Scroll to bottom
        container = self.query_one("#log-content", ScrollableContainer)
        container.scroll_end(animate=False)

    def finish(self, stats: dict):
        self.stats = stats
        self.running = False
        self.query_one("#close", Button).disabled = False
        self.add_log("", "info")
        self.add_log("--- Execution finished. Press Close or Escape ---", "info")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close":
            self.dismiss(self.stats)

    def action_close(self) -> None:
        if not self.running:
            self.dismiss(self.stats)


class GmailCleanerApp(App):
    """Main TUI Application."""

    TITLE = "Gmail Cleaner Bot"
    CSS = """
    ToastRack {
        dock: top;
        align-horizontal: right;
        margin-top: 3;
    }

    #stats-container {
        height: 5;
        margin: 1;
        padding: 1;
        background: $surface;
        border: round $primary;
    }

    #stats-container Horizontal {
        height: 3;
    }

    .stat-box {
        width: 1fr;
        height: 3;
        content-align: center middle;
        text-align: center;
    }

    #rules-table {
        height: 1fr;
        margin: 1;
    }

    #logs-table {
        height: 1fr;
        margin: 1;
    }

    #action-bar {
        height: 3;
        margin: 1;
        align: center middle;
    }

    #action-bar Button {
        margin: 0 1;
    }

    .connection-status {
        dock: top;
        height: 1;
        background: $success;
        color: $text;
        text-align: center;
    }

    .connection-status.error {
        background: $error;
    }

    .dry-indicator {
        dock: top;
        height: 1;
        background: $success;
        color: $text;
        text-align: center;
    }

    .dry-indicator.dry-on {
        background: orange;
        text-style: bold;
    }

    #filter-bar {
        dock: top;
        height: 1;
        background: $primary;
        color: $text;
        text-align: center;
        display: none;
    }

    #filter-bar.active {
        display: block;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("n", "new_rule", "New Rule"),
        Binding("a", "run_all_rules", "Run All"),
        Binding("s", "run_selected_rule", "Run Selected"),
        Binding("t", "test_connection", "Test Connection"),
        Binding("d", "toggle_dry_run", "Toggle Dry Run"),
        Binding("slash", "start_filter", "/Filter"),
        Binding("escape", "clear_filter", "Clear Filter", show=False),
    ]

    def __init__(self):
        super().__init__()
        self.db = Database()
        self.gmail = None
        self.dry_run = DRY_RUN
        self.filter_text = ""
        self.filter_mode = False
        self.all_rules: list[Rule] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Connecting...", id="connection-status", classes="connection-status")
        yield Static("Mode: LIVE", id="dry-indicator", classes="dry-indicator")
        yield Static("", id="filter-bar")

        with TabbedContent():
            with TabPane("Rules", id="rules-tab"):
                yield DataTable(id="rules-table")
                with Horizontal(id="action-bar"):
                    yield Button("New Rule", variant="primary", id="btn-new")
                    yield Button("Edit", variant="default", id="btn-edit")
                    yield Button("Toggle", variant="default", id="btn-toggle")
                    yield Button("Delete", variant="error", id="btn-delete")
                    yield Button("Run All", variant="success", id="btn-run-all")
                    yield Button("Run Selected", variant="warning", id="btn-run-selected")

            with TabPane("Logs", id="logs-tab"):
                yield DataTable(id="logs-table")
                with Horizontal(id="action-bar"):
                    yield Button("Refresh", variant="primary", id="btn-refresh-logs")
                    yield Button("Clear Old (30d)", variant="warning", id="btn-clear-logs")

        yield Footer()

    def on_mount(self) -> None:
        self._init_tables()
        self._test_connection()
        self._refresh_stats()
        self._refresh_rules()
        self._refresh_logs()
        # Focus on rules table at startup
        self.query_one("#rules-table", DataTable).focus()

    def _init_tables(self) -> None:
        rules_table = self.query_one("#rules-table", DataTable)
        rules_table.add_columns("ID", "Name", "Field", "Operator", "Value", "Action", "Days", "Last Run", "Status")
        rules_table.cursor_type = "row"

        logs_table = self.query_one("#logs-table", DataTable)
        logs_table.add_columns("Time", "Rule", "Subject", "From", "Action", "Status")
        logs_table.cursor_type = "row"

    def _test_connection(self) -> None:
        errors = validate_config()
        status = self.query_one("#connection-status", Static)

        if errors:
            status.update(f"Config Error: {errors[0]}")
            status.add_class("error")
            return

        try:
            self.gmail = GmailClient()
            success, message = self.gmail.test_connection()
            if success:
                status.update(f"Connected: {message}")
                status.remove_class("error")
            else:
                status.update(f"Connection Failed: {message}")
                status.add_class("error")
        except Exception as e:
            status.update(f"Error: {e}")
            status.add_class("error")

    def _refresh_stats(self) -> None:
        self._update_dry_indicator()

    def _refresh_rules(self, keep_filter: bool = False) -> None:
        if not keep_filter:
            self.all_rules = self.db.get_rules()

        table = self.query_one("#rules-table", DataTable)
        table.clear()

        # Filter rules if filter_text is set
        rules = self.all_rules
        if self.filter_text:
            filter_lower = self.filter_text.lower()
            rules = [r for r in self.all_rules if (
                filter_lower in r.name.lower() or
                filter_lower in r.value.lower() or
                filter_lower in r.field.value.lower() or
                filter_lower in r.operator.value.lower() or
                filter_lower in r.action.value.lower()
            )]

        for rule in rules:
            status_text = Text("ON", style="green") if rule.enabled else Text("OFF", style="red")
            last_run = rule.last_run_at.strftime("%m-%d %H:%M") if rule.last_run_at else "Never"
            table.add_row(
                str(rule.id),
                rule.name,
                rule.field.value,
                rule.operator.value,
                rule.value[:30] + "..." if len(rule.value) > 30 else rule.value,
                rule.action.value,
                str(rule.older_than_days),
                last_run,
                status_text,
            )

    def _refresh_logs(self) -> None:
        table = self.query_one("#logs-table", DataTable)
        table.clear()

        for log in self.db.get_logs(limit=100):
            status_text = Text("OK", style="green") if log.success else Text("FAIL", style="red")
            table.add_row(
                log.executed_at.strftime("%Y-%m-%d %H:%M"),
                log.rule_name,
                log.message_subject[:40] + "..." if len(log.message_subject) > 40 else log.message_subject,
                log.message_from[:30] + "..." if len(log.message_from) > 30 else log.message_from,
                log.action.value,
                status_text,
            )

    def _get_selected_rule_id(self) -> int | None:
        table = self.query_one("#rules-table", DataTable)
        if table.cursor_row is not None:
            row = table.get_row_at(table.cursor_row)
            if row:
                return int(row[0])
        return None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id

        if button_id == "btn-new":
            self.action_new_rule()
        elif button_id == "btn-edit":
            self._edit_rule()
        elif button_id == "btn-toggle":
            self._toggle_rule()
        elif button_id == "btn-delete":
            self._delete_rule()
        elif button_id == "btn-run-all":
            self.action_run_all_rules()
        elif button_id == "btn-run-selected":
            self.action_run_selected_rule()
        elif button_id == "btn-refresh-logs":
            self._refresh_logs()
        elif button_id == "btn-clear-logs":
            self._clear_old_logs()

    def action_new_rule(self) -> None:
        def handle_result(rule: Rule | None) -> None:
            if rule:
                self.db.create_rule(rule)
                self._refresh_rules()
                self._refresh_stats()
                self.notify("Rule created")

        self.push_screen(RuleFormScreen(), handle_result)

    def _edit_rule(self) -> None:
        rule_id = self._get_selected_rule_id()
        if not rule_id:
            self.notify("Select a rule first", severity="warning")
            return

        rule = self.db.get_rule(rule_id)
        if not rule:
            return

        def handle_result(updated: Rule | None) -> None:
            if updated:
                updated.id = rule_id
                self.db.update_rule(updated)
                self._refresh_rules()
                self._refresh_stats()
                self.notify("Rule updated")

        self.push_screen(RuleFormScreen(rule), handle_result)

    def _toggle_rule(self) -> None:
        rule_id = self._get_selected_rule_id()
        if rule_id:
            self.db.toggle_rule(rule_id)
            self._refresh_rules()
            self._refresh_stats()
            self.notify("Rule toggled")

    def _delete_rule(self) -> None:
        rule_id = self._get_selected_rule_id()
        if not rule_id:
            self.notify("Select a rule first", severity="warning")
            return

        def handle_confirm(confirmed: bool) -> None:
            if confirmed:
                self.db.delete_rule(rule_id)
                self._refresh_rules()
                self._refresh_stats()
                self.notify("Rule deleted")

        self.push_screen(ConfirmScreen("Delete this rule?"), handle_confirm)

    def action_run_all_rules(self) -> None:
        if not self.gmail:
            self.notify("Not connected to Gmail", severity="error")
            return

        import src.config
        src.config.DRY_RUN = self.dry_run

        log_screen = RunLogScreen()

        def handle_result(stats: dict) -> None:
            self._refresh_rules()
            self._refresh_logs()
            self._refresh_stats()

        def run_in_thread():
            def thread_safe_log(msg, level="info"):
                self.call_from_thread(log_screen.add_log, msg, level)

            engine = RulesEngine(self.db, self.gmail, on_log=thread_safe_log)
            stats = engine.run_all_rules()
            self.call_from_thread(log_screen.finish, stats)

        def start_worker():
            self.run_worker(run_in_thread, thread=True)

        log_screen.call_after_refresh(start_worker)
        self.push_screen(log_screen, handle_result)

    def action_run_selected_rule(self) -> None:
        if not self.gmail:
            self.notify("Not connected to Gmail", severity="error")
            return

        rule_id = self._get_selected_rule_id()
        if not rule_id:
            self.notify("Select a rule first", severity="warning")
            return

        rule = self.db.get_rule(rule_id)
        if not rule:
            self.notify("Rule not found", severity="error")
            return

        import src.config
        src.config.DRY_RUN = self.dry_run

        log_screen = RunLogScreen()

        def handle_result(stats: dict) -> None:
            self._refresh_rules()
            self._refresh_logs()
            self._refresh_stats()

        def run_in_thread():
            def thread_safe_log(msg, level="info"):
                self.call_from_thread(log_screen.add_log, msg, level)

            engine = RulesEngine(self.db, self.gmail, on_log=thread_safe_log)
            stats = engine.process_rule(rule)
            self.call_from_thread(log_screen.finish, stats)

        def start_worker():
            self.run_worker(run_in_thread, thread=True)

        log_screen.call_after_refresh(start_worker)
        self.push_screen(log_screen, handle_result)

    def action_test_connection(self) -> None:
        self._test_connection()

    def action_toggle_dry_run(self) -> None:
        self.dry_run = not self.dry_run
        self._update_dry_indicator()
        self.notify(f"Dry Run: {'ON' if self.dry_run else 'OFF'}")

    def _update_dry_indicator(self) -> None:
        """Update the dry run indicator."""
        indicator = self.query_one("#dry-indicator", Static)
        if self.dry_run:
            indicator.update("Mode: DRY RUN (no changes)")
            indicator.add_class("dry-on")
        else:
            indicator.update("Mode: LIVE")
            indicator.remove_class("dry-on")

    def _clear_old_logs(self) -> None:
        count = self.db.clear_old_logs(30)
        self._refresh_logs()
        self._refresh_stats()
        self.notify(f"Cleared {count} old log entries")

    def _update_filter_bar(self) -> None:
        """Update the filter bar display."""
        filter_bar = self.query_one("#filter-bar", Static)
        if self.filter_mode or self.filter_text:
            text = self.filter_text if self.filter_text else ""
            filter_bar.update(f"/{text}_ (Enter to confirm, Esc to clear)")
            filter_bar.add_class("active")
        else:
            filter_bar.update("")
            filter_bar.remove_class("active")

    def action_clear_filter(self) -> None:
        """Clear the filter text and exit filter mode."""
        if self.filter_mode or self.filter_text:
            self.filter_text = ""
            self.filter_mode = False
            self._update_filter_bar()
            self._refresh_rules(keep_filter=True)

    def action_start_filter(self) -> None:
        """Enter filter mode."""
        rules_table = self.query_one("#rules-table", DataTable)
        if rules_table.has_focus and not self.filter_mode:
            self.filter_mode = True
            self._update_filter_bar()

    def on_key(self, event) -> None:
        """Handle key presses for live filtering."""
        # Only filter when rules table is focused
        rules_table = self.query_one("#rules-table", DataTable)
        if not rules_table.has_focus:
            return

        # Only process keys in filter mode
        if not self.filter_mode:
            return

        # Enter confirms filter and exits filter mode
        if event.key == "enter":
            self.filter_mode = False
            self._update_filter_bar()
            event.prevent_default()
            return

        # Handle backspace
        if event.key == "backspace":
            if self.filter_text:
                self.filter_text = self.filter_text[:-1]
                self._update_filter_bar()
                self._refresh_rules(keep_filter=True)
            event.prevent_default()
            return

        # Handle printable characters
        if event.is_printable and event.character:
            self.filter_text += event.character
            self._update_filter_bar()
            self._refresh_rules(keep_filter=True)
            event.prevent_default()


def main():
    errors = validate_config()
    if errors:
        print("Configuration errors:")
        for error in errors:
            print(f"  - {error}")
        print("\nPlease create a .env file (see .env.example)")
        sys.exit(1)

    app = GmailCleanerApp()
    app.run()


if __name__ == "__main__":
    main()
