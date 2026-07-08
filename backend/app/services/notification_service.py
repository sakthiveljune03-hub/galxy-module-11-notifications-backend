import logging
import os
import json
import datetime
import pathlib
import sys
import threading

# Configuration
from app.configs.config import Config

# Setup Logger
logger = logging.getLogger("notification_service")
if not logger.hasHandlers():
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    logger.setLevel(log_level)
    handler = logging.StreamHandler()
    formatter = logging.Formatter('[%(asctime)s] %(levelname)s in %(module)s: %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# Attempt to import PyMongo and BSON
try:
    from bson import ObjectId
    from pymongo import MongoClient, DESCENDING, ASCENDING
    from pymongo.errors import ConnectionFailure
    pymongo_available = True
except ImportError:
    class ObjectId:
        def __init__(self, o=None):
            self.o = o if o else "mock_id"
        def __str__(self):
            return str(self.o)
        def __repr__(self):
            return f"ObjectId('{self.o}')"
        @staticmethod
        def is_valid(val):
            return isinstance(val, str) and len(val) == 24
            
    class ConnectionFailure(Exception):
        pass
        
    class MongoClient:
        def __init__(self, *args, **kwargs):
            raise ConnectionFailure("pymongo is not installed in this environment.")
            
    DESCENDING = -1
    ASCENDING = 1
    pymongo_available = False

# Import delivery service helpers
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
    send_telegram_notification,
)

# Import send_email_notification at module level for unittest patches
from app.services.email_service import send_email_notification

# Shared DB Connection
from app.database import get_db
from app.models.notification import prepare_notification, create_notification_indexes
from app.models.telegram_subscription import prepare_telegram_subscription, create_telegram_subscription_indexes

# Global Database Configuration & Mock database fallback
_mongo_client = None
db = None
use_mock_db = True
db_lock = threading.RLock()

try:
    if pymongo_available:
        _mongo_client = MongoClient(Config.MONGO_URI, serverSelectionTimeoutMS=2000)
        _mongo_client.admin.command('ping')
        db = _mongo_client[Config.DATABASE_NAME]
        
        # Run database migration checks
        from app.db.migrations import run_migrations
        run_migrations(db)
        use_mock_db = False
        print("[DB] Connected successfully to MongoDB.")
except (ConnectionFailure, Exception) as e:
    print(f"[DB] MongoDB connection failed at startup: {e}. Falling back to Mock Memory DB.")
    use_mock_db = True

def _should_use_mock_file():
    global use_mock_db
    if not use_mock_db:
        return False
    try:
        current_db = get_db()
        if current_db is None:
            return True
        db_type_name = type(current_db).__name__
        if db_type_name in ('MockDatabase', 'Mock', 'MagicMock'):
            return False
    except Exception:
        pass
    return True

# Mock DB Data Store Configuration
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

# Index Creation Helper
_indexes_created = False

def ensure_indexes():
    global _indexes_created
    if _indexes_created or use_mock_db:
        return
    try:
        current_db = get_db()
        create_notification_indexes(current_db)
        create_telegram_subscription_indexes(current_db)
        _indexes_created = True
    except Exception as e:
        logger.error(f"Failed to create database indexes: {str(e)}")

# --- Core Service Logic - Ajay's Flow ---

