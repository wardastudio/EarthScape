from __future__ import annotations

from typing import Any, Dict

from flask import g, jsonify, request

from services.ml_service_v2 import ml_service
from services.notification_service import notification_service
from services.alerts_service import alerts_service
from utils.errors import AppError
from utils.helpers import sanitize_input


def _user_id() -> str | None:
    return getattr(g, "user_id", None)


def list_models():
    return jsonify({"models": ml_service.list_models()}), 200


def predict():
    uid = _user_id()
    payload = request.get_json(silent=True) or request.form or {}
    model_name = sanitize_input(payload.get("model", "linear_regression"))
    city = sanitize_input(payload.get("city", "")) or None
    features = {k: payload.get(k) for k in payload.keys() if k not in {"model", "city"}}
    try:
        result = ml_service.predict(model_name, features, user_id=uid, city=city)
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    should_alert = (result.confidence is not None and result.confidence < 0.6) or (result.class_label in {"High", "Yes"})
    if should_alert:
        try:
            severity = "high" if result.confidence is not None and result.confidence >= 0.7 else "moderate"
            alerts_service.create_prediction_alert(
                user_id=uid,
                model=model_name,
                city=city,
                severity=severity,
                description=result.recommendation or "",
            )
            if uid:
                confidence_summary = f" (confidence {int(result.confidence * 100)}%)" if result.confidence is not None else ""
                notification_service.create_prediction_alert(
                    user_id=uid,
                    model=model_name,
                    city=city,
                    prediction_summary=f"Prediction: {result.class_label or round(result.prediction, 2)}{confidence_summary}",
                    action_required=result.recommendation,
                )
        except Exception:
            pass
    return jsonify(result.to_dict()), 200


def predict_carbon():
    uid = _user_id()
    payload = request.get_json(silent=True) or request.form or {}
    city = sanitize_input(payload.get("city", "")) or None
    try:
        result = ml_service.predict_carbon(payload, user_id=uid, city=city)
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify(result.to_dict()), 200


def predict_severity():
    uid = _user_id()
    payload = request.get_json(silent=True) or request.form or {}
    city = sanitize_input(payload.get("city", "")) or None
    try:
        result = ml_service.predict_severity(payload, user_id=uid, city=city)
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify(result.to_dict()), 200


def predict_heatwave():
    uid = _user_id()
    payload = request.get_json(silent=True) or request.form or {}
    city = sanitize_input(payload.get("city", "")) or None
    try:
        result = ml_service.predict_heatwave(payload, user_id=uid, city=city)
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify(result.to_dict()), 200


def predict_all():
    uid = _user_id()
    payload = request.get_json(silent=True) or request.form or {}
    city = sanitize_input(payload.get("city", "")) or None
    try:
        results = ml_service.predict_all(payload, user_id=uid, city=city)
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify({k: v.to_dict() for k, v in results.items()}), 200


def evaluate_model(model_name: str):
    payload = request.get_json(silent=True) or {}
    X = payload.get("X") or payload.get("features") or []
    y = payload.get("y") or payload.get("labels") or []
    if not X or not y:
        return jsonify({"error": "validation_error", "message": "X and y are required"}), 422
    try:
        result = ml_service.evaluate(model_name, X, y)
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify(result), 200


def train_model(model_name: str):
    payload = request.get_json(silent=True) or {}
    dataset_path = payload.get("dataset_path")
    target = payload.get("target")
    try:
        result = ml_service.train(model_name, dataset_path=dataset_path, target=target)
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify(result), 200


def prediction_history():
    uid = _user_id()
    model = sanitize_input(request.args.get("model", "")) or None
    limit = int(request.args.get("limit", 50))
    result = ml_service.list_prediction_history(user_id=uid, model=model, limit=limit)
    return jsonify(result), 200


def prediction_accuracy():
    model = sanitize_input(request.args.get("model", "")) or None
    window = int(request.args.get("window_days", 30))
    result = ml_service.get_prediction_accuracy(model=model, window_days=window)
    return jsonify(result), 200
