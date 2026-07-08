import datetime
import json
import os
import sys
import threading
import pathlib
from flask import request

_audit_lock = threading.Lock()

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent.parent.parent
AUDIT_LOG_FILE = os.path.join(os.getenv("MOCK_DATA_DIR", str(BASE_DIR / "scratch")), "mock_audit.log")

def log_audit_event(user_id, role, action, status, details=None):
    """
    Writes an audit entry for security compliance.
    Logs event time, subject ID, subject role, action, execution status, client IP, and contextual metadata.
    """
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    ip_addr = "0.0.0.0"
    try:
        # Check if running in a Flask request context
        if request:
            ip_addr = request.headers.get("X-Forwarded-For", request.remote_addr) or "0.0.0.0"
            # Extract first IP in list if proxy header is comma separated
            if "," in ip_addr:
                ip_addr = ip_addr.split(",")[0].strip()
    except RuntimeError:
        # Flask request context is unavailable (e.g. standard thread execution or testing setup)
        pass
        
    audit_entry = {
        "timestamp": timestamp,
        "user_id": user_id,
        "role": role,
        "action": action,
        "status": status,
        "client_ip": ip_addr,
        "details": details or {}
    }
    
    # Console print standard format
    log_msg = f"[AUDIT] [{timestamp}] User: {user_id} ({role}) | Action: {action} | Status: {status} | IP: {ip_addr} | Details: {json.dumps(details or {})}"
    print(log_msg)
    
    # Append to structured json-lines mock_audit.log file in a thread-safe manner
    with _audit_lock:
        try:
            os.makedirs(os.path.dirname(AUDIT_LOG_FILE), exist_ok=True)
            with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(audit_entry) + "\n")
        except Exception as e:
            print(f"[Audit Error] Failed to write log file: {e}", file=sys.stderr)
