import logging

from app.services.email_delivery_service import (
    send_admin_new_order_alert,
    send_general_notification_email,
    send_order_received_email,
    send_order_status_changed_email,
)
from app.services.telegram_delivery_service import (
    send_admin_new_order_alert_telegram,
    send_order_received_telegram,
    send_order_status_changed_telegram,
)

logger = logging.getLogger(__name__)


def notify_user(
    event_type: str,
    recipient: dict,
    event_data: dict,
    smtp_sender,
    subscriptions_collection,
    send_email: bool = True,
    send_telegram: bool = True,
) -> dict:
    result = {"email": False, "telegram": False}

    if send_email and smtp_sender:
        result["email"] = _dispatch_email(event_type, recipient, event_data, smtp_sender)

    if send_telegram and subscriptions_collection is not None:
        result["telegram"] = _dispatch_telegram(event_type, recipient, event_data, subscriptions_collection)

    return result


def _dispatch_email(event_type: str, recipient: dict, data: dict, smtp_sender) -> bool:
    try:
        if event_type == "order_received":
            return send_order_received_email(
                user_email=recipient["email"],
                customer_name=recipient["name"],
                order_number=data["order_number"],
                estimated_total=data.get("estimated_total", 0),
                dashboard_url=data.get("dashboard_url", ""),
                smtp_sender=smtp_sender,
            )
        elif event_type == "order_status_changed":
            return send_order_status_changed_email(
                user_email=recipient["email"],
                customer_name=recipient["name"],
                order_number=data["order_number"],
                new_status=data["new_status"],
                note=data.get("note"),
                dashboard_url=data.get("dashboard_url", ""),
                smtp_sender=smtp_sender,
            )
        elif event_type == "admin_new_order_alert":
            return send_admin_new_order_alert(
                admin_email=recipient["email"],
                customer_name=recipient["name"],
                customer_email=recipient.get("customer_email", ""),
                order_number=data["order_number"],
                estimated_total=data.get("estimated_total", 0),
                admin_url=data.get("admin_url", ""),
                smtp_sender=smtp_sender,
            )
        elif event_type == "general":
            return send_general_notification_email(
                to=recipient["email"],
                subject=data.get("subject", ""),
                message=data.get("message", ""),
                smtp_sender=smtp_sender,
            )
        logger.warning("Unknown email event_type: %s", event_type)
        return False
    except Exception:
        logger.exception("Failed to dispatch email for event=%s", event_type)
        return False


def _dispatch_telegram(event_type: str, recipient: dict, data: dict, subscriptions_collection) -> bool:
    try:
        if event_type == "order_received":
            return send_order_received_telegram(
                user_id=recipient["user_id"],
                customer_name=recipient["name"],
                order_number=data["order_number"],
                estimated_total=data.get("estimated_total", 0),
                subscriptions_collection=subscriptions_collection,
            )
        elif event_type == "order_status_changed":
            return send_order_status_changed_telegram(
                user_id=recipient["user_id"],
                customer_name=recipient["name"],
                order_number=data["order_number"],
                new_status=data["new_status"],
                note=data.get("note"),
                subscriptions_collection=subscriptions_collection,
            )
        elif event_type == "admin_new_order_alert":
            return send_admin_new_order_alert_telegram(
                customer_name=recipient["name"],
                customer_email=recipient.get("customer_email", ""),
                order_number=data["order_number"],
                estimated_total=data.get("estimated_total", 0),
            )
        logger.warning("Unknown telegram event_type: %s", event_type)
        return False
    except Exception:
        logger.exception("Failed to dispatch telegram for event=%s", event_type)
        return False
import os
import json
import datetime
try:
    from bson import ObjectId
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure
    pymongo_available = True
except ImportError:
    # Fallback stubs to prevent ModuleNotFoundError if pymongo/bson are not installed in the active environment
    class ObjectId:
        def __init__(self, o=None):
            self.o = o if o else "mock_id"
        def __str__(self):
            return str(self.o)
        def __repr__(self):
            return f"ObjectId('{self.o}')"
            
    class ConnectionFailure(Exception):
        pass

    class MongoClient:
        def __init__(self, *args, **kwargs):
            # Raise connection failure to trigger mock database failover
            raise ConnectionFailure("pymongo is not installed in this environment.")
            
    pymongo_available = False
