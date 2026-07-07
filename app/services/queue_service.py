import queue
import threading
import sys
from app.services.email_service import send_email_notification
from app.services.telegram_delivery_service import send_telegram_notification

# Thread-safe in-memory task queue
_notification_queue = queue.Queue()
_worker_thread = None
_lock = threading.Lock()

def _worker():
    """Background daemon thread worker processing notification dispatches."""
    while True:
        try:
            job = _notification_queue.get()
            if job is None:
                _notification_queue.task_done()
                break
                
            job_type = job.get("type")
            user_id = job.get("user_id")
            message = job.get("message")
            order_id = job.get("order_id")
            
            if job_type == "email":
                try:
                    send_email_notification(user_id, message, order_id)
                except Exception as e:
                    print(f"[Queue Error] Background email dispatch failed: {e}", file=sys.stderr)
            elif job_type == "telegram":
                try:
                    send_telegram_notification(user_id, message, order_id)
                except Exception as e:
                    print(f"[Queue Error] Background Telegram dispatch failed: {e}", file=sys.stderr)
            
            _notification_queue.task_done()
        except Exception as queue_err:
            print(f"[Queue Error] Exception in background daemon: {queue_err}", file=sys.stderr)

def start_queue_worker():
    """Starts the background worker thread if not already running."""
    global _worker_thread
    with _lock:
        if _worker_thread is None or not _worker_thread.is_alive():
            _worker_thread = threading.Thread(target=_worker, daemon=True)
            _worker_thread.start()
            print("[Queue] Background daemon notification worker started successfully.")

def enqueue_notification_jobs(user_id, message, order_id=None):
    """Enqueues notification dispatches to background tasks so they run asynchronously."""
    # Ensure worker is active
    start_queue_worker()
    
    # Enqueue Email job
    _notification_queue.put({
        "type": "email",
        "user_id": user_id,
        "message": message,
        "order_id": order_id
    })
    
    # Enqueue Telegram job
    _notification_queue.put({
        "type": "telegram",
        "user_id": user_id,
        "message": message,
        "order_id": order_id
    })
