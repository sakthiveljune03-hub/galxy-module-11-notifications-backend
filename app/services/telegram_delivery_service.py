import logging
import os
import re
import traceback
from typing import Callable, Optional

import requests

from app.constants.order_status import STATUS_LABELS

logger = logging.getLogger(__name__)


def _format_estimated_total(value) -> str:
    try:
        return f"{float(value):,.0f}"
    except (ValueError, TypeError):
        logger.warning("Invalid estimated_total: %s, falling back to raw value", value)
        return str(value)


TELEGRAM_TEMPLATES: dict = {
    "order_received": (
        "\U0001F4E6 *Order Received \u2014 {order_number}*\n\n"
        "Hi {customer_name}, your order *{order_number}* has been received.\n"
        "Estimated total: \u20B9{estimated_total}\n\n"
        "We'll review your configuration and send a quote shortly."
    ),
    "order_status_changed": (
        "\U0001F504 *Order Update \u2014 {order_number}*\n\n"
        "Your order has moved to: *{status_label}*\n"
        "{note_block}"
    ),
    "admin_new_order_alert": (
        "\U0001F514 *NEW ORDER*\n\n"
        "Customer: {customer_name} ({customer_email})\n"
        "Order: {order_number}\n"
        "Estimated Total: \u20B9{estimated_total}\n\n"
        "Review from the admin dashboard."
    ),
    "general": "{message}",
}

TELEGRAM_MAX_LENGTH = 4096

_MARKDOWNV2_SPECIAL = re.compile(r'([_*\[\]()~`>#+\-=|{}.!])')


def _escape_markdown_v2(text: str) -> str:
    return _MARKDOWNV2_SPECIAL.sub(r'\\\1', text)


def _get_config() -> dict:
    return {
        "bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
        "admin_chat_id": os.getenv("TELEGRAM_ADMIN_CHAT_ID", ""),
        "api_base_url": os.getenv(
            "TELEGRAM_API_BASE_URL", "https://api.telegram.org"
        ),
    }


_ENTITY_MARKERS = ("*", "_", "~", "`")


def _count_unescaped(text: str, marker: str) -> int:
    count = 0
    i = 0
    while i < len(text):
        if text[i] == "\\" and i + 1 < len(text):
            i += 2
            continue
        if text[i] == marker:
            count += 1
        i += 1
    return count


def _balance_entities(text: str) -> str:
    result = text
    for marker in _ENTITY_MARKERS:
        if _count_unescaped(result, marker) % 2 != 0:
            last_idx = -1
            i = 0
            while i < len(result):
                if result[i] == "\\" and i + 1 < len(result):
                    i += 2
                    continue
                if result[i] == marker:
                    last_idx = i
                i += 1
            if last_idx >= 0:
                result = result[:last_idx] + result[last_idx + 1:]
    return result


def _truncate(text: str, max_len: int = TELEGRAM_MAX_LENGTH) -> str:
    if len(text) <= max_len:
        return text
    truncated = text[: max_len - 1]
    if truncated.endswith("\\"):
        truncated = truncated[:-1]
    truncated = _balance_entities(truncated)
    logger.warning(
        "Telegram message truncated from %d to %d chars", len(text), max_len
    )
    return truncated


def _build_message(template_key: str, data: dict) -> str:
    template = TELEGRAM_TEMPLATES.get(template_key)
    if not template:
        template = TELEGRAM_TEMPLATES["general"]

    escaped_data = {
        k: _escape_markdown_v2(str(v)) if isinstance(v, str) else v
        for k, v in data.items()
    }
    escaped_data["note_block"] = ""
    if template_key == "order_status_changed":
        note = escaped_data.get("note", "")
        if note:
            escaped_data["note_block"] = f'\nNote: "{note}"'

    return template.format(**escaped_data)


