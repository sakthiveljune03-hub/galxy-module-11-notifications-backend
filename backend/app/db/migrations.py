import sys

def run_migrations(db):
    """
    Performs initial schema index creation and validation checks for MongoDB.
    Acts as the canonical database migration runner.
    """
    print("[Migrations] Starting database migration checks...")
    try:
        # 1. Indexing on notifications collection
        # Index for fetching feed (sorted by created_at desc)
        notif_idx_1 = db.notifications.create_index([("user_id", 1), ("created_at", -1)])
        print(f"[Migrations] Verified feed index user_id/created_at: {notif_idx_1}")
        
        # Index for filtering unread counts
        notif_idx_2 = db.notifications.create_index([("user_id", 1), ("is_read", 1)])
        print(f"[Migrations] Verified filter index user_id/is_read: {notif_idx_2}")
        
        # 2. Indexing on telegram_subscriptions collection
        # Unique index on user_id to prevent duplicate bindings
        telegram_idx = db.telegram_subscriptions.create_index([("user_id", 1)], unique=True)
        print(f"[Migrations] Verified unique telegram index: {telegram_idx}")
        
        print("[Migrations] Database migration checks completed successfully.")
        return True
    except Exception as e:
        print(f"[Migrations Error] Failed to run database migrations: {e}", file=sys.stderr)
        return False
