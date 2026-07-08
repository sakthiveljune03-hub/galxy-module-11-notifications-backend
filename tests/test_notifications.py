import unittest
from unittest.mock import MagicMock, patch
import datetime
# pyrefly: ignore [missing-import]
from bson import ObjectId

# Set up test paths so we can import app modules directly
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.models.notification import validate_notification, prepare_notification
from app.models.telegram_subscription import validate_telegram_subscription, prepare_telegram_subscription
from app.services.notification_service import (
    notify_user, 
    list_notifications, 
    mark_as_read, 
    mark_all_as_read, 
    get_unread_count,
    subscribe_telegram,
    unsubscribe_telegram
)

class TestNotificationModels(unittest.TestCase):
    
    def test_validate_notification_valid(self):
        valid_data = {
            "user_id": ObjectId(),
            "type": "order_status_changed",
            "title": "Order Shipped",
            "message": "Your package has been handed over to the courier.",
            "related_order_number": "GLX-2026-12345",
            "related_product_id": ObjectId(),
            "is_read": False,
            "created_at": datetime.datetime.now(datetime.timezone.utc)
        }
        self.assertTrue(validate_notification(valid_data))
        
        # Test valid string format of ObjectId
        valid_data["user_id"] = str(ObjectId())
        self.assertTrue(validate_notification(valid_data))

    def test_validate_notification_invalid(self):
        # Missing required field
        invalid_data = {
            "type": "order_status_changed",
            "title": "Order Shipped",
            "message": "Your package has been handed over to the courier."
        }
        with self.assertRaises(ValueError) as ctx:
            validate_notification(invalid_data)
        self.assertIn("Missing required field", str(ctx.exception))
        
        # Invalid ObjectId format
        invalid_data = {
            "user_id": "invalid_object_id_format",
            "type": "order_status_changed",
            "title": "Order Shipped",
            "message": "Your package has been handed over to the courier."
        }
        with self.assertRaises(ValueError) as ctx:
            validate_notification(invalid_data)
        self.assertIn("not a valid ObjectId format", str(ctx.exception))

        # Invalid field types
        invalid_data = {
            "user_id": ObjectId(),
            "type": 1234, # Should be string
            "title": "Order Shipped",
            "message": "Your package has been handed over to the courier."
        }
        with self.assertRaises(ValueError) as ctx:
            validate_notification(invalid_data)
        self.assertIn("must be a non-empty string", str(ctx.exception))

    def test_prepare_notification(self):
        user_id_str = str(ObjectId())
        prod_id_str = str(ObjectId())
        raw_data = {
            "user_id": user_id_str,
            "type": " order_status_changed  ",
            "title": " Order Shipped  ",
            "message": "Your package is on its way. ",
            "related_order_number": "GLX-2026-99",
            "related_product_id": prod_id_str
        }
        prepared = prepare_notification(raw_data)
        self.assertIsInstance(prepared["user_id"], ObjectId)
        self.assertIsInstance(prepared["related_product_id"], ObjectId)
        self.assertEqual(prepared["user_id"], ObjectId(user_id_str))
        self.assertEqual(prepared["type"], "order_status_changed")
        self.assertEqual(prepared["title"], "Order Shipped")
        self.assertEqual(prepared["message"], "Your package is on its way.")
        self.assertFalse(prepared["is_read"])
        self.assertIsInstance(prepared["created_at"], datetime.datetime)

        # Test empty/whitespace related_product_id normalization to None
        raw_data["related_product_id"] = "   "
        prepared_empty = prepare_notification(raw_data)
        self.assertIsNone(prepared_empty["related_product_id"])

        # Test valid but unstripped related_product_id string
        raw_data["related_product_id"] = f"  {prod_id_str}  "
        prepared_unstripped = prepare_notification(raw_data)
        self.assertEqual(prepared_unstripped["related_product_id"], ObjectId(prod_id_str))


