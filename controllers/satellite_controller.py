from __future__ import annotations

from flask import jsonify, request

from services.satellite_service import satellite_service
from utils.errors import AppError
from utils.helpers import sanitize_input


def latest_satellite_products():
    lat = request.args.get("lat") or request.args.get("latitude")
    lon = request.args.get("lon") or request.args.get("longitude")
    radius = request.args.get("radius_km", 20)
    limit = request.args.get("limit", 10)
    days = request.args.get("days", 14)
    collection = request.args.get("collection")

    try:
        latitude = float(sanitize_input(lat))
        longitude = float(sanitize_input(lon))
        radius_km = float(sanitize_input(radius))
        limit = int(sanitize_input(limit))
        days = int(sanitize_input(days))
        if collection is not None:
            collection = sanitize_input(collection)
    except (TypeError, ValueError):
        return jsonify({"error": "validation_error", "message": "Invalid numeric query parameters."}), 422

    try:
        # Only pass `collection` when explicitly provided to keep test monkeypatch compatibility
        if collection:
            result = satellite_service.get_latest_products(
                latitude=latitude,
                longitude=longitude,
                radius_km=radius_km,
                limit=limit,
                days=days,
                collection=collection,
            )
        else:
            result = satellite_service.get_latest_products(
                latitude=latitude,
                longitude=longitude,
                radius_km=radius_km,
                limit=limit,
                days=days,
            )
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify(result), 200
