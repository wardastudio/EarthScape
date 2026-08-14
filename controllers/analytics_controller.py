from __future__ import annotations

from flask import jsonify, request

from services.analytics_service import analytics_service
from utils.errors import AppError


def dashboard_overview():
    return jsonify(analytics_service.dashboard_overview()), 200


def analytics_overview():
    try:
        result = analytics_service.get_unified_analytics()
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify(result), 200


def temperature_trends():
    interval = request.args.get("interval", "weekly").lower()
    try:
        result = analytics_service.temperature_trends(interval=interval)
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify(result), 200


def humidity_trends():
    interval = request.args.get("interval", "weekly").lower()
    try:
        result = analytics_service.humidity_trends(interval=interval)
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify(result), 200


def rainfall_trends():
    interval = request.args.get("interval", "weekly").lower()
    try:
        result = analytics_service.rainfall_trends(interval=interval)
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify(result), 200


def pressure_trends():
    interval = request.args.get("interval", "weekly").lower()
    try:
        result = analytics_service.pressure_trends(interval=interval)
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify(result), 200


def wind_trends():
    interval = request.args.get("interval", "weekly").lower()
    try:
        result = analytics_service.wind_trends(interval=interval)
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify(result), 200


def all_trends():
    interval = request.args.get("interval", "weekly").lower()
    return jsonify(analytics_service.all_trends(interval=interval)), 200


def monthly_statistics():
    try:
        year = int(request.args.get("year")) if request.args.get("year") else None
    except ValueError:
        year = None
    return jsonify(analytics_service.monthly_statistics(year=year)), 200


def historical_analysis():
    try:
        start = int(request.args.get("start")) if request.args.get("start") else None
        end = int(request.args.get("end")) if request.args.get("end") else None
    except ValueError:
        start = end = None
    return jsonify(analytics_service.historical_analysis(start_period=start, end_period=end)), 200


def prediction_accuracy():
    model = request.args.get("model") or None
    return jsonify(analytics_service.prediction_accuracy(model=model)), 200


def weather_distribution():
    return jsonify(analytics_service.weather_distribution()), 200


def carbon_vs_temperature():
    samples = int(request.args.get("samples", 100))
    return jsonify(analytics_service.carbon_vs_temperature(samples=samples)), 200


def pollution_ranking():
    limit = int(request.args.get("limit", 10))
    return jsonify(analytics_service.pollution_ranking(limit=limit)), 200