from app.configs.config import Config

import threading

# Initialize MongoDB Client or Mock
_mongo_client = None
db = None
use_mock_db = True
db_lock = threading.RLock()

try:
    # Attempt to connect to MongoDB
    _mongo_client = MongoClient(Config.MONGO_URI, serverSelectionTimeoutMS=2000)
    # Trigger a call to verify if connection is successful
    _mongo_client.admin.command('ping')
    db = _mongo_client[Config.DATABASE_NAME]
    
    # Run database migration checks (M-6)
    if pymongo_available:
        from app.db.migrations import run_migrations
        run_migrations(db)
            
    use_mock_db = False
    print("[DB] Connected successfully to MongoDB.")
except (ConnectionFailure, Exception) as e:
    print(f"[DB] MongoDB connection failed at startup: {e}. Falling back to Mock Memory DB.")
    use_mock_db = True

# Mock DB Data Store for Fallback
# We will also persist mock data to JSON files in scratch if possible, so it behaves like a DB
import pathlib
BASE_DIR = pathlib.Path(__file__).resolve().parent.parent.parent.parent
MOCK_DATA_DIR = os.getenv("MOCK_DATA_DIR", os.path.join(str(BASE_DIR), "scratch"))
MOCK_NOTIF_FILE = os.path.join(MOCK_DATA_DIR, "mock_notifications.json")
MOCK_TELEGRAM_FILE = os.path.join(MOCK_DATA_DIR, "mock_telegram.json")

def load_mock_data(file_path, default_data):
    with db_lock:
        if not os.path.exists(file_path):
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(default_data, f)
            except Exception:
                pass
            return default_data
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default_data

def save_mock_data(file_path, data):
    with db_lock:
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, default=str)
        except Exception as e:
            print(f"Error saving mock data: {e}")

# Seed some initial notifications for testing if mock files don't exist
initial_notifications = [
    {
        "_id": "notif_1",
        "user_id": "customer1",
        "order_id": "GLX-2026-00001",
        "message": "Your order #GLX-2026-00001 has been received and is awaiting review.",
        "is_read": False,
        "created_at": (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=2)).isoformat()
    },
    {
        "_id": "notif_2",
        "user_id": "customer1",
        "order_id": "GLX-2026-00001",
        "message": "Your order #GLX-2026-00001 status changed to 'Reviewed'. Price quote sent.",
        "is_read": False,
        "created_at": (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)).isoformat()
    },
    {
        "_id": "notif_3",
        "user_id": "customer1",
        "order_id": "GLX-2026-00002",
        "message": "Your custom design preview is ready! Click to view.",
        "is_read": True,
        "created_at": (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=5)).isoformat()
    },
    {
        "_id": "notif_4",
        "user_id": "customer2",
        "order_id": "GLX-2026-00003",
        "message": "Your order #GLX-2026-00003 has been shipped!",
        "is_read": False,
        "created_at": (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)).isoformat()
    }
]
load_mock_data(MOCK_NOTIF_FILE, initial_notifications)
load_mock_data(MOCK_TELEGRAM_FILE, [])

# Helper to serialize Mongo object ids
def serialize_doc(doc):
    if not doc:
        return None
    doc = dict(doc)
    if "_id" in doc:
        doc["_id"] = str(doc["_id"])
    if "created_at" in doc and isinstance(doc["created_at"], datetime.datetime):
        doc["created_at"] = doc["created_at"].isoformat()
    if "updated_at" in doc and isinstance(doc["updated_at"], datetime.datetime):
        doc["updated_at"] = doc["updated_at"].isoformat()
    return doc

# --- Service API Implementation ---

