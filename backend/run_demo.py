import os
import sys
import json
from bson import ObjectId

# Add current directory to python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.database import get_db
from app.services.notification_service import (
    notify_user,
    list_notifications,
    get_unread_count,
    mark_all_as_read,
    subscribe_telegram
)

def run_demonstration():
    print("=" * 60)
    print(" GALXY MODULE 11 - NOTIFICATION SERVICE DEMO RUN ")
    print("=" * 60)
    
    # 1. Initialize MongoDB connection
    print("\n[1] Initializing MongoDB Connection...")
    try:
        db = get_db()
        # Ping the server to check connection
        db.command("ping")
        print(" -> MongoDB Connected Successfully!")
    except Exception as e:
        print(f" -> MongoDB Connection failed: {str(e)}")
        print("    (Note: The demo requires a running MongoDB server at mongodb://localhost:27017)")
        sys.exit(1)
        
    # 2. Define a Mock User
    mock_user_id = ObjectId()
    print(f"\n[2] Defined Mock User ID: {mock_user_id}")
    
    # 3. Create a Telegram Subscription
    print("\n[3] Setting up Telegram Subscription for Mock User...")
    sub_res = subscribe_telegram(mock_user_id, chat_id="demo_chat_9876")
    print(f" -> Result: {json.dumps(sub_res, indent=2)}")
    
    # 4. Trigger Notifications (In-App, Email, and Telegram)
    print("\n[4] Sending Notifications...")
    
    # Alert 1: Order inquiry received
    notif_1 = notify_user(
        user_id=mock_user_id,
        notification_type="order_created",
        title="Inquiry Received",
        message="Your request for a custom Pink Neon Sign has been submitted.",
        related_order_number="GLX-2026-00042",
        send_email=True,
        send_telegram=False
    )
    print(f" -> Alert 1 Dispatched: {json.dumps(notif_1, indent=2)}")
    
    # Alert 2: Order status transition
    notif_2 = notify_user(
        user_id=mock_user_id,
        notification_type="order_status_changed",
        title="Stage: In Production",
        message="Asil has confirmed your design and started crafting your sign.",
        related_order_number="GLX-2026-00042",
        send_email=True,
        send_telegram=True
    )
    print(f" -> Alert 2 Dispatched: {json.dumps(notif_2, indent=2)}")
    
    # 5. Check Unread Notifications Count
    unread_count = get_unread_count(mock_user_id)
    print(f"\n[5] Fetching Unread Count for User {mock_user_id}:")
    print(f" -> Count: {unread_count} notifications unread")
    
    # 6. Retrieve Notifications List (Paginated)
    print("\n[6] Listing Notifications Feed (Standard Contract):")
    feed = list_notifications(mock_user_id, page=1, limit=10)
    print(json.dumps(feed, indent=2))
    
    # 7. Bulk Mark Read
    print("\n[7] Marking All Notifications as Read...")
    read_res = mark_all_as_read(mock_user_id)
    print(f" -> Result: {json.dumps(read_res, indent=2)}")
    
    # Verify count is reset
    new_count = get_unread_count(mock_user_id)
    print(f" -> New Unread Count: {new_count}")
    
    # Clean up test records
    print("\n[8] Cleaning up Demo Records...")
    db["notifications"].delete_many({"user_id": mock_user_id})
    db["telegram_subscriptions"].delete_many({"user_id": mock_user_id})
    print(" -> Demo records removed.")
    
    print("\n" + "=" * 60)
    print(" DEMO RUN COMPLETE ")
    print("=" * 60)

if __name__ == '__main__':
    run_demonstration()
