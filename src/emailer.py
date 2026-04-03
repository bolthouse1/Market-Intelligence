"""SMTP email delivery for intel reports."""

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def send_report(
    html_content: str,
    recipients: list[str],
    subject: str,
    email_config: dict,
) -> bool:
    """Send the HTML report via SMTP.

    Args:
        html_content: Rendered HTML report string.
        recipients: List of email addresses.
        subject: Email subject line.
        email_config: Dict with smtp_host, smtp_port, from_name keys.
            SMTP_USER and SMTP_PASSWORD are read from environment.

    Returns:
        True if sent successfully.

    Raises:
        Exception on SMTP failure.
    """
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")

    if not smtp_user or not smtp_password:
        raise ValueError("SMTP_USER and SMTP_PASSWORD must be set in .env")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{email_config.get('from_name', '120VC Intel')} <{smtp_user}>"
    msg["To"] = ", ".join(recipients)

    plain = (
        "Your daily C-Suite Intel Briefing is ready. "
        "View this email in an HTML-capable client for the full report."
    )
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html_content, "html"))

    host = email_config.get("smtp_host", "smtp.gmail.com")
    port = email_config.get("smtp_port", 587)

    logger.info(f"Sending report to {', '.join(recipients)} via {host}:{port}")

    with smtplib.SMTP(host, port, timeout=10) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)

    logger.info("Email sent successfully")
    return True