def get_notifications_feed(user_id, page=1, limit=10, is_read=None):
    """
    Retrieves notifications and unread_count in a single query using MongoDB $facet aggregation.
    """
    global use_mock_db
    if use_mock_db:
        notifs = load_mock_data(MOCK_NOTIF_FILE, [])
        user_notifs = [n for n in notifs if n["user_id"] == user_id]
        unread_count = len([n for n in user_notifs if not n["is_read"]])
        
        # Apply filter
        filtered_notifs = list(user_notifs)
        if is_read is not None:
            filtered_notifs = [n for n in filtered_notifs if n["is_read"] == is_read]
            
        # Sort by created_at desc
        filtered_notifs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        total = len(filtered_notifs)
        start = (page - 1) * limit
        end = start + limit
        paginated_data = filtered_notifs[start:end]
        
        total_pages = (total + limit - 1) // limit if total > 0 else 0
        return paginated_data, total, total_pages, unread_count
    else:
        try:
            # Construct the aggregation query
            match_stage = {"user_id": user_id}
            
            # Construct facet stages
            paginated_results_pipeline = []
            if is_read is not None:
                paginated_results_pipeline.append({"$match": {"is_read": is_read}})
            
            paginated_results_pipeline.extend([
                {"$sort": {"created_at": -1}},
                {"$skip": (page - 1) * limit},
                {"$limit": limit}
            ])
            
            total_count_pipeline = []
            if is_read is not None:
                total_count_pipeline.append({"$match": {"is_read": is_read}})
            total_count_pipeline.append({"$count": "count"})
            
            unread_count_pipeline = [
                {"$match": {"is_read": False}},
                {"$count": "count"}
            ]
            
            facet_stage = {
                "paginatedResults": paginated_results_pipeline,
                "totalCount": total_count_pipeline,
                "unreadCount": unread_count_pipeline
            }
            
            result = list(db.notifications.aggregate([
                {"$match": match_stage},
                {"$facet": facet_stage}
            ]))
            
            facet_data = result[0] if result else {}
            
            # Extract results
            paginated_results = [serialize_doc(d) for d in facet_data.get("paginatedResults", [])]
            
            total_list = facet_data.get("totalCount", [])
            total = total_list[0]["count"] if total_list else 0
            
            unread_list = facet_data.get("unreadCount", [])
            unread_count = unread_list[0]["count"] if unread_list else 0
            
            total_pages = (total + limit - 1) // limit if total > 0 else 0
            
            return paginated_results, total, total_pages, unread_count
        except Exception as e:
            print(f"[DB Error] Aggregation failed: {e}. Failing over to Mock DB.", file=sys.stderr)
            use_mock_db = True
            return get_notifications_feed(user_id, page, limit, is_read)



def get_unread_count(user_id):
    """
    Returns count of unread notifications for user_id.
    """
    global use_mock_db
    if use_mock_db:
        notifs = load_mock_data(MOCK_NOTIF_FILE, [])
        return len([n for n in notifs if n["user_id"] == user_id and not n["is_read"]])
    else:
        try:
            return db.notifications.count_documents({"user_id": user_id, "is_read": False})
        except Exception as e:
            print(f"[DB Error] MongoDB count failed: {e}. Failing over to Mock DB.")
            use_mock_db = True
            return get_unread_count(user_id)

def mark_read(user_id, notification_id):
    """
    Marks a single notification as read.
    Checks user ownership. Returns updated doc or None if not found/unauthorized.
    """
    global use_mock_db
    if use_mock_db:
        with db_lock:
            notifs = load_mock_data(MOCK_NOTIF_FILE, [])
            found_notif = None
            for n in notifs:
                if n["_id"] == notification_id:
                    if n["user_id"] == user_id:
                        n["is_read"] = True
                        found_notif = n
                    break
            if found_notif:
                save_mock_data(MOCK_NOTIF_FILE, notifs)
                return found_notif
            return None
    else:
        try:
            try:
                query = {"_id": ObjectId(notification_id)}
            except Exception:
                # Handle invalid ObjectId string
                # If the DB has string ids, check that too
                query = {"_id": notification_id}
                
            # Check ownership first
            notif = db.notifications.find_one(query)
            if not notif:
                # Try matching string id
                query = {"_id": notification_id}
                notif = db.notifications.find_one(query)
                if not notif:
                    return None
                    
            if notif.get("user_id") != user_id:
                return None # Wrong user -> treat as not found for security (404)
                
            db.notifications.update_one(query, {"$set": {"is_read": True}})
            updated = db.notifications.find_one(query)
            return serialize_doc(updated)
        except Exception as e:
            print(f"[DB Error] MongoDB update failed: {e}. Failing over to Mock DB.")
            use_mock_db = True
            return mark_read(user_id, notification_id)

