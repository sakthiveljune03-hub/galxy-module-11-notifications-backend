from unittest.mock import Mock, patch

import pytest

from app.services.notification_service import (
    _dispatch_email,
    _dispatch_telegram,
    notify_user,
)


class TestNotifyUser:
    @patch("app.services.notification_service._dispatch_email", return_value=True)
    @patch("app.services.notification_service._dispatch_telegram", return_value=True)
    def test_both_channels_succeed(self, mock_tg, mock_email):
        result = notify_user(
            event_type="order_received",
            recipient={"user_id": "u1", "email": "a@b.com", "name": "Test"},
            event_data={"order_number": "O-1", "estimated_total": 100},
            smtp_sender=Mock(),
            subscriptions_collection=Mock(),
            send_email=True,
            send_telegram=True,
        )
        assert result == {"email": True, "telegram": True}
        mock_email.assert_called_once()
        mock_tg.assert_called_once()

    @patch("app.services.notification_service._dispatch_email", return_value=False)
    @patch("app.services.notification_service._dispatch_telegram", return_value=True)
    def test_email_fails_telegram_succeeds_channel_isolation(self, mock_tg, mock_email):
        result = notify_user(
            event_type="order_received",
            recipient={"user_id": "u1", "email": "a@b.com", "name": "Test"},
            event_data={"order_number": "O-1"},
            smtp_sender=Mock(),
            subscriptions_collection=Mock(),
        )
        assert result == {"email": False, "telegram": True}

    @patch("app.services.notification_service._dispatch_email", return_value=True)
    @patch("app.services.notification_service._dispatch_telegram", return_value=False)
    def test_telegram_fails_email_succeeds_channel_isolation(self, mock_tg, mock_email):
        result = notify_user(
            event_type="order_received",
            recipient={"user_id": "u1", "email": "a@b.com", "name": "Test"},
            event_data={"order_number": "O-1"},
            smtp_sender=Mock(),
            subscriptions_collection=Mock(),
        )
        assert result == {"email": True, "telegram": False}

    @patch("app.services.notification_service._dispatch_email")
    @patch("app.services.notification_service._dispatch_telegram")
    def test_send_email_false_skips_email(self, mock_tg, mock_email):
        result = notify_user(
            event_type="order_received",
            recipient={"user_id": "u1", "email": "a@b.com", "name": "Test"},
            event_data={"order_number": "O-1"},
            smtp_sender=Mock(),
            subscriptions_collection=Mock(),
            send_email=False,
            send_telegram=True,
        )
        assert result == {"email": False, "telegram": mock_tg.return_value}
        mock_email.assert_not_called()
        mock_tg.assert_called_once()

    @patch("app.services.notification_service._dispatch_email")
    @patch("app.services.notification_service._dispatch_telegram")
    def test_send_telegram_false_skips_telegram(self, mock_tg, mock_email):
        result = notify_user(
            event_type="order_received",
            recipient={"user_id": "u1", "email": "a@b.com", "name": "Test"},
            event_data={"order_number": "O-1"},
            smtp_sender=Mock(),
            subscriptions_collection=Mock(),
            send_email=True,
            send_telegram=False,
        )
        assert result == {"email": mock_email.return_value, "telegram": False}
        mock_email.assert_called_once()
        mock_tg.assert_not_called()

    @patch("app.services.notification_service._dispatch_email")
    @patch("app.services.notification_service._dispatch_telegram")
    def test_both_flags_false_dispatches_nothing(self, mock_tg, mock_email):
        result = notify_user(
            event_type="order_received",
            recipient={"user_id": "u1", "email": "a@b.com", "name": "Test"},
            event_data={"order_number": "O-1"},
            smtp_sender=Mock(),
            subscriptions_collection=Mock(),
            send_email=False,
            send_telegram=False,
        )
        assert result == {"email": False, "telegram": False}
        mock_email.assert_not_called()
        mock_tg.assert_not_called()

    def test_smtp_sender_none_skips_email(self):
        with patch(
            "app.services.notification_service._dispatch_telegram",
            return_value=True,
        ) as mock_tg:
            result = notify_user(
                event_type="order_received",
                recipient={"user_id": "u1", "email": "a@b.com", "name": "Test"},
                event_data={"order_number": "O-1"},
                smtp_sender=None,
                subscriptions_collection=Mock(),
                send_email=True,
                send_telegram=True,
            )
        assert result == {"email": False, "telegram": True}
        mock_tg.assert_called_once()

    def test_subscriptions_collection_none_skips_telegram(self):
        with patch(
            "app.services.notification_service._dispatch_email",
            return_value=True,
        ) as mock_email:
            result = notify_user(
                event_type="order_received",
                recipient={"user_id": "u1", "email": "a@b.com", "name": "Test"},
                event_data={"order_number": "O-1"},
                smtp_sender=Mock(),
                subscriptions_collection=None,
                send_email=True,
                send_telegram=True,
            )
        assert result == {"email": True, "telegram": False}
        mock_email.assert_called_once()

    @patch("app.services.notification_service._dispatch_email", return_value=False)
    @patch("app.services.notification_service._dispatch_telegram", return_value=False)
    def test_unknown_event_type_returns_false(self, mock_tg, mock_email):
        result = notify_user(
            event_type="unknown_event",
            recipient={"user_id": "u1", "email": "a@b.com", "name": "Test"},
            event_data={},
            smtp_sender=Mock(),
            subscriptions_collection=Mock(),
        )
        assert result == {"email": False, "telegram": False}

    def test_missing_recipient_key_does_not_raise(self):
        result = notify_user(
            event_type="order_received",
            recipient={},
            event_data={"order_number": "O-1"},
            smtp_sender=Mock(),
            subscriptions_collection=Mock(),
        )
        assert result == {"email": False, "telegram": False}


