from flask import Blueprint, request, jsonify, g
from app.utils.auth import require_auth
from app.services import notification_service as notif_service
from app.utils.audit_log import log_audit_event

import time
from collections import defaultdict

notification_bp = Blueprint("notifications", __name__)

_rate_limit_records = defaultdict(list)
RATE_LIMIT_MAX = 100  # maximum requests
RATE_LIMIT_WINDOW = 60  # seconds

@notification_bp.before_request
def rate_limit_check():
    """
    Blueprint-level rate limiter for defense-in-depth.
    Bypassed during testing.
    """
    from flask import current_app
    if current_app.config.get("TESTING"):
        return None
        
    ip = request.remote_addr or "unknown"
    now = time.time()
    
    # Clean up old timestamps outside the window
    timestamps = _rate_limit_records[ip]
    while timestamps and timestamps[0] < now - RATE_LIMIT_WINDOW:
        timestamps.pop(0)
        
    if len(timestamps) >= RATE_LIMIT_MAX:
        import sys
        print(f"[Rate Limit Exceeded] IP: {ip}", file=sys.stderr)
        return jsonify({
            "success": False,
            "message": "Too many requests. Please try again later.",
            "data": None
        }), 429
        
    timestamps.append(now)
    return None


@notification_bp.route("/api/v1/notifications", methods=["GET"])
@require_auth
def get_notifications():
    """
    GET /api/v1/notifications
    Query parameters:
      - page: int (default 1)
      - limit: int (default 10)
      - is_read: str ("true" or "false", optional)
    """
    user_id = g.user_id
    
    try:
        page = int(request.args.get("page", 1))
        if page < 1:
            page = 1
    except ValueError:
        page = 1
        
    try:
        limit = int(request.args.get("limit", 10))
        if limit < 1:
            limit = 10
        elif limit > 100:
            limit = 100
    except ValueError:
        limit = 10
        
    is_read_param = request.args.get("is_read")
    is_read_filter = None
    if is_read_param is not None:
        is_read_filter = is_read_param.lower() == "true"
        
    try:
        # Fetch notifications feed and unread count in a single aggregation pipeline
        data, total, total_pages, unread_count = notif_service.get_notifications_feed(
            user_id=user_id,
            page=page,
            limit=limit,
            is_read=is_read_filter
        )
        
        telegram_status = notif_service.get_telegram_status(user_id)
        
        log_audit_event(user_id, g.user_role, "get_notifications", "SUCCESS", {
            "page": page,
            "limit": limit,
            "is_read_filter": is_read_filter
        })
        
        return jsonify({
            "success": True,
            "message": "Notifications retrieved successfully",
            "data": data,
            "page": page,
            "limit": limit,
            "total": total,
            "totalPages": total_pages,
            "unread_count": unread_count,
            "telegram_linked": telegram_status is not None and telegram_status.get("is_verified", False),
            "telegram_chat_id": telegram_status["chat_id"] if telegram_status and telegram_status.get("is_verified", False) else None
        }), 200
        
    except Exception as e:
        import sys
        print(f"[Error] Retrieving notifications: {e}", file=sys.stderr)
        log_audit_event(user_id, g.user_role, "get_notifications", "FAILED", { "error": str(e) })
        return jsonify({
            "success": False,
            "message": "An unexpected error occurred while retrieving notifications.",
            "data": None
        }), 500


@notification_bp.route("/api/v1/notifications/<string:notification_id>/read", methods=["PUT"])
@require_auth
def mark_notification_read(notification_id):
    """
    PUT /api/v1/notifications/:id/read
    Marks a single notification as read.
    """
    user_id = g.user_id
    
    try:
        updated_notif = notif_service.mark_read(user_id, notification_id)
        if not updated_notif:
            log_audit_event(user_id, g.user_role, "read_notification", "FAILED", {
                "reason": "Notification not found or wrong user",
                "notification_id": notification_id
            })
            return jsonify({
                "success": False,
                "message": "Notification not found",
                "data": None
            }), 404
            
        unread_count = notif_service.get_unread_count(user_id)
        
        log_audit_event(user_id, g.user_role, "read_notification", "SUCCESS", { "notification_id": notification_id })
        
        return jsonify({
            "success": True,
            "message": "Notification marked as read",
            "data": updated_notif,
            "unread_count": unread_count
        }), 200
        
    except Exception as e:
        import sys
        print(f"[Error] Marking notification {notification_id} read: {e}", file=sys.stderr)
        log_audit_event(user_id, g.user_role, "read_notification", "FAILED", { "error": str(e), "notification_id": notification_id })
        return jsonify({
            "success": False,
            "message": "An unexpected error occurred while marking the notification as read.",
            "data": None
        }), 500


