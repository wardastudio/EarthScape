from __future__ import annotations

from flask import Blueprint

from controllers import satellite_controller as satellite_ctrl

satellite_bp = Blueprint("satellite_api", __name__, url_prefix="/api/satellite")

# Explicitly register the latest endpoint (GET)
satellite_bp.add_url_rule(
	"/latest",
	endpoint="latest_satellite_products",
	view_func=satellite_ctrl.latest_satellite_products,
	methods=["GET"],
)
