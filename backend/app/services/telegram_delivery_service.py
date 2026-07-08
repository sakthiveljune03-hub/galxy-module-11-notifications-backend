import logging
import os
import re
import traceback
import datetime
import requests
import json
import urllib.request
import urllib.parse
from typing import Callable, Optional

from app.constants.order_status import STATUS_LABELS

logger = logging.getLogger(__name__)

_format_estimated_total = lambda value: f"{float(value):,.0f}" if isinstance(value, (int, float, str)) and str(value).replace(".", "", 1).isdigit() else str(value)

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


# --- Unified send_telegram_notification ---

def _send_telegram_notification_ajay(chat_id: str, title: str, message: str) -> bool:
    try:
        text = _build_message("general", {"message": f"{title}\n\n{message}"})
        if send_telegram_message(chat_id, text):
            return True
        
        config = _get_config()
        if not config["bot_token"]:
            # Mock fallback when token is not set, only for mock chat IDs
            if str(chat_id).startswith("chat_"):
                import pathlib
                BASE_DIR = pathlib.Path(__file__).resolve().parent.parent.parent.parent
                MOCK_TELEGRAM_LOG = os.path.join(os.getenv("MOCK_DATA_DIR", str(BASE_DIR / "scratch")), "mock_telegram_delivery.log")
                os.makedirs(os.path.dirname(MOCK_TELEGRAM_LOG), exist_ok=True)
                timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
                formatted_msg = f"🔔 *GALXY Alert*:\n{title}\n\n{message}"
                log_entry = f"[{timestamp}] TO CHAT_ID: {chat_id} (AJAY_FLOW)\nMESSAGE:\n{formatted_msg}\n{'-'*60}\n"
                with open(MOCK_TELEGRAM_LOG, "a", encoding="utf-8") as f:
                    f.write(log_entry)
                logger.info("[Telegram Service] Mock telegram notification logged to %s (Ajay flow fallback)", MOCK_TELEGRAM_LOG)
                return True
            return False
        return False
    except Exception:
        logger.error(
            "Failed to send Telegram notification to chat %s\n%s",
            chat_id, traceback.format_exc()
        )
        return False


def _send_telegram_notification_sakthivel(user_id, message, order_id=None) -> bool:
    from app.services import notification_service as notif_service
    status = notif_service.get_telegram_status(user_id)
    if not status or not status.get("is_active") or not status.get("chat_id"):
        return False
        
    chat_id = status["chat_id"]
    formatted_msg = f"🔔 *GALXY Alert*:\n{message}"
    if order_id:
        formatted_msg += f"\n📦 *Order*: {order_id}"
        
    # Check if real bot token is present
    config = _get_config()
    if config["bot_token"]:
        try:
            url = f"{config['api_base_url']}/bot{config['bot_token']}/sendMessage"
            data = urllib.parse.urlencode({
                "chat_id": chat_id,
                "text": formatted_msg,
                "parse_mode": "Markdown"
            }).encode("utf-8")
            
            req = urllib.request.Request(url, data=data, method="POST")
            with urllib.request.urlopen(req, timeout=5) as response:
                res_body = response.read().decode("utf-8")
                res_json = json.loads(res_body)
                if res_json.get("ok"):
                    logger.info("[Telegram Service] Message successfully sent to chat %s", chat_id)
                    return True
        except Exception as e:
            logger.error("[Telegram Error] Network delivery failed to %s: %s", chat_id, e)
            
    # Mock fallback
    try:
        import pathlib
        BASE_DIR = pathlib.Path(__file__).resolve().parent.parent.parent.parent
        MOCK_TELEGRAM_LOG = os.path.join(os.getenv("MOCK_DATA_DIR", str(BASE_DIR / "scratch")), "mock_telegram_delivery.log")
        os.makedirs(os.path.dirname(MOCK_TELEGRAM_LOG), exist_ok=True)
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        log_entry = f"[{timestamp}] TO CHAT_ID: {chat_id} (user: {user_id})\nMESSAGE:\n{formatted_msg}\n{'-'*60}\n"
        with open(MOCK_TELEGRAM_LOG, "a", encoding="utf-8") as f:
            f.write(log_entry)
        logger.info("[Telegram Service] Mock telegram notification logged to %s", MOCK_TELEGRAM_LOG)
        return True
    except Exception as err:
        logger.error("[Telegram Error] Failed writing mock telegram log: %s", err)
        return False


