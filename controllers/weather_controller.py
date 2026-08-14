from __future__ import annotations

from typing import Any, Dict

from flask import g, jsonify, request

from services.weather_service import weather_service
from utils.errors import AppError
from utils.helpers import sanitize_input


def _user_id() -> str | None:
    return getattr(g, "user_id", None)


def search_city():
    query = sanitize_input(request.args.get("q", "").strip())
    limit = int(request.args.get("limit", 10))
    try:
        results = weather_service.search_city(query, limit=limit)
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify({"items": results, "query": query}), 200


def get_current_weather():
    city = ""
    latitude = None
    longitude = None
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        city = sanitize_input(request.args.get("city") or payload.get("city", ""))
        latitude = payload.get("lat") if payload.get("lat") is not None else payload.get("latitude")
        longitude = payload.get("lon") if payload.get("lon") is not None else payload.get("longitude")
    else:
        city = sanitize_input(request.args.get("city", ""))
        latitude = request.args.get("lat") or request.args.get("latitude")
        longitude = request.args.get("lon") or request.args.get("longitude")

    country = sanitize_input(request.args.get("country", ""))
    try:
        latitude = float(latitude) if latitude is not None and latitude != "" else None
    except (ValueError, TypeError):
        return jsonify({"error": "validation_error", "message": "Latitude must be a number"}), 422
    try:
        longitude = float(longitude) if longitude is not None and longitude != "" else None
    except (ValueError, TypeError):
        return jsonify({"error": "validation_error", "message": "Longitude must be a number"}), 422

    try:
        result = weather_service.get_current_weather(city, country=country, latitude=latitude, longitude=longitude)
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify(result), 200


def get_forecast():
    city = sanitize_input(request.args.get("city", ""))
    country = sanitize_input(request.args.get("country", ""))
    days = int(request.args.get("days", 7))
    try:
        result = weather_service.get_forecast(city, days=days, country=country)
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify(result), 200


def get_air_quality():
    city = sanitize_input(request.args.get("city", ""))
    country = sanitize_input(request.args.get("country", ""))
    try:
        result = weather_service.get_air_quality(city, country=country)
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify(result), 200


def get_coordinates():
    city = sanitize_input(request.args.get("city", ""))
    country = sanitize_input(request.args.get("country", ""))
    try:
        result = weather_service.get_coordinates(city, country=country)
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify(result), 200


def list_saved_cities():
    uid = _user_id()
    if not uid:
        return jsonify({"error": "authentication_error", "message": "Authentication required"}), 401
    results = weather_service.get_saved_cities(uid)
    return jsonify({"items": results}), 200


def save_city():
    uid = _user_id()
    if not uid:
        return jsonify({"error": "authentication_error", "message": "Authentication required"}), 401
    payload = request.get_json(silent=True) or request.form or {}
    city = sanitize_input(payload.get("city", ""))
    country = sanitize_input(payload.get("country", ""))
    nickname = sanitize_input(payload.get("nickname", ""))
    try:
        result = weather_service.save_city(uid, city, country=country, nickname=nickname)
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify({"message": "City saved successfully", "item": result}), 201


def delete_saved_city(city_id: str):
    uid = _user_id()
    if not uid:
        return jsonify({"error": "authentication_error", "message": "Authentication required"}), 401
    ok = weather_service.delete_saved_city(uid, city_id)
    if not ok:
        return jsonify({"error": "not_found", "message": "Saved city not found"}), 404
    return jsonify({"message": "City removed successfully"}), 200


def weather_summary():
    city = sanitize_input(request.args.get("city", ""))
    country = sanitize_input(request.args.get("country", ""))
    try:
        current = weather_service.get_current_weather(city, country=country)
        aqi = weather_service.get_air_quality(city, country=country)
        forecast = weather_service.get_forecast(city, days=5, country=country)
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify({"current": current, "air_quality": aqi, "forecast_5d": forecast}), 200
