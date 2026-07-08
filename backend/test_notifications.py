import os
# Configure environment for development prior to importing configurations
os.environ["FLASK_ENV"] = "development"

import unittest
import json
import jwt
import datetime
from app import create_app
from app.configs.config import Config
from app.services import notification_service as notif_service

class TestNotificationsAPI(unittest.TestCase):
    def setUp(self):
        # Create Flask app configured for testing
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        
        # Ensure mock DB is used for tests
        notif_service.use_mock_db = True
        
        # Seeding clean data
        self.test_notifications = [
            {
                "_id": "t_notif_1",
                "user_id": "customer1",
                "order_id": "GLX-2026-00001",
                "message": "Notification 1 for customer1",
                "is_read": False,
                "created_at": "2026-07-04T10:00:00"
            },
            {
                "_id": "t_notif_2",
                "user_id": "customer1",
                "order_id": "GLX-2026-00001",
                "message": "Notification 2 for customer1",
                "is_read": False,
                "created_at": "2026-07-04T11:00:00"
            },
            {
                "_id": "t_notif_3",
                "user_id": "customer1",
                "order_id": "GLX-2026-00002",
                "message": "Notification 3 for customer1 (Read)",
                "is_read": True,
                "created_at": "2026-07-04T12:00:00"
            },
            {
                "_id": "t_notif_4",
                "user_id": "customer2",
                "order_id": "GLX-2026-00003",
                "message": "Notification belonging to customer2",
                "is_read": False,
                "created_at": "2026-07-04T13:00:00"
            }
        ]
        
        # Reset files
        notif_service.save_mock_data(notif_service.MOCK_NOTIF_FILE, self.test_notifications)
        notif_service.save_mock_data(notif_service.MOCK_TELEGRAM_FILE, [])

    def tearDown(self):
        pass

    def get_auth_headers(self, user_id, role="customer"):
        """Generates a valid signed JWT for testing to comply with secure auth policies."""
        payload = {
            "user_id": user_id,
            "role": role,
            "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
        }
        token = jwt.encode(payload, Config.JWT_SECRET, algorithm="HS256")
        return {"Authorization": f"Bearer {token}"}

    def test_auth_enforcement(self):
        """Enforces authentication check when Authorization header is missing or invalid."""
        # 1. Missing header
        res = self.client.get("/api/v1/notifications")
        self.assertEqual(res.status_code, 401)
        data = json.loads(res.data)
        self.assertFalse(data["success"])
        self.assertIn("Authorization header is missing", data["message"])
        
        # 2. Invalid schema format
        headers = {"Authorization": "Basic customer1"}
        res = self.client.get("/api/v1/notifications", headers=headers)
        self.assertEqual(res.status_code, 401)

    def test_get_notifications_all(self):
        """Retrieves all notifications for the authenticated user."""
        headers = self.get_auth_headers("customer1")
        res = self.client.get("/api/v1/notifications", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        
        self.assertTrue(data["success"])
        self.assertEqual(len(data["data"]), 3)
        self.assertEqual(data["total"], 3)
        self.assertEqual(data["unread_count"], 2)
        self.assertEqual(data["data"][0]["_id"], "t_notif_3")
        self.assertEqual(data["data"][2]["_id"], "t_notif_1")

    def test_get_notifications_filtered(self):
        """Retrieves notifications filtered by is_read, with unread_count always correct."""
        headers = self.get_auth_headers("customer1")
        
        # Filter is_read = false (Unread only)
        res = self.client.get("/api/v1/notifications?is_read=false", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertEqual(len(data["data"]), 2)
        self.assertEqual(data["unread_count"], 2)
        self.assertEqual(data["total"], 2)
        
        # Filter is_read = true (Read only)
        res = self.client.get("/api/v1/notifications?is_read=true", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertEqual(len(data["data"]), 1)
        self.assertEqual(data["data"][0]["_id"], "t_notif_3")
        self.assertEqual(data["unread_count"], 2)

    def test_get_notifications_pagination(self):
        """Applies page and limit parameters correctly to paginated results."""
        headers = self.get_auth_headers("customer1")
        
        # Page 1, limit 2
        res = self.client.get("/api/v1/notifications?page=1&limit=2", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertEqual(len(data["data"]), 2)
        self.assertEqual(data["total"], 3)
        self.assertEqual(data["totalPages"], 2)
        
        # Page 2, limit 2
        res = self.client.get("/api/v1/notifications?page=2&limit=2", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertEqual(len(data["data"]), 1)

    def test_mark_read_success(self):
        """Successfully updates the notification state to read."""
        headers = self.get_auth_headers("customer1")
        res = self.client.put("/api/v1/notifications/t_notif_1/read", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        
        self.assertTrue(data["success"])
        self.assertTrue(data["data"]["is_read"])
        self.assertEqual(data["unread_count"], 1)

        # Verify unread count matches
        res = self.client.get("/api/v1/notifications", headers=headers)
        self.assertEqual(json.loads(res.data)["unread_count"], 1)

    def test_mark_read_404_not_found(self):
        """Returns 404 (never 403) when notification ID does not exist."""
        headers = self.get_auth_headers("customer1")
        res = self.client.put("/api/v1/notifications/t_notif_nonexistent/read", headers=headers)
        self.assertEqual(res.status_code, 404)

    def test_mark_read_wrong_user(self):
        """Returns 404 (never 403) when trying to read another user's notification."""
        headers = self.get_auth_headers("customer1")
        res = self.client.put("/api/v1/notifications/t_notif_4/read", headers=headers)
        self.assertEqual(res.status_code, 404)

    def test_mark_all_read(self):
        """Marks all user notifications as read."""
        headers = self.get_auth_headers("customer1")
        res = self.client.put("/api/v1/notifications/read-all", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["modified_count"], 2)
        self.assertEqual(data["unread_count"], 0)
        
        res = self.client.get("/api/v1/notifications", headers=headers)
        self.assertEqual(json.loads(res.data)["unread_count"], 0)

    def test_telegram_linking_and_verification_handshake(self):
        """Verifies Telegram linking, verification code generation, verify endpoint, and unlink."""
        headers = self.get_auth_headers("customer1")
        
        # 1. Unlinked initially
        res = self.client.get("/api/v1/notifications/telegram/status", headers=headers)
        self.assertEqual(res.status_code, 200)
        status_data = json.loads(res.data)
        self.assertFalse(status_data["data"]["linked"])
        
        # 2. Link a chat ID
        payload = {"chat_id": "987654321"}
        res = self.client.post("/api/v1/notifications/telegram/link", headers=headers, json=payload)
        self.assertEqual(res.status_code, 200)
        link_data = json.loads(res.data)
        self.assertTrue(link_data["success"])
        self.assertEqual(link_data["data"]["chat_id"], "987654321")
        self.assertFalse(link_data["data"]["is_active"]) # Not active yet!
        self.assertFalse(link_data["data"]["is_verified"]) # Not verified yet!
        
        # Verification code should NOT be returned in link response payload (High §3.2)
        self.assertNotIn("verification_code", link_data["data"])
        
        # Ensure status response does NOT leak verification code
        res = self.client.get("/api/v1/notifications/telegram/status", headers=headers)
        status_data = json.loads(res.data)
        self.assertIsNone(status_data["data"]["verification_code"])
        
        # Retrieve code securely directly from service layer for testing verification
        status = notif_service.get_telegram_status("customer1")
        code = status["verification_code"]
        self.assertIsNotNone(code)
        
        # 3. Verify with wrong code -> returns 400
        res = self.client.post("/api/v1/notifications/telegram/verify", headers=headers, json={"verification_code": "000000"})
        self.assertEqual(res.status_code, 400)
        
        # 4. Verify with correct code -> returns 200
        res = self.client.post("/api/v1/notifications/telegram/verify", headers=headers, json={"verification_code": code})
        self.assertEqual(res.status_code, 200)
        verify_data = json.loads(res.data)
        self.assertTrue(verify_data["success"])
        
        # 5. Status should now show linked=True, is_verified=True, is_active=True
        res = self.client.get("/api/v1/notifications/telegram/status", headers=headers)
        status_data = json.loads(res.data)
        self.assertTrue(status_data["data"]["linked"])
        self.assertTrue(status_data["data"]["is_active"])
        self.assertTrue(status_data["data"]["is_verified"])
        
        # 6. Unlink
        res = self.client.delete("/api/v1/notifications/telegram/link", headers=headers)
        self.assertEqual(res.status_code, 200)
        
        # 7. Status should be unlinked again
        res = self.client.get("/api/v1/notifications/telegram/status", headers=headers)
        status_data = json.loads(res.data)
        self.assertFalse(status_data["data"]["linked"])

    def test_invalid_pagination(self):
        """Falls back to defaults when page/limit are non-integers or negative."""
        headers = self.get_auth_headers("customer1")
        res = self.client.get("/api/v1/notifications?page=-5&limit=abc", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertTrue(data["success"])
        self.assertEqual(data["limit"], 10)
        self.assertEqual(data["page"], 1)

    def test_link_telegram_validation(self):
        """Returns 400 when linking with missing or invalid format chat_id."""
        headers = self.get_auth_headers("customer1")
        
        # Missing chat_id
        res = self.client.post("/api/v1/notifications/telegram/link", headers=headers, json={})
        self.assertEqual(res.status_code, 400)
        
        # Too short (< 5 digits)
        res = self.client.post("/api/v1/notifications/telegram/link", headers=headers, json={"chat_id": "123"})
        self.assertEqual(res.status_code, 400)
        
        # Too long (> 15 digits)
        res = self.client.post("/api/v1/notifications/telegram/link", headers=headers, json={"chat_id": "12345678901234567"})
        self.assertEqual(res.status_code, 400)

    def test_mock_trigger_notification(self):
        """Successfully triggers a mock notification using the test endpoint."""
        headers = self.get_auth_headers("customer1")
        payload = {
            "message": "Custom alert triggered for test",
            "order_id": "GLX-TEST-99"
        }
        res = self.client.post("/api/v1/notifications/mock-trigger", headers=headers, json=payload)
        self.assertEqual(res.status_code, 201)
        data = json.loads(res.data)
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["message"], "Custom alert triggered for test")

if __name__ == "__main__":
    unittest.main()
