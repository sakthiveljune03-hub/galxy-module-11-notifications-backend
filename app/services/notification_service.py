import os
import logging
import datetime
# pyrefly: ignore [missing-import]
from bson import ObjectId
# pyrefly: ignore [missing-import]
from pymongo import DESCENDING

from app.database import get_db
from app.models.notification import prepare_notification, create_notification_indexes
from app.models.telegram_subscription import prepare_telegram_subscription, create_telegram_subscription_indexes

# Configure Logger
logger = logging.getLogger("notification_service")
if not logger.hasHandlers():
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    logger.setLevel(log_level)
    handler = logging.StreamHandler()
    formatter = logging.Formatter('[%(asctime)s] %(levelname)s in %(module)s: %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# Attempt to load Ajay's delivery services dynamically.
# If they are not yet implemented or available, fall back to mock loggers.
try:
    # pyrefly: ignore [missing-import]
    from app.services.email_delivery_service import send_email_notification
except (ImportError, ModuleNotFoundError):
    def send_email_notification(user_id, title, message):
        logger.info(f"[MOCK EMAIL] Dispatching email to user {user_id}. Title: '{title}', Body: '{message}'")
        return True

try:
    # pyrefly: ignore [missing-import]
    from app.services.telegram_delivery_service import send_telegram_notification
except (ImportError, ModuleNotFoundError):
    def send_telegram_notification(chat_id, title, message):
        logger.info(f"[MOCK TELEGRAM] Dispatching Telegram message to chat {chat_id}. Title: '{title}', Body: '{message}'")
        return True


# Global flag to track index creation status
_indexes_created = False


def ensure_indexes():
    """
    Helper to verify database indexes exist for both collections.
    """
    global _indexes_created
    if _indexes_created:
        return
    try:
        db = get_db()
        create_notification_indexes(db)
        create_telegram_subscription_indexes(db)
        _indexes_created = True
    except Exception as e:
        logger.error(f"Failed to create database indexes: {str(e)}")


def notify_user(
    user_id,
    notification_type,
    title,
    message,
    related_order_number=None,
    related_product_id=None,
    send_email=False,
    send_telegram=False
):
    """
    Main notification dispatcher function.
    Inserts an in-app notification and dispatches to email/telegram if flags are set.
    """
    ensure_indexes()
    db = get_db()
    
    # 1. Prepare and validate notification
    doc_data = {
        "user_id": user_id,
        "type": notification_type,
        "title": title,
        "message": message,
        "related_order_number": related_order_number,
        "related_product_id": related_product_id,
        "is_read": False,
        "created_at": datetime.datetime.now(datetime.timezone.utc)
    }
    
    # Prepare and validate (will raise ValueError on violation)
    sanitized_doc = prepare_notification(doc_data)
    
    # 2. Insert into local notifications collection (In-app source of truth)
    result = db["notifications"].insert_one(sanitized_doc)
    notification_id = str(result.inserted_id)
    logger.info(f"Created in-app notification {notification_id} for user {user_id}")
    
    # 3. Handle Email Dispatch
    email_sent = False
    if send_email:
        try:
            # Pass user_id (or lookup user's email if needed; for core contract we invoke with user_id)
            email_sent = send_email_notification(str(user_id), title, message)
            logger.info(f"Email dispatch request completed for user {user_id}: status={email_sent}")
        except Exception as e:
            logger.error(f"Error dispatching email to user {user_id}: {str(e)}")
            
    # 4. Handle Telegram Dispatch
    telegram_sent = False
    if send_telegram:
        try:
            # Retrieve user's telegram subscription details - reuse sanitized_doc["user_id"]
            sub = db["telegram_subscriptions"].find_one({
                "user_id": sanitized_doc["user_id"],
                "is_active": True
            })
            
            if sub and sub.get("chat_id"):
                chat_id = sub["chat_id"]
                telegram_sent = send_telegram_notification(chat_id, title, message)
                logger.info(f"Telegram dispatch request completed for chat {chat_id}: status={telegram_sent}")
            else:
                logger.warning(f"Telegram delivery requested but user {user_id} has no active subscription.")
        except Exception as e:
            logger.error(f"Error dispatching Telegram message to user {user_id}: {str(e)}")
            
    return {
        "notification_id": notification_id,
        "in_app": True,
        "email_dispatched": email_sent,
        "telegram_dispatched": telegram_sent
    }


def list_notifications(user_id, is_read=None, page=1, limit=20):
    """
    Retrieves user notifications paginated and sorted newest-first.
    Aligns response with Section 4 API Response Contract.
    """
    ensure_indexes()
    db = get_db()
    
    try:
        parsed_user_id = ObjectId(user_id) if isinstance(user_id, str) else user_id
    except Exception:
        raise ValueError("Invalid user_id format.")
        
    query = {"user_id": parsed_user_id}
    
    if is_read is not None:
        if not isinstance(is_read, bool):
            raise ValueError("is_read filter must be a boolean.")
        query["is_read"] = is_read
        
    # Calculate skip offset
    page = max(1, int(page))
    limit = min(max(1, int(limit)), 100)
    skip = (page - 1) * limit
    
    collection = db["notifications"]
    total = collection.count_documents(query)
    
    # Query with sorting and pagination
    cursor = collection.find(query).sort("created_at", DESCENDING).skip(skip).limit(limit)
    
    # Format list
    notifications = []
    for item in cursor:
        notifications.append({
            "id": str(item["_id"]),
            "user_id": str(item["user_id"]),
            "type": item["type"],
            "title": item["title"],
            "message": item["message"],
            "related_order_number": item.get("related_order_number"),
            "related_product_id": str(item["related_product_id"]) if item.get("related_product_id") else None,
            "is_read": item["is_read"],
            "created_at": item["created_at"].isoformat() if isinstance(item["created_at"], datetime.datetime) else item["created_at"]
        })
        
    total_pages = (total + limit - 1) // limit if limit > 0 else 0
    
    return {
        "success": True,
        "data": notifications,
        "page": page,
        "limit": limit,
        "total": total,
        "totalPages": total_pages
    }


def mark_as_read(user_id, notification_id):
    """
    Marks a single notification as read.
    """
    ensure_indexes()
    db = get_db()
    
    try:
        parsed_user_id = ObjectId(user_id) if isinstance(user_id, str) else user_id
        parsed_notification_id = ObjectId(notification_id) if isinstance(notification_id, str) else notification_id
    except Exception:
        raise ValueError("Invalid format for user_id or notification_id.")
        
    result = db["notifications"].update_one(
        {"_id": parsed_notification_id, "user_id": parsed_user_id},
        {"$set": {"is_read": True}}
    )
    
    return {
        "success": True,
        "modified_count": result.modified_count,
        "found": result.matched_count > 0
    }


def mark_all_as_read(user_id):
    """
    Marks all unread notifications for a user as read.
    """
    ensure_indexes()
    db = get_db()
    
    try:
        parsed_user_id = ObjectId(user_id) if isinstance(user_id, str) else user_id
    except Exception:
        raise ValueError("Invalid user_id format.")
        
    result = db["notifications"].update_many(
        {"user_id": parsed_user_id, "is_read": False},
        {"$set": {"is_read": True}}
    )
    
    return {
        "success": True,
        "modified_count": result.modified_count
    }


def get_unread_count(user_id):
    """
    Computes count of unread notifications, unaffected by list filters.
    """
    ensure_indexes()
    db = get_db()
    
    try:
        parsed_user_id = ObjectId(user_id) if isinstance(user_id, str) else user_id
    except Exception:
        raise ValueError("Invalid user_id format.")
        
    count = db["notifications"].count_documents({
        "user_id": parsed_user_id,
        "is_read": False
    })
    
    return count


# Subscription Management functions (for settings integration by Guru Dev)
def subscribe_telegram(user_id, chat_id):
    """
    Creates or updates (upserts) a Telegram chat registration.
    """
    ensure_indexes()
    db = get_db()
    
    sub_data = {
        "user_id": user_id,
        "chat_id": chat_id,
        "is_active": True,
        "linked_at": datetime.datetime.now(datetime.timezone.utc)
    }
    
    sanitized_sub = prepare_telegram_subscription(sub_data)
    
    # Enforces single subscription using unique user_id index
    result = db["telegram_subscriptions"].update_one(
        {"user_id": sanitized_sub["user_id"]},
        {"$set": sanitized_sub},
        upsert=True
    )
    
    return {
        "success": True,
        "upserted_id": str(result.upserted_id) if result.upserted_id else None,
        "modified_count": result.modified_count
    }


def unsubscribe_telegram(user_id):
    """
    Deactivates a user's Telegram subscription.
    """
    ensure_indexes()
    db = get_db()
    
    try:
        parsed_user_id = ObjectId(user_id) if isinstance(user_id, str) else user_id
    except Exception:
        raise ValueError("Invalid user_id format.")
        
    result = db["telegram_subscriptions"].update_one(
        {"user_id": parsed_user_id},
        {"$set": {"is_active": False}}
    )
    
    return {
        "success": True,
        "modified_count": result.modified_count
    }
