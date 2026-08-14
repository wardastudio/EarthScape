from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from bson import ObjectId

from config import Config
from database import get_db
from utils.errors import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from utils.helpers import (
    create_access_token,
    create_email_verification_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
    hash_password,
    is_strong_password,
    is_valid_email,
    is_valid_phone,
    now_iso,
    serialize_document,
    verify_email_verification_token,
    verify_password,
    verify_password_reset_token,
)
from utils.logging_setup import log_auth


ROLES = {"admin", "analyst", "researcher", "guest"}
ROLE_HIERARCHY = {
    "admin": {"admin", "analyst", "researcher", "guest"},
    "analyst": {"analyst", "researcher", "guest"},
    "researcher": {"researcher", "guest"},
    "guest": {"guest"},
}


class AuthService:
    def __init__(self) -> None:
        self.db = None

    def _ensure_db(self) -> None:
        if self.db is None:
            self.db = get_db()
            if self.db is None:
                raise RuntimeError("Database unavailable")

    def register(
        self,
        full_name: str,
        email: str,
        phone: str,
        password: str,
        confirm_password: Optional[str] = None,
        role: str = "researcher",
    ) -> Dict[str, Any]:
        self._ensure_db()
        full_name = (full_name or "").strip()
        email = (email or "").strip().lower()
        phone = (phone or "").strip()
        role = (role or "").strip().lower()

        if not full_name:
            raise ValidationError("Full name is required")
        if not is_valid_email(email):
            raise ValidationError("Invalid email address")
        if phone and not is_valid_phone(phone):
            raise ValidationError("Invalid phone number")
        if confirm_password is not None and password != confirm_password:
            raise ValidationError("Passwords do not match")
        if role not in ROLES:
            raise ValidationError(f"Invalid role. Must be one of: {', '.join(sorted(ROLES))}")

        strong, reason = is_strong_password(password)
        if not strong:
            raise ValidationError(reason)

        if self.db.users.find_one({"email": email}):
            raise ConflictError("Email already registered")

        user = {
            "full_name": full_name,
            "email": email,
            "phone": phone,
            "password": hash_password(password),
            "role": role,
            "profile_image": "",
            "email_verified": False,
            "is_active": True,
            "last_login": None,
            "refresh_tokens": [],
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        result = self.db.users.insert_one(user)
        user_id = str(result.inserted_id)

        verification_token = create_email_verification_token(email, user_id)

        self.db.audit_logs.insert_one({
            "user_id": user_id,
            "user_email": email,
            "action": "register",
            "details": {"role": role},
            "ip": None,
            "created_at": now_iso(),
        })

        log_auth("register", user_id=user_id, email=email, success=True)

        return {
            "user": {
                "id": user_id,
                "full_name": full_name,
                "email": email,
                "role": role,
                "email_verified": False,
            },
            "verification_token": verification_token,
        }

    def login(self, email: str, password: str, ip: Optional[str] = None) -> Dict[str, Any]:
        self._ensure_db()
        email = (email or "").strip().lower()
        if not email or not password:
            log_auth("login", email=email, success=False, ip=ip)
            raise AuthenticationError("Email and password are required")

        user = self.db.users.find_one({"email": email})
        if not user or not verify_password(password, user.get("password", "")):
            log_auth("login", email=email, success=False, ip=ip)
            raise AuthenticationError("Invalid credentials")

        if not user.get("is_active", True):
            log_auth("login", email=email, success=False, ip=ip, details={"reason": "disabled"})
            raise AuthorizationError("Account has been disabled")

        user_id = str(user["_id"])
        role = user.get("role", "researcher")
        access_token = create_access_token(user_id, role, extra={"email": email})
        refresh_token = create_refresh_token(user_id, role)

        self.db.users.update_one(
            {"_id": user["_id"]},
            {
                "$set": {"last_login": now_iso(), "updated_at": now_iso()},
                "$addToSet": {"refresh_tokens": refresh_token},
            },
        )

        self.db.audit_logs.insert_one({
            "user_id": user_id,
            "user_email": email,
            "action": "login",
            "details": {"success": True},
            "ip": ip,
            "created_at": now_iso(),
        })

        log_auth("login", user_id=user_id, email=email, success=True, ip=ip)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": Config.JWT_ACCESS_TTL,
            "user": {
                "id": user_id,
                "full_name": user.get("full_name", ""),
                "email": email,
                "role": role,
                "email_verified": user.get("email_verified", False),
                "profile_image": user.get("profile_image", ""),
            },
        }

    def logout(self, user_id: str, refresh_token: Optional[str] = None) -> None:
        update: Dict[str, Any] = {"$set": {"updated_at": now_iso()}}
        if refresh_token:
            update["$pull"] = {"refresh_tokens": refresh_token}
        else:
            update["$set"]["refresh_tokens"] = []
        self.db.users.update_one({"_id": ObjectId(user_id)}, update)
        log_auth("logout", user_id=user_id, success=True)

    def refresh(self, refresh_token: str) -> Dict[str, Any]:
        try:
            payload = decode_token(refresh_token, Config.JWT_REFRESH_SECRET)
        except Exception as exc:
            raise AuthenticationError("Invalid or expired refresh token") from exc

        if payload.get("type") != "refresh":
            raise AuthenticationError("Invalid token type")

        user_id = payload.get("sub", "")
        user = self.db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise AuthenticationError("User not found")

        stored_tokens = user.get("refresh_tokens", [])
        if refresh_token not in stored_tokens:
            raise AuthenticationError("Refresh token revoked")

        role = user.get("role", "researcher")
        email = user.get("email", "")
        new_access = create_access_token(user_id, role, extra={"email": email})
        new_refresh = create_refresh_token(user_id, role)

        stored_tokens = user.get("refresh_tokens", [])
        updated_tokens = [t for t in stored_tokens if t != refresh_token]
        if new_refresh not in updated_tokens:
            updated_tokens.append(new_refresh)
        self.db.users.update_one(
            {"_id": ObjectId(user_id)},
            {
                "$set": {
                    "updated_at": now_iso(),
                    "refresh_tokens": updated_tokens,
                },
            },
        )

        log_auth("refresh", user_id=user_id, success=True)

        return {
            "access_token": new_access,
            "refresh_token": new_refresh,
            "token_type": "bearer",
            "expires_in": Config.JWT_ACCESS_TTL,
        }

    def forgot_password(self, email: str, ip: Optional[str] = None) -> Dict[str, Any]:
        email = (email or "").strip().lower()
        if not is_valid_email(email):
            raise ValidationError("Invalid email address")

        user = self.db.users.find_one({"email": email})
        if user:
            reset_token = create_password_reset_token(email)
            log_auth("forgot_password", email=email, success=True, ip=ip)
            self.db.audit_logs.insert_one({
                "user_id": str(user["_id"]),
                "user_email": email,
                "action": "forgot_password",
                "details": {"token_issued": True},
                "ip": ip,
                "created_at": now_iso(),
            })
            return {"message": "If the email exists, a reset link has been sent", "reset_token": reset_token}

        log_auth("forgot_password", email=email, success=False, ip=ip)
        return {"message": "If the email exists, a reset link has been sent"}

    def reset_password(self, token: str, new_password: str, confirm_password: Optional[str] = None) -> Dict[str, Any]:
        if confirm_password is not None and new_password != confirm_password:
            raise ValidationError("Passwords do not match")

        strong, reason = is_strong_password(new_password)
        if not strong:
            raise ValidationError(reason)

        email = verify_password_reset_token(token)
        if not email:
            raise ValidationError("Invalid or expired reset token")

        user = self.db.users.find_one({"email": email})
        if not user:
            raise NotFoundError("User not found")

        hashed = hash_password(new_password)
        self.db.users.update_one(
            {"_id": user["_id"]},
            {"$set": {"password": hashed, "updated_at": now_iso(), "refresh_tokens": []}},
        )

        self.db.audit_logs.insert_one({
            "user_id": str(user["_id"]),
            "user_email": email,
            "action": "reset_password",
            "details": {"success": True},
            "created_at": now_iso(),
        })

        log_auth("reset_password", user_id=str(user["_id"]), email=email, success=True)
        return {"message": "Password reset successfully"}

    def verify_email(self, token: str) -> Dict[str, Any]:
        result = verify_email_verification_token(token)
        if not result:
            raise ValidationError("Invalid or expired verification token")

        user_id = result["user_id"]
        email = result["email"]
        user = self.db.users.find_one({"_id": ObjectId(user_id), "email": email})
        if not user:
            raise NotFoundError("User not found")

        self.db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"email_verified": True, "updated_at": now_iso()}},
        )

        log_auth("verify_email", user_id=user_id, email=email, success=True)
        return {"message": "Email verified successfully", "email_verified": True}

    def change_password(self, user_id: str, old_password: str, new_password: str) -> Dict[str, Any]:
        user = self.db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise NotFoundError("User not found")
        if not verify_password(old_password, user.get("password", "")):
            raise AuthenticationError("Current password is incorrect")

        strong, reason = is_strong_password(new_password)
        if not strong:
            raise ValidationError(reason)

        self.db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"password": hash_password(new_password), "updated_at": now_iso()}},
        )
        log_auth("change_password", user_id=user_id, success=True)
        return {"message": "Password changed successfully"}

    def get_user(self, user_id: str) -> Dict[str, Any]:
        user = self.db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise NotFoundError("User not found")
        return serialize_document(user)

    def list_users(self, page: int = 1, page_size: int = 50, role: Optional[str] = None) -> Dict[str, Any]:
        query: Dict[str, Any] = {}
        if role:
            query["role"] = role.lower()
        skip = max(0, (page - 1) * page_size)
        cursor = self.db.users.find(query).skip(skip).limit(page_size).sort("created_at", -1)
        items = serialize_document(list(cursor))
        total = self.db.users.count_documents(query)
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    def update_user_role(self, admin_user_id: str, target_user_id: str, new_role: str) -> Dict[str, Any]:
        admin = self.db.users.find_one({"_id": ObjectId(admin_user_id)})
        if not admin or admin.get("role") != "admin":
            raise AuthorizationError("Admin role required")
        if new_role not in ROLES:
            raise ValidationError(f"Invalid role. Must be one of: {', '.join(sorted(ROLES))}")

        target = self.db.users.find_one({"_id": ObjectId(target_user_id)})
        if not target:
            raise NotFoundError("User not found")

        self.db.users.update_one(
            {"_id": ObjectId(target_user_id)},
            {"$set": {"role": new_role, "updated_at": now_iso()}},
        )
        log_auth("update_role", user_id=target_user_id, success=True, details={"new_role": new_role})
        return {"message": f"Role updated to {new_role}"}

    def toggle_user_active(self, admin_user_id: str, target_user_id: str, active: bool) -> Dict[str, Any]:
        admin = self.db.users.find_one({"_id": ObjectId(admin_user_id)})
        if not admin or admin.get("role") != "admin":
            raise AuthorizationError("Admin role required")
        target = self.db.users.find_one({"_id": ObjectId(target_user_id)})
        if not target:
            raise NotFoundError("User not found")
        self.db.users.update_one(
            {"_id": ObjectId(target_user_id)},
            {"$set": {"is_active": active, "updated_at": now_iso()}},
        )
        log_auth("toggle_active", user_id=target_user_id, success=True, details={"active": active})
        return {"message": f"User {'activated' if active else 'deactivated'}"}

    def user_has_role(self, user_role: str, required_role: str) -> bool:
        allowed = ROLE_HIERARCHY.get(user_role, set())
        return required_role in allowed

    def get_audit_logs(self, user_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {}
        if user_id:
            query["user_id"] = user_id
        logs = list(self.db.audit_logs.find(query).sort("created_at", -1).limit(limit))
        return serialize_document(logs)


auth_service = AuthService()
