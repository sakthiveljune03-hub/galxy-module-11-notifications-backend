from unittest.mock import Mock

import pytest

from app.services.email_delivery_service import (
    _build_body,
    deliver_email,
    send_admin_new_order_alert,
    send_general_notification_email,
    send_order_received_email,
    send_order_status_changed_email,
)


class TestBuildBody:
    def test_order_received_template(self):
        data = {
            "customer_name": "Test User",
            "order_number": "GLX-2026-00001",
            "estimated_total": "1,500",
            "dashboard_url": "https://galxy.in/dashboard",
        }
        subject, body = _build_body("order_received", data)
        assert "GLX-2026-00001" in subject
        assert "Test User" in body
        assert "1,500" in body
        assert "#FF2E8A" in body

    def test_order_status_changed_with_note(self):
        data = {
            "customer_name": "Test User",
            "order_number": "GLX-2026-00001",
            "status_label": "In Production",
            "note": "Your design is being cut",
            "dashboard_url": "https://galxy.in/dashboard",
        }
        subject, body = _build_body("order_status_changed", data)
        assert "In Production" in subject
        assert "Your design is being cut" in body

    def test_order_status_changed_without_note(self):
        data = {
            "customer_name": "Test User",
            "order_number": "GLX-2026-00001",
            "status_label": "Delivered",
            "note": "",
            "dashboard_url": "https://galxy.in/dashboard",
        }
        subject, body = _build_body("order_status_changed", data)
        assert "Delivered" in subject
        assert 'style="color:#9B5CFF;font-style:italic;"' not in body

    def test_unknown_template_falls_back_to_general(self):
        data = {"subject": "Hello", "message": "Fallback message"}
        subject, body = _build_body("nonexistent_key", data)
        assert subject == "Hello"
        assert "Fallback message" in body


class TestDeliverEmail:
    def test_success_returns_true(self, mock_smtp_sender):
        result = deliver_email(
            "user@test.com", "general",
            {"subject": "Hi", "message": "Hello"}, mock_smtp_sender
        )
        assert result is True
        mock_smtp_sender.assert_called_once()

    def test_failure_returns_false(self, mock_smtp_sender):
        mock_smtp_sender.side_effect = Exception("SMTP down")
        result = deliver_email(
            "user@test.com", "general",
            {"subject": "Hi", "message": "Hello"}, mock_smtp_sender
        )
        assert result is False

    def test_failure_never_raises(self, mock_smtp_sender):
        mock_smtp_sender.side_effect = Exception("SMTP down")
        try:
            deliver_email(
                "user@test.com", "general",
                {"subject": "Hi", "message": "Hello"}, mock_smtp_sender
            )
        except Exception:
            pytest.fail("deliver_email raised on failure")


class TestSendOrderReceivedEmail:
    def test_sends_correct_template(self, mock_smtp_sender):
        result = send_order_received_email(
            user_email="cust@test.com",
            customer_name="Ravi",
            order_number="GLX-2026-00042",
            estimated_total=2500.0,
            dashboard_url="https://galxy.in/orders/GLX-2026-00042",
            smtp_sender=mock_smtp_sender,
        )
        assert result is True
        mock_smtp_sender.assert_called_once()
        call_kwargs = mock_smtp_sender.call_args[1]
        assert "GLX-2026-00042" in call_kwargs["subject"]
        assert "Ravi" in call_kwargs["body_html"]

    def test_smtp_failure_returns_false(self, mock_smtp_sender):
        mock_smtp_sender.side_effect = Exception("Connection refused")
        result = send_order_received_email(
            user_email="cust@test.com",
            customer_name="Ravi",
            order_number="GLX-2026-00042",
            estimated_total=2500.0,
            dashboard_url="https://galxy.in/orders/GLX-2026-00042",
            smtp_sender=mock_smtp_sender,
        )
        assert result is False


class TestSendOrderStatusChangedEmail:
    def test_sends_with_note(self, mock_smtp_sender):
        result = send_order_status_changed_email(
            user_email="cust@test.com",
            customer_name="Ravi",
            order_number="GLX-2026-00042",
            new_status="in_production",
            note="Cutting the acrylic now",
            dashboard_url="https://galxy.in/orders/GLX-2026-00042",
            smtp_sender=mock_smtp_sender,
        )
        assert result is True
        call_kwargs = mock_smtp_sender.call_args[1]
        assert "In Production" in call_kwargs["subject"]
        assert "Cutting the acrylic now" in call_kwargs["body_html"]

    def test_sends_without_note(self, mock_smtp_sender):
        result = send_order_status_changed_email(
            user_email="cust@test.com",
            customer_name="Ravi",
            order_number="GLX-2026-00042",
            new_status="delivered",
            note=None,
            dashboard_url="https://galxy.in/orders/GLX-2026-00042",
            smtp_sender=mock_smtp_sender,
        )
        assert result is True
        call_kwargs = mock_smtp_sender.call_args[1]
        assert "Delivered" in call_kwargs["subject"]


