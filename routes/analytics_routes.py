from __future__ import annotations

from flask import Blueprint

from controllers import analytics_controller as analytics_ctrl
from middleware.auth import login_required


analytics_bp = Blueprint("analytics_api", __name__, url_prefix="/api/analytics")


analytics_bp.get("/overview")(analytics_ctrl.analytics_overview)
analytics_bp.get("/earthscape")(analytics_ctrl.analytics_overview)
analytics_bp.get("/dashboard")(analytics_ctrl.dashboard_overview)
analytics_bp.get("/trends/temperature")(analytics_ctrl.temperature_trends)
analytics_bp.get("/trends/humidity")(analytics_ctrl.humidity_trends)
analytics_bp.get("/trends/rainfall")(analytics_ctrl.rainfall_trends)
analytics_bp.get("/trends/pressure")(analytics_ctrl.pressure_trends)
analytics_bp.get("/trends/wind")(analytics_ctrl.wind_trends)
analytics_bp.get("/trends")(analytics_ctrl.all_trends)
analytics_bp.get("/monthly")(analytics_ctrl.monthly_statistics)
analytics_bp.get("/historical")(analytics_ctrl.historical_analysis)
analytics_bp.get("/prediction-accuracy")(analytics_ctrl.prediction_accuracy)
analytics_bp.get("/weather-distribution")(analytics_ctrl.weather_distribution)
analytics_bp.get("/carbon-vs-temperature")(analytics_ctrl.carbon_vs_temperature)
analytics_bp.get("/pollution-ranking")(analytics_ctrl.pollution_ranking)
