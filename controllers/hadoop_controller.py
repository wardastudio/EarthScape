from __future__ import annotations

from flask import jsonify, request

from services.hadoop_service import hadoop_service
from utils.errors import AppError


def hadoop_status():
    status = hadoop_service.detect_hadoop()
    return jsonify(status), 200


def hadoop_process():
    payload = request.get_json(silent=True) or {}
    dataset_path = payload.get("dataset_path")
    try:
        result = hadoop_service.process_dataset(dataset_path)
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify(result), 200


def import_mapreduce_results():
    payload = request.get_json(silent=True) or {}
    jsonl_path = payload.get("jsonl_path")
    try:
        result = hadoop_service.import_mapreduce_results(jsonl_path)
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify(result), 200


def hadoop_station_analytics():
    try:
        result = hadoop_service.get_station_analytics()
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify(result), 200


def hadoop_risk_analytics():
    try:
        result = hadoop_service.get_risk_analytics()
    except AppError as exc:
        return jsonify(exc.to_dict()), exc.status_code
    return jsonify(result), 200
