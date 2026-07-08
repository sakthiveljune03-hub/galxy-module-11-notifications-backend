import os
import smtplib
import sys
import datetime
import pathlib
from email.mime.text import MIMEText
from app.configs.config import Config

# Email Config (optional environment variables)
SMTP_SERVER = os.getenv("SMTP_SERVER", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
EMAIL_SENDER = os.getenv("EMAIL_SENDER", "noreply@galxy.com")

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent.parent.parent
MOCK_EMAIL_LOG = os.path.join(os.getenv("MOCK_DATA_DIR", str(BASE_DIR / "scratch")), "mock_emails.log")

def send_email_notification(user_id, message, order_id=None):
    """
    Sends an email notification to the user.
    If SMTP variables are not configured, it writes to a local mock log file.
    """
    # For a real application, we would lookup the user's email address from the DB (Module 1/Users).
    # Since we are isolating Module 11, we will default to a mock recipient: <user_id>@example.com
    recipient_email = f"{user_id}@example.com"
    subject = f"GALXY Alert: Order Update {f'({order_id})' if order_id else ''}"
    
    # Body HTML/Plain text
    body = f"""
    Hello {user_id},
    
    You have received a new notification from GALXY:
    
    "{message}"
    
    {f'Linked Order Reference: {order_id}' if order_id else ''}
    
    Best regards,
    The GALXY Team
    """
    
    # Check if SMTP is configured
    if SMTP_SERVER and SMTP_USER and SMTP_PASSWORD:
        try:
            msg = MIMEText(body)
            msg['Subject'] = subject
            msg['From'] = EMAIL_SENDER
            msg['To'] = recipient_email
            
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(EMAIL_SENDER, [recipient_email], msg.as_string())
            print(f"[Email Service] Real email successfully sent to {recipient_email}")
            return True
        except Exception as e:
            print(f"[Email Error] SMTP delivery failed to {recipient_email}: {e}. Falling back to mock log.", file=sys.stderr)
            
    # Fallback/Mock Mode: write to mock_emails.log file
    try:
        os.makedirs(os.path.dirname(MOCK_EMAIL_LOG), exist_ok=True)
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        log_entry = f"[{timestamp}] TO: {recipient_email} | SUBJECT: {subject}\nBODY:\n{body}\n{'-'*60}\n"
        with open(MOCK_EMAIL_LOG, "a", encoding="utf-8") as f:
            f.write(log_entry)
        print(f"[Email Service] Mock email logged to {MOCK_EMAIL_LOG}")
        return True
    except Exception as err:
        print(f"[Email Error] Failed writing mock email log: {err}", file=sys.stderr)
        return False