def mark_all_read(user_id):
    """
    Marks all notifications for user_id as read.
    """
    global use_mock_db
    if use_mock_db:
        with db_lock:
            notifs = load_mock_data(MOCK_NOTIF_FILE, [])
            count = 0
            for n in notifs:
                if n["user_id"] == user_id and not n["is_read"]:
                    n["is_read"] = True
                    count += 1
            if count > 0:
                save_mock_data(MOCK_NOTIF_FILE, notifs)
            return count
    else:
        try:
            result = db.notifications.update_many(
                {"user_id": user_id, "is_read": False},
                {"$set": {"is_read": True}}
            )
            return result.modified_count
        except Exception as e:
            print(f"[DB Error] MongoDB bulk update failed: {e}. Failing over to Mock DB.")
            use_mock_db = True
            return mark_all_read(user_id)

# --- Telegram Subscription Service Functions ---

def link_telegram(user_id, chat_id):
    """
    Links a customer's telegram chat_id. Writes/Updates telegram_subscriptions.
    Generates a 6-digit verification code to verify chat_id ownership (Contract Violation 2).
    """
    import random
    global use_mock_db
    verification_code = str(random.randint(100000, 999999))
    
    # Deliver verification code directly to the chat ID via Telegram (High §3.2)
    try:
        from app.services.telegram_delivery_service import send_telegram_verification_code
        send_telegram_verification_code(chat_id, verification_code)
    except Exception as e:
        import sys
        print(f"[Delivery Warning] Failed to dispatch verification code: {e}", file=sys.stderr)
        
    if use_mock_db:
        with db_lock:
            subs = load_mock_data(MOCK_TELEGRAM_FILE, [])
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            
            # Check if subscription already exists for this user
            existing_sub = None
            for s in subs:
                if s["user_id"] == user_id:
                    existing_sub = s
                    break
                    
            if existing_sub:
                existing_sub["chat_id"] = chat_id
                existing_sub["is_verified"] = False
                existing_sub["is_active"] = False
                existing_sub["verification_code"] = verification_code
                existing_sub["updated_at"] = now
                sub_to_return = existing_sub
            else:
                new_sub = {
                    "_id": f"sub_{len(subs) + 1}",
                    "user_id": user_id,
                    "chat_id": chat_id,
                    "is_verified": False,
                    "is_active": False,
                    "verification_code": verification_code,
                    "created_at": now,
                    "updated_at": now
                }
                subs.append(new_sub)
                sub_to_return = new_sub
                
            save_mock_data(MOCK_TELEGRAM_FILE, subs)
            return sub_to_return
    else:
        try:
            now = datetime.datetime.now(datetime.timezone.utc)
            query = {"user_id": user_id}
            update = {
                "$set": {
                    "chat_id": chat_id,
                    "is_verified": False,
                    "is_active": False,
                    "verification_code": verification_code,
                    "updated_at": now
                },
                "$setOnInsert": {
                    "created_at": now
                }
            }
            db.telegram_subscriptions.update_one(query, update, upsert=True)
            sub = db.telegram_subscriptions.find_one(query)
            return serialize_doc(sub)
        except Exception as e:
            print(f"[DB Error] MongoDB link failed: {e}. Failing over to Mock DB.", file=sys.stderr)
            use_mock_db = True
            return link_telegram(user_id, chat_id)