@notification_bp.route("/api/v1/notifications/read-all", methods=["PUT"])
@require_auth
def mark_all_notifications_read():
    """
    PUT /api/v1/notifications/read-all
    Marks all notifications for current user as read.
    """
    user_id = g.user_id
    
    try:
        modified_count = notif_service.mark_all_read(user_id)
        log_audit_event(user_id, g.user_role, "read_all_notifications", "SUCCESS", { "modified_count": modified_count })
        
        return jsonify({
            "success": True,
            "message": f"All notifications marked as read. Modified count: {modified_count}",
            "data": {
                "modified_count": modified_count
            },
            "unread_count": 0
        }), 200
    except Exception as e:
        import sys
        print(f"[Error] Marking all read: {e}", file=sys.stderr)
        log_audit_event(user_id, g.user_role, "read_all_notifications", "FAILED", { "error": str(e) })
        return jsonify({
            "success": False,
            "message": "An unexpected error occurred while marking all notifications as read.",
            "data": None
        }), 500


# --- Telegram Linking and Verification Routes ---

@notification_bp.route("/api/v1/notifications/telegram/link", methods=["POST"])
@require_auth
def link_telegram_chat():
    """
    POST /api/v1/notifications/telegram/link
    Accepts JSON body: { "chat_id": "..." }
    """
    user_id = g.user_id
    body = request.get_json(silent=True) or {}
    chat_id = body.get("chat_id")
    
    if not chat_id:
        log_audit_event(user_id, g.user_role, "link_telegram", "FAILED", { "reason": "chat_id is required" })
        return jsonify({
            "success": False,
            "message": "chat_id is required",
            "data": None
        }), 400
        
    chat_id_str = str(chat_id).strip()
    is_valid = False
    if chat_id_str.startswith("-"):
        is_valid = chat_id_str[1:].isdigit()
    else:
        is_valid = chat_id_str.isdigit()
        
    if not is_valid or len(chat_id_str) < 5 or len(chat_id_str) > 15:
        log_audit_event(user_id, g.user_role, "link_telegram", "FAILED", { "reason": "Invalid chat_id format", "chat_id": chat_id_str })
        return jsonify({
            "success": False,
            "message": "Invalid chat_id format. It must be numeric and between 5 and 15 digits.",
            "data": None
        }), 400
        
    try:
        sub = notif_service.link_telegram(user_id, chat_id_str)
        unread_count = notif_service.get_unread_count(user_id)
        
        log_audit_event(user_id, g.user_role, "link_telegram", "SUCCESS", { "chat_id": chat_id_str })
        
        return jsonify({
            "success": True,
            "message": "Telegram notifications link code generated and delivered.",
            "data": {
                "chat_id": sub["chat_id"],
                "is_active": sub["is_active"],
                "is_verified": sub.get("is_verified", False)
            },
            "unread_count": unread_count
        }), 200
    except Exception as e:
        import sys
        print(f"[Error] Linking Telegram: {e}", file=sys.stderr)
        log_audit_event(user_id, g.user_role, "link_telegram", "FAILED", { "error": str(e) })
        return jsonify({
            "success": False,
            "message": "An unexpected error occurred while linking Telegram.",
            "data": None
        }), 500


@notification_bp.route("/api/v1/notifications/telegram/verify", methods=["POST"])
@require_auth
def verify_telegram_chat():
    """
    POST /api/v1/notifications/telegram/verify
    Accepts JSON body: { "verification_code": "..." }
    Verifies chat_id ownership before activating (Contract Violation 2).
    """
    user_id = g.user_id
    body = request.get_json(silent=True) or {}
    code = body.get("verification_code")
    
    if not code:
        log_audit_event(user_id, g.user_role, "verify_telegram", "FAILED", { "reason": "verification_code is required" })
        return jsonify({
            "success": False,
            "message": "verification_code is required",
            "data": None
        }), 400
        
    try:
        success = notif_service.verify_telegram(user_id, code)
        unread_count = notif_service.get_unread_count(user_id)
        status = notif_service.get_telegram_status(user_id)
        
        if success:
            log_audit_event(user_id, g.user_role, "verify_telegram", "SUCCESS", { "code": code })
            return jsonify({
                "success": True,
                "message": "Telegram channel verified successfully. Alerts are now active.",
                "data": {
                    "chat_id": status["chat_id"] if status else None,
                    "is_active": True,
                    "is_verified": True
                },
                "unread_count": unread_count
            }), 200
        else:
            log_audit_event(user_id, g.user_role, "verify_telegram", "FAILED", { "reason": "Incorrect code provided", "code": code })
            return jsonify({
                "success": False,
                "message": "Invalid verification code. Please check and try again.",
                "data": None
            }), 400
    except Exception as e:
        import sys
        print(f"[Error] Verifying Telegram: {e}", file=sys.stderr)
        log_audit_event(user_id, g.user_role, "verify_telegram", "FAILED", { "error": str(e) })
        return jsonify({
            "success": False,
            "message": "An unexpected error occurred while verifying Telegram.",
            "data": None
        }), 500