class TestDispatchEmail:
    def test_order_received(self):
        smtp = Mock(return_value=True)
        with patch(
            "app.services.notification_service.send_order_received_email",
            return_value=True,
        ) as mock_svc:
            result = _dispatch_email(
                "order_received",
                {"email": "a@b.com", "name": "Test"},
                {"order_number": "O-1", "estimated_total": 100},
                smtp,
            )
        assert result is True
        mock_svc.assert_called_once_with(
            user_email="a@b.com",
            customer_name="Test",
            order_number="O-1",
            estimated_total=100,
            dashboard_url="",
            smtp_sender=smtp,
        )

    def test_order_status_changed(self):
        smtp = Mock()
        with patch(
            "app.services.notification_service.send_order_status_changed_email",
            return_value=True,
        ) as mock_svc:
            result = _dispatch_email(
                "order_status_changed",
                {"email": "a@b.com", "name": "Test"},
                {"order_number": "O-1", "new_status": "in_production", "note": "cutting"},
                smtp,
            )
        assert result is True
        mock_svc.assert_called_once()

    def test_admin_new_order_alert(self):
        smtp = Mock()
        with patch(
            "app.services.notification_service.send_admin_new_order_alert",
            return_value=True,
        ) as mock_svc:
            result = _dispatch_email(
                "admin_new_order_alert",
                {"email": "admin@galxy.in", "name": "Ravi", "customer_email": "r@t.com"},
                {"order_number": "O-1", "estimated_total": 500, "admin_url": "https://galxy.in/admin"},
                smtp,
            )
        assert result is True
        mock_svc.assert_called_once()

    def test_general(self):
        smtp = Mock()
        with patch(
            "app.services.notification_service.send_general_notification_email",
            return_value=True,
        ) as mock_svc:
            result = _dispatch_email(
                "general",
                {"email": "a@b.com", "name": "Test"},
                {"subject": "Hi", "message": "Hello"},
                smtp,
            )
        assert result is True
        mock_svc.assert_called_once_with(
            to="a@b.com",
            subject="Hi",
            message="Hello",
            smtp_sender=smtp,
        )

    def test_unknown_event_type(self):
        result = _dispatch_email("nonexistent", {"email": "a@b.com"}, {}, Mock())
        assert result is False

    def test_missing_key_caught_and_returns_false(self):
        result = _dispatch_email("order_received", {}, {}, Mock())
        assert result is False


class TestDispatchTelegram:
    def test_order_received(self):
        subs = Mock()
        with patch(
            "app.services.notification_service.send_order_received_telegram",
            return_value=True,
        ) as mock_svc:
            result = _dispatch_telegram(
                "order_received",
                {"user_id": "u1", "name": "Test"},
                {"order_number": "O-1", "estimated_total": 100},
                subs,
            )
        assert result is True
        mock_svc.assert_called_once_with(
            user_id="u1",
            customer_name="Test",
            order_number="O-1",
            estimated_total=100,
            subscriptions_collection=subs,
        )

    def test_order_status_changed(self):
        subs = Mock()
        with patch(
            "app.services.notification_service.send_order_status_changed_telegram",
            return_value=True,
        ) as mock_svc:
            result = _dispatch_telegram(
                "order_status_changed",
                {"user_id": "u1", "name": "Test"},
                {"order_number": "O-1", "new_status": "delivered"},
                subs,
            )
        assert result is True
        mock_svc.assert_called_once()

    def test_admin_new_order_alert(self):
        with patch(
            "app.services.notification_service.send_admin_new_order_alert_telegram",
            return_value=True,
        ) as mock_svc:
            result = _dispatch_telegram(
                "admin_new_order_alert",
                {"name": "Ravi", "customer_email": "r@t.com"},
                {"order_number": "O-1", "estimated_total": 500},
                None,
            )
        assert result is True
        mock_svc.assert_called_once_with(
            customer_name="Ravi",
            customer_email="r@t.com",
            order_number="O-1",
            estimated_total=500,
        )

    def test_unknown_event_type(self):
        result = _dispatch_telegram("nonexistent", {}, {}, Mock())
        assert result is False

    def test_missing_user_id_caught_and_returns_false(self):
        result = _dispatch_telegram(
            "order_received", {"name": "Test"}, {"order_number": "O-1"}, Mock()
        )
        assert result is False
