import html
import logging
import os
import traceback
from typing import Callable, Optional

from app.constants.order_status import STATUS_LABELS

logger = logging.getLogger(__name__)

_ALLOWED_URL_SCHEMES = ("https://", "http://")
_GALXY_BASE_URL = os.getenv("GALXY_BASE_URL", "")


def _validate_url(url: str, field_name: str = "url") -> str:
    if not isinstance(url, str) or not url.startswith(_ALLOWED_URL_SCHEMES):
        logger.warning("Invalid %s scheme: %s — falling back to empty string", field_name, url)
        return ""
    if _GALXY_BASE_URL and not url.startswith(_GALXY_BASE_URL):
        logger.warning(
            "%s %s does not match GALXY_BASE_URL — falling back to empty string",
            field_name, url
        )
        return ""
    return url


def _format_estimated_total(value) -> str:
    try:
        return f"{float(value):,.0f}"
    except (ValueError, TypeError):
        logger.warning("Invalid estimated_total: %s, falling back to raw value", value)
        return str(value)


EMAIL_TEMPLATES: dict = {
    "order_received": {
        "subject": "Order Confirmed — {order_number}",
        "body_html": """
        <div style="background:#0B0B0F;padding:32px;font-family:Inter,sans-serif;">
            <h2 style="color:#FF2E8A;">Thank you, {customer_name}!</h2>
            <p style="color:#F4F4F7;">Your order <strong>{order_number}</strong> has been received.</p>
            <p style="color:#8A8A97;">Estimated total: <span style="color:#18E7FF;">₹{estimated_total}</span></p>
            <p style="color:#8A8A97;">We'll review your configuration and send a quote shortly. You can track your order status anytime from your dashboard.</p>
            <a href="{dashboard_url}" style="display:inline-block;padding:12px 24px;background:#FF2E8A;color:#0B0B0F;text-decoration:none;border-radius:8px;margin-top:16px;">Track Order</a>
            <p style="color:#8A8A97;margin-top:24px;font-size:12px;">— Team Galxy</p>
        </div>
        """,
    },
    "order_status_changed": {
        "subject": "Order Update — {order_number} is now {status_label}",
        "body_html": """
        <div style="background:#0B0B0F;padding:32px;font-family:Inter,sans-serif;">
            <h2 style="color:#FF2E8A;">Status Update</h2>
            <p style="color:#F4F4F7;">Your order <strong>{order_number}</strong> has moved to:</p>
            <p style="color:#18E7FF;font-size:20px;font-weight:600;">{status_label}</p>
            {note_block}
            <a href="{dashboard_url}" style="display:inline-block;padding:12px 24px;background:#FF2E8A;color:#0B0B0F;text-decoration:none;border-radius:8px;margin-top:16px;">View Order</a>
            <p style="color:#8A8A97;margin-top:24px;font-size:12px;">— Team Galxy</p>
        </div>
        """,
    },
    "admin_new_order_alert": {
        "subject": "NEW ORDER — {order_number} from {customer_name}",
        "body_html": """
        <div style="background:#0B0B0F;padding:32px;font-family:Inter,sans-serif;">
            <h2 style="color:#FFD84D;">New Order Received</h2>
            <p style="color:#F4F4F7;"><strong>Customer:</strong> {customer_name} ({customer_email})</p>
            <p style="color:#F4F4F7;"><strong>Order:</strong> {order_number}</p>
            <p style="color:#F4F4F7;"><strong>Estimated Total:</strong> <span style="color:#18E7FF;">₹{estimated_total}</span></p>
            <p style="color:#8A8A97;">Review and respond from the admin dashboard.</p>
            <a href="{admin_url}" style="display:inline-block;padding:12px 24px;background:#FFD84D;color:#0B0B0F;text-decoration:none;border-radius:8px;margin-top:16px;">Open Dashboard</a>
            <p style="color:#8A8A97;margin-top:24px;font-size:12px;">— Galxy Admin Notification</p>
        </div>
        """,
    },
    "general": {
        "subject": "{subject}",
        "body_html": """
        <div style="background:#0B0B0F;padding:32px;font-family:Inter,sans-serif;">
            <p style="color:#F4F4F7;">{message}</p>
            <p style="color:#8A8A97;margin-top:24px;font-size:12px;">— Team Galxy</p>
        </div>
        """,
    },
}