class TestTelegramSubscriptionModels(unittest.TestCase):
    
    def test_validate_telegram_subscription_valid(self):
        valid_data = {
            "user_id": ObjectId(),
            "chat_id": "123456789",
            "is_active": True,
            "linked_at": datetime.datetime.now(datetime.timezone.utc)
        }
        self.assertTrue(validate_telegram_subscription(valid_data))

    def test_validate_telegram_subscription_invalid(self):
        # Missing chat_id
        invalid_data = {
            "user_id": ObjectId(),
            "is_active": True
        }
        with self.assertRaises(ValueError) as ctx:
            validate_telegram_subscription(invalid_data)
        self.assertIn("Missing required field", str(ctx.exception))

    def test_prepare_telegram_subscription(self):
        user_id_str = str(ObjectId())
        raw_data = {
            "user_id": user_id_str,
            "chat_id": " 987654321 "
        }
        prepared = prepare_telegram_subscription(raw_data)
        self.assertEqual(prepared["user_id"], ObjectId(user_id_str))
        self.assertEqual(prepared["chat_id"], "987654321")
        self.assertTrue(prepared["is_active"])
        self.assertIsInstance(prepared["linked_at"], datetime.datetime)


class TestNotificationService(unittest.TestCase):

    @patch("app.services.notification_service.get_db")
    @patch("app.services.notification_service.send_email_notification")
    @patch("app.services.notification_service.send_telegram_notification")
    def test_notify_user_triggers(self, mock_send_telegram, mock_send_email, mock_get_db):
        # Setup mocks
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        
        user_id = ObjectId()
        mock_db["notifications"].insert_one.return_value.inserted_id = ObjectId()
        
        # Test Case 1: In-app notification only
        result = notify_user(
            user_id=user_id,
            notification_type="order_status",
            title="In Production",
            message="Your custom sign has entered production stage.",
            send_email=False,
            send_telegram=False
        )
        self.assertTrue(result["in_app"])
        self.assertFalse(result["email_dispatched"])
        self.assertFalse(result["telegram_dispatched"])
        mock_db["notifications"].insert_one.assert_called_once()
        mock_send_email.assert_not_called()
        mock_send_telegram.assert_not_called()

        # Reset mocks
        mock_db["notifications"].insert_one.reset_mock()
        mock_send_email.reset_mock()
        mock_send_telegram.reset_mock()
        
        # Mock telegram subscriptions query success
        mock_db["telegram_subscriptions"].find_one.return_value = {
            "user_id": user_id,
            "chat_id": "my_chat_id",
            "is_active": True
        }
        mock_send_email.return_value = True
        mock_send_telegram.return_value = True
        
        # Test Case 2: In-app + Email + Telegram
        result = notify_user(
            user_id=user_id,
            notification_type="order_status",
            title="In Production",
            message="Your custom sign has entered production stage.",
            send_email=True,
            send_telegram=True
        )
        self.assertTrue(result["in_app"])
        self.assertTrue(result["email_dispatched"])
        self.assertTrue(result["telegram_dispatched"])
        
        # Ensure email dispatcher called
        mock_send_email.assert_called_once_with(str(user_id), "In Production", "Your custom sign has entered production stage.")
        
        # Ensure telegram dispatcher called with correct active chat_id
        mock_db["telegram_subscriptions"].find_one.assert_called_once()
        mock_send_telegram.assert_called_once_with("my_chat_id", "In Production", "Your custom sign has entered production stage.")

    @patch("app.services.notification_service.get_db")
    def test_list_notifications(self, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        
        user_id = ObjectId()
        mock_cursor = MagicMock()
        
        # Return mock notification items
        mock_items = [
            {
                "_id": ObjectId(),
                "user_id": user_id,
                "type": "order_status",
                "title": "Alert 1",
                "message": "Body 1",
                "is_read": False,
                "created_at": datetime.datetime.now(datetime.timezone.utc)
            },
            {
                "_id": ObjectId(),
                "user_id": user_id,
                "type": "order_status",
                "title": "Alert 2",
                "message": "Body 2",
                "is_read": True,
                "created_at": datetime.datetime.now(datetime.timezone.utc)
            }
        ]
        
        mock_db["notifications"].find.return_value.sort.return_value.skip.return_value.limit.return_value = mock_items
        mock_db["notifications"].count_documents.return_value = 2
        
        res = list_notifications(user_id, page=1, limit=2)
        
        self.assertTrue(res["success"])
        self.assertEqual(len(res["data"]), 2)
        self.assertEqual(res["total"], 2)
        self.assertEqual(res["page"], 1)
        self.assertEqual(res["totalPages"], 1)
        self.assertEqual(res["data"][0]["title"], "Alert 1")
        self.assertFalse(res["data"][0]["is_read"])
        self.assertTrue(res["data"][1]["is_read"])

    @patch("app.services.notification_service.get_db")
    def test_mark_as_read(self, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        
        user_id = ObjectId()
        notification_id = ObjectId()
        
        mock_db["notifications"].update_one.return_value.modified_count = 1
        mock_db["notifications"].update_one.return_value.matched_count = 1
        
        res = mark_as_read(user_id, notification_id)
        self.assertTrue(res["success"])
        self.assertEqual(res["modified_count"], 1)
        self.assertTrue(res["found"])
        
        # Verify call arguments
        mock_db["notifications"].update_one.assert_called_once_with(
            {"_id": notification_id, "user_id": user_id},
            {"$set": {"is_read": True}}
        )

    @patch("app.services.notification_service.get_db")
    def test_mark_all_as_read(self, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        
        user_id = ObjectId()
        mock_db["notifications"].update_many.return_value.modified_count = 5
        
        res = mark_all_as_read(user_id)
        self.assertTrue(res["success"])
        self.assertEqual(res["modified_count"], 5)
        
        # Verify call arguments
        mock_db["notifications"].update_many.assert_called_once_with(
            {"user_id": user_id, "is_read": False},
            {"$set": {"is_read": True}}
        )

    @patch("app.services.notification_service.get_db")
    def test_get_unread_count(self, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        
        user_id = ObjectId()
        mock_db["notifications"].count_documents.return_value = 3
        
        count = get_unread_count(user_id)
        self.assertEqual(count, 3)
        mock_db["notifications"].count_documents.assert_called_once_with({
            "user_id": user_id,
            "is_read": False
        })


class TestTelegramSubscriptionService(unittest.TestCase):

    @patch("app.services.notification_service.get_db")
    def test_subscribe_telegram_new(self, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        
        user_id = ObjectId()
        chat_id = "test_chat_123"
        
        mock_update_result = MagicMock()
        mock_update_result.upserted_id = ObjectId()
        mock_update_result.modified_count = 0
        mock_db["telegram_subscriptions"].update_one.return_value = mock_update_result
        
        res = subscribe_telegram(user_id, chat_id)
        self.assertTrue(res["success"])
        self.assertIsNotNone(res["upserted_id"])
        
        mock_db["telegram_subscriptions"].update_one.assert_called_once()
        call_args = mock_db["telegram_subscriptions"].update_one.call_args[0]
        self.assertEqual(call_args[0]["user_id"], user_id)

    @patch("app.services.notification_service.get_db")
    def test_subscribe_telegram_update(self, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        
        user_id = ObjectId()
        chat_id = "test_chat_456"
        
        mock_update_result = MagicMock()
        mock_update_result.upserted_id = None
        mock_update_result.modified_count = 1
        mock_db["telegram_subscriptions"].update_one.return_value = mock_update_result
        
        res = subscribe_telegram(user_id, chat_id)
        self.assertTrue(res["success"])
        self.assertIsNone(res["upserted_id"])
        self.assertEqual(res["modified_count"], 1)

    @patch("app.services.notification_service.get_db")
    def test_unsubscribe_telegram(self, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        
        user_id = ObjectId()
        
        mock_update_result = MagicMock()
        mock_update_result.modified_count = 1
        mock_db["telegram_subscriptions"].update_one.return_value = mock_update_result
        
        res = unsubscribe_telegram(user_id)
        self.assertTrue(res["success"])
        self.assertEqual(res["modified_count"], 1)
        
        mock_db["telegram_subscriptions"].update_one.assert_called_once_with(
            {"user_id": user_id},
            {"$set": {"is_active": False}}
        )


class MockCollection:
    def __init__(self, name):
        self.name = name
        self.documents = []

    def insert_one(self, doc):
        if "_id" not in doc:
            doc["_id"] = ObjectId()
        self.documents.append(doc)
        
        class InsertOneResult:
            def __init__(self, inserted_id):
                self.inserted_id = inserted_id
        return InsertOneResult(doc["_id"])

    def find_one(self, query):
        for doc in self.documents:
            match = True
            for k, v in query.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                return doc
        return None

    def find(self, query):
        results = []
        for doc in self.documents:
            match = True
            for k, v in query.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                results.append(doc)
        
        class MockCursor:
            def __init__(self, items):
                self.items = items
            def sort(self, key, direction=1):
                self.items.sort(key=lambda x: x.get(key, datetime.datetime.min), reverse=(direction == -1))
                return self
            def skip(self, count):
                self.items = self.items[count:]
                return self
            def limit(self, count):
                self.items = self.items[:count]
                return self
            def __iter__(self):
                return iter(self.items)
        return MockCursor(results)

    def count_documents(self, query):
        count = 0
        for doc in self.documents:
            match = True
            for k, v in query.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                count += 1
        return count

    def update_one(self, query, update, upsert=False):
        doc = self.find_one(query)
        modified_count = 0
        matched_count = 0
        
        class UpdateResult:
            def __init__(self, matched, modified, upserted_id=None):
                self.matched_count = matched
                self.modified_count = modified
                self.upserted_id = upserted_id

        if doc:
            matched_count = 1
            if "$set" in update:
                for k, v in update["$set"].items():
                    doc[k] = v
                modified_count = 1
            return UpdateResult(matched_count, modified_count)
            
        if upsert:
            new_doc = query.copy()
            if "$set" in update:
                new_doc.update(update["$set"])
            self.insert_one(new_doc)
            return UpdateResult(0, 0, new_doc["_id"])
            
        return UpdateResult(0, 0)

    def update_many(self, query, update):
        modified_count = 0
        for doc in self.documents:
            match = True
            for k, v in query.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                if "$set" in update:
                    for k, v in update["$set"].items():
                        doc[k] = v
                    modified_count += 1
                    
        class UpdateManyResult:
            def __init__(self, modified):
                self.modified_count = modified
        return UpdateManyResult(modified_count)

    def create_index(self, keys, name=None, unique=False):
        pass


class MockDatabase:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        if name not in self.collections:
            self.collections[name] = MockCollection(name)
        return self.collections[name]

    def command(self, cmd):
        return {"ok": 1.0}


class TestNotificationIntegration(unittest.TestCase):
    
    @patch("app.services.notification_service.get_db")
    def test_end_to_end_mock_scenario(self, mock_get_db):
        mock_db = MockDatabase()
        mock_get_db.return_value = mock_db
        
        user_id = ObjectId()
        
        # 1. Subscribe to telegram
        sub_res = subscribe_telegram(user_id, chat_id="chat_999")
        self.assertTrue(sub_res["success"])
        
        # 2. Trigger notification 1 (In-App + Email)
        res1 = notify_user(
            user_id=user_id,
            notification_type="order_created",
            title="Order Received",
            message="Your order has been logged.",
            send_email=True,
            send_telegram=False
        )
        self.assertTrue(res1["in_app"])
        self.assertTrue(res1["email_dispatched"])
        self.assertFalse(res1["telegram_dispatched"])
        
        # 3. Trigger notification 2 (In-App + Telegram)
        res2 = notify_user(
            user_id=user_id,
            notification_type="order_status_changed",
            title="Order Shipped",
            message="Your order is on the way.",
            send_email=False,
            send_telegram=True
        )
        self.assertTrue(res2["in_app"])
        self.assertFalse(res2["email_dispatched"])
        self.assertTrue(res2["telegram_dispatched"])
        
        # 4. Check unread count
        count = get_unread_count(user_id)
        self.assertEqual(count, 2)
        
        # 5. Fetch notification feed
        feed = list_notifications(user_id, page=1, limit=5)
        self.assertTrue(feed["success"])
        self.assertEqual(feed["total"], 2)
        self.assertEqual(len(feed["data"]), 2)
        
        # 6. Mark first as read
        first_notif_id = feed["data"][0]["id"]
        read_res = mark_as_read(user_id, first_notif_id)
        self.assertTrue(read_res["success"])
        self.assertTrue(read_res["found"])
        
        count_after = get_unread_count(user_id)
        self.assertEqual(count_after, 1)
        
        # 7. Bulk mark read
        bulk_res = mark_all_as_read(user_id)
        self.assertTrue(bulk_res["success"])
        
        count_final = get_unread_count(user_id)
        self.assertEqual(count_final, 0)


if __name__ == '__main__':
    unittest.main()