@notification_bp.route("/api/v1/notifications/telegram/link", methods=["DELETE"])
@require_auth
def unlink_telegram_chat():
    """
    DELETE /api/v1/notifications/telegram/link
    Unlinks/deactivates the subscription.
    """
    user_id = g.user_id
    
    try:
        success = notif_service.unlink_telegram(user_id)
        unread_count = notif_service.get_unread_count(user_id)
        
        log_audit_event(user_id, g.user_role, "unlink_telegram", "SUCCESS")
        
        return jsonify({
            "success": True,
            "message": "Telegram notifications unlinked successfully",
            "data": {},
            "unread_count": unread_count
        }), 200
    except Exception as e:
        import sys
        print(f"[Error] Unlinking Telegram: {e}", file=sys.stderr)
        log_audit_event(user_id, g.user_role, "unlink_telegram", "FAILED", { "error": str(e) })
        return jsonify({
            "success": False,
            "message": "An unexpected error occurred while unlinking Telegram.",
            "data": None
        }), 500
        

@notification_bp.route("/api/v1/notifications/telegram/status", methods=["GET"])
@require_auth
def get_telegram_link_status():
    """
    GET /api/v1/notifications/telegram/status
    Retrieves current linking status.
    """
    user_id = g.user_id
    try:
        status = notif_service.get_telegram_status(user_id)
        unread_count = notif_service.get_unread_count(user_id)
        
        log_audit_event(user_id, g.user_role, "get_telegram_status", "SUCCESS")
        
        if status:
            return jsonify({
                "success": True,
                "data": {
                    "linked": status.get("is_verified", False),
                    "chat_id": status["chat_id"] if status.get("is_verified", False) else None,
                    "is_active": status["is_active"],
                    "is_verified": status.get("is_verified", False),
                    "verification_code": None
                },
                "unread_count": unread_count
            }), 200
        else:
            return jsonify({
                "success": True,
                "data": {
                    "linked": False,
                    "chat_id": None,
                    "is_active": False,
                    "is_verified": False,
                    "verification_code": None
                },
                "unread_count": unread_count
            }), 200
    except Exception as e:
        import sys
        print(f"[Error] Getting Telegram status: {e}", file=sys.stderr)
        log_audit_event(user_id, g.user_role, "get_telegram_status", "FAILED", { "error": str(e) })
        return jsonify({
            "success": False,
            "message": "An unexpected error occurred while retrieving Telegram status.",
            "data": None
        }), 500


@notification_bp.route("/api/v1/notifications/mock-trigger", methods=["POST"])
@require_auth(roles=["admin", "customer"])
def create_mock_notification():
    """
    POST /api/v1/notifications/mock-trigger
    Accepts JSON body: { "message": "...", "order_id": "..." }
    Requires role authorization (RBAC).
    """
    user_id = g.user_id
    body = request.get_json(silent=True) or {}
    message = body.get("message", "Test alert triggered from the demo page.")
    order_id = body.get("order_id", "GLX-2026-MOCK")
    
    try:
        from app.models.notification_model import notify_user
        new_notif = notify_user(user_id, message, order_id)
        unread_count = notif_service.get_unread_count(user_id)
        
        log_audit_event(user_id, g.user_role, "trigger_mock_notification", "SUCCESS", { "order_id": order_id })
        
        return jsonify({
            "success": True,
            "message": "Mock notification created successfully",
            "data": new_notif,
            "unread_count": unread_count
        }), 201
    except Exception as e:
        import sys
        print(f"[Error] Triggering mock notification: {e}", file=sys.stderr)
        log_audit_event(user_id, g.user_role, "trigger_mock_notification", "FAILED", { "error": str(e) })
        return jsonify({
            "success": False,
            "message": "An unexpected error occurred while triggering the mock notification.",
            "data": None
        }), 500


@notification_bp.route("/api/v1/auth/token", methods=["POST"])
def get_mock_jwt_token():
    """
    POST /api/v1/auth/token
    Generates a signed JWT token for the requested user_id for dev/testing.
    Enforces customer and admin roles in token payload.
    """
    from app.configs.config import Config
    body = request.get_json(silent=True) or {}
    user_id = body.get("user_id", "customer1")
    
    if Config.FLASK_ENV != "development":
        log_audit_event(user_id, "none", "request_jwt_token", "FAILED", { "reason": "Mock auth only available in development" })
        return jsonify({
            "success": False,
            "message": "Forbidden: mock authentication is only available in development mode",
            "data": None
        }), 403
    
    import jwt
    import datetime
    from app.configs.config import Config
    
    role = "admin" if user_id == "admin1" else "customer"
    
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=24)
    }
    token = jwt.encode(payload, Config.JWT_SECRET, algorithm="HS256")
    
    log_audit_event(user_id, role, "request_jwt_token", "SUCCESS")
    
    return jsonify({
        "success": True,
        "token": token
    })
