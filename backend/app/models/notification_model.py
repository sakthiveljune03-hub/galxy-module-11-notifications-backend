import datetime
import sys
from app.services import notification_service as notif_service
from app.services.email_service import send_email_notification
from app.services.telegram_delivery_service import send_telegram_notification

# MongoDB schema documentation / definition for Notifications
NOTIFICATION_SCHEMA = {
    "bsonType": "object",
    "required": ["user_id", "message", "is_read", "created_at"],
    "properties": {
        "_id": {
            "bsonType": "objectId",
            "description": "Unique identifier of the notification"
        },
        "user_id": {
            "bsonType": "string",
            "description": "Identifier of the user receiving the notification"
        },
        "order_id": {
            "bsonType": "string",
            "description": "Optional order identifier linked to the notification"
        },
        "message": {
            "bsonType": "string",
            "description": "Text content of the notification"
        },
        "is_read": {
            "bsonType": "bool",
            "description": "Read status flag (default is False)"
        },
        "created_at": {
            "bsonType": "date",
            "description": "Timestamp when the notification was generated"
        }
    }
}

def notify_user(user_id, message, order_id=None):
    """
    Canonical entry point for triggering a notification for a user.
    Creates an in-app notification and dispatches to enabled delivery channels
    (such as Email and Telegram) asynchronously via the background queue.
    """
    # 1. Create in-app notification via the notification service
    notif = notif_service.create_notification(user_id, message, order_id)
    
    # 2. Enqueue background notification dispatches (Integration/Queue Review)
    try:
        from app.services.queue_service import enqueue_notification_jobs
        enqueue_notification_jobs(user_id, message, order_id)
    except Exception as e:
        print(f"[Queue Warning] Failed to enqueue background jobs: {e}", file=sys.stderr)
        
    return notif