def send_telegram_message(chat_id: str, text: str) -> bool:
    config = _get_config()
    if not config["bot_token"]:
        logger.warning("TELEGRAM_BOT_TOKEN not set \u2014 skipping message to %s", chat_id)
        return False

    text = _truncate(text)

    url = f"{config['api_base_url']}/bot{config['bot_token']}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "MarkdownV2",
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        result = resp.json()
        if result.get("ok"):
            logger.info("Telegram message sent to chat %s", chat_id)
            return True
        logger.error("Telegram API returned not-ok for chat %s", chat_id)
        return False
    except requests.exceptions.RequestException as exc:
        status = None
        try:
            status = exc.response.status_code
        except (AttributeError, KeyError):
            pass
        logger.error(
            "Telegram API request failed for chat %s (http_status=%s)",
            chat_id, status
        )
        return False
    except Exception:
        logger.error(
            "Unexpected error sending Telegram message to chat %s\n%s",
            chat_id, traceback.format_exc()
        )
        return False


def get_user_chat_id(
    user_id: str,
    subscriptions_collection,
) -> Optional[str]:
    try:
        sub = subscriptions_collection.find_one(
            {"user_id": user_id, "is_active": True},
            sort=[("created_at", -1)],
        )
        if sub and sub.get("chat_id"):
            return sub["chat_id"]
        return None
    except Exception:
        logger.error(
            "Failed to lookup telegram subscription for user %s\n%s",
            user_id, traceback.format_exc()
        )
        return None


def deliver_telegram(
    user_id: str,
    template_key: str,
    template_data: dict,
    subscriptions_collection,
) -> bool:
    try:
        chat_id = get_user_chat_id(user_id, subscriptions_collection)
        if not chat_id:
            logger.info(
                "No telegram subscription for user %s \u2014 skipping", user_id
            )
            return False

        text = _build_message(template_key, template_data)
        return send_telegram_message(chat_id, text)
    except Exception:
        order_number = template_data.get("order_number", "?")
        logger.error(
            "Failed to deliver Telegram notification to user %s (template=%s, order=%s)\n%s",
            user_id, template_key, order_number, traceback.format_exc()
        )
        return False


def send_order_received_telegram(
    user_id: str,
    customer_name: str,
    order_number: str,
    estimated_total: float,
    subscriptions_collection,
) -> bool:
    data = {
        "customer_name": customer_name,
        "order_number": order_number,
        "estimated_total": _format_estimated_total(estimated_total),
    }
    return deliver_telegram(user_id, "order_received", data, subscriptions_collection)


def send_order_status_changed_telegram(
    user_id: str,
    customer_name: str,
    order_number: str,
    new_status: str,
    note: Optional[str],
    subscriptions_collection,
) -> bool:
    status_label = STATUS_LABELS.get(new_status, new_status.replace("_", " ").title())
    data = {
        "customer_name": customer_name,
        "order_number": order_number,
        "status_label": status_label,
        "note": note or "",
    }
    return deliver_telegram(user_id, "order_status_changed", data, subscriptions_collection)


def send_admin_new_order_alert_telegram(
    customer_name: str,
    customer_email: str,
    order_number: str,
    estimated_total: float,
) -> bool:
    try:
        config = _get_config()
        if not config["admin_chat_id"]:
            logger.warning(
                "TELEGRAM_ADMIN_CHAT_ID not set \u2014 skipping admin alert"
            )
            return False

        data = {
            "customer_name": customer_name,
            "customer_email": customer_email,
            "order_number": order_number,
            "estimated_total": _format_estimated_total(estimated_total),
        }
        text = _build_message("admin_new_order_alert", data)
        return send_telegram_message(config["admin_chat_id"], text)
    except Exception:
        logger.error(
            "Failed to send Telegram admin alert for order %s\n%s",
            order_number, traceback.format_exc()
        )
        return False


def send_telegram_notification(chat_id: str, title: str, message: str) -> bool:
    try:
        text = _build_message("general", {"message": f"{title}\n\n{message}"})
        return send_telegram_message(chat_id, text)
    except Exception:
        logger.error(
            "Failed to send Telegram notification to chat %s\n%s",
            chat_id, traceback.format_exc()
        )
        return False
