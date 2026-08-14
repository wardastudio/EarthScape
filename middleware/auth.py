from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Optional

import jwt
from bson import ObjectId
from flask import g, jsonify, request, session

from config import Config
from database import get_db
from services.auth_service import ROLE_HIERARCHY
from utils.helpers import decode_token, serialize_document
from utils.rate_limiter import rate_limiter


def _set_request_user(payload: dict) -> None:
    user_id = payload.get("sub", "")
    if not user_id:
        g.current_user = None
        g.user_id = None
        g.user_role = None
        return
    
    try:
        db = get_db()
        user = db.users.find_one({"_id": ObjectId(user_id)})
        if user:
            g.current_user = serialize_document(user)
            g.user_id = user_id
            g.user_role = user.get("role", "researcher").strip().lower()
        else:
            g.current_user = None
            g.user_id = None
            g.user_role = None
    except Exception:
        # Invalid ObjectId format
        g.current_user = None
        g.user_id = None
        g.user_role = None


def token_required(required_role: Optional[str] = None) -> Callable:
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any):
            auth_header = request.headers.get("Authorization", "")
            token = auth_header.replace("Bearer ", "", 1).strip()
            if not token:
                return jsonify({"error": "authentication_error", "message": "Authentication required"}), 401
            try:
                payload = decode_token(token, Config.JWT_SECRET)
            except jwt.ExpiredSignatureError:
                return jsonify({"error": "token_expired", "message": "Access token expired"}), 401
            except jwt.InvalidTokenError:
                return jsonify({"error": "invalid_token", "message": "Invalid access token"}), 401
            if payload.get("type") != "access":
                return jsonify({"error": "invalid_token", "message": "Invalid token type"}), 401
            _set_request_user(payload)
            if required_role:
                role = getattr(g, "user_role", None)
                if role:
                    role = role.strip().lower()
                allowed = ROLE_HIERARCHY.get(role or "", set())
                if required_role.lower() not in allowed:
                    return jsonify({"error": "forbidden", "message": "Insufficient permissions"}), 403
            return func(*args, **kwargs)
        return wrapper
    return decorator


def login_required(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any):
        user = session.get("user")
        auth_header = request.headers.get("Authorization", "")
        token = auth_header.replace("Bearer ", "", 1).strip()
        if token:
            try:
                payload = decode_token(token, Config.JWT_SECRET)
                if payload.get("type") == "access":
                    _set_request_user(payload)
                    return func(*args, **kwargs)
            except Exception:
                pass
        if not user:
            if request.path.startswith("/api/") or request.is_json:
                return jsonify({"error": "authentication_error", "message": "Authentication required"}), 401
            from flask import redirect, url_for
            return redirect(url_for("main.login"))
        g.current_user = user
        g.user_id = user.get("id")
        g.user_role = user.get("role", "researcher").strip().lower()
        return func(*args, **kwargs)
    return wrapper


def role_required(*roles: str) -> Callable:
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        @login_required
        def wrapper(*args: Any, **kwargs: Any):
            user_role = getattr(g, "user_role", "") or (session.get("user") or {}).get("role", "")
            user_role = user_role.strip().lower()
            user_allowed_roles = ROLE_HIERARCHY.get(user_role, {user_role})
            normalized_roles = [r.strip().lower() for r in roles]
            if not any(r in user_allowed_roles for r in normalized_roles):
                if request.path.startswith("/api/") or request.is_json:
                    return jsonify({"error": "forbidden", "message": "Insufficient permissions"}), 403
                from flask import redirect, url_for
                return redirect(url_for("main.unauthorized"))
            return func(*args, **kwargs)
        return wrapper
    return decorator


def admin_required(func: Callable) -> Callable:
    return role_required("admin")(func)


def rate_limit(key_prefix: str = "global", limit: int = 120, window: int = 60) -> Callable:
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any):
            ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
            key = f"{key_prefix}:{ip}"
            try:
                rate_limiter.enforce(key, limit=limit, window=window)
            except Exception as exc:
                message = getattr(exc, "message", "Too many requests")
                return jsonify({"error": "too_many_requests", "message": message}), 429
            return func(*args, **kwargs)
        return wrapper
    return decorator


def login_rate_limit(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any):
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
        email = ""
        if request.method == "POST":
            payload = request.get_json(silent=True) or request.form or {}
            email = (payload.get("email") or "").strip().lower()
        key = f"login:ip:{ip}"
        email_key = f"login:email:{email}" if email else None
        try:
            rate_limiter.enforce(key, limit=10, window=300)
            if email_key:
                rate_limiter.enforce(email_key, limit=5, window=300)
        except Exception as exc:
            message = getattr(exc, "message", "Too many login attempts. Please try again later.")
            return jsonify({"error": "too_many_requests", "message": message}), 429
        return func(*args, **kwargs)
    return wrapper
