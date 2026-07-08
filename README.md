# GALXY — Notifications Backend Service

This service handles the persistence, retrieval, and management of user-facing notifications for the GALXY application. It also supports Telegram channel subscriptions and email alerts.

---

## 🛠️ Technology Stack
* **Language**: Python 3.11+
* **Framework**: Flask (Web Framework)
* **Database**: MongoDB (via `pymongo` with automatic Mock Memory DB fallback)
* **Authentication**: JWT-based mock session tokens (`PyJWT`)

---

## ⚙️ Setup & Execution

### 1. Configure the Environment
Create your `.env` configuration file from the provided example template:
```powershell
copy .env.example .env
```

### 2. Run the Service
1. Activate your python virtual environment:
   ```powershell
   # Windows PowerShell
   .\.venv\Scripts\Activate.ps1
   ```
2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the development server:
   ```bash
   python run.py
   ```
   *The server runs locally on **`http://localhost:5000`**.*

---

## 🧪 Testing

To run the automated unit and integration tests:
```bash
python -m unittest discover -s tests -p "test_*.py"
```

---

## 📡 REST API Reference

All requests must contain a valid mock token in the header unless otherwise noted:
`Authorization: Bearer <JWT_TOKEN>`

### 1. Authentication
* **Request Token**: `POST /api/v1/auth/token`
  - **Body**: `{ "user_id": "customer1" }`
  - **Response**: `{ "success": true, "token": "<JWT_TOKEN>" }`

### 2. Notifications Feed
* **Fetch Notifications**: `GET /api/v1/notifications`
  - **Query Params**: `page` (default: 1), `limit` (default: 10), `is_read` (optional filter)
* **Trigger Event (Notification)**: `POST /api/v1/notifications/mock-trigger`
  - **Body**: `{ "message": "Notification message text", "order_id": "GLX-2026-00042" }`
* **Mark All as Read**: `PATCH /api/v1/notifications/read-all`

### 3. Telegram Subscriptions
* **Link chat ID**: `POST /api/v1/notifications/telegram/status`
  - **Body**: `{ "chat_id": "chat_12345" }`
* **Verify link**: `POST /api/v1/notifications/telegram/verify`
  - **Body**: `{ "code": "6-digit-verification-code" }`
* **Check status**: `GET /api/v1/notifications/telegram/status`
* **Unlink subscription**: `DELETE /api/v1/notifications/telegram/status`

---

## 🪵 Mock Logs
If SMTP or Telegram API Bot tokens are not configured in your `.env`, outbox alerts are logged to local files:
- **Mock Emails**: `backend/scratch/mock_emails.log`
- **Mock Telegram alerts**: `scratch/mock_telegram_delivery.log`
