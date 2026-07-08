from unittest.mock import Mock

import pytest


@pytest.fixture
def mock_smtp_sender():
    return Mock()


@pytest.fixture
def mock_subscriptions_collection():
    collection = Mock()
    collection.find_one.return_value = {
        "user_id": "user1",
        "chat_id": "67890",
        "is_active": True,
    }
    return collection


@pytest.fixture
def sample_order_data():
    return {
        "customer_name": "Ravi",
        "customer_email": "ravi@example.com",
        "order_number": "GLX-2026-00042",
        "estimated_total": 2500.0,
    }
