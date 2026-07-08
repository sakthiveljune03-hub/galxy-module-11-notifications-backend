import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from unittest.mock import Mock
from app.services.email_delivery_service import (
    _build_body,
    send_order_received_email,
    send_admin_new_order_alert,
)
from app.services.telegram_delivery_service import (
    _build_message,
    send_telegram_message,
    send_admin_new_order_alert_telegram,
)

print("=" * 60)
print("MODULE 11 — NOTIFICATION SERVICES VERIFICATION")
print("=" * 60)

print("\n--- 1. Email Template Building ---")
subject, body = _build_body("order_received", {
    "customer_name": "Ravi",
    "order_number": "GLX-2026-00042",
    "estimated_total": "2,500",
    "dashboard_url": "https://galxy.in/dashboard",
})
print(f"Subject: {subject}")
print(f"Body HTML: {body[:120]}...")

print("\n--- 2. Order Status Email (with note) ---")
subject, body = _build_body("order_status_changed", {
    "customer_name": "Ravi",
    "order_number": "GLX-2026-00042",
    "status_label": "In Production",
    "note": "Cutting the acrylic now",
    "dashboard_url": "https://galxy.in/dashboard",
})
print(f"Subject: {subject}")
print(f"Has note block: {'Cutting the acrylic now' in body}")

print("\n--- 3. Order Status Email (without note) ---")
subject, body = _build_body("order_status_changed", {
    "customer_name": "Ravi",
    "order_number": "GLX-2026-00042",
    "status_label": "Delivered",
    "note": "",
    "dashboard_url": "https://galxy.in/dashboard",
})
print(f"Subject: {subject}")
print(f"Has italic block: {'color:#9B5CFF' in body}")

print("\n--- 4. Admin New Order Alert ---")
subject, body = _build_body("admin_new_order_alert", {
    "customer_name": "Ravi",
    "customer_email": "ravi@test.com",
    "order_number": "GLX-2026-00042",
    "estimated_total": "3,500",
    "admin_url": "https://galxy.in/admin/orders/GLX-2026-00042",
})
print(f"Subject: {subject}")

print("\n--- 5. Email Delivery (Mock SMTP) ---")
smtp = Mock()
result = send_order_received_email(
    user_email="cust@test.com",
    customer_name="Ravi",
    order_number="GLX-2026-00042",
    estimated_total=2500.0,
    dashboard_url="https://galxy.in/dashboard",
    smtp_sender=smtp,
)
print(f"Email sent: {result}")
print(f"SMTP called: {smtp.called}")
if smtp.called:
    print(f"To: {smtp.call_args[1]['to']}")
    print(f"Subject: {smtp.call_args[1]['subject']}")

print("\n--- 6. Admin Email Alert ---")
admin_smtp = Mock()
result = send_admin_new_order_alert(
    admin_email="asil@galxy.in",
    customer_name="Ravi",
    customer_email="ravi@test.com",
    order_number="GLX-2026-00042",
    estimated_total=3500.0,
    admin_url="https://galxy.in/admin/orders/GLX-2026-00042",
    smtp_sender=admin_smtp,
)
print(f"Admin alert sent: {result}")
print(f"Subject: {admin_smtp.call_args[1]['subject']}")

print("\n--- 7. SMTP Failure (Fire-and-Forget) ---")
broken_smtp = Mock(side_effect=Exception("SMTP connection refused"))
result = send_order_received_email(
    user_email="cust@test.com",
    customer_name="Ravi",
    order_number="GLX-2026-00042",
    estimated_total=2500.0,
    dashboard_url="https://galxy.in/dashboard",
    smtp_sender=broken_smtp,
)
print(f"Returned on failure: {result} (not crashed)")

print("\n--- 8. Telegram Template Building ---")
msg = _build_message("order_received", {
    "customer_name": "Ravi",
    "order_number": "GLX-2026-00042",
    "estimated_total": "2,500",
})
print(f"Telegram message:\n{msg}")

print("\n--- 9. Telegram Status (with note) ---")
msg = _build_message("order_status_changed", {
    "customer_name": "Ravi",
    "order_number": "GLX-2026-00042",
    "status_label": "In Production",
    "note": "Cutting now",
})
print(f"Telegram message:\n{msg}")

print("\n--- 10. Telegram Admin Alert (check env var gate) ---")
os.environ["TELEGRAM_BOT_TOKEN"] = "test:token"
os.environ["TELEGRAM_ADMIN_CHAT_ID"] = "admin123"
os.environ["TELEGRAM_API_BASE_URL"] = "https://api.telegram.org"
import importlib
import app.services.telegram_delivery_service as tg
importlib.reload(tg)

result = tg.send_admin_new_order_alert_telegram(
    customer_name="Ravi",
    customer_email="ravi@test.com",
    order_number="GLX-2026-00042",
    estimated_total=3500.0,
)
print(f"Telegram admin alert attempted: {result}")
print("(Actual send skipped — Telegram API not reachable in this env)")

print("\n" + "=" * 60)
print("ALL VERIFICATION CHECKS COMPLETE")
print("=" * 60)
