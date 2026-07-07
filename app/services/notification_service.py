import logging

from app.services.email_delivery_service import (
    send_admin_new_order_alert,
    send_general_notification_email,
    send_order_received_email,
    send_order_status_changed_email,
)
from app.services.telegram_delivery_service import (
    send_admin_new_order_alert_telegram,
    send_order_received_telegram,
    send_order_status_changed_telegram,
)

logger = logging.getLogger(__name__)


def notify_user(
    event_type: str,
    recipient: dict,
    event_data: dict,
    smtp_sender,
    subscriptions_collection,
    send_email: bool = True,
    send_telegram: bool = True,
) -> dict:
    result = {"email": False, "telegram": False}

    if send_email and smtp_sender:
        result["email"] = _dispatch_email(event_type, recipient, event_data, smtp_sender)

    if send_telegram and subscriptions_collection is not None:
        result["telegram"] = _dispatch_telegram(event_type, recipient, event_data, subscriptions_collection)

    return result


def _dispatch_email(event_type: str, recipient: dict, data: dict, smtp_sender) -> bool:
    try:
        if event_type == "order_received":
            return send_order_received_email(
                user_email=recipient["email"],
                customer_name=recipient["name"],
                order_number=data["order_number"],
                estimated_total=data.get("estimated_total", 0),
                dashboard_url=data.get("dashboard_url", ""),
                smtp_sender=smtp_sender,
            )
        elif event_type == "order_status_changed":
            return send_order_status_changed_email(
                user_email=recipient["email"],
                customer_name=recipient["name"],
                order_number=data["order_number"],
                new_status=data["new_status"],
                note=data.get("note"),
                dashboard_url=data.get("dashboard_url", ""),
                smtp_sender=smtp_sender,
            )
        elif event_type == "admin_new_order_alert":
            return send_admin_new_order_alert(
                admin_email=recipient["email"],
                customer_name=recipient["name"],
                customer_email=recipient.get("customer_email", ""),
                order_number=data["order_number"],
                estimated_total=data.get("estimated_total", 0),
                admin_url=data.get("admin_url", ""),
                smtp_sender=smtp_sender,
            )
        elif event_type == "general":
            return send_general_notification_email(
                to=recipient["email"],
                subject=data.get("subject", ""),
                message=data.get("message", ""),
                smtp_sender=smtp_sender,
            )
        logger.warning("Unknown email event_type: %s", event_type)
        return False
    except Exception:
        logger.exception("Failed to dispatch email for event=%s", event_type)
        return False


def _dispatch_telegram(event_type: str, recipient: dict, data: dict, subscriptions_collection) -> bool:
    try:
        if event_type == "order_received":
            return send_order_received_telegram(
                user_id=recipient["user_id"],
                customer_name=recipient["name"],
                order_number=data["order_number"],
                estimated_total=data.get("estimated_total", 0),
                subscriptions_collection=subscriptions_collection,
            )
        elif event_type == "order_status_changed":
            return send_order_status_changed_telegram(
                user_id=recipient["user_id"],
                customer_name=recipient["name"],
                order_number=data["order_number"],
                new_status=data["new_status"],
                note=data.get("note"),
                subscriptions_collection=subscriptions_collection,
            )
        elif event_type == "admin_new_order_alert":
            return send_admin_new_order_alert_telegram(
                customer_name=recipient["name"],
                customer_email=recipient.get("customer_email", ""),
                order_number=data["order_number"],
                estimated_total=data.get("estimated_total", 0),
            )
        logger.warning("Unknown telegram event_type: %s", event_type)
        return False
    except Exception:
        logger.exception("Failed to dispatch telegram for event=%s", event_type)
        return False
