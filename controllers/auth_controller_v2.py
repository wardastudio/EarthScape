from __future__ import annotations

from typing import Any, Dict

from flask import g, jsonify, redirect, render_template, request, session, url_for

from middleware.auth import login_rate_limit
from services.auth_service import auth_service
from utils.errors import AppError
from utils.helpers import get_client_ip, sanitize_input


def _is_api_request() -> bool:
    return request.path.startswith("/api/") or request.is_json or "application/json" in request.headers.get("Accept", "")


def _payload() -> Dict[str, Any]:
    return request.get_json(silent=True) or request.form or {}


def register():
    payload = _payload()
    try:
        result = auth_service.register(
            full_name=sanitize_input(payload.get("full_name") or payload.get("name", "")),
            email=sanitize_input(payload.get("email", "")),
            phone=sanitize_input(payload.get("phone", "")),
            password=payload.get("password", ""),
            confirm_password=payload.get("confirm_password") or payload.get("confirm"),
            role=sanitize_input(payload.get("role", "analyst")),
        )
    except AppError as exc:
        if _is_api_request():
            return jsonify(exc.to_dict()), exc.status_code
        return render_template("auth/register.html", error_message=exc.message)
    if _is_api_request():
        return jsonify({"message": "User registered successfully", **result}), 201
    return render_template("auth/login.html", success_message="Account registered successfully! Please log in.")


@login_rate_limit
def login():
    payload = _payload()
    ip = get_client_ip()
    try:
        result = auth_service.login(
            email=sanitize_input(payload.get("email", "")),
            password=payload.get("password", ""),
            ip=ip,
        )
    except AppError as exc:
        if _is_api_request():
            return jsonify(exc.to_dict()), exc.status_code
        return render_template("auth/login.html", error_message=exc.message)
    user = result["user"]
    session["user"] = user
    if _is_api_request():
        return jsonify(result), 200
    role = (user.get("role") or "").strip().lower()
    if role == "admin":
        return redirect(url_for("main.admin_dashboard"))
    if role == "analyst":
        return redirect(url_for("main.analyst_dashboard"))
    if role == "researcher":
        return redirect(url_for("main.researcher_dashboard"))
    return redirect(url_for("main.guest_dashboard"))


def logout():
    user_id = getattr(g, "user_id", None) or (session.get("user") or {}).get("id")
    if user_id:
        refresh = _payload().get("refresh_token")
        auth_service.logout(user_id, refresh_token=refresh)
    session.clear()
    if _is_api_request():
        return jsonify({"message": "Logged out successfully"}), 200
    return redirect(url_for("main.index"))


def refresh():
    payload = _payload()
    refresh_token = payload.get("refresh_token") or request.headers.get("X-Refresh-Token", "")
    if not refresh_token:
        return jsonify({"error": "validation_error", "message": "Refresh token is required"}), 422
    try:
        result = auth_service.refresh(refresh_token)
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify(result), 200


def forgot_password():
    payload = _payload()
    ip = get_client_ip()
    try:
        result = auth_service.forgot_password(
            email=sanitize_input(payload.get("email", "")),
            ip=ip,
        )
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify(result), 200


def reset_password():
    payload = _payload()
    try:
        result = auth_service.reset_password(
            token=sanitize_input(payload.get("token", "")),
            new_password=payload.get("password", ""),
            confirm_password=payload.get("confirm_password") or payload.get("confirm"),
        )
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify(result), 200


def verify_email():
    payload = _payload()
    token = sanitize_input(payload.get("token") or request.args.get("token", ""))
    if not token:
        return jsonify({"error": "validation_error", "message": "Verification token is required"}), 422
    try:
        result = auth_service.verify_email(token)
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify(result), 200


def change_password():
    user_id = getattr(g, "user_id", None)
    if not user_id:
        return jsonify({"error": "authentication_error", "message": "Authentication required"}), 401
    payload = _payload()
    try:
        result = auth_service.change_password(
            user_id=user_id,
            old_password=payload.get("old_password", ""),
            new_password=payload.get("new_password", ""),
        )
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify(result), 200
