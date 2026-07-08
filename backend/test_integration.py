import os
# Configure environment for development prior to importing configurations
os.environ["FLASK_ENV"] = "development"

import unittest
import json
import jwt
import datetime
from app import create_app
from app.services import notification_service as notif_service
from app.configs.config import Config

class TestNotificationsIntegration(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        
        self.user_id = "integration_test_user"
        
        # Clean existing entries for this user
        if not notif_service.use_mock_db:
            notif_service.db.notifications.delete_many({"user_id": self.user_id})
            notif_service.db.telegram_subscriptions.delete_many({"user_id": self.user_id})
        else:
            # Clean in mock JSON
            notifs = notif_service.load_mock_data(notif_service.MOCK_NOTIF_FILE, [])
            notifs = [n for n in notifs if n["user_id"] != self.user_id]
            notif_service.save_mock_data(notif_service.MOCK_NOTIF_FILE, notifs)
            
            subs = notif_service.load_mock_data(notif_service.MOCK_TELEGRAM_FILE, [])
            subs = [s for s in subs if s["user_id"] != self.user_id]
            notif_service.save_mock_data(notif_service.MOCK_TELEGRAM_FILE, subs)

    def tearDown(self):
        pass

    def get_auth_headers(self, user_id, role="customer"):
        payload = {
            "user_id": user_id,
            "role": role,
            "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
        }
        token = jwt.encode(payload, Config.JWT_SECRET, algorithm="HS256")
        return {"Authorization": f"Bearer {token}"}

    def test_full_integration_workflow(self):
        """Verifies the complete flow: notify_user -> DB write -> API fetch -> mark read -> Telegram link & verify."""
        headers = self.get_auth_headers(self.user_id)
        
        # 1. Trigger a notification via the canonical model notify_user() function
        from app.models.notification_model import notify_user
        notif = notify_user(
            user_id=self.user_id,
            message="Your order #GLX-INT-01 has been confirmed!",
            order_id="GLX-INT-01"
        )
        self.assertIsNotNone(notif)
        self.assertEqual(notif["user_id"], self.user_id)
        
        # 2. Retrieve notifications list via API and verify it is listed in the feed
        res = self.client.get(f"/api/v1/notifications", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertTrue(data["success"])
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["unread_count"], 1)
        self.assertEqual(data["data"][0]["message"], "Your order #GLX-INT-01 has been confirmed!")
        
        notif_id = data["data"][0]["_id"]
        
        # 3. Mark the notification as read via API and verify read count updates
        res = self.client.put(f"/api/v1/notifications/{notif_id}/read", headers=headers)
        self.assertEqual(res.status_code, 200)
        
        # Verify feed shows unread count = 0
        res = self.client.get(f"/api/v1/notifications", headers=headers)
        self.assertEqual(json.loads(res.data)["unread_count"], 0)
        
        # 4. Link a Telegram chat ID
        res = self.client.post("/api/v1/notifications/telegram/link", headers=headers, json={"chat_id": "1122334455"})
        self.assertEqual(res.status_code, 200)
        link_data = json.loads(res.data)
        self.assertTrue(link_data["success"])
        
        # Ensure code is not leaked in linking API response
        self.assertNotIn("verification_code", link_data["data"])
        
        # Retrieve code securely from database status lookup
        status_data = notif_service.get_telegram_status(self.user_id)
        code = status_data["verification_code"]
        self.assertIsNotNone(code)
        
        # Verify link via API code verification
        res = self.client.post("/api/v1/notifications/telegram/verify", headers=headers, json={"verification_code": code})
        self.assertEqual(res.status_code, 200)
        
        # Status should show linked=True
        res = self.client.get("/api/v1/notifications/telegram/status", headers=headers)
        status_data = json.loads(res.data)
        self.assertTrue(status_data["data"]["linked"])
        self.assertEqual(status_data["data"]["chat_id"], "1122334455")
        
        # 5. Trigger another notification
        notif2 = notify_user(
            user_id=self.user_id,
            message="Your package is shipped!",
            order_id="GLX-INT-01"
        )
        
        # Verify that the notification was written to DB
        res = self.client.get(f"/api/v1/notifications?is_read=false", headers=headers)
        self.assertEqual(json.loads(res.data)["total"], 1)

if __name__ == "__main__":
    unittest.main()
