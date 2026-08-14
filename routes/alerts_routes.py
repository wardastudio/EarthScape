from __future__ import annotations

from flask import Blueprint

from controllers import alerts_controller as alerts_ctrl
from middleware.auth import login_required


alerts_bp = Blueprint("alerts_api", __name__, url_prefix="/api/alerts")


alerts_bp.get("")(login_required(alerts_ctrl.list_alerts))
alerts_bp.post("")(login_required(alerts_ctrl.create_alert))
alerts_bp.get("/<alert_id>")(login_required(alerts_ctrl.get_alert))
alerts_bp.patch("/<alert_id>", endpoint="update_alert_status_patch")(login_required(alerts_ctrl.update_alert_status))
alerts_bp.put("/<alert_id>", endpoint="update_alert_status_put")(login_required(alerts_ctrl.update_alert_status))
alerts_bp.delete("/<alert_id>")(login_required(alerts_ctrl.delete_alert))