def verify_telegram(user_id, verification_code):
    """
    Verifies the Telegram chat ID ownership using the 6-digit verification code.
    If correct, sets is_verified = True and is_active = True.
    """
    global use_mock_db
    if use_mock_db:
        with db_lock:
            subs = load_mock_data(MOCK_TELEGRAM_FILE, [])
            success = False
            for s in subs:
                if s["user_id"] == user_id:
                    if str(s.get("verification_code")) == str(verification_code).strip():
                        s["is_verified"] = True
                        s["is_active"] = True
                        s["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                        success = True
                    break
            if success:
                save_mock_data(MOCK_TELEGRAM_FILE, subs)
            return success
    else:
        try:
            query = {"user_id": user_id}
            sub = db.telegram_subscriptions.find_one(query)
            if sub and str(sub.get("verification_code")) == str(verification_code).strip():
                now = datetime.datetime.now(datetime.timezone.utc)
                db.telegram_subscriptions.update_one(
                    query,
                    {"$set": {"is_verified": True, "is_active": True, "updated_at": now}}
                )
                return True
            return False
        except Exception as e:
            print(f"[DB Error] MongoDB verify failed: {e}. Failing over to Mock DB.", file=sys.stderr)
            use_mock_db = True
            return verify_telegram(user_id, verification_code)

def unlink_telegram(user_id):
    """
    Soft-deactivates the telegram subscription by setting is_active = False and is_verified = False (M-1).
    """
    global use_mock_db
    if use_mock_db:
        with db_lock:
            subs = load_mock_data(MOCK_TELEGRAM_FILE, [])
            success = False
            for s in subs:
                if s["user_id"] == user_id and s["is_active"]:
                    s["is_active"] = False
                    s["is_verified"] = False
                    s["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    success = True
                    break
            if success:
                save_mock_data(MOCK_TELEGRAM_FILE, subs)
            return success
    else:
        try:
            now = datetime.datetime.now(datetime.timezone.utc)
            result = db.telegram_subscriptions.update_one(
                {"user_id": user_id, "is_active": True},
                {"$set": {"is_active": False, "is_verified": False, "updated_at": now}}
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"[DB Error] MongoDB unlink failed: {e}. Failing over to Mock DB.", file=sys.stderr)
            use_mock_db = True
            return unlink_telegram(user_id)

def get_telegram_status(user_id):
    """
    Returns the telegram subscription status for a user: { chat_id, is_active, is_verified, verification_code } or None.
    """
    global use_mock_db
    if use_mock_db:
        subs = load_mock_data(MOCK_TELEGRAM_FILE, [])
        for s in subs:
            if s["user_id"] == user_id:
                return {
                    "chat_id": s["chat_id"],
                    "is_active": s["is_active"],
                    "is_verified": s.get("is_verified", False),
                    "verification_code": s.get("verification_code")
                }
        return None
    else:
        try:
            sub = db.telegram_subscriptions.find_one({"user_id": user_id})
            if sub:
                return {
                    "chat_id": sub.get("chat_id"),
                    "is_active": sub.get("is_active", True),
                    "is_verified": sub.get("is_verified", False),
                    "verification_code": sub.get("verification_code")
                }
            return None
        except Exception as e:
            print(f"[DB Error] MongoDB get status failed: {e}. Failing over to Mock DB.", file=sys.stderr)
            use_mock_db = True
            return get_telegram_status(user_id)

# Helper function to create an in-app notification (useful for tests or integration)
def create_notification(user_id, message, order_id=None):
    global use_mock_db
    if use_mock_db:
        with db_lock:
            notifs = load_mock_data(MOCK_NOTIF_FILE, [])
            new_notif = {
                "_id": f"notif_{len(notifs) + 1}",
                "user_id": user_id,
                "order_id": order_id,
                "message": message,
                "is_read": False,
                "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
            notifs.append(new_notif)
            save_mock_data(MOCK_NOTIF_FILE, notifs)
            return new_notif
    else:
        try:
            new_notif = {
                "user_id": user_id,
                "order_id": order_id,
                "message": message,
                "is_read": False,
                "created_at": datetime.datetime.now(datetime.timezone.utc)
            }
            result = db.notifications.insert_one(new_notif)
            new_notif["_id"] = str(result.inserted_id)
            new_notif["created_at"] = new_notif["created_at"].isoformat()
            return new_notif
        except Exception as e:
            print(f"[DB Error] MongoDB insert failed: {e}. Failing over to Mock DB.")
            use_mock_db = True
            return create_notification(user_id, message, order_id)
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
