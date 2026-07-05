# GALXY — Module 11 (Notifications)

This subsystem handles the persistence, retrieval, and management of user-facing notifications for the GALXY application. It also supports Telegram channel subscriptions (added in Week 2).

## Core Responsibilities

1. **In-App Notifications Feed**: Validating, indexing, and storing notifications.
2. **Delivery Dispatch Hooks**: Interfacing with Email and Telegram delivery systems.
3. **Subscriptions Management**: Managing links between users and their Telegram chat handles.

## Setup Instructions

1. Install requirements:
   ```bash
   pip install -r requirements.txt
   ```
2. Copy environment variable template and modify if necessary:
   ```bash
   copy .env.example .env
   ```

## Running Tests

To run the complete test suite:
```bash
python -m unittest discover -s tests -p "test_*.py"
```

## Running Demos

- **In-Memory Mock Demo (No MongoDB needed)**:
  ```bash
  python run_mock_demo.py
  ```
- **Real Database Demo (Requires MongoDB running locally)**:
  ```bash
  python run_demo.py
  ```
