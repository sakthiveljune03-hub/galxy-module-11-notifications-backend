from unittest.mock import Mock, patch

import pytest

from app.services.telegram_delivery_service import (
    _build_message,
    _get_config,
    _escape_markdown_v2,
    _truncate,
    deliver_telegram,
    get_user_chat_id,
    send_admin_new_order_alert_telegram,
    send_order_received_telegram,
    send_order_status_changed_telegram,
    send_telegram_message,
    send_telegram_notification,
)


class TestBuildMessage:
    def test_order_received(self):
        data = {
            "customer_name": "Ravi",
            "order_number": "GLX-2026-00042",
            "estimated_total": "2,500",
        }
        msg = _build_message("order_received", data)
        assert "Order Received" in msg
        assert "Ravi" in msg
        assert _escape_markdown_v2("GLX-2026-00042") in msg
        assert _escape_markdown_v2("2,500") in msg

    def test_order_status_changed_with_note(self):
        data = {
            "customer_name": "Ravi",
            "order_number": "GLX-2026-00042",
            "status_label": "In Production",
            "note": "We started cutting",
        }
        msg = _build_message("order_status_changed", data)
        assert "In Production" in msg
        assert "We started cutting" in msg

    def test_order_status_changed_without_note(self):
        data = {
            "customer_name": "Ravi",
            "order_number": "GLX-2026-00042",
            "status_label": "Delivered",
            "note": "",
        }
        msg = _build_message("order_status_changed", data)
        assert "Delivered" in msg
        assert "Note:" not in msg

    def test_admin_new_order_alert(self):
        data = {
            "customer_name": "Ravi",
            "customer_email": "ravi@test.com",
            "order_number": "GLX-2026-00042",
            "estimated_total": "2,500",
        }
        msg = _build_message("admin_new_order_alert", data)
        assert "NEW ORDER" in msg
        assert "Ravi" in msg
        assert "ravi" in msg
        assert _escape_markdown_v2("@test.com") in msg

    def test_unknown_template_falls_back_to_general(self):
        msg = _build_message("nonexistent", {"message": "Fallback"})
        assert msg == "Fallback"


class TestSendTelegramMessage:
    @patch(
        "app.services.telegram_delivery_service._get_config",
        return_value={"bot_token": "test-token", "admin_chat_id": "admin123", "api_base_url": "https://api.telegram.org"},
    )
    @patch("app.services.telegram_delivery_service.requests.post")
    def test_success(self, mock_post, mock_config):
        mock_post.return_value.json.return_value = {"ok": True}
        mock_post.return_value.raise_for_status = Mock()
        result = send_telegram_message("12345", "Test message")
        assert result is True
        mock_post.assert_called_once()

    @patch(
        "app.services.telegram_delivery_service._get_config",
        return_value={"bot_token": "test-token", "admin_chat_id": "admin123", "api_base_url": "https://api.telegram.org"},
    )
    @patch("app.services.telegram_delivery_service.requests.post")
    def test_api_returns_not_ok(self, mock_post, mock_config):
        mock_post.return_value.json.return_value = {
            "ok": False, "error_code": 400
        }
        mock_post.return_value.raise_for_status = Mock()
        result = send_telegram_message("12345", "Test")
        assert result is False

    @patch(
        "app.services.telegram_delivery_service._get_config",
        return_value={"bot_token": "test-token", "admin_chat_id": "admin123", "api_base_url": "https://api.telegram.org"},
    )
    @patch("app.services.telegram_delivery_service.requests.post")
    def test_network_failure_returns_false(self, mock_post, mock_config):
        mock_post.side_effect = Exception("Network error")
        result = send_telegram_message("12345", "Test")
        assert result is False

    @patch(
        "app.services.telegram_delivery_service._get_config",
        return_value={"bot_token": "", "admin_chat_id": "", "api_base_url": "https://api.telegram.org"},
    )
    def test_missing_token_returns_false(self, mock_config):
        result = send_telegram_message("12345", "Test")
        assert result is False