class TestSendGeneralNotification:
    def test_sends_general(self, mock_smtp_sender):
        result = send_general_notification_email(
            to="user@test.com",
            subject="Special Offer",
            message="20% off on neon boards!",
            smtp_sender=mock_smtp_sender,
        )
        assert result is True
        call_kwargs = mock_smtp_sender.call_args[1]
        assert call_kwargs["subject"] == "Special Offer"


class TestSendAdminNewOrderAlert:
    def test_sends_admin_alert(self, mock_smtp_sender):
        result = send_admin_new_order_alert(
            admin_email="asil@galxy.in",
            customer_name="Ravi",
            customer_email="ravi@test.com",
            order_number="GLX-2026-00042",
            estimated_total=3500.0,
            admin_url="https://galxy.in/admin/orders/GLX-2026-00042",
            smtp_sender=mock_smtp_sender,
        )
        assert result is True
        call_kwargs = mock_smtp_sender.call_args[1]
        assert "NEW ORDER" in call_kwargs["subject"]
        assert "Ravi" in call_kwargs["body_html"]

    def test_admin_alert_failure_does_not_raise(self, mock_smtp_sender):
        mock_smtp_sender.side_effect = Exception("SMTP timeout")
        try:
            send_admin_new_order_alert(
                admin_email="asil@galxy.in",
                customer_name="Ravi",
                customer_email="ravi@test.com",
                order_number="GLX-2026-00042",
                estimated_total=3500.0,
                admin_url="https://galxy.in/admin/orders/GLX-2026-00042",
                smtp_sender=mock_smtp_sender,
            )
        except Exception:
            pytest.fail("Admin alert raised on SMTP failure")


class TestCombinedCustomerAndAdminFlow:
    def test_order_received_triggers_both_customer_and_admin(self):
        customer_smtp = Mock()
        admin_smtp = Mock()
        result_customer = send_order_received_email(
            user_email="cust@test.com",
            customer_name="Ravi",
            order_number="GLX-2026-00042",
            estimated_total=2500.0,
            dashboard_url="https://galxy.in/dashboard",
            smtp_sender=customer_smtp,
        )
        result_admin = send_admin_new_order_alert(
            admin_email="asil@galxy.in",
            customer_name="Ravi",
            customer_email="ravi@test.com",
            order_number="GLX-2026-00042",
            estimated_total=2500.0,
            admin_url="https://galxy.in/admin/orders/GLX-2026-00042",
            smtp_sender=admin_smtp,
        )
        assert result_customer is True
        assert result_admin is True
        customer_smtp.assert_called_once()
        admin_smtp.assert_called_once()
        assert "GLX-2026-00042" in customer_smtp.call_args[1]["subject"]
        assert "NEW ORDER" in admin_smtp.call_args[1]["subject"]


class TestMalformedEstimatedTotal:
    def test_non_numeric_does_not_raise(self, mock_smtp_sender):
        try:
            send_order_received_email(
                user_email="cust@test.com",
                customer_name="Ravi",
                order_number="GLX-2026-00042",
                estimated_total="not-a-number",
                dashboard_url="https://galxy.in/dashboard",
                smtp_sender=mock_smtp_sender,
            )
        except Exception:
            pytest.fail("send_order_received_email raised on non-numeric estimated_total")

    def test_none_estimated_total_does_not_raise(self, mock_smtp_sender):
        try:
            send_order_received_email(
                user_email="cust@test.com",
                customer_name="Ravi",
                order_number="GLX-2026-00042",
                estimated_total=None,
                dashboard_url="https://galxy.in/dashboard",
                smtp_sender=mock_smtp_sender,
            )
        except Exception:
            pytest.fail("send_order_received_email raised on None estimated_total")

    def test_admin_alert_non_numeric_does_not_raise(self, mock_smtp_sender):
        try:
            send_admin_new_order_alert(
                admin_email="asil@galxy.in",
                customer_name="Ravi",
                customer_email="ravi@test.com",
                order_number="GLX-2026-00042",
                estimated_total="bad-input",
                admin_url="https://galxy.in/admin",
                smtp_sender=mock_smtp_sender,
            )
        except Exception:
            pytest.fail("send_admin_new_order_alert raised on non-numeric estimated_total")

    def test_non_numeric_still_calls_smtp_with_fallback(self, mock_smtp_sender):
        send_order_received_email(
            user_email="cust@test.com",
            customer_name="Ravi",
            order_number="GLX-2026-00042",
            estimated_total="bad-input",
            dashboard_url="https://galxy.in/dashboard",
            smtp_sender=mock_smtp_sender,
        )
        mock_smtp_sender.assert_called_once()
        call_kwargs = mock_smtp_sender.call_args[1]
        assert "bad-input" in call_kwargs["body_html"]


