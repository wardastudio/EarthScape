from __future__ import annotations

from typing import Any, Dict

from bson import ObjectId
from bson.errors import InvalidId
from flask import g, jsonify, request

from database import get_db
from services.notification_service import notification_service
from utils.errors import AppError, NotFoundError, ValidationError
from utils.helpers import hash_password, is_strong_password, is_valid_email, is_valid_phone, now_iso, sanitize_input, serialize_document, verify_password


def _user_id() -> str | None:
    return getattr(g, "user_id", None)


def _safe_object_id_user_query(uid: str) -> Dict[str, Any]:
    try:
        return {"_id": ObjectId(uid)}
    except InvalidId:
        return {"_id": uid}


def _safe_get_user(uid: str):
    db = get_db()
    user = db.users.find_one(_safe_object_id_user_query(uid))
    if not user:
        return None
    return user


def get_profile():
    uid = _user_id()
    if not uid:
        return jsonify({"error": "authentication_error", "message": "Authentication required"}), 401
    try:
        user = _safe_get_user(uid)
    except InvalidId:
        return jsonify({"error": "authentication_error", "message": "Invalid session"}), 401
    if not user:
        return jsonify({"error": "not_found", "message": "User not found"}), 404
    user_doc = serialize_document(user)
    user_doc.pop("password", None)
    user_doc.pop("refresh_tokens", None)
    return jsonify({"user": user_doc}), 200


def update_profile():
    uid = _user_id()
    if not uid:
        return jsonify({"error": "authentication_error", "message": "Authentication required"}), 401
    payload = request.get_json(silent=True) or request.form or {}
    db = get_db()
    update: Dict[str, Any] = {"updated_at": now_iso()}
    if "full_name" in payload or "name" in payload:
        name = sanitize_input(payload.get("full_name") or payload.get("name", "")).strip()
        if name:
            update["full_name"] = name
    if "phone" in payload:
        phone = sanitize_input(payload.get("phone", "")).strip()
        if phone and not is_valid_phone(phone):
            return jsonify({"error": "validation_error", "message": "Invalid phone number"}), 422
        if phone:
            update["phone"] = phone
    if "email" in payload:
        email = sanitize_input(payload.get("email", "")).strip().lower()
        if email and not is_valid_email(email):
            return jsonify({"error": "validation_error", "message": "Invalid email"}), 422
        existing = db.users.find_one({"email": email})
        if existing and str(existing["_id"]) != str(uid):
            return jsonify({"error": "conflict", "message": "Email already in use"}), 409
        if email:
            update["email"] = email
    if "profile_image" in payload:
        update["profile_image"] = sanitize_input(payload.get("profile_image", ""))
    result = db.users.update_one(_safe_object_id_user_query(uid), {"$set": update})
    if result.matched_count == 0:
        return jsonify({"error": "not_found", "message": "User not found"}), 404
    return jsonify({"message": "Profile updated successfully"}), 200


def notifications():
    uid = _user_id()
    if not uid:
        return jsonify({"error": "authentication_error", "message": "Authentication required"}), 401
    only_unread = request.args.get("unread", "").lower() in {"1", "true", "yes"}
    notification_type = request.args.get("type") or None
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 50))
    result = notification_service.list_for_user(
        user_id=uid,
        only_unread=only_unread,
        notification_type=notification_type,
        page=page,
        page_size=page_size,
    )
    return jsonify(result), 200


def notification_unread_count():
    uid = _user_id()
    if not uid:
        return jsonify({"error": "authentication_error", "message": "Authentication required"}), 401
    return jsonify(notification_service.unread_count(uid)), 200


def mark_notification_read(notification_id: str):
    uid = _user_id()
    if not uid:
        return jsonify({"error": "authentication_error", "message": "Authentication required"}), 401
    try:
        result = notification_service.mark_read(uid, notification_id)
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify(result), 200


def mark_all_notifications_read():
    uid = _user_id()
    if not uid:
        return jsonify({"error": "authentication_error", "message": "Authentication required"}), 401
    return jsonify(notification_service.mark_all_read(uid)), 200


def delete_notification(notification_id: str):
    uid = _user_id()
    if not uid:
        return jsonify({"error": "authentication_error", "message": "Authentication required"}), 401
    try:
        result = notification_service.delete(uid, notification_id)
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify(result), 200


def create_notification():
    uid = _user_id()
    if not uid:
        return jsonify({"error": "authentication_error", "message": "Authentication required"}), 401
    payload = request.get_json(silent=True) or request.form or {}
    try:
        result = notification_service.create(
            user_id=uid,
            title=sanitize_input(payload.get("title", "")),
            message=sanitize_input(payload.get("message", "")),
            notification_type=sanitize_input(payload.get("type", "info")),
            priority=sanitize_input(payload.get("priority", "normal")),
            metadata=payload.get("metadata"),
        )
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify({"message": "Notification created", "item": result}), 201


def change_password():
    uid = _user_id()
    if not uid:
        return jsonify({"error": "authentication_error", "message": "Authentication required"}), 401
    payload = request.get_json(silent=True) or request.form or {}
    old = payload.get("old_password", "")
    new = payload.get("new_password", "") or payload.get("password", "")
    if not old or not new:
        return jsonify({"error": "validation_error", "message": "old_password and new_password are required"}), 422
    db = get_db()
    user = db.users.find_one(_safe_object_id_user_query(uid))
    if not user:
        return jsonify({"error": "not_found", "message": "User not found"}), 404
    if not verify_password(old, user.get("password", "")):
        return jsonify({"error": "authentication_error", "message": "Current password is incorrect"}), 401
    strong, reason = is_strong_password(new)
    if not strong:
        return jsonify({"error": "validation_error", "message": reason}), 422
    db.users.update_one(
        _safe_object_id_user_query(uid),
        {"$set": {"password": hash_password(new), "updated_at": now_iso(), "refresh_tokens": []}},
    )
    return jsonify({"message": "Password changed successfully"}), 200


def submit_feedback():
    uid = _user_id()
    payload = request.get_json(silent=True) or request.form or {}
    rating = payload.get("rating")
    message = sanitize_input(payload.get("message", ""))
    category = sanitize_input(payload.get("category", "general"))
    try:
        rating_val = int(rating) if rating is not None else None
    except (TypeError, ValueError):
        return jsonify({"error": "validation_error", "message": "Invalid rating"}), 422
    if rating_val is not None and (rating_val < 1 or rating_val > 5):
        return jsonify({"error": "validation_error", "message": "Rating must be between 1 and 5"}), 422
    if not message and not rating_val:
        return jsonify({"error": "validation_error", "message": "Rating or message required"}), 422
    db = get_db()
    doc = {
        "user_id": uid,
        "rating": rating_val,
        "message": message,
        "category": category,
        "created_at": now_iso(),
    }
    result = db.feedback.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    return jsonify({"message": "Feedback submitted successfully", "item": serialize_document(doc)}), 201
