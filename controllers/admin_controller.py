from __future__ import annotations

from typing import Any, Dict

from bson import ObjectId
from flask import g, jsonify, request

from database import get_db
from services.auth_service import auth_service
from services.data_service import DataService
from utils.errors import AppError, AuthorizationError, NotFoundError
from utils.helpers import hash_password, is_strong_password, is_valid_email, is_valid_phone, now_iso, sanitize_input, serialize_document


def _admin_id() -> str | None:
    return getattr(g, "user_id", None)


def _ensure_admin() -> None:
    role = getattr(g, "user_role", "")
    if role != "admin":
        raise AuthorizationError("Admin role required")


def dashboard_stats():
    _ensure_admin()
    service = DataService()
    return jsonify(service.get_dashboard_metrics()), 200


def list_users():
    _ensure_admin()
    admin_id = _admin_id()
    role = request.args.get("role") or None
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 50))
    result = auth_service.list_users(page=page, page_size=page_size, role=role)
    for item in result["items"]:
        item.pop("password", None)
        item.pop("refresh_tokens", None)
    return jsonify(result), 200


def get_user(user_id: str):
    _ensure_admin()
    try:
        user = auth_service.get_user(user_id)
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    user.pop("password", None)
    user.pop("refresh_tokens", None)
    return jsonify({"user": user}), 200


def create_user():
    _ensure_admin()
    admin_id = _admin_id()
    payload = request.get_json(silent=True) or request.form or {}
    full_name = sanitize_input(payload.get("full_name") or payload.get("name", "")).strip()
    email = sanitize_input(payload.get("email", "")).strip().lower()
    phone = sanitize_input(payload.get("phone", "")).strip()
    password = payload.get("password", "")
    role = sanitize_input(payload.get("role", "researcher")).strip().lower()
    if not full_name or not email or not password:
        return jsonify({"error": "validation_error", "message": "full_name, email and password are required"}), 422
    if not is_valid_email(email):
        return jsonify({"error": "validation_error", "message": "Invalid email"}), 422
    if phone and not is_valid_phone(phone):
        return jsonify({"error": "validation_error", "message": "Invalid phone"}), 422
    strong, reason = is_strong_password(password)
    if not strong:
        return jsonify({"error": "validation_error", "message": reason}), 422
    try:
        result = auth_service.register(
            full_name=full_name,
            email=email,
            phone=phone,
            password=password,
            confirm_password=password,
            role=role,
        )
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify({"message": "User created successfully", **result}), 201


def update_user_role(user_id: str):
    _ensure_admin()
    admin_id = _admin_id()
    payload = request.get_json(silent=True) or request.form or {}
    role = sanitize_input(payload.get("role", "")).strip().lower()
    try:
        result = auth_service.update_user_role(admin_id or "", user_id, role)
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify(result), 200


def toggle_user_active(user_id: str):
    _ensure_admin()
    admin_id = _admin_id()
    payload = request.get_json(silent=True) or request.form or {}
    active = payload.get("active", True)
    if isinstance(active, str):
        active = active.lower() in {"true", "1", "yes"}
    try:
        result = auth_service.toggle_user_active(admin_id or "", user_id, bool(active))
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify(result), 200


def delete_user(user_id: str):
    _ensure_admin()
    db = get_db()
    result = db.users.delete_one({"_id": ObjectId(user_id)})
    if result.deleted_count == 0:
        return jsonify({"error": "not_found", "message": "User not found"}), 404
    return jsonify({"message": "User deleted successfully"}), 200


def list_audit_logs():
    _ensure_admin()
    admin_id = _admin_id()
    user_id = request.args.get("user_id") or None
    limit = int(request.args.get("limit", 100))
    logs = auth_service.get_audit_logs(user_id=user_id, limit=limit)
    return jsonify({"items": logs, "total": len(logs)}), 200


def list_feedback():
    _ensure_admin()
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 50))
    db = get_db()
    skip = max(0, (page - 1) * page_size)
    cursor = db.feedback.find({}).skip(skip).limit(page_size).sort("created_at", -1)
    items = serialize_document(list(cursor))
    total = db.feedback.count_documents({})
    return jsonify({"items": items, "total": total, "page": page, "page_size": page_size}), 200


def system_settings():
    _ensure_admin()
    db = get_db()
    if request.method == "POST":
        payload = request.get_json(silent=True) or request.form or {}
        for key, value in payload.items():
            db.settings.update_one(
                {"key": key},
                {"$set": {"key": key, "value": value, "updated_at": now_iso()}},
                upsert=True,
            )
        return jsonify({"message": "Settings saved"}), 200
    docs = list(db.settings.find({}))
    return jsonify({"items": serialize_document(docs)}), 200


def list_datasets():
    _ensure_admin()
    db = get_db()
    docs = list(db.datasets.find({}).sort("created_at", -1).limit(100))
    return jsonify({"items": serialize_document(docs), "total": len(docs)}), 200
