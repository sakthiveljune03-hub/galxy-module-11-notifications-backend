import os
import sys
import json
import datetime
from bson import ObjectId

# Add current directory to python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Simple In-Memory Mock Database to simulate PyMongo collections
class MockCollection:
    def __init__(self, name):
        self.name = name
        self.documents = []

    def insert_one(self, doc):
        if "_id" not in doc:
            doc["_id"] = ObjectId()
        self.documents.append(doc)
        
        # Simulating PyMongo's InsertOneResult
        class InsertOneResult:
            def __init__(self, inserted_id):
                self.inserted_id = inserted_id
        return InsertOneResult(doc["_id"])

    def find_one(self, query):
        for doc in self.documents:
            match = True
            for k, v in query.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                return doc
        return None

    def find(self, query):
        results = []
        for doc in self.documents:
            match = True
            for k, v in query.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                results.append(doc)
        
        # Mock cursor functionality for sorting and pagination
        class MockCursor:
            def __init__(self, items):
                self.items = items
            def sort(self, key, direction=1):
                # Simple sort by created_at DESC
                self.items.sort(key=lambda x: x.get(key, datetime.datetime.min), reverse=(direction == -1))
                return self
            def skip(self, count):
                self.items = self.items[count:]
                return self
            def limit(self, count):
                self.items = self.items[:count]
                return self
            def __iter__(self):
                return iter(self.items)
        return MockCursor(results)

    def count_documents(self, query):
        count = 0
        for doc in self.documents:
            match = True
            for k, v in query.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                count += 1
        return count

    def update_one(self, query, update, upsert=False):
        doc = self.find_one(query)
        modified_count = 0
        matched_count = 0
        
        # Simulating PyMongo's UpdateResult
        class UpdateResult:
            def __init__(self, matched, modified, upserted_id=None):
                self.matched_count = matched
                self.modified_count = modified
                self.upserted_id = upserted_id

        if doc:
            matched_count = 1
            if "$set" in update:
                for k, v in update["$set"].items():
                    doc[k] = v
                modified_count = 1
            return UpdateResult(matched_count, modified_count)
            
        if upsert:
            new_doc = query.copy()
            if "$set" in update:
                new_doc.update(update["$set"])
            self.insert_one(new_doc)
            return UpdateResult(0, 0, new_doc["_id"])
            
        return UpdateResult(0, 0)

    def update_many(self, query, update):
        modified_count = 0
        for doc in self.documents:
            match = True
            for k, v in query.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                if "$set" in update:
                    for k, v in update["$set"].items():
                        doc[k] = v
                    modified_count += 1
                    
        class UpdateManyResult:
            def __init__(self, modified):
                self.modified_count = modified
        return UpdateManyResult(modified_count)

    def create_index(self, keys, name=None, unique=False):
        pass


class MockDatabase:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        if name not in self.collections:
            self.collections[name] = MockCollection(name)
        return self.collections[name]

    def command(self, cmd):
        return {"ok": 1.0}


# Instantiate our Mock database
mock_db_instance = MockDatabase()

# Patch get_db to return our in-memory database
import app.services.notification_service
app.services.notification_service.get_db = lambda: mock_db_instance

from app.services.notification_service import (
    notify_user,
    list_notifications,
    get_unread_count,
    mark_as_read,
    mark_all_as_read,
    subscribe_telegram
)

def run_mock_demo():
    print("=" * 70)
    print("      GALXY NOTIFICATION SERVICE - IN-MEMORY OPERATION TESTING       ")
    print("=" * 70)
    
    mock_user_id = ObjectId()
    print(f"Generated test User ID: {mock_user_id}")
    
    # 1. Subscribe user to Telegram
    print("\n[Step 1] Creating a Telegram Subscription for the User:")
    sub_res = subscribe_telegram(mock_user_id, chat_id="telegram_user_chat_101")
    print(f"Result: {sub_res}")
    
    # 2. Trigger notification 1 (only in-app and email)
    print("\n[Step 2] Triggering notification 1 (In-App + Email):")
    res1 = notify_user(
        user_id=mock_user_id,
        notification_type="order_created",
        title="Order Inquiry Placed",
        message="Your design inquiry has been submitted. Estimated quote: INR 2,500.",
        related_order_number="GLX-2026-0099",
        send_email=True,
        send_telegram=False
    )
    print(f"Result: {res1}")
    
    # 3. Trigger notification 2 (in-app + Telegram)
    print("\n[Step 3] Triggering notification 2 (In-App + Telegram):")
    res2 = notify_user(
        user_id=mock_user_id,
        notification_type="order_status_changed",
        title="Order In Production",
        message="Your Neon Name Sign is currently being bent and mounted in our craft studio.",
        related_order_number="GLX-2026-0099",
        send_email=False,
        send_telegram=True
    )
    print(f"Result: {res2}")
    
    # 4. Count unread notifications
    print("\n[Step 4] Checking unread notifications count:")
    count = get_unread_count(mock_user_id)
    print(f"Count: {count} unread notifications (Expect: 2)")
    
    # 5. Fetch notification feed list
    print("\n[Step 5] Retrieving user notification feed:")
    feed = list_notifications(mock_user_id, page=1, limit=5)
    print("Feed output:")
    for notif in feed["data"]:
        print(f" - [{notif['type']}] {notif['title']}: {notif['message']} (Read: {notif['is_read']})")
    
    # 6. Mark first notification as read
    target_id = feed["data"][0]["id"]
    print(f"\n[Step 6] Marking single notification {target_id} as read:")
    read_res = mark_as_read(mock_user_id, target_id)
    print(f"Result: {read_res}")
    
    # Verify count decremented
    count_after = get_unread_count(mock_user_id)
    print(f"Count after single read: {count_after} (Expect: 1)")
    
    # 7. Mark all remaining read
    print("\n[Step 7] Bulk marking all notifications as read:")
    bulk_res = mark_all_as_read(mock_user_id)
    print(f"Result: {bulk_res}")
    
    # Verify count is 0
    count_final = get_unread_count(mock_user_id)
    print(f"Final Count: {count_final} (Expect: 0)")
    
    print("\n" + "=" * 70)
    print(" IN-MEMORY OPERATIONS VERIFIED SUCCESSFULLY ")
    print("=" * 70)

if __name__ == '__main__':
    run_mock_demo()
