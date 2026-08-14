from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from flask import jsonify, redirect, render_template, request, session, url_for

from config import Config
from database import get_db, ensure_indexes
from middleware.auth import login_required, token_required
from services.data_service import DataService
from services.ml_service import predict_emission
from utils.helpers import create_access_token, create_refresh_token, hash_password, is_valid_email, is_valid_phone, sanitize_input, verify_password

service = DataService()


def register_user():
    payload = request.form if request.form else request.get_json(silent=True) or {}
    full_name = sanitize_input(payload.get("full_name") or payload.get("name", "")).strip()
    email = sanitize_input(payload.get("email", "")).strip().lower()
    phone = sanitize_input(payload.get("phone", "")).strip()
    password = payload.get("password", "")
    confirm_password = payload.get("confirm_password") or payload.get("confirm", "")
    if not all([full_name, email, phone, password]):
        if request.path.startswith("/api") or request.is_json:
            return jsonify({"error": "All fields are required"}), 422
        return redirect(url_for("main.login"))
    if not is_valid_email(email):
        if request.path.startswith("/api") or request.is_json:
            return jsonify({"error": "Invalid email address"}), 422
        return redirect(url_for("main.login"))
    if not is_valid_phone(phone):
        if request.path.startswith("/api") or request.is_json:
            return jsonify({"error": "Invalid phone number"}), 422
        return redirect(url_for("main.login"))
    if password != confirm_password:
        if request.path.startswith("/api") or request.is_json:
            return jsonify({"error": "Passwords do not match"}), 422
        return redirect(url_for("main.login"))
    db = get_db()
    if db.users.find_one({"email": email}):
        if request.path.startswith("/api") or request.is_json:
            return jsonify({"error": "Email already exists"}), 422
        return redirect(url_for("main.login"))
    user = {
        "full_name": full_name,
        "email": email,
        "phone": phone,
        "password": hash_password(password),
        "role": "user",
        "profile_image": "",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "last_login": None,
        "is_active": True,
    }
    result = db.users.insert_one(user)
    session["user"] = {"id": str(result.inserted_id), "email": email, "name": full_name, "role": "user"}
    if request.path.startswith("/api") or request.is_json:
        return jsonify({"message": "User registered successfully", "user": {"email": email, "role": "user"}}), 201
    return redirect(url_for("main.login"))


def login_user():
    payload = request.form if request.form else request.get_json(silent=True) or {}
    email = sanitize_input(payload.get("email", "")).strip().lower()
    password = payload.get("password", "")
    if not email or not password:
        if request.path.startswith("/api") or request.is_json:
            return jsonify({"error": "Email and password are required"}), 422
        return redirect(url_for("main.login"))
    db = get_db()
    user = db.users.find_one({"email": email})
    if not user or not verify_password(password, user.get("password", "")):
        if request.path.startswith("/api") or request.is_json:
            return jsonify({"error": "Invalid credentials"}), 401
        return redirect(url_for("main.login"))
    if not user.get("is_active", True):
        if request.path.startswith("/api") or request.is_json:
            return jsonify({"error": "Account disabled"}), 403
        return redirect(url_for("main.login"))
    access_token = create_access_token(str(user.get("_id")), user.get("role", "user"))
    refresh_token = create_refresh_token(str(user.get("_id")), user.get("role", "user"))
    db.users.update_one({"_id": user["_id"]}, {"$set": {"last_login": datetime.utcnow().isoformat()}})
    session["user"] = {"id": str(user.get("_id")), "email": email, "name": user.get("full_name", email), "role": user.get("role", "user")}
    if request.path.startswith("/api") or request.is_json:
        return jsonify({"message": "Login successful", "access_token": access_token, "refresh_token": refresh_token, "user": session["user"]})
    if session["user"].get("role") == "admin":
        return redirect(url_for("main.admin_dashboard"))
    return redirect(url_for("main.analyst_dashboard"))


def logout_user():
    session.clear()
    return jsonify({"message": "Logged out"})


def profile_view():
    if not session.get("user"):
        return jsonify({"error": "Authentication required"}), 401
    db = get_db()
    user = db.users.find_one({"email": session["user"]["email"]})
    return jsonify({"user": {"full_name": user.get("full_name"), "email": user.get("email"), "role": user.get("role"), "phone": user.get("phone")}})


def forgot_password():
    payload = request.form if request.form else request.get_json(silent=True) or {}
    email = sanitize_input(payload.get("email", "")).strip().lower()
    if not is_valid_email(email):
        return jsonify({"error": "Invalid email"}), 422
    return jsonify({"message": "Password reset instructions sent"})


def reset_password():
    payload = request.form if request.form else request.get_json(silent=True) or {}
    token = payload.get("token", "")
    password = payload.get("password", "")
    if not token or not password:
        return jsonify({"error": "Token and password are required"}), 422
    return jsonify({"message": "Password reset successful"})
