from __future__ import annotations

from flask import Blueprint

from controllers import profile_controller as profile_ctrl
from middleware.auth import login_required


profile_bp = Blueprint("profile_api", __name__, url_prefix="/api/profile")


profile_bp.get("")(login_required(profile_ctrl.get_profile))
profile_bp.put("", endpoint="update_profile_put")(login_required(profile_ctrl.update_profile))
profile_bp.patch("", endpoint="update_profile_patch")(login_required(profile_ctrl.update_profile))
profile_bp.post("/change-password")(login_required(profile_ctrl.change_password))

profile_bp.get("/notifications")(login_required(profile_ctrl.notifications))
profile_bp.get("/notifications/unread-count")(login_required(profile_ctrl.notification_unread_count))
profile_bp.post("/notifications")(login_required(profile_ctrl.create_notification))
profile_bp.post("/notifications/<notification_id>/read")(login_required(profile_ctrl.mark_notification_read))
profile_bp.post("/notifications/read-all")(login_required(profile_ctrl.mark_all_notifications_read))
profile_bp.delete("/notifications/<notification_id>")(login_required(profile_ctrl.delete_notification))

profile_bp.post("/feedback")(login_required(profile_ctrl.submit_feedback))
