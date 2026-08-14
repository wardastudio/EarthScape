from __future__ import annotations

from flask import Blueprint

from controllers import weather_controller as weather_ctrl
from middleware.auth import login_required, role_required


weather_bp = Blueprint("weather_api", __name__, url_prefix="/api/weather")


weather_bp.get("/search")(weather_ctrl.search_city)
weather_bp.get("/current")(weather_ctrl.get_current_weather)
weather_bp.get("/forecast")(weather_ctrl.get_forecast)
weather_bp.get("/air-quality")(weather_ctrl.get_air_quality)
weather_bp.get("/coordinates")(weather_ctrl.get_coordinates)
weather_bp.get("/summary")(weather_ctrl.weather_summary)

weather_bp.get("/saved-cities")(login_required(weather_ctrl.list_saved_cities))
weather_bp.post("/saved-cities")(login_required(weather_ctrl.save_city))
weather_bp.delete("/saved-cities/<city_id>")(login_required(weather_ctrl.delete_saved_city))
