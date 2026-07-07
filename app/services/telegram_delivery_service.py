import os
import urllib.request
import urllib.parse
import json
import sys
import datetime
import pathlib
from app.services import notification_service as notif_service

# Load token from environment
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent.parent.parent
MOCK_TELEGRAM_LOG = os.path.join(os.getenv("MOCK_DATA_DIR", str(BASE_DIR / "scratch")), "mock_telegram_delivery.log")

def send_telegram_notification(user_id, message, order_id=None):
    """
    Looks up the Telegram subscription for user_id.
    If active and chat_id is present, dispatches the message via Telegram Bot API
    or logs to a local mock log file if no token is configured.
    """
    # 1. Lookup subscription
    status = notif_service.get_telegram_status(user_id)
    if not status or not status.get("is_active") or not status.get("chat_id"):
        # No subscription active -> skip
        return False
        
    chat_id = status["chat_id"]
    formatted_msg = f"🔔 *GALXY Alert*:\n{message}"
    if order_id:
        formatted_msg += f"\n📦 *Order*: {order_id}"
        
    # 2. Check token config
    if TELEGRAM_BOT_TOKEN:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
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
                    print(f"[Telegram Service] Message successfully sent to chat {chat_id}")
                    return True
                else:
                    print(f"[Telegram Error] Bot API response failed: {res_body}. Falling back to mock log.", file=sys.stderr)
        except Exception as e:
            print(f"[Telegram Error] Network delivery failed to {chat_id}: {e}. Falling back to mock log.", file=sys.stderr)
            
    # Fallback/Mock Mode: write to mock_telegram_delivery.log file
    try:
        os.makedirs(os.path.dirname(MOCK_TELEGRAM_LOG), exist_ok=True)
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        log_entry = f"[{timestamp}] TO CHAT_ID: {chat_id} (user: {user_id})\nMESSAGE:\n{formatted_msg}\n{'-'*60}\n"
        with open(MOCK_TELEGRAM_LOG, "a", encoding="utf-8") as f:
            f.write(log_entry)
        print(f"[Telegram Service] Mock telegram notification logged to {MOCK_TELEGRAM_LOG}")
        return True
    except Exception as err:
        print(f"[Telegram Error] Failed writing mock telegram log: {err}", file=sys.stderr)
        return False

def send_telegram_verification_code(chat_id, verification_code):
    """
    Delivers a 6-digit Telegram verification code directly to the chat_id.
    Bypasses is_active check because subscription is pending verification.
    """
    formatted_msg = f"🔐 *GALXY Telegram Verification Code*:\nYour code is: `{verification_code}`\n\nPlease enter this code on the verification settings screen to activate your notifications."
    
    if TELEGRAM_BOT_TOKEN:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
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
                    print(f"[Telegram Service] Verification code successfully sent to chat {chat_id}")
                    return True
                else:
                    print(f"[Telegram Error] Verification Bot API response failed: {res_body}. Falling back to mock log.", file=sys.stderr)
        except Exception as e:
            print(f"[Telegram Error] Verification Network delivery failed to {chat_id}: {e}. Falling back to mock log.", file=sys.stderr)
            
    # Fallback/Mock Mode: write to mock_telegram_delivery.log file
    try:
        os.makedirs(os.path.dirname(MOCK_TELEGRAM_LOG), exist_ok=True)
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        log_entry = f"[{timestamp}] TO CHAT_ID: {chat_id} (VERIFICATION)\nMESSAGE:\n{formatted_msg}\n{'-'*60}\n"
        with open(MOCK_TELEGRAM_LOG, "a", encoding="utf-8") as f:
            f.write(log_entry)
        print(f"[Telegram Service] Mock telegram verification code logged to {MOCK_TELEGRAM_LOG}")
        return True
    except Exception as err:
        print(f"[Telegram Error] Failed writing mock telegram verification log: {err}", file=sys.stderr)
        return False
