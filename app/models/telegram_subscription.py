import datetime
# pyrefly: ignore [missing-import]
from bson import ObjectId
# pyrefly: ignore [missing-import]
from pymongo import ASCENDING

def validate_telegram_subscription(data):
    """
    Validates a telegram subscription document for data integrity.
    Raises ValueError if validation fails.
    """
    required_fields = ["user_id", "chat_id"]
    for field in required_fields:
        if field not in data or data[field] is None:
            raise ValueError(f"Missing required field: '{field}'")

    if not isinstance(data["user_id"], (ObjectId, str)):
        raise ValueError("Field 'user_id' must be an instance of ObjectId or a string representation of one.")
    if isinstance(data["user_id"], str):
        if not ObjectId.is_valid(data["user_id"].strip()):
            raise ValueError("Field 'user_id' is a string but is not a valid ObjectId format.")

    if not isinstance(data["chat_id"], str) or not data["chat_id"].strip():
        raise ValueError("Field 'chat_id' must be a non-empty string.")

    if "is_active" in data and not isinstance(data["is_active"], bool):
        raise ValueError("Field 'is_active' must be a boolean.")

    if "linked_at" in data and not isinstance(data["linked_at"], datetime.datetime):
        raise ValueError("Field 'linked_at' must be a datetime object.")

    return True

def create_telegram_subscription_indexes(db):
    """
    Ensures unique index on user_id inside 'telegram_subscriptions' collection.
    Only allows one subscription mapping per user.
    """
    collection = db["telegram_subscriptions"]
    index_name = "user_id_unique_idx"
    collection.create_index(
        [("user_id", ASCENDING)],
        name=index_name,
        unique=True
    )
    return index_name

def prepare_telegram_subscription(data):
    """
    Sanitizes types, converts string user_id to ObjectId,
    and populates default values for insertion.
    """
    validate_telegram_subscription(data)
    
    doc = {
        "user_id": ObjectId(data["user_id"].strip()) if isinstance(data["user_id"], str) else data["user_id"],
        "chat_id": data["chat_id"].strip(),
        "is_active": data.get("is_active", True),
        "linked_at": data.get("linked_at") or datetime.datetime.now(datetime.timezone.utc)
    }
    
    return doc