class TestGetUserChatId:
    def test_found_active_subscription(self):
        collection = Mock()
        collection.find_one.return_value = {
            "user_id": "user1", "chat_id": "67890", "is_active": True,
        }
        chat_id = get_user_chat_id("user1", collection)
        assert chat_id == "67890"
        collection.find_one.assert_called_once_with(
            {"user_id": "user1", "is_active": True},
            sort=[("created_at", -1)]
        )

    def test_no_subscription_returns_none(self):
        collection = Mock()
        collection.find_one.return_value = None
        chat_id = get_user_chat_id("user1", collection)
        assert chat_id is None

    def test_db_error_returns_none(self):
        collection = Mock()
        collection.find_one.side_effect = Exception("DB timeout")
        chat_id = get_user_chat_id("user1", collection)
        assert chat_id is None


class TestDeliverTelegram:
    def test_with_subscription_sends_message(self, mock_subscriptions_collection):
        with patch(
            "app.services.telegram_delivery_service.send_telegram_message",
            return_value=True,
        ) as mock_send:
            result = deliver_telegram(
                "user1", "general",
                {"message": "Hello"}, mock_subscriptions_collection
            )
            assert result is True
            mock_send.assert_called_once_with("67890", "Hello")

    def test_without_subscription_skips(self):
        collection = Mock()
        collection.find_one.return_value = None
        with patch(
            "app.services.telegram_delivery_service.send_telegram_message"
        ) as mock_send:
            result = deliver_telegram(
                "user1", "general",
                {"message": "Hello"}, collection
            )
            assert result is False
            mock_send.assert_not_called()

    def test_failure_returns_false(self):
        collection = Mock()
        collection.find_one.side_effect = Exception("DB error")
        result = deliver_telegram(
            "user1", "general",
            {"message": "Hello"}, collection
        )
        assert result is False


class TestSendOrderReceivedTelegram:
    def test_sends(self, mock_subscriptions_collection):
        with patch(
            "app.services.telegram_delivery_service.send_telegram_message",
            return_value=True,
        ) as mock_send:
            result = send_order_received_telegram(
                user_id="user1",
                customer_name="Ravi",
                order_number="GLX-2026-00042",
                estimated_total=2500.0,
                subscriptions_collection=mock_subscriptions_collection,
            )
            assert result is True
            sent_text = mock_send.call_args[0][1]
            assert _escape_markdown_v2("GLX-2026-00042") in sent_text
            assert "Ravi" in sent_text


class TestSendOrderStatusChangedTelegram:
    def test_sends_with_note(self, mock_subscriptions_collection):
        with patch(
            "app.services.telegram_delivery_service.send_telegram_message",
            return_value=True,
        ) as mock_send:
            result = send_order_status_changed_telegram(
                user_id="user1",
                customer_name="Ravi",
                order_number="GLX-2026-00042",
                new_status="in_production",
                note="Cutting the acrylic",
                subscriptions_collection=mock_subscriptions_collection,
            )
            assert result is True
            sent_text = mock_send.call_args[0][1]
            assert "In Production" in sent_text
            assert "Cutting the acrylic" in sent_text


class TestSendAdminNewOrderAlertTelegram:
    @patch(
        "app.services.telegram_delivery_service._get_config",
        return_value={"bot_token": "test-token", "admin_chat_id": "admin123", "api_base_url": "https://api.telegram.org"},
    )
    @patch(
        "app.services.telegram_delivery_service.send_telegram_message",
        return_value=True,
    )
    def test_sends_alert(self, mock_send, mock_config):
        result = send_admin_new_order_alert_telegram(
            customer_name="Ravi",
            customer_email="ravi@test.com",
            order_number="GLX-2026-00042",
            estimated_total=3500.0,
        )
        assert result is True
        assert mock_send.call_args[0][0] == "admin123"

    @patch(
        "app.services.telegram_delivery_service._get_config",
        return_value={"bot_token": "", "admin_chat_id": "", "api_base_url": "https://api.telegram.org"},
    )
    @patch("app.services.telegram_delivery_service.send_telegram_message")
    def test_missing_admin_chat_skips(self, mock_send, mock_config):
        result = send_admin_new_order_alert_telegram(
            customer_name="Ravi",
            customer_email="ravi@test.com",
            order_number="GLX-2026-00042",
            estimated_total=3500.0,
        )
        assert result is False
        mock_send.assert_not_called()


