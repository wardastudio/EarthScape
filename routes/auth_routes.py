from __future__ import annotations

from flask import Blueprint

from controllers import auth_controller_v2 as auth_ctrl
from middleware.auth import login_required, rate_limit


auth_bp = Blueprint("auth_api", __name__, url_prefix="/api/auth")


auth_bp.post("/register")(rate_limit(key_prefix="auth_register", limit=20, window=3600)(auth_ctrl.register))
auth_bp.post("/login")(auth_ctrl.login)
auth_bp.post("/logout")(login_required(auth_ctrl.logout))
auth_bp.post("/refresh")(auth_ctrl.refresh)
auth_bp.post("/forgot-password")(rate_limit(key_prefix="auth_forgot", limit=10, window=3600)(auth_ctrl.forgot_password))
auth_bp.post("/reset-password")(auth_ctrl.reset_password)
auth_bp.post("/verify-email")(auth_ctrl.verify_email)
auth_bp.post("/change-password")(login_required(auth_ctrl.change_password))