def _sanitize_for_subject(value):
    if isinstance(value, str):
        return value.replace("\r", "").replace("\n", " ")
    return value


def _build_body(template_key: str, data: dict) -> tuple:
    template = EMAIL_TEMPLATES.get(template_key)
    if not template:
        template = EMAIL_TEMPLATES["general"]

    subject_data = {k: _sanitize_for_subject(v) for k, v in data.items()}
    subject = template["subject"].format(**subject_data)

    escaped_data = {
        k: html.escape(str(v)) if isinstance(v, str) else v
        for k, v in data.items()
    }

    render_data = dict(escaped_data)
    render_data["note_block"] = ""
    if template_key == "order_status_changed":
        note_html = render_data.get("note", "")
        if note_html:
            render_data["note_block"] = (
                f'<p style="color:#9B5CFF;font-style:italic;">"{note_html}"</p>'
            )

    body_html = template["body_html"].format(**render_data)
    return subject, body_html


def deliver_email(
    to: str,
    template_key: str,
    template_data: dict,
    smtp_sender: Callable[..., None],
) -> bool:
    try:
        subject, body_html = _build_body(template_key, template_data)
        smtp_sender(to=to, subject=subject, body_html=body_html)
        logger.info("Email delivered to %s (template=%s)", to, template_key)
        return True
    except Exception:
        order_number = template_data.get("order_number", "?")
        logger.error(
            "Failed to send email to %s (template=%s, order=%s)\n%s",
            to, template_key, order_number, traceback.format_exc()
        )
        return False


def send_order_received_email(
    user_email: str,
    customer_name: str,
    order_number: str,
    estimated_total: float,
    dashboard_url: str,
    smtp_sender: Callable[..., None],
) -> bool:
    data = {
        "customer_name": customer_name,
        "order_number": order_number,
        "estimated_total": _format_estimated_total(estimated_total),
        "dashboard_url": _validate_url(dashboard_url, "dashboard_url"),
    }
    return deliver_email(user_email, "order_received", data, smtp_sender)


def send_order_status_changed_email(
    user_email: str,
    customer_name: str,
    order_number: str,
    new_status: str,
    note: Optional[str],
    dashboard_url: str,
    smtp_sender: Callable[..., None],
) -> bool:
    status_label = STATUS_LABELS.get(new_status, new_status.replace("_", " ").title())
    data = {
        "customer_name": customer_name,
        "order_number": order_number,
        "status_label": status_label,
        "note": note or "",
        "dashboard_url": _validate_url(dashboard_url, "dashboard_url"),
    }
    return deliver_email(user_email, "order_status_changed", data, smtp_sender)


def send_general_notification_email(
    to: str,
    subject: str,
    message: str,
    smtp_sender: Callable[..., None],
) -> bool:
    data = {"subject": subject, "message": message}
    return deliver_email(to, "general", data, smtp_sender)


def send_admin_new_order_alert(
    admin_email: str,
    customer_name: str,
    customer_email: str,
    order_number: str,
    estimated_total: float,
    admin_url: str,
    smtp_sender: Callable[..., None],
) -> bool:
    data = {
        "customer_name": customer_name,
        "customer_email": customer_email,
        "order_number": order_number,
        "estimated_total": _format_estimated_total(estimated_total),
        "admin_url": _validate_url(admin_url, "admin_url"),
    }
    return deliver_email(admin_email, "admin_new_order_alert", data, smtp_sender)
