from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from flask import jsonify, request

from database import get_db
from services.data_service import DataService
from services.ml_service import predict_classification, predict_emission, predict_heatwave
from utils.helpers import sanitize_input

service = DataService()


def get_dashboard():
    return jsonify(service.get_dashboard_metrics())


def create_prediction():
    payload = request.get_json(silent=True) or request.form or {}
    city = sanitize_input(payload.get("city", ""))
    if not city:
        return jsonify({"error": "City is required"}), 422
    try:
        result = predict_emission(payload)
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 500
    doc = {
        "city": city,
        "date": datetime.utcnow().isoformat(),
        "predicted_emission": result["prediction"],
        "prediction_model": "linear_regression",
        "confidence_score": result["confidence"],
        "status": result["status"],
        "temperature": payload.get("temperature"),
        "humidity": payload.get("humidity"),
        "pressure": payload.get("pressure"),
        "wind_speed": payload.get("wind_speed"),
        "rainfall": payload.get("rainfall"),
        "aqi": payload.get("aqi"),
        "co2": payload.get("co2"),
        "timestamp": datetime.utcnow().isoformat(),
    }
    db = get_db()
    db.prediction_history.insert_one(doc)
    db.api_logs.insert_one({"endpoint": "/api/predict", "method": request.method, "status_code": 200, "response_time": 0, "timestamp": datetime.utcnow().isoformat()})
    return jsonify({"prediction": result["prediction"], "confidence": result["confidence"], "status": result["status"], "recommendation": result["recommendation"]})


def search_records():
    query = request.args.get("q", "")
    collection = request.args.get("collection", "users")
    db = get_db()
    if query:
        filter_query = {
            "$or": [
                {"email": {"$regex": query, "$options": "i"}},
                {"full_name": {"$regex": query, "$options": "i"}},
                {"city": {"$regex": query, "$options": "i"}},
                {"name": {"$regex": query, "$options": "i"}},
            ]
        }
    else:
        filter_query = {}
    results = list(db[collection].find(filter_query).limit(20))
    return jsonify({"results": results})


def create_weather():
    payload = request.get_json(silent=True) or request.form or {}
    doc = {"city": payload.get("city"), "temperature": payload.get("temperature"), "humidity": payload.get("humidity"), "pressure": payload.get("pressure"), "wind_speed": payload.get("wind_speed"), "rainfall": payload.get("rainfall"), "air_quality_index": payload.get("air_quality_index") or payload.get("aqi"), "co2_level": payload.get("co2_level") or payload.get("co2"), "timestamp": datetime.utcnow().isoformat()}
    service.create_document("weather_data", doc)
    return jsonify({"message": "Weather record created"})


def create_air_quality():
    payload = request.get_json(silent=True) or request.form or {}
    doc = {"city": payload.get("city"), "aqi": payload.get("aqi"), "pm25": payload.get("pm25"), "pm10": payload.get("pm10"), "no2": payload.get("no2"), "co": payload.get("co"), "so2": payload.get("so2"), "ozone": payload.get("ozone"), "timestamp": datetime.utcnow().isoformat()}
    service.create_document("air_quality", doc)
    return jsonify({"message": "Air quality record created"})


def create_emission():
    payload = request.get_json(silent=True) or request.form or {}
    doc = {"city": payload.get("city"), "industry": payload.get("industry"), "vehicle_count": payload.get("vehicle_count"), "co2": payload.get("co2"), "methane": payload.get("methane"), "nitrous_oxide": payload.get("nitrous_oxide"), "total_emission": payload.get("total_emission"), "date": payload.get("date") or datetime.utcnow().isoformat()}
    service.create_document("emission_reports", doc)
    return jsonify({"message": "Emission report created"})


def list_collection(collection: str):
    docs = service.find_documents(collection)
    return jsonify({"items": docs})


def crud_collection(collection: str):
    if request.method == "POST":
        payload = request.get_json(silent=True) or request.form or {}
        item = service.create_document(collection, payload)
        return jsonify({"message": "Created", "item": item}), 201
    if request.method == "PUT":
        payload = request.get_json(silent=True) or request.form or {}
        item_id = request.args.get("id") or payload.get("id")
        if not item_id:
            return jsonify({"error": "id required"}), 422
        ok = service.update_document(collection, {"_id": item_id}, payload)
        return jsonify({"message": "Updated" if ok else "No changes made"})
    if request.method == "DELETE":
        item_id = request.args.get("id") or request.get_json(silent=True, force=True).get("id") if request.get_json(silent=True) else None
        if not item_id:
            return jsonify({"error": "id required"}), 422
        ok = service.delete_document(collection, {"_id": item_id})
        return jsonify({"message": "Deleted" if ok else "Not found"})
    return jsonify({"error": "Method not allowed"}), 405
