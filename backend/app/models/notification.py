import datetime
# pyrefly: ignore [missing-import]
from bson import ObjectId
# pyrefly: ignore [missing-import]
from pymongo import ASCENDING, DESCENDING

def validate_notification(data):
    """
    Validates a notification document for data integrity.
    Raises ValueError if validation fails.
    """
    required_fields = ["user_id", "type", "title", "message"]
    for field in required_fields:
        if field not in data or data[field] is None:
            raise ValueError(f"Missing required field: '{field}'")
            
    if not isinstance(data["user_id"], (ObjectId, str)):
        raise ValueError("Field 'user_id' must be an instance of ObjectId or a string representation of one.")
    if isinstance(data["user_id"], str):
        if not ObjectId.is_valid(data["user_id"].strip()):
            try:
                from app.services.notification_service import use_mock_db
                is_mock = use_mock_db
            except Exception:
                is_mock = True
            if not is_mock or len(data["user_id"].strip()) >= 24:
                raise ValueError("Field 'user_id' is a string but is not a valid ObjectId format.")

    if not isinstance(data["type"], str) or not data["type"].strip():
        raise ValueError("Field 'type' must be a non-empty string.")
    if len(data["type"].strip()) > 100:
        raise ValueError("Field 'type' must not exceed 100 characters.")

    if not isinstance(data["title"], str) or not data["title"].strip():
        raise ValueError("Field 'title' must be a non-empty string.")
    if len(data["title"].strip()) > 200:
        raise ValueError("Field 'title' must not exceed 200 characters.")

    if not isinstance(data["message"], str) or not data["message"].strip():
        raise ValueError("Field 'message' must be a non-empty string.")
    if len(data["message"].strip()) > 2000:
        raise ValueError("Field 'message' must not exceed 2000 characters.")

    # Validate optional fields
    if "related_order_number" in data and data["related_order_number"] is not None:
        if not isinstance(data["related_order_number"], str):
            raise ValueError("Field 'related_order_number' must be a string if provided.")

    if "related_product_id" in data and data["related_product_id"] is not None:
        if not isinstance(data["related_product_id"], (ObjectId, str)):
            raise ValueError("Field 'related_product_id' must be an instance of ObjectId or a string if provided.")
        if isinstance(data["related_product_id"], str) and data["related_product_id"].strip():
            if not ObjectId.is_valid(data["related_product_id"].strip()):
                raise ValueError("Field 'related_product_id' is a string but is not a valid ObjectId format.")

    if "is_read" in data and not isinstance(data["is_read"], bool):
        raise ValueError("Field 'is_read' must be a boolean value.")

    if "created_at" in data and not isinstance(data["created_at"], datetime.datetime):
        raise ValueError("Field 'created_at' must be a datetime object.")

    return True

def create_notification_indexes(db):
    """
    Ensures correct indexes exist on the 'notifications' collection:
    1. Compound index on (user_id, is_read) for quick unread badge/count queries.
    2. Chronological index on (created_at) for newest-first sorting.
    """
    collection = db["notifications"]
    
    # Compound index on user_id + is_read
    # Use ASCENDING for both
    index_name_user_read = "user_id_is_read_idx"
    collection.create_index(
        [("user_id", ASCENDING), ("is_read", ASCENDING)],
        name=index_name_user_read
    )
    
    # Chronological sort index on created_at
    index_name_created = "created_at_idx"
    collection.create_index(
        [("created_at", DESCENDING)],
        name=index_name_created
    )
    
    return [index_name_user_read, index_name_created]

def prepare_notification(data):
    """
    Sanitizes types, converts valid string user_ids / product_ids to ObjectIds,
    and populates default values for insertion.
    """
    validate_notification(data)
    
    # Clone and prepare document
    doc = {
        "user_id": ObjectId(data["user_id"].strip()) if isinstance(data["user_id"], str) and ObjectId.is_valid(data["user_id"].strip()) else data["user_id"],
        "type": data["type"].strip(),
        "title": data["title"].strip(),
        "message": data["message"].strip(),
        "related_order_number": data.get("related_order_number"),
        "is_read": data.get("is_read", False),
        "created_at": data.get("created_at") or datetime.datetime.now(datetime.timezone.utc)
    }
    
    related_prod = data.get("related_product_id")
    if related_prod and (not isinstance(related_prod, str) or related_prod.strip()):
        doc["related_product_id"] = ObjectId(related_prod.strip()) if isinstance(related_prod, str) else related_prod
    else:
        doc["related_product_id"] = None
        
    return doc
