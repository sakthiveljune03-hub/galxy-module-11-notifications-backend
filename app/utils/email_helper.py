import logging
import os
import smtplib
import ssl
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def send_email(to: str, subject: str, body_html: str) -> None:
    msg = MIMEText(body_html, "html")
    msg["Subject"] = subject
    msg["To"] = to
    msg["From"] = "noreply@galxy.in"

    smtp_host = os.getenv("SMTP_HOST", "email-smtp.ap-south-1.amazonaws.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.starttls(context=ssl.create_default_context())
            server.login(
                os.environ["SMTP_USERNAME"],
                os.environ["SMTP_PASSWORD"],
            )
            server.send_message(msg)
            logger.info("Email sent to %s (subject=%s)", to, subject)
    except Exception:
        logger.exception("Failed to send email to %s", to)
        raise
