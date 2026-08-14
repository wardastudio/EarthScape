from __future__ import annotations

import joblib
import numpy as np
from pathlib import Path

from config import Config

MODEL_DIR = Config.MODEL_DIR

MODEL_CACHE = {}


def load_model(name: str):
    if name in MODEL_CACHE:
        return MODEL_CACHE[name]
    model_path = MODEL_DIR / name
    if not model_path.exists():
        raise FileNotFoundError(f"Model file not found: {model_path}")
    model = joblib.load(model_path)
    MODEL_CACHE[name] = model
    return model


def predict_emission(payload: dict) -> dict:
    model = load_model("linear_regression.pkl")
    sample = np.array([
        float(payload.get("temperature", 0)),
        float(payload.get("humidity", 0)),
        float(payload.get("pressure", 0)),
        float(payload.get("wind_speed", 0)),
        float(payload.get("rainfall", 0)),
        float(payload.get("aqi", 0)),
        float(payload.get("co2", 0)),
    ], dtype=float).reshape(1, -1)
    prediction = float(model.predict(sample)[0])
    confidence = round(min(0.99, max(0.65, 0.72 + min(0.2, abs(prediction) / 10000))), 2)
    recommendation = "Emission is within expected range." if prediction < 250 else "Emission is elevated; increase mitigation measures."
    return {"prediction": round(prediction, 2), "confidence": confidence, "status": "success", "recommendation": recommendation}


def predict_classification(payload: dict) -> dict:
    model = load_model("decision_tree.pkl")
    sample = np.array([
        float(payload.get("temperature", 0)),
        float(payload.get("humidity", 0)),
        float(payload.get("rainfall", 0)),
        float(payload.get("wind_speed", 0)),
        float(payload.get("pressure", 0)),
    ], dtype=float).reshape(1, -1)
    prediction = int(model.predict(sample)[0])
    labels = {0: "Low", 1: "Medium", 2: "High"}
    return {"prediction": labels.get(prediction, prediction), "status": "success"}


def predict_heatwave(payload: dict) -> dict:
    model = load_model("knn.pkl")
    sample = np.array([
        float(payload.get("temperature", 0)),
        float(payload.get("humidity", 0)),
        float(payload.get("aqi", 0)),
        float(payload.get("uv_index", 0)),
    ], dtype=float).reshape(1, -1)
    prediction = int(model.predict(sample)[0])
    return {"prediction": "Yes" if prediction == 1 else "No", "status": "success"}