def send_telegram_notification(*args, **kwargs) -> bool:
    is_ajay = False
    if 'chat_id' in kwargs or 'title' in kwargs:
        is_ajay = True
    elif 'user_id' in kwargs:
        is_ajay = False
    elif len(args) >= 2:
        first_arg = args[0]
        if isinstance(first_arg, str):
            first_arg_clean = first_arg.strip()
            if first_arg_clean.startswith("chat_"):
                is_ajay = True
            elif first_arg_clean.startswith("-"):
                is_ajay = first_arg_clean[1:].isdigit()
            else:
                is_ajay = first_arg_clean.isdigit()
        else:
            is_ajay = False

    if is_ajay:
        chat_id = kwargs.get('chat_id') or (args[0] if len(args) > 0 else None)
        title = kwargs.get('title') or (args[1] if len(args) > 1 else None)
        message = kwargs.get('message') or (args[2] if len(args) > 2 else None)
        return _send_telegram_notification_ajay(chat_id, title, message)
    else:
        user_id = kwargs.get('user_id') or (args[0] if len(args) > 0 else None)
        message = kwargs.get('message') or (args[1] if len(args) > 1 else None)
        order_id = kwargs.get('order_id') or (args[2] if len(args) > 2 else None)
        return _send_telegram_notification_sakthivel(user_id, message, order_id)


def send_telegram_verification_code(chat_id: str, verification_code: str) -> bool:
    formatted_msg = (
        f"🔐 *GALXY Telegram Verification Code*:\n"
        f"Your code is: `{verification_code}`\n\n"
        f"Please enter this code on the verification settings screen to activate your notifications."
    )
    
    config = _get_config()
    if config["bot_token"]:
        try:
            url = f"{config['api_base_url']}/bot{config['bot_token']}/sendMessage"
            data = urllib.parse.urlencode({
                "chat_id": chat_id,
                "text": formatted_msg,
                "parse_mode": "Markdown"
            }).encode("utf-8")
            
            req = urllib.request.Request(url, data=data, method="POST")
            with urllib.request.urlopen(req, timeout=5) as response:
                res_body = response.read().decode("utf-8")
                res_json = json.loads(res_body)
                if res_json.get("ok"):
                    logger.info("[Telegram Service] Verification code successfully sent to chat %s", chat_id)
                    return True
        except Exception as e:
            logger.error("[Telegram Error] Verification Network delivery failed to %s: %s", chat_id, e)
            
    # Mock fallback
    try:
        import pathlib
        BASE_DIR = pathlib.Path(__file__).resolve().parent.parent.parent.parent
        MOCK_TELEGRAM_LOG = os.path.join(os.getenv("MOCK_DATA_DIR", str(BASE_DIR / "scratch")), "mock_telegram_delivery.log")
        os.makedirs(os.path.dirname(MOCK_TELEGRAM_LOG), exist_ok=True)
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        log_entry = f"[{timestamp}] TO CHAT_ID: {chat_id} (VERIFICATION)\nMESSAGE:\n{formatted_msg}\n{'-'*60}\n"
        with open(MOCK_TELEGRAM_LOG, "a", encoding="utf-8") as f:
            f.write(log_entry)
        logger.info("[Telegram Service] Mock telegram verification code logged to %s", MOCK_TELEGRAM_LOG)
        return True
    except Exception as err:
        logger.error("[Telegram Error] Failed writing mock telegram verification log: %s", err)
        return False