class TestSubjectSanitization:
    def test_crlf_stripped_from_customer_name(self, mock_smtp_sender):
        send_order_received_email(
            user_email="cust@test.com",
            customer_name="Ravi\r\nCc: attacker@evil.com",
            order_number="GLX-2026-00042",
            estimated_total=2500.0,
            dashboard_url="https://galxy.in/dashboard",
            smtp_sender=mock_smtp_sender,
        )
        call_kwargs = mock_smtp_sender.call_args[1]
        assert "\r" not in call_kwargs["subject"]
        assert "\n" not in call_kwargs["subject"]

    def test_crlf_stripped_from_order_number(self, mock_smtp_sender):
        send_order_received_email(
            user_email="cust@test.com",
            customer_name="Ravi",
            order_number="GLX-2026-00042\r\nEvil",
            estimated_total=2500.0,
            dashboard_url="https://galxy.in/dashboard",
            smtp_sender=mock_smtp_sender,
        )
        call_kwargs = mock_smtp_sender.call_args[1]
        assert "\r" not in call_kwargs["subject"]
        assert "\n" not in call_kwargs["subject"]

    def test_crlf_stripped_from_status_label(self, mock_smtp_sender):
        send_order_status_changed_email(
            user_email="cust@test.com",
            customer_name="Ravi",
            order_number="GLX-2026-00042",
            new_status="in_production",
            note="Cutting now",
            dashboard_url="https://galxy.in/dashboard",
            smtp_sender=mock_smtp_sender,
        )
        call_kwargs = mock_smtp_sender.call_args[1]
        assert "\r" not in call_kwargs["subject"]
        assert "\n" not in call_kwargs["subject"]

    def test_body_html_still_contains_raw_values(self, mock_smtp_sender):
        send_order_received_email(
            user_email="cust@test.com",
            customer_name="Ravi & Sons",
            order_number="GLX-2026-00042",
            estimated_total=2500.0,
            dashboard_url="https://galxy.in/dashboard",
            smtp_sender=mock_smtp_sender,
        )
        call_kwargs = mock_smtp_sender.call_args[1]
        assert "Ravi &amp; Sons" in call_kwargs["body_html"]


class TestFireAndForgetContract:
    def test_failed_send_never_fails_calling_operation(self, mock_smtp_sender):
        mock_smtp_sender.side_effect = Exception("SMTP crashed")
        result = deliver_email(
            "user@test.com", "order_received",
            {
                "customer_name": "Test",
                "order_number": "GLX-2026-00001",
                "estimated_total": "1,000",
                "dashboard_url": "https://galxy.in/dashboard",
            },
            mock_smtp_sender,
        )
        assert result is False


class TestSendEmailFlagBehavior:
    def test_review_approved_send_email_false_triggers_no_email_via_notify(
        self, mock_smtp_sender, mock_subscriptions_collection
    ):
        from app.services.notification_service import notify_user

        result = notify_user(
            event_type="order_received",
            recipient={
                "user_id": "user1",
                "email": "cust@test.com",
                "name": "Ravi",
            },
            event_data={
                "order_number": "GLX-2026-00042",
                "estimated_total": 2500.0,
            },
            smtp_sender=mock_smtp_sender,
            subscriptions_collection=mock_subscriptions_collection,
            send_email=False,
        )
        assert result["email"] is False
        mock_smtp_sender.assert_not_called()

    def test_send_email_true_triggers_email_delivery(self, mock_smtp_sender):
        from app.services.notification_service import notify_user

        result = notify_user(
            event_type="general",
            recipient={"email": "cust@test.com", "name": "Ravi", "user_id": "user1"},
            event_data={"subject": "Test", "message": "Hello"},
            smtp_sender=mock_smtp_sender,
            subscriptions_collection=None,
            send_email=True,
            send_telegram=False,
        )
        assert result["email"] is True
        mock_smtp_sender.assert_called_once()