class TestTruncate:
    def test_short_text_unchanged(self):
        result = _truncate("Hello world")
        assert result == "Hello world"

    def test_exact_max_length_unchanged(self):
        text = "A" * 4096
        result = _truncate(text)
        assert result == text

    def test_oversized_truncated(self):
        text = "A" * 5000
        result = _truncate(text)
        assert len(result) < 5000
        assert result == "A" * 4095

    def test_truncation_does_not_split_escape_sequence(self):
        text = "A" * 4000 + "\\_" + "B" * 100
        result = _truncate(text)
        assert not result.endswith("\\")
        assert len(result) == 4095 or len(result) == 4094

    def test_odd_bold_marker_balanced(self):
        text = "*Bold start " + "A" * 5000
        result = _truncate(text)
        assert result.count("*") % 2 == 0

    def test_odd_italic_marker_balanced(self):
        text = "_italic start " + "A" * 5000
        result = _truncate(text)
        assert result.count("_") % 2 == 0

    def test_odd_code_marker_balanced(self):
        text = "`code start " + "A" * 5000
        result = _truncate(text)
        assert result.count("`") % 2 == 0


class TestSendTelegramNotification:
    @patch(
        "app.services.telegram_delivery_service._get_config",
        return_value={"bot_token": "test-token", "admin_chat_id": "admin123", "api_base_url": "https://api.telegram.org"},
    )
    @patch("app.services.telegram_delivery_service.requests.post")
    def test_sends_with_title_and_message(self, mock_post, mock_config):
        mock_post.return_value.json.return_value = {"ok": True}
        mock_post.return_value.raise_for_status = Mock()
        result = send_telegram_notification(
            chat_id="12345", title="Alert", message="Something happened"
        )
        assert result is True
        mock_post.assert_called_once()
        sent_payload = mock_post.call_args[1]["json"]
        assert "Alert" in sent_payload["text"]
        assert "Something happened" in sent_payload["text"]

    @patch(
        "app.services.telegram_delivery_service._get_config",
        return_value={"bot_token": "", "admin_chat_id": "", "api_base_url": "https://api.telegram.org"},
    )
    def test_missing_token_skips(self, mock_config):
        result = send_telegram_notification(
            chat_id="12345", title="Alert", message="Test"
        )
        assert result is False


class TestMalformedEstimatedTotalTelegram:
    def test_non_numeric_does_not_raise(self, mock_subscriptions_collection):
        with patch(
            "app.services.telegram_delivery_service.send_telegram_message",
            return_value=True,
        ):
            try:
                send_order_received_telegram(
                    user_id="user1",
                    customer_name="Ravi",
                    order_number="GLX-2026-00042",
                    estimated_total="bad-number",
                    subscriptions_collection=mock_subscriptions_collection,
                )
            except Exception:
                pytest.fail("send_order_received_telegram raised on non-numeric estimated_total")

    def test_none_estimated_total_does_not_raise(self, mock_subscriptions_collection):
        with patch(
            "app.services.telegram_delivery_service.send_telegram_message",
            return_value=True,
        ):
            try:
                send_order_received_telegram(
                    user_id="user1",
                    customer_name="Ravi",
                    order_number="GLX-2026-00042",
                    estimated_total=None,
                    subscriptions_collection=mock_subscriptions_collection,
                )
            except Exception:
                pytest.fail("send_order_received_telegram raised on None estimated_total")