def _notify_user_ajay(
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

# --- Core Service Logic - Sakthivel's Flow ---

def _notify_user_sakthivel(
    user_id,
    notification_type,
    title,
    message,
    related_order_number=None,
    related_product_id=None,
    send_email=False,
    send_telegram=False
):
    ensure_indexes()
    
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
    
    # Validation checks
    sanitized_doc = prepare_notification(doc_data)
    
    # 2. Insert into local notifications collection
    result_doc = create_notification(
        user_id=sanitized_doc["user_id"],
        message=sanitized_doc["message"],
        order_id=sanitized_doc.get("related_order_number")
    )
    notification_id = result_doc["_id"]
    
    # Mock fallback support
    
    # 3. Handle Email Dispatch
    email_sent = False
    if send_email:
        try:
            email_sent = send_email_notification(str(user_id), title, message)
            logger.info(f"Email dispatch request completed for user {user_id}: status={email_sent}")
        except Exception as e:
            logger.error(f"Error dispatching email to user {user_id}: {str(e)}")
            
    # 4. Handle Telegram Dispatch
    telegram_sent = False
    if send_telegram:
        try:
            chat_id = None
            if _should_use_mock_file():
                status = get_telegram_status(user_id)
                if status and status.get("is_active"):
                    chat_id = status["chat_id"]
            else:
                sub = get_db()["telegram_subscriptions"].find_one({
                    "user_id": sanitized_doc["user_id"],
                    "is_active": True
                })
                if sub:
                    chat_id = sub.get("chat_id")
            
            if chat_id:
                telegram_sent = send_telegram_notification(chat_id, title, message)
                logger.info(f"Telegram dispatch request completed for user {user_id}: status={telegram_sent}")
            else:
                logger.info(f"No active telegram subscription for user {user_id} - skipping telegram delivery.")
        except Exception as e:
            logger.error(f"Error dispatching Telegram message to user {user_id}: {str(e)}")
            
    return {
        "notification_id": notification_id,
        "in_app": True,
        "email_dispatched": email_sent,
        "telegram_dispatched": telegram_sent
    }

# --- Router function ---

def notify_user(*args, **kwargs):
    is_ajay = False
    if len(args) >= 2 and isinstance(args[1], dict):
        is_ajay = True
    elif 'event_type' in kwargs or 'recipient' in kwargs or 'event_data' in kwargs:
        is_ajay = True
        
    if is_ajay:
        event_type = kwargs.get('event_type') or (args[0] if len(args) > 0 else None)
        recipient = kwargs.get('recipient') or (args[1] if len(args) > 1 else None)
        event_data = kwargs.get('event_data') or (args[2] if len(args) > 2 else {})
        smtp_sender = kwargs.get('smtp_sender') or (args[3] if len(args) > 3 else None)
        subscriptions_collection = kwargs.get('subscriptions_collection') or (args[4] if len(args) > 4 else None)
        send_email = kwargs.get('send_email', True if len(args) <= 5 else args[5])
        send_telegram = kwargs.get('send_telegram', True if len(args) <= 6 else args[6])
        
        return _notify_user_ajay(
            event_type=event_type,
            recipient=recipient,
            event_data=event_data,
            smtp_sender=smtp_sender,
            subscriptions_collection=subscriptions_collection,
            send_email=send_email,
            send_telegram=send_telegram
        )
    else:
        user_id = kwargs.get('user_id') or (args[0] if len(args) > 0 else None)
        notification_type = kwargs.get('notification_type') or (args[1] if len(args) > 1 else None)
        title = kwargs.get('title') or (args[2] if len(args) > 2 else None)
        message = kwargs.get('message') or (args[3] if len(args) > 3 else None)
        related_order_number = kwargs.get('related_order_number') or (args[4] if len(args) > 4 else None)
        related_product_id = kwargs.get('related_product_id') or (args[5] if len(args) > 5 else None)
        send_email = kwargs.get('send_email', False if len(args) <= 6 else args[6])
        send_telegram = kwargs.get('send_telegram', False if len(args) <= 7 else args[7])
        
        return _notify_user_sakthivel(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            related_order_number=related_order_number,
            related_product_id=related_product_id,
            send_email=send_email,
            send_telegram=send_telegram
        )

# --- Service API Implementation with Mock DB Compatibility ---

def get_notifications_feed(user_id, page=1, limit=10, is_read=None):
    global use_mock_db
    if _should_use_mock_file():
        notifs = load_mock_data(MOCK_NOTIF_FILE, [])
        user_notifs = [n for n in notifs if n["user_id"] == user_id]
        unread_count = len([n for n in user_notifs if not n["is_read"]])
        
        filtered_notifs = list(user_notifs)
        if is_read is not None:
            filtered_notifs = [n for n in filtered_notifs if n["is_read"] == is_read]
            
        filtered_notifs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        total = len(filtered_notifs)
        start = (page - 1) * limit
        end = start + limit
        paginated_data = filtered_notifs[start:end]
        
        total_pages = (total + limit - 1) // limit if total > 0 else 0
        return paginated_data, total, total_pages, unread_count
    else:
        try:
            ensure_indexes()
            match_stage = {"user_id": user_id}
            
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
            
            result = list(get_db()["notifications"].aggregate([
                {"$match": match_stage},
                {"$facet": facet_stage}
            ]))
            
            facet_data = result[0] if result else {}
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
    global use_mock_db
    if _should_use_mock_file():
        notifs = load_mock_data(MOCK_NOTIF_FILE, [])
        return len([n for n in notifs if n["user_id"] == user_id and not n["is_read"]])
    else:
        try:
            ensure_indexes()
            parsed_user_id = ObjectId(user_id) if isinstance(user_id, str) and ObjectId.is_valid(user_id) else user_id
            return get_db()["notifications"].count_documents({"user_id": parsed_user_id, "is_read": False})
        except Exception as e:
            print(f"[DB Error] MongoDB count failed: {e}. Failing over to Mock DB.")
            use_mock_db = True
            return get_unread_count(user_id)


def mark_read(user_id, notification_id):
    global use_mock_db
    if _should_use_mock_file():
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
            ensure_indexes()
            try:
                query = {"_id": ObjectId(notification_id)}
            except Exception:
                query = {"_id": notification_id}
                
            notif = get_db()["notifications"].find_one(query)
            if not notif:
                query = {"_id": notification_id}
                notif = get_db()["notifications"].find_one(query)
                if not notif:
                    return None
                    
            if notif.get("user_id") != user_id:
                return None
                
            get_db()["notifications"].update_one(query, {"$set": {"is_read": True}})
            updated = get_db()["notifications"].find_one(query)
            return serialize_doc(updated)
        except Exception as e:
            print(f"[DB Error] MongoDB update failed: {e}. Failing over to Mock DB.")
            use_mock_db = True
            return mark_read(user_id, notification_id)


def mark_all_read(user_id):
    global use_mock_db
    if _should_use_mock_file():
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
            ensure_indexes()
            result = get_db()["notifications"].update_many(
                {"user_id": user_id, "is_read": False},
                {"$set": {"is_read": True}}
            )
            return result.modified_count
        except Exception as e:
            print(f"[DB Error] MongoDB bulk update failed: {e}. Failing over to Mock DB.")
            use_mock_db = True
            return mark_all_read(user_id)


def link_telegram(user_id, chat_id):
    import random
    global use_mock_db
    verification_code = str(random.randint(100000, 999999))
    
    try:
        from app.services.telegram_delivery_service import send_telegram_verification_code
        send_telegram_verification_code(chat_id, verification_code)
    except Exception as e:
        print(f"[Delivery Warning] Failed to dispatch verification code: {e}", file=sys.stderr)
        
    if _should_use_mock_file():
        with db_lock:
            subs = load_mock_data(MOCK_TELEGRAM_FILE, [])
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            
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
            ensure_indexes()
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
            get_db()["telegram_subscriptions"].update_one(query, update, upsert=True)
            sub = get_db()["telegram_subscriptions"].find_one(query)
            return serialize_doc(sub)
        except Exception as e:
            print(f"[DB Error] MongoDB link failed: {e}. Failing over to Mock DB.", file=sys.stderr)
            use_mock_db = True
            return link_telegram(user_id, chat_id)


def verify_telegram(user_id, verification_code):
    global use_mock_db
    if _should_use_mock_file():
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
            ensure_indexes()
            query = {"user_id": user_id}
            sub = get_db()["telegram_subscriptions"].find_one(query)
            if sub and str(sub.get("verification_code")) == str(verification_code).strip():
                now = datetime.datetime.now(datetime.timezone.utc)
                get_db()["telegram_subscriptions"].update_one(
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
    global use_mock_db
    if _should_use_mock_file():
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
            ensure_indexes()
            now = datetime.datetime.now(datetime.timezone.utc)
            result = get_db()["telegram_subscriptions"].update_one(
                {"user_id": user_id, "is_active": True},
                {"$set": {"is_active": False, "is_verified": False, "updated_at": now}}
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"[DB Error] MongoDB unlink failed: {e}. Failing over to Mock DB.", file=sys.stderr)
            use_mock_db = True
            return unlink_telegram(user_id)


def get_telegram_status(user_id):
    global use_mock_db
    if _should_use_mock_file():
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
            ensure_indexes()
            sub = get_db()["telegram_subscriptions"].find_one({"user_id": user_id})
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


def create_notification(user_id, message, order_id=None):
    global use_mock_db
    if _should_use_mock_file():
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
            ensure_indexes()
            parsed_user_id = ObjectId(user_id) if isinstance(user_id, str) and ObjectId.is_valid(user_id) else user_id
            new_notif = {
                "user_id": parsed_user_id,
                "order_id": order_id,
                "message": message,
                "is_read": False,
                "created_at": datetime.datetime.now(datetime.timezone.utc)
            }
            result = get_db()["notifications"].insert_one(new_notif)
            ret_notif = dict(new_notif)
            ret_notif["_id"] = str(result.inserted_id)
            if isinstance(ret_notif["created_at"], datetime.datetime):
                ret_notif["created_at"] = ret_notif["created_at"].isoformat()
            return ret_notif
        except Exception as e:
            print(f"[DB Error] MongoDB insert failed: {e}. Failing over to Mock DB.")
            use_mock_db = True
            return create_notification(user_id, message, order_id)


# --- Backward Compatibility Wrapper Functions (Old API Specs) ---

def list_notifications(user_id, is_read=None, page=1, limit=20):
    global use_mock_db
    if _should_use_mock_file():
        paginated_data, total, total_pages, unread_count = get_notifications_feed(user_id, page, limit, is_read)
        formatted_data = []
        for item in paginated_data:
            formatted_data.append({
                "id": str(item["_id"]),
                "user_id": str(item["user_id"]),
                "type": item.get("type", "general"),
                "title": item.get("title", ""),
                "message": item.get("message", ""),
                "related_order_number": item.get("order_id") or item.get("related_order_number"),
                "related_product_id": item.get("related_product_id"),
                "is_read": item["is_read"],
                "created_at": item.get("created_at")
            })
        return {
            "success": True,
            "data": formatted_data,
            "page": page,
            "limit": limit,
            "total": total,
            "totalPages": total_pages
        }
    else:
        ensure_indexes()
        current_db = get_db()
        try:
            parsed_user_id = ObjectId(user_id) if isinstance(user_id, str) and ObjectId.is_valid(user_id) else user_id
        except Exception:
            raise ValueError("Invalid user_id format.")
            
        query = {"user_id": parsed_user_id}
        if is_read is not None:
            if not isinstance(is_read, bool):
                raise ValueError("is_read filter must be a boolean.")
            query["is_read"] = is_read
            
        page = max(1, int(page))
        limit = min(max(1, int(limit)), 100)
        skip = (page - 1) * limit
        
        collection = current_db["notifications"]
        total = collection.count_documents(query)
        cursor = collection.find(query).sort("created_at", DESCENDING).skip(skip).limit(limit)
        
        notifications = []
        for item in cursor:
            notifications.append({
                "id": str(item["_id"]),
                "user_id": str(item["user_id"]),
                "type": item.get("type", "general"),
                "title": item.get("title", ""),
                "message": item.get("message"),
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
    global use_mock_db
    if _should_use_mock_file():
        updated = mark_read(user_id, notification_id)
        return {
            "success": True,
            "modified_count": 1 if updated else 0,
            "found": updated is not None
        }
    else:
        ensure_indexes()
        current_db = get_db()
        try:
            parsed_user_id = ObjectId(user_id) if isinstance(user_id, str) and ObjectId.is_valid(user_id) else user_id
            parsed_notification_id = ObjectId(notification_id) if isinstance(notification_id, str) and ObjectId.is_valid(notification_id) else notification_id
        except Exception:
            raise ValueError("Invalid format for user_id or notification_id.")
            
        result = current_db["notifications"].update_one(
            {"_id": parsed_notification_id, "user_id": parsed_user_id},
            {"$set": {"is_read": True}}
        )
        return {
            "success": True,
            "modified_count": result.modified_count,
            "found": result.matched_count > 0
        }


def mark_all_as_read(user_id):
    global use_mock_db
    if _should_use_mock_file():
        modified = mark_all_read(user_id)
        return {
            "success": True,
            "modified_count": modified
        }
    else:
        ensure_indexes()
        current_db = get_db()
        try:
            parsed_user_id = ObjectId(user_id) if isinstance(user_id, str) and ObjectId.is_valid(user_id) else user_id
        except Exception:
            raise ValueError("Invalid user_id format.")
            
        result = current_db["notifications"].update_many(
            {"user_id": parsed_user_id, "is_read": False},
            {"$set": {"is_read": True}}
        )
        return {
            "success": True,
            "modified_count": result.modified_count
        }


def subscribe_telegram(user_id, chat_id):
    global use_mock_db
    if _should_use_mock_file():
        sub = link_telegram(user_id, chat_id)
        with db_lock:
            subs = load_mock_data(MOCK_TELEGRAM_FILE, [])
            for s in subs:
                if s["user_id"] == user_id:
                    s["is_verified"] = True
                    s["is_active"] = True
                    break
            save_mock_data(MOCK_TELEGRAM_FILE, subs)
        return {
            "success": True,
            "upserted_id": sub.get("_id"),
            "modified_count": 1
        }
    else:
        ensure_indexes()
        current_db = get_db()
        try:
            parsed_user_id = ObjectId(user_id) if isinstance(user_id, str) and ObjectId.is_valid(user_id) else user_id
        except Exception:
            parsed_user_id = user_id
            
        sub_data = {
            "user_id": parsed_user_id,
            "chat_id": chat_id,
            "is_active": True,
            "linked_at": datetime.datetime.now(datetime.timezone.utc)
        }
        sanitized_sub = prepare_telegram_subscription(sub_data)
        result = current_db["telegram_subscriptions"].update_one(
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
    global use_mock_db
    if _should_use_mock_file():
        unlink_telegram(user_id)
        return {
            "success": True,
            "modified_count": 1
        }
    else:
        ensure_indexes()
        current_db = get_db()
        try:
            parsed_user_id = ObjectId(user_id) if isinstance(user_id, str) and ObjectId.is_valid(user_id) else user_id
        except Exception:
            raise ValueError("Invalid user_id format.")
            
        result = current_db["telegram_subscriptions"].update_one(
            {"user_id": parsed_user_id},
            {"$set": {"is_active": False}}
        )
        return {
            "success": True,
            "modified_count": result.modified_count
        }
