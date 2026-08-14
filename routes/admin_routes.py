from __future__ import annotations

from flask import Blueprint

from controllers import admin_controller as admin_ctrl
from middleware.auth import admin_required


admin_bp = Blueprint("admin_api", __name__, url_prefix="/api/admin")


admin_bp.get("/dashboard")(admin_required(admin_ctrl.dashboard_stats))
admin_bp.get("/users")(admin_required(admin_ctrl.list_users))
admin_bp.get("/users/<user_id>")(admin_required(admin_ctrl.get_user))
admin_bp.post("/users")(admin_required(admin_ctrl.create_user))
admin_bp.patch("/users/<user_id>/role", endpoint="update_user_role_patch")(admin_required(admin_ctrl.update_user_role))
admin_bp.put("/users/<user_id>/role", endpoint="update_user_role_put")(admin_required(admin_ctrl.update_user_role))
admin_bp.patch("/users/<user_id>/active", endpoint="toggle_user_active_patch")(admin_required(admin_ctrl.toggle_user_active))
admin_bp.put("/users/<user_id>/active", endpoint="toggle_user_active_put")(admin_required(admin_ctrl.toggle_user_active))
admin_bp.delete("/users/<user_id>")(admin_required(admin_ctrl.delete_user))

admin_bp.get("/audit-logs")(admin_required(admin_ctrl.list_audit_logs))
admin_bp.get("/feedback")(admin_required(admin_ctrl.list_feedback))
admin_bp.get("/settings", endpoint="system_settings_get")(admin_required(admin_ctrl.system_settings))
admin_bp.post("/settings", endpoint="system_settings_post")(admin_required(admin_ctrl.system_settings))
admin_bp.get("/datasets")(admin_required(admin_ctrl.list_datasets))
