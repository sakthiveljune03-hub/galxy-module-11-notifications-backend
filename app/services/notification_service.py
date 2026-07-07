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
