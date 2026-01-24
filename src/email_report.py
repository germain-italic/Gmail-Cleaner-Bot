"""Email report functionality for Gmail Cleaner Bot."""

import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

from .config import (
    SMTP_ENABLED, SMTP_HOST, SMTP_PORT, SMTP_USER,
    SMTP_PASSWORD, SMTP_FROM, SMTP_TO, SMTP_TLS, DRY_RUN
)


def _format_log_line_html(line: str) -> str:
    """Format a single log line with HTML styling."""
    # Skip empty lines
    if not line.strip():
        return ""

    # Error lines (red)
    if "error" in line.lower() or "failed" in line.lower() or "cancelled" in line.lower():
        return f'<div style="color: #dc3545; padding: 2px 0;">{_escape_html(line)}</div>'

    # Action lines - delete (red background)
    if "Action 'delete'" in line:
        return f'<div style="background-color: #f8d7da; color: #721c24; padding: 4px 8px; margin: 2px 0; border-radius: 3px; font-family: monospace; font-size: 12px;">{_escape_html(line)}</div>'

    # Action lines - archive (blue background)
    if "Action 'archive'" in line:
        return f'<div style="background-color: #cce5ff; color: #004085; padding: 4px 8px; margin: 2px 0; border-radius: 3px; font-family: monospace; font-size: 12px;">{_escape_html(line)}</div>'

    # Action lines - mark_read (gray background)
    if "Action 'mark_read'" in line:
        return f'<div style="background-color: #e2e3e5; color: #383d41; padding: 4px 8px; margin: 2px 0; border-radius: 3px; font-family: monospace; font-size: 12px;">{_escape_html(line)}</div>'

    # Action lines - label (yellow background)
    if "Action 'label'" in line:
        return f'<div style="background-color: #fff3cd; color: #856404; padding: 4px 8px; margin: 2px 0; border-radius: 3px; font-family: monospace; font-size: 12px;">{_escape_html(line)}</div>'

    # DRY RUN lines (orange)
    if "[DRY RUN]" in line:
        return f'<div style="color: #fd7e14; padding: 2px 0; font-family: monospace; font-size: 12px;">{_escape_html(line)}</div>'

    # Rule processing lines (bold blue)
    if line.startswith("Processing rule:"):
        rule_name = line.replace("Processing rule:", "").strip()
        return f'<div style="color: #0056b3; font-weight: bold; padding: 8px 0 2px 0; border-top: 1px solid #dee2e6; margin-top: 8px;">{_escape_html(line)}</div>'

    # Rule complete lines with matches (green if success, gray if no match)
    if "complete:" in line:
        if "0 matched" in line:
            return f'<div style="color: #6c757d; font-size: 12px; padding: 0 0 4px 0;">{_escape_html(line)}</div>'
        else:
            return f'<div style="color: #28a745; font-weight: bold; padding: 0 0 4px 0;">{_escape_html(line)}</div>'

    # Starting/Found messages (info)
    if line.startswith("Starting cleanup") or line.startswith("Found ") or "Fetching messages" in line:
        return f'<div style="color: #17a2b8; padding: 2px 0;">{_escape_html(line)}</div>'

    # Search query lines (gray, smaller)
    if line.startswith("Searching with query:"):
        return f'<div style="color: #6c757d; font-size: 11px; font-family: monospace; padding: 0 0 2px 12px;">{_escape_html(line)}</div>'

    # Default styling
    return f'<div style="color: #333; padding: 1px 0; font-size: 12px;">{_escape_html(line)}</div>'


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def send_report(stats: dict, rule_details: list[dict] = None, duration: str = None, logs: list[str] = None) -> bool:
    """Send execution report via email.

    Args:
        stats: Dictionary with keys: rules_processed, matched, success, failed
        rule_details: Optional list of per-rule stats
        duration: Optional execution duration string (e.g., "2m 30s")
        logs: Optional list of execution log lines

    Returns:
        True if email sent successfully, False otherwise
    """
    if not SMTP_ENABLED:
        return False

    if not all([SMTP_HOST, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SMTP_TO]):
        return False

    # Build email content
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    mode = "DRY RUN" if DRY_RUN else "LIVE"
    mode_color = "#fd7e14" if DRY_RUN else "#28a745"

    subject = f"[Gmail Cleaner] Rapport du {now}"
    if stats['matched'] == 0:
        subject += " - Aucune action"
    elif stats['failed'] > 0:
        subject += f" - {stats['failed']} erreur(s)"

    # Build HTML email
    html_parts = [
        '<!DOCTYPE html>',
        '<html>',
        '<head><meta charset="utf-8"></head>',
        '<body style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background-color: #f5f5f5;">',
        '<div style="background-color: white; border-radius: 8px; padding: 24px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">',

        # Header
        '<h1 style="color: #333; margin: 0 0 20px 0; font-size: 24px; border-bottom: 2px solid #007bff; padding-bottom: 10px;">Gmail Cleaner Bot</h1>',

        # Info bar (using table for email client compatibility)
        f'<table style="margin-bottom: 20px;"><tr>',
        f'<td style="padding-right: 30px;"><strong>Date:</strong> {now}</td>',
        f'<td style="padding-right: 30px;"><strong>Mode:</strong> <span style="color: {mode_color}; font-weight: bold;">{mode}</span></td>',
        f'<td><strong>Durée:</strong> {duration}</td>' if duration else '',
        f'</tr></table>',
    ]

    # Summary table
    success_color = "#28a745" if stats['success'] > 0 else "#6c757d"
    failed_color = "#dc3545" if stats['failed'] > 0 else "#6c757d"
    matched_color = "#007bff" if stats['matched'] > 0 else "#6c757d"

    html_parts.extend([
        '<h2 style="color: #333; font-size: 18px; margin: 20px 0 10px 0;">Résumé</h2>',
        '<table style="border-collapse: collapse; width: 100%; max-width: 400px;">',
        f'<tr><td style="padding: 8px; border-bottom: 1px solid #dee2e6;">Règles traitées</td><td style="padding: 8px; border-bottom: 1px solid #dee2e6; text-align: right; font-weight: bold;">{stats["rules_processed"]}</td></tr>',
        f'<tr><td style="padding: 8px; border-bottom: 1px solid #dee2e6;">Messages trouvés</td><td style="padding: 8px; border-bottom: 1px solid #dee2e6; text-align: right; font-weight: bold; color: {matched_color};">{stats["matched"]}</td></tr>',
        f'<tr><td style="padding: 8px; border-bottom: 1px solid #dee2e6;">Actions réussies</td><td style="padding: 8px; border-bottom: 1px solid #dee2e6; text-align: right; font-weight: bold; color: {success_color};">{stats["success"]}</td></tr>',
        f'<tr><td style="padding: 8px;">Actions échouées</td><td style="padding: 8px; text-align: right; font-weight: bold; color: {failed_color};">{stats["failed"]}</td></tr>',
        '</table>',
    ])

    # Logs section
    if logs:
        # Filter and categorize logs
        action_logs = [l for l in logs if "Action '" in l or "[DRY RUN]" in l]

        # Summary of actions at the top
        if action_logs:
            html_parts.extend([
                '<h2 style="color: #333; font-size: 18px; margin: 24px 0 10px 0;">Actions effectuées</h2>',
                '<div style="background-color: #f8f9fa; border-radius: 4px; padding: 12px; margin-bottom: 16px;">',
            ])
            for log in action_logs:
                html_parts.append(_format_log_line_html(log))
            html_parts.append('</div>')

        # Full execution log (collapsible style - always shown but in smaller font)
        html_parts.extend([
            '<h2 style="color: #333; font-size: 18px; margin: 24px 0 10px 0;">Log complet</h2>',
            '<div style="background-color: #f8f9fa; border-radius: 4px; padding: 12px; max-height: 500px; overflow-y: auto;">',
        ])
        for log in logs:
            formatted = _format_log_line_html(log)
            if formatted:
                html_parts.append(formatted)
        html_parts.append('</div>')

    # Footer
    html_parts.extend([
        '<div style="margin-top: 24px; padding-top: 16px; border-top: 1px solid #dee2e6; color: #6c757d; font-size: 12px;">',
        'Gmail Cleaner Bot',
        '</div>',
        '</div>',
        '</body>',
        '</html>',
    ])

    html_body = '\n'.join(html_parts)

    # Plain text fallback
    plain_lines = [
        f"Gmail Cleaner Bot - Rapport d'exécution",
        f"Date: {now} | Mode: {mode}" + (f" | Durée: {duration}" if duration else ""),
        f"",
        f"Résumé: {stats['rules_processed']} règles, {stats['matched']} messages, {stats['success']} OK, {stats['failed']} KO",
    ]
    if logs:
        plain_lines.extend(["", "Log:"] + logs)
    plain_body = "\n".join(plain_lines)

    # Create message with both HTML and plain text
    msg = MIMEMultipart('alternative')
    msg['From'] = SMTP_FROM
    msg['To'] = SMTP_TO
    msg['Subject'] = subject

    # Attach plain text first, then HTML (email clients prefer last)
    msg.attach(MIMEText(plain_body, 'plain', 'utf-8'))
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))

    try:
        if SMTP_TLS:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT)

        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Failed to send email report: {e}")
        return False
