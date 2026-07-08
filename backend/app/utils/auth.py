import functools
import jwt
from flask import request, jsonify, g
from app.configs.config import Config
from app.utils.audit_log import log_audit_event

def require_auth(f=None, roles=None):
    """
    Enforces authentication and optional Role-Based Access Control (RBAC).
    Supports:
      - @require_auth (any valid user)
      - @require_auth(roles=["admin"]) (restricted access)
    """
    if f is None:
        return lambda func: require_auth(func, roles=roles)
        
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            log_audit_event("anonymous", "none", "authenticate_user", "FAILED", { "reason": "Authorization header is missing" })
            return jsonify({
                "success": False,
                "message": "Authorization header is missing",
                "data": None
            }), 401
        
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            log_audit_event("anonymous", "none", "authenticate_user", "FAILED", { "reason": "Authorization header must be Bearer <token>" })
            return jsonify({
                "success": False,
                "message": "Authorization header must be Bearer <token>",
                "data": None
            }), 401
            
        token = parts[1]
        
        try:
            payload = jwt.decode(token, Config.JWT_SECRET, algorithms=["HS256"])
            g.user_id = payload.get("user_id")
            g.user_role = payload.get("role", "customer")
            
            if not g.user_id:
                raise jwt.InvalidTokenError("user_id not in payload")
        except jwt.ExpiredSignatureError:
            log_audit_event("anonymous", "none", "authenticate_user", "FAILED", { "reason": "Token has expired" })
            return jsonify({
                "success": False,
                "message": "Token has expired",
                "data": None
            }), 401
        except jwt.InvalidTokenError as e:
            log_audit_event("anonymous", "none", "authenticate_user", "FAILED", { "reason": f"Invalid token: {str(e)}" })
            return jsonify({
                "success": False,
                "message": f"Invalid token: {str(e)}",
                "data": None
            }), 401
            
        # Enforce Role-Based Access Control (RBAC)
        if roles and g.user_role not in roles:
            log_audit_event(g.user_id, g.user_role, request.endpoint or "access_route", "FAILED", { "reason": f"Forbidden: user role '{g.user_role}' is not in allowed roles: {roles}" })
            return jsonify({
                "success": False,
                "message": f"Forbidden: user role '{g.user_role}' is not authorized to access this resource",
                "data": None
            }), 403
                
        return f(*args, **kwargs)
        
    return decorated
