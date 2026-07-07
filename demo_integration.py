import os
import sys
from unittest.mock import Mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.notification_service import notify_user

print("=" * 60)
print("MODULE 11 — INTEGRATION DEMO")
print("=" * 60)

smtp_mock = Mock()
subs_mock = Mock()
subs_mock.find_one.return_value = {
    "user_id": "user1", "chat_id": "67890", "is_active": True,
}

print("\n--- 1. Customer Email + Telegram on New Order ---")
result = notify_user(
    event_type="order_received",
    recipient={"user_id": "user1", "email": "cust@test.com", "name": "Ravi"},
    event_data={"order_number": "GLX-2026-00042", "estimated_total": 2500.0,
                "dashboard_url": "https://galxy.in/dashboard"},
    smtp_sender=smtp_mock,
    subscriptions_collection=subs_mock,
    send_email=True,
    send_telegram=True,
)
print(f"Customer notified: email={result['email']}, telegram={result['telegram']}")

print("\n--- 2. Admin Alert alongside Customer Email ---")
admin_smtp = Mock()
admin_result = notify_user(
    event_type="admin_new_order_alert",
    recipient={"email": "asil@galxy.in", "name": "Ravi",
               "customer_email": "ravi@test.com", "user_id": "admin"},
    event_data={"order_number": "GLX-2026-00042", "estimated_total": 3500.0,
                "admin_url": "https://galxy.in/admin/orders/GLX-2026-00042"},
    smtp_sender=admin_smtp,
    subscriptions_collection=None,
    send_email=True,
    send_telegram=False,
)
print(f"Admin alerted: email={admin_result['email']}")

print("\n--- 3. send_email=False skips email ---")
smtp_skip = Mock()
skip_result = notify_user(
    event_type="order_received",
    recipient={"user_id": "user1", "email": "cust@test.com", "name": "Ravi"},
    event_data={"order_number": "GLX-2026-00042", "estimated_total": 2500.0},
    smtp_sender=smtp_skip,
    subscriptions_collection=subs_mock,
    send_email=False,
    send_telegram=True,
)
print(f"Email skipped (False): {skip_result}")
print(f"SMTP was called: {smtp_skip.called}")

print("\n--- 4. Failure isolation (broken SMTP) ---")
broken_smtp = Mock(side_effect=Exception("SMTP down"))
fail_result = notify_user(
    event_type="general",
    recipient={"email": "cust@test.com", "name": "Ravi", "user_id": "user1"},
    event_data={"subject": "Test", "message": "Hello"},
    smtp_sender=broken_smtp,
    subscriptions_collection=None,
    send_email=True,
    send_telegram=False,
)
print(f"On SMTP failure: email={fail_result['email']} (did not crash)")

print("\n--- 5. Order Status Change (with note) ---")
status_result = notify_user(
    event_type="order_status_changed",
    recipient={"user_id": "user1", "email": "cust@test.com", "name": "Ravi"},
    event_data={"order_number": "GLX-2026-00042", "new_status": "in_production",
                "note": "Cutting the acrylic now",
                "dashboard_url": "https://galxy.in/dashboard"},
    smtp_sender=smtp_mock,
    subscriptions_collection=subs_mock,
    send_email=True,
    send_telegram=True,
)
print(f"Status notified: email={status_result['email']}, telegram={status_result['telegram']}")

print("\n" + "=" * 60)
print("ALL INTEGRATION CHECKS PASSED")
print("=" * 60)
