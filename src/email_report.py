"""Email report functionality for Gmail Cleaner Bot."""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

from .config import (
    SMTP_ENABLED, SMTP_HOST, SMTP_PORT, SMTP_USER,
    SMTP_PASSWORD, SMTP_FROM, SMTP_TO, SMTP_TLS, DRY_RUN
)


def send_report(stats: dict, rule_details: list[dict] = None) -> bool:
    """Send execution report via email.

    Args:
        stats: Dictionary with keys: rules_processed, matched, success, failed
        rule_details: Optional list of per-rule stats

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

    subject = f"[Gmail Cleaner] Rapport du {now}"
    if stats['matched'] == 0:
        subject += " - Aucune action"
    elif stats['failed'] > 0:
        subject += f" - {stats['failed']} erreur(s)"

    # Plain text body
    body_lines = [
        f"Gmail Cleaner Bot - Rapport d'exécution",
        f"========================================",
        f"",
        f"Date: {now}",
        f"Mode: {mode}",
        f"",
        f"Résumé:",
        f"  - Règles traitées: {stats['rules_processed']}",
        f"  - Messages trouvés: {stats['matched']}",
        f"  - Actions réussies: {stats['success']}",
        f"  - Actions échouées: {stats['failed']}",
    ]

    if rule_details:
        body_lines.extend([
            f"",
            f"Détails par règle:",
            f"------------------",
        ])
        for rule in rule_details:
            body_lines.append(f"  {rule['name']}: {rule['matched']} message(s), {rule['success']} OK, {rule['failed']} KO")

    body_lines.extend([
        f"",
        f"--",
        f"Gmail Cleaner Bot",
    ])

    body = "\n".join(body_lines)

    # Create message
    msg = MIMEMultipart()
    msg['From'] = SMTP_FROM
    msg['To'] = SMTP_TO
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

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
