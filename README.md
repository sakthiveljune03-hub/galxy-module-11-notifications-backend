# GALXY — Module 11 (Notifications Ecosystem)

This repository contains the complete **Notifications Ecosystem** for the GALXY application. It handles the persistence, retrieval, and management of user-facing notifications, email alerts, and Telegram channel subscriptions.

The project is split into two main subsystems:
1. **[Backend Service](file:///c:/Users/sakth/OneDrive/Desktop/module%2011/backend)**: Python (Flask) API with MongoDB support (or mock in-memory fallback).
2. **[Frontend Dashboard](file:///c:/Users/sakth/OneDrive/Desktop/module%2011/frontend)**: React (Vite) interface built with Tailwind CSS.

---

## 📂 Project Structure

```
module 11/
├── backend/                  # Python Flask API Subsystem
│   ├── app/                  # Main Flask application packages
│   │   ├── configs/          # Environment variables & CORS settings
│   │   ├── models/           # Notification & Subscription schemas
│   │   ├── routes/           # REST API Route blueprints
│   │   └── services/         # Telegram & Email dispatchers
│   ├── tests/                # Unit & Integration test suite
│   ├── .env                  # Configuration variables (local dev overrides)
│   ├── requirements.txt      # Python dependencies list
│   └── run.py                # Server entry script (port 5000)
│
├── frontend/                 # React Vite Client Subsystem
│   ├── src/                  # Components, Hooks, CSS, and main assets
│   │   ├── components/       # UI elements (Bell badge, Telegram settings card)
│   │   └── config.js         # API connection endpoint definitions
│   ├── package.json          # Node configurations & scripts (port 3050)
│   └── index.html            # Entry layout template
│
└── documents/                # Local Word document files (*.docx)
```

---

## ⚙️ Subsystem Setup & Running Instructions

### 🐍 1. Backend Subsystem (Flask)

The backend exposes the REST API, issues mock JWT authentication tokens, and dispatches mock/real emails & Telegram alerts.

#### Setup & Run:
1. Navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Activate your virtual environment:
   ```powershell
   # Windows PowerShell
   .\.venv\Scripts\Activate.ps1
   ```
3. Install required Python packages:
   ```bash
   pip install -r requirements.txt
   ```
4. Start the server:
   ```bash
   python run.py
   ```
   *The backend will boot on: **`http://localhost:5000`***

#### Running Backend Tests:
To run the automated tests:
```bash
python -m unittest discover -s tests -p "test_*.py"
```

---

### ⚛️ 2. Frontend Subsystem (Vite + React)

The frontend offers a real-time control room, account switcher, in-app feed, and Telegram subscription link forms.

#### Setup & Run:
1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install npm dependencies:
   ```bash
   npm install
   ```
3. Start the development server:
   ```bash
   npm run dev
   ```
   *The frontend will boot on: **`http://localhost:3050`*** *(Vite is configured to use port 3050 to prevent cache conflicts with previous projects on port 3000)*.

#### Running Frontend Tests:
To run unit and rendering tests (Vitest):
```bash
npm run test
```

---

## 🔗 System Integration & Mock Flow Details

### CORS Policy
The backend [config.py](file:///c:/Users/sakth/OneDrive/Desktop/module%2011/backend/app/configs/config.py) is configured to permit Cross-Origin requests from `http://localhost:3050` so the React application can safely access backend APIs.

### Mock Notification Logging (No external APIs needed)
If you don't have active SMTP or Telegram bot credentials configured in the backend environment, notifications will fall back to local log files:
* **Outgoing Emails** are logged directly to:
  `backend/scratch/mock_emails.log`
* **Telegram Messages & Link Codes** are logged directly to:
  `scratch/mock_telegram_delivery.log`
  *(Use the 6-digit codes generated here to verify and link fake Telegram IDs in the UI).*
