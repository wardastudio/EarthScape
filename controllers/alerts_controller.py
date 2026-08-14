from __future__ import annotations

from typing import Any, Dict

from flask import g, jsonify, request

from services.alerts_service import alerts_service
from utils.errors import AppError
from utils.helpers import sanitize_input


def _user_id() -> str | None:
    return getattr(g, "user_id", None)


def create_alert():
    uid = _user_id()
    payload: Dict[str, Any] = request.get_json(silent=True) or request.form or {}
    try:
        result = alerts_service.create(
            user_id=uid,
            title=sanitize_input(payload.get("title", "")),
            description=sanitize_input(payload.get("description", "")),
            alert_type=sanitize_input(payload.get("type", "weather")),
            severity=sanitize_input(payload.get("severity", "moderate")),
            city=sanitize_input(payload.get("city", "")) or None,
            metadata=payload.get("metadata"),
        )
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify({"message": "Alert created", "item": result}), 201


def list_alerts():
    uid = _user_id()
    status = sanitize_input(request.args.get("status", "")) or None
    severity = sanitize_input(request.args.get("severity", "")) or None
    alert_type = sanitize_input(request.args.get("type", "")) or None
    city = sanitize_input(request.args.get("city", "")) or None
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 50))
    result = alerts_service.list(
        user_id=uid,
        status=status,
        severity=severity,
        alert_type=alert_type,
        city=city,
        page=page,
        page_size=page_size,
    )
    return jsonify(result), 200


def get_alert(alert_id: str):
    uid = _user_id()
    try:
        result = alerts_service.get(alert_id, user_id=uid)
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify(result), 200


def update_alert_status(alert_id: str):
    uid = _user_id()
    payload = request.get_json(silent=True) or request.form or {}
    status = sanitize_input(payload.get("status", ""))
    if not status:
        return jsonify({"error": "validation_error", "message": "status is required"}), 422
    try:
        result = alerts_service.update_status(alert_id, status, acknowledged_by=uid)
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify(result), 200


def delete_alert(alert_id: str):
    uid = _user_id()
    try:
        result = alerts_service.delete(alert_id, user_id=uid)
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify(result), 200
