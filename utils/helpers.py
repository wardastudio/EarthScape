from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import bcrypt
import jwt
from bson import ObjectId
from flask import request

from config import Config


EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
PHONE_REGEX = re.compile(r"^\+?[1-9]\d{9,14}$")


class JSONEncoder:
    @staticmethod
    def default(o: Any) -> Any:
        if isinstance(o, ObjectId):
            return str(o)
        if isinstance(o, datetime):
            return o.isoformat()
        raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")


def get_client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.remote_addr or "127.0.0.1"


def sanitize_input(value: Any) -> Any:
    if isinstance(value, str):
        cleaned = value.replace("\0", "")
        cleaned = re.sub(r"[<>\"';&]", "", cleaned)
        return cleaned
    if isinstance(value, dict):
        return {k: sanitize_input(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_input(item) for item in value]
    return value


def sanitize_mongo_query(query: Dict[str, Any]) -> Dict[str, Any]:
    safe: Dict[str, Any] = {}
    for key, value in query.items():
        if isinstance(key, str) and key.startswith("$"):
            continue
        if isinstance(value, dict):
            nested_safe: Dict[str, Any] = {}
            for k, v in value.items():
                if isinstance(k, str) and k.startswith("$") and k not in {
                    "$eq", "$gt", "$gte", "$in", "$lt", "$lte", "$ne", "$nin",
                    "$regex", "$options", "$exists",
                }:
                    continue
                nested_safe[k] = sanitize_mongo_query(v) if isinstance(v, dict) else v
            safe[key] = nested_safe
        else:
            safe[key] = value
    return safe


def is_valid_email(email: str) -> bool:
    if not email or not isinstance(email, str):
        return False
    return bool(EMAIL_REGEX.match(email.strip()))


def is_valid_phone(phone: str) -> bool:
    if not phone or not isinstance(phone, str):
        return False
    digits = re.sub(r"[\s\-\(\)\.]", "", phone)
    return bool(PHONE_REGEX.match(digits))


def is_valid_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    try:
        result = urlparse(url)
        return result.scheme in {"http", "https"} and bool(result.netloc)
    except Exception:
        return False


def is_strong_password(password: str) -> tuple[bool, str]:
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r"\d", password):
        return False, "Password must contain at least one digit"
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>_\-+=]", password):
        return False, "Password must contain at least one special character"
    return True, "Password is strong"


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: str, role: str, extra: Optional[Dict[str, Any]] = None) -> str:
    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(seconds=Config.JWT_ACCESS_TTL),
        "jti": secrets.token_hex(16),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, Config.JWT_SECRET, algorithm="HS256")


def create_refresh_token(user_id: str, role: str, extra: Optional[Dict[str, Any]] = None) -> str:
    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "type": "refresh",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(seconds=Config.JWT_REFRESH_TTL),
        "jti": secrets.token_hex(16),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, Config.JWT_REFRESH_SECRET, algorithm="HS256")


def decode_token(token: str, secret: Optional[str] = None) -> Dict[str, Any]:
    secret = secret or Config.JWT_SECRET
    payload = jwt.decode(token, secret, algorithms=["HS256"])
    return payload


def create_password_reset_token(email: str) -> str:
    payload: Dict[str, Any] = {
        "email": email,
        "type": "password_reset",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, Config.JWT_SECRET, algorithm="HS256")


def verify_password_reset_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, Config.JWT_SECRET, algorithms=["HS256"])
        if payload.get("type") != "password_reset":
            return None
        return payload.get("email")
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def create_email_verification_token(email: str, user_id: str) -> str:
    payload: Dict[str, Any] = {
        "email": email,
        "user_id": str(user_id),
        "type": "email_verification",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, Config.JWT_SECRET, algorithm="HS256")


def verify_email_verification_token(token: str) -> Optional[Dict[str, str]]:
    try:
        payload = jwt.decode(token, Config.JWT_SECRET, algorithms=["HS256"])
        if payload.get("type") != "email_verification":
            return None
        return {"email": payload.get("email", ""), "user_id": payload.get("user_id", "")}
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def serialize_document(doc: Any) -> Any:
    if isinstance(doc, list):
        return [serialize_document(item) for item in doc]
    if isinstance(doc, dict):
        result = {}
        for key, value in doc.items():
            if key == "_id":
                result["id"] = str(value)
            else:
                result[key] = serialize_document(value)
        return result
    if isinstance(doc, ObjectId):
        return str(doc)
    if isinstance(doc, datetime):
        return doc.isoformat()
    return doc


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def generate_verification_code(length: int = 6) -> str:
    return "".join(secrets.choice("0123456789") for _ in range(length))
