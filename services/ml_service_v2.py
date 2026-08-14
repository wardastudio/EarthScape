from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

import math

import joblib
import numpy as np
import pandas as pd

from config import Config
from database import get_db
from utils.errors import MLModelError, ValidationError
from utils.helpers import now_iso, serialize_document
from utils.logging_setup import log_prediction


MODEL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "linear_regression": {
        "file": "linear_regression.pkl",
        "type": "regression",
        "task": "carbon_emission_prediction",
        "features": ["temperature", "humidity", "aqi", "co2", "industrial_index", "energy_consumption", "renewable_energy"],
        "feature_columns": ["Temperature_C", "Humidity_%", "AQI", "CO2_ppm", "IndustrialIndex", "EnergyConsumption_MWh", "RenewableEnergy_%"],
        "target": "CarbonEmission",
        "description": "Predicts carbon emission levels based on climate and pollution factors.",
    },
    "decision_tree": {
        "file": "decision_tree.pkl",
        "type": "classification",
        "task": "flood_risk_prediction",
        "features": ["temperature", "humidity", "rainfall", "wind_speed", "pressure"],
        "feature_columns": ["Temperature_C", "Humidity_%", "Rainfall_mm", "WindSpeed_kmh", "Pressure_hPa"],
        "target": "FloodRisk",
        "classes": {0: "Low", 1: "Medium", 2: "High"},
        "description": "Predicts flood risk levels based on weather and pressure indicators.",
    },
    "knn": {
        "file": "knn.pkl",
        "type": "classification",
        "task": "heatwave_prediction",
        "features": ["temperature", "humidity", "aqi", "uv_index"],
        "feature_columns": ["Temperature_C", "Humidity_%", "AQI", "UV_Index"],
        "target": "Heatwave",
        "classes": {0: "No", 1: "Yes"},
        "description": "Predicts heatwave occurrence based on temperature, humidity, AQI and UV index.",
    },
    "carbon_model": {
        "file": "carbon_model.pkl",
        "type": "regression",
        "task": "carbon_emission_prediction",
        "features": ["temperature", "humidity", "aqi", "co2", "industrial_index", "energy_consumption", "renewable_energy"],
        "feature_columns": ["Temperature_C", "Humidity_%", "AQI", "CO2_ppm", "IndustrialIndex", "EnergyConsumption_MWh", "RenewableEnergy_%"],
        "target": "CarbonEmission",
        "description": "Colab-trained carbon emission model for comparison.",
    },
    "flood_model": {
        "file": "flood_model.pkl",
        "type": "classification",
        "task": "flood_risk_prediction",
        "features": ["temperature", "humidity", "rainfall", "wind_speed", "pressure"],
        "feature_columns": ["Temperature_C", "Humidity_%", "Rainfall_mm", "WindSpeed_kmh", "Pressure_hPa"],
        "target": "FloodRisk",
        "classes": {0: "Low", 1: "Medium", 2: "High"},
        "description": "Colab-trained flood risk model for comparison.",
    },
    "heatwave_model": {
        "file": "heatwave_model.pkl",
        "type": "classification",
        "task": "heatwave_prediction",
        "features": ["temperature", "humidity", "aqi", "uv_index"],
        "feature_columns": ["Temperature_C", "Humidity_%", "AQI", "UV_Index"],
        "target": "Heatwave",
        "classes": {0: "No", 1: "Yes"},
        "description": "Colab-trained heatwave model for comparison.",
    },
    "tomorrow_temp": {
        "file": "tomorrow_temp_model_clean.pkl",
        "type": "regression",
        "task": "tomorrow_temperature_prediction",
        "features": [
            "temperature",
            "humidity_percent",
            "rainfall",
            "wind_speed",
            "pressure",
            "uv_index",
            "co2",
            "pm2_5",
            "pm10",
            "no2",
            "so2",
            "ozone",
        ],
        "feature_columns": [
            "Temperature_C",
            "Humidity_Percent",
            "Rainfall_mm",
            "Wind_Speed_kmh",
            "Pressure_hPa",
            "UV_Index",
            "CO2_ppm",
            "PM2_5_ug_m3",
            "PM10_ug_m3",
            "NO2_ppb",
            "SO2_ppb",
            "Ozone_ppb",
        ],
        "target": "Tomorrow_Temp_C",
        "description": "Clean fusion model for next-day temperature prediction.",
    },
    "rain_tomorrow": {
        "file": "rain_tomorrow_model_clean.pkl",
        "type": "classification",
        "task": "rain_tomorrow_prediction",
        "features": [
            "temperature",
            "humidity_percent",
            "rainfall",
            "wind_speed",
            "pressure",
            "uv_index",
            "co2",
            "pm2_5",
            "pm10",
            "no2",
            "so2",
            "ozone",
        ],
        "feature_columns": [
            "Temperature_C",
            "Humidity_Percent",
            "Rainfall_mm",
            "Wind_Speed_kmh",
            "Pressure_hPa",
            "UV_Index",
            "CO2_ppm",
            "PM2_5_ug_m3",
            "PM10_ug_m3",
            "NO2_ppb",
            "SO2_ppb",
            "Ozone_ppb",
        ],
        "target": "Rain_Tomorrow",
        "description": "Clean fusion model for next-day rainfall prediction.",
    },
    "temp_anomaly": {
        "file": "temp_anomaly_model_clean.pkl",
        "type": "regression",
        "task": "temperature_anomaly_prediction",
        "features": [
            "temperature",
            "humidity_percent",
            "rainfall",
            "wind_speed",
            "pressure",
            "uv_index",
            "co2",
            "pm2_5",
            "pm10",
            "no2",
            "so2",
            "ozone",
        ],
        "feature_columns": [
            "Temperature_C",
            "Humidity_Percent",
            "Rainfall_mm",
            "Wind_Speed_kmh",
            "Pressure_hPa",
            "UV_Index",
            "CO2_ppm",
            "PM2_5_ug_m3",
            "PM10_ug_m3",
            "NO2_ppb",
            "SO2_ppb",
            "Ozone_ppb",
        ],
        "target": "Temp_Anomaly_C",
        "description": "Clean fusion model for temperature anomaly magnitude prediction.",
    },
    "temp_anomaly_detect": {
        "file": "temp_anomaly_detect_model_clean.pkl",
        "type": "classification",
        "task": "temperature_anomaly_detection",
        "features": [
            "temperature",
            "humidity_percent",
            "rainfall",
            "wind_speed",
            "pressure",
            "uv_index",
            "co2",
            "pm2_5",
            "pm10",
            "no2",
            "so2",
            "ozone",
        ],
        "feature_columns": [
            "Temperature_C",
            "Humidity_Percent",
            "Rainfall_mm",
            "Wind_Speed_kmh",
            "Pressure_hPa",
            "UV_Index",
            "CO2_ppm",
            "PM2_5_ug_m3",
            "PM10_ug_m3",
            "NO2_ppb",
            "SO2_ppb",
            "Ozone_ppb",
        ],
        "target": "Temp_Anomaly_Detect",
        "description": "Clean fusion model for temperature anomaly detection.",
    },
}

MODEL_SCHEMAS: Dict[str, List[str]] = {name: meta["feature_columns"] for name, meta in MODEL_REGISTRY.items()}

MODEL_COLUMN_ALIASES: Dict[str, List[str]] = {
    "Temperature_C": ["Temperature_C", "temperature"],
    "Humidity_%": ["Humidity_%", "Humidity_Percent", "humidity", "humidity_percent"],
    "Humidity_Percent": ["Humidity_Percent", "Humidity_%", "humidity", "humidity_percent"],
    "Rainfall_mm": ["Rainfall_mm", "rainfall"],
    "WindSpeed_kmh": ["WindSpeed_kmh", "Wind_Speed_kmh", "wind_speed"],
    "Wind_Speed_kmh": ["Wind_Speed_kmh", "WindSpeed_kmh", "wind_speed"],
    "Pressure_hPa": ["Pressure_hPa", "pressure"],
    "UV_Index": ["UV_Index", "uv_index"],
    "CO2_ppm": ["CO2_ppm", "co2"],
    "PM2_5_ug_m3": ["PM2_5_ug_m3", "pm2_5", "pm2_5_ug_m3"],
    "PM10_ug_m3": ["PM10_ug_m3", "pm10", "pm10_ug_m3"],
    "NO2_ppb": ["NO2_ppb", "no2"],
    "SO2_ppb": ["SO2_ppb", "so2"],
    "Ozone_ppb": ["Ozone_ppb", "ozone"],
    "AQI": ["AQI", "aqi"],
    "IndustrialIndex": ["IndustrialIndex", "industrial_index"],
    "EnergyConsumption_MWh": ["EnergyConsumption_MWh", "energy_consumption"],
    "RenewableEnergy_%": ["RenewableEnergy_%", "renewable_energy"],
}

FEATURE_NAME_MAP: Dict[str, str] = {
    "temperature": "Temperature_C",
    "humidity": "Humidity_%",
    "pressure": "Pressure_hPa",
    "rainfall": "Rainfall_mm",
    "wind_speed": "WindSpeed_kmh",
    "aqi": "AQI",
    "co2": "CO2_ppm",
    "industrial_index": "IndustrialIndex",
    "energy_consumption": "EnergyConsumption_MWh",
    "renewable_energy": "RenewableEnergy_%",
    "uv_index": "UV_Index",
}


@dataclass
class PredictionResult:
    model: str
    task: str
    prediction: Any
    confidence: Optional[float] = None
    class_label: Optional[str] = None
    recommendation: Optional[str] = None
    evaluation: Dict[str, Any] = field(default_factory=dict)
    feature_importance: Dict[str, float] = field(default_factory=dict)
    raw_input: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MLService:
    def __init__(self) -> None:
        self.db = None
        self._model_cache: Dict[str, Any] = {}
        self._feature_stats = self._compute_feature_stats()

    def _ensure_db(self) -> None:
        if self.db is not None:
            return
        try:
            self.db = get_db()
        except Exception:
            self.db = None

    def list_models(self) -> List[Dict[str, Any]]:
        results = []
        for name, meta in MODEL_REGISTRY.items():
            entry = dict(meta)
            entry["name"] = name
            entry["loaded"] = name in self._model_cache or (Config.MODEL_DIR / entry["file"]).exists()
            results.append(entry)
        return results

    def load_model(self, name: str) -> Any:
        if name not in MODEL_REGISTRY:
            raise MLModelError(f"Unknown model: {name}. Available: {sorted(MODEL_REGISTRY.keys())}")
        if name in self._model_cache:
            return self._model_cache[name]
        meta = MODEL_REGISTRY[name]
        model_path = Config.MODEL_DIR / meta["file"]
        if not model_path.exists():
            raise MLModelError(f"Model file not found: {model_path}")
        try:
            model = joblib.load(model_path)
        except Exception as exc:
            raise MLModelError(f"Failed to load model {name}: {exc}") from exc
        self._model_cache[name] = model
        return model

    def predict(self, model_name: str, features: Dict[str, Any], user_id: Optional[str] = None, city: Optional[str] = None) -> PredictionResult:
        if model_name not in MODEL_REGISTRY:
            raise ValidationError(f"Unknown model: {model_name}")
        meta = MODEL_REGISTRY[model_name]
        required = meta["features"]
        fused_features = self._build_fused_features(features, required)
        merged_features = {**fused_features, **features}
        prepared = self._prepare_model_features(model_name, merged_features)
        model = self.load_model(model_name)
        sample = np.array([prepared], dtype=float)
        try:
            raw_pred = model.predict(sample)
        except Exception as exc:
            log_prediction(model_name, user_id=user_id, city=city, error=str(exc))
            raise MLModelError(f"Prediction failed: {exc}") from exc
        prediction_value = raw_pred[0].item() if hasattr(raw_pred[0], "item") else raw_pred[0]
        if meta["type"] == "classification":
            prediction_value = int(prediction_value)
        else:
            prediction_value = float(prediction_value)
        confidence = self._infer_confidence(model_name, model, sample, prediction_value)
        class_label = None
        if meta["type"] == "classification" and "classes" in meta:
            class_label = meta["classes"].get(int(prediction_value), str(prediction_value))
        recommendation = self._recommendation_for(model_name, prediction_value, class_label)
        importance = self._feature_importance(model_name, prepared)
        evaluation = self._model_evaluation(model_name)
        raw_input = {}
        for k in required:
            # Preserve original payload semantics for missing fused values.
            if k in features:
                raw_input[k] = features[k]
            else:
                raw_input[k] = None

        result = PredictionResult(
            model=model_name,
            task=meta["task"],
            prediction=prediction_value,
            confidence=round(float(confidence), 3) if confidence is not None else None,
            class_label=class_label,
            recommendation=recommendation,
            evaluation=evaluation,
            feature_importance={k: round(v, 4) for k, v in importance.items()},
            raw_input=raw_input,
        )
        self._store_prediction(result, user_id=user_id, city=city)
        log_prediction(model_name, user_id=user_id, city=city, result={"prediction": prediction_value, "confidence": confidence})
        return result

    def predict_carbon(self, features: Dict[str, Any], user_id: Optional[str] = None, city: Optional[str] = None) -> PredictionResult:
        return self.predict("linear_regression", features, user_id=user_id, city=city)

    def predict_severity(self, features: Dict[str, Any], user_id: Optional[str] = None, city: Optional[str] = None) -> PredictionResult:
        return self.predict("decision_tree", features, user_id=user_id, city=city)

    def predict_heatwave(self, features: Dict[str, Any], user_id: Optional[str] = None, city: Optional[str] = None) -> PredictionResult:
        return self.predict("knn", features, user_id=user_id, city=city)

    def predict_tomorrow_temperature(self, features: Dict[str, Any], user_id: Optional[str] = None, city: Optional[str] = None) -> PredictionResult:
        return self.predict("tomorrow_temp", features, user_id=user_id, city=city)

    def predict_rain_tomorrow(self, features: Dict[str, Any], user_id: Optional[str] = None, city: Optional[str] = None) -> PredictionResult:
        return self.predict("rain_tomorrow", features, user_id=user_id, city=city)

    def predict_temperature_anomaly(self, features: Dict[str, Any], user_id: Optional[str] = None, city: Optional[str] = None) -> PredictionResult:
        return self.predict("temp_anomaly", features, user_id=user_id, city=city)

    def predict_temperature_anomaly_detect(self, features: Dict[str, Any], user_id: Optional[str] = None, city: Optional[str] = None) -> PredictionResult:
        return self.predict("temp_anomaly_detect", features, user_id=user_id, city=city)

    def predict_all(self, features: Dict[str, Any], user_id: Optional[str] = None, city: Optional[str] = None) -> Dict[str, PredictionResult]:
        return {
            "carbon_emission": self.predict_carbon(features, user_id=user_id, city=city),
            "climate_severity": self.predict_severity(features, user_id=user_id, city=city),
            "heatwave": self.predict_heatwave(features, user_id=user_id, city=city),
        }

    def evaluate(self, model_name: str, X: List[List[float]], y: List[Any]) -> Dict[str, Any]:
        if model_name not in MODEL_REGISTRY:
            raise ValidationError(f"Unknown model: {model_name}")
        meta = MODEL_REGISTRY[model_name]
        model = self.load_model(model_name)
        try:
            X_arr = np.array(X, dtype=float)
            y_arr = np.array(y)
            predictions = model.predict(X_arr)
        except Exception as exc:
            raise MLModelError(f"Evaluation failed: {exc}") from exc

        metrics: Dict[str, Any] = {"model": model_name, "n_samples": int(len(y))}
        if meta["type"] == "regression":
            y_true = y_arr.astype(float)
            y_pred = predictions.astype(float)
            metrics["mae"] = round(float(np.mean(np.abs(y_true - y_pred))), 4)
            metrics["mse"] = round(float(np.mean((y_true - y_pred) ** 2)), 4)
            metrics["rmse"] = round(float(np.sqrt(metrics["mse"])), 4)
            ss_res = float(np.sum((y_true - y_pred) ** 2))
            ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
            metrics["r2"] = round(1 - (ss_res / ss_tot) if ss_tot else 0.0, 4)
        else:
            from collections import Counter
            y_true = y_arr.astype(int) if np.issubdtype(y_arr.dtype, np.number) else y_arr
            y_pred = predictions.astype(int) if np.issubdtype(predictions.dtype, np.number) else predictions
            correct = int(np.sum(y_true == y_pred))
            metrics["accuracy"] = round(correct / len(y_true), 4)
            labels = sorted(set(y_true.tolist() + y_pred.tolist()))
            per_class = {}
            for label in labels:
                tp = int(np.sum((y_pred == label) & (y_true == label)))
                fp = int(np.sum((y_pred == label) & (y_true != label)))
                fn = int(np.sum((y_pred != label) & (y_true == label)))
                precision = tp / (tp + fp) if (tp + fp) else 0.0
                recall = tp / (tp + fn) if (tp + fn) else 0.0
                f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
                per_class[str(label)] = {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4), "support": int(np.sum(y_true == label))}
            metrics["per_class"] = per_class
        return metrics

    def compare_models(
        self,
        model_names: Optional[List[str]] = None,
        dataset_path: Optional[str] = None,
        test_size: float = 0.2,
        random_state: int = 42,
    ) -> Dict[str, Any]:
        from sklearn.model_selection import train_test_split

        if model_names is None:
            model_names = list(MODEL_REGISTRY.keys())
        if not model_names:
            raise ValidationError("At least one model name must be provided for comparison.")

        df = self._load_training_data(dataset_path)
        if df.empty:
            raise MLModelError("Comparison dataset is empty.")

        results: Dict[str, Any] = {}
        indices = df.index.to_numpy()
        train_idx, test_idx = train_test_split(indices, test_size=test_size, random_state=random_state, shuffle=True)

        for model_name in model_names:
            if model_name not in MODEL_REGISTRY:
                raise ValidationError(f"Unknown model: {model_name}")
            meta = MODEL_REGISTRY[model_name]
            feature_columns = meta.get("feature_columns", [self._dataset_feature_name(name) for name in meta["features"]])
            target_col = meta["target"]
            missing = [c for c in feature_columns if c not in df.columns]
            if missing:
                raise ValidationError(f"Comparison dataset missing required columns for {model_name}: {missing}")
            if target_col not in df.columns:
                raise ValidationError(f"Comparison dataset missing target column for {model_name}: {target_col}")

            X_test = df.loc[test_idx, feature_columns].astype(float).values.tolist()
            y_test = df.loc[test_idx, target_col].tolist()
            results[model_name] = self.evaluate(model_name, X_test, y_test)
        return results

    def train(self, model_name: str, dataset_path: Optional[str] = None, target: Optional[str] = None) -> Dict[str, Any]:
        if model_name not in MODEL_REGISTRY:
            raise ValidationError(f"Unknown model: {model_name}")
        meta = MODEL_REGISTRY[model_name]
        try:
            df = self._load_training_data(dataset_path)
        except Exception as exc:
            raise MLModelError(f"Failed to load training data: {exc}") from exc
        features = meta["features"]
        feature_columns = meta.get("feature_columns", [self._dataset_feature_name(name) for name in features])
        target_col = target or meta["target"]
        missing = [c for c in feature_columns if c not in df.columns]
        if missing:
            raise ValidationError(f"Training data missing required columns: {missing}")
        if target_col not in df.columns:
            raise ValidationError(f"Training data missing target column: {target_col}")

        from sklearn.linear_model import LinearRegression
        from sklearn.tree import DecisionTreeClassifier
        from sklearn.neighbors import KNeighborsClassifier
        from sklearn.model_selection import train_test_split

        X = df[feature_columns].astype(float).values
        y = df[target_col].values
        if meta["type"] == "classification":
            y = y.astype(int)
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

        if model_name == "linear_regression":
            model = LinearRegression()
        elif model_name == "decision_tree":
            model = DecisionTreeClassifier(max_depth=5, random_state=42)
        else:
            model = KNeighborsClassifier(n_neighbors=5)
        try:
            model.fit(X_train, y_train)
        except Exception as exc:
            raise MLModelError(f"Training failed: {exc}") from exc
        eval_metrics = self.evaluate(model_name, X_test.tolist(), y_test.tolist())
        save_path = self.save_model(model_name, model)
        self._model_cache[model_name] = model
        self._save_model_metadata(model_name, {
            "model": model_name,
            "file": str(save_path),
            "features": feature_columns,
            "target": target_col,
            "type": meta["type"],
            "metrics": eval_metrics,
            "train_samples": int(len(X_train)),
            "test_samples": int(len(X_test)),
        })
        return {
            "model": model_name,
            "saved_to": str(save_path),
            "train_samples": int(len(X_train)),
            "test_samples": int(len(X_test)),
            "metrics": eval_metrics,
        }

    def _save_model_metadata(self, model_name: str, metadata: Dict[str, Any]) -> None:
        metadata_path = Config.MODEL_DIR / "model_metadata.json"
        Config.MODEL_DIR.mkdir(parents=True, exist_ok=True)
        existing: Dict[str, Any] = {}
        if metadata_path.exists():
            try:
                with metadata_path.open("r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = {}
        existing[model_name] = metadata
        with metadata_path.open("w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)

    def save_model(self, model_name: str, model: Any) -> Path:
        if model_name not in MODEL_REGISTRY:
            raise ValidationError(f"Unknown model: {model_name}")
        meta = MODEL_REGISTRY[model_name]
        Config.MODEL_DIR.mkdir(parents=True, exist_ok=True)
        path = Config.MODEL_DIR / meta["file"]
        joblib.dump(model, path)
        return path

    def list_prediction_history(self, user_id: Optional[str] = None, model: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
        self._ensure_db()
        if self.db is None:
            return {"items": [], "total": 0}
        query: Dict[str, Any] = {}
        if user_id:
            query["user_id"] = user_id
        if model:
            query["model"] = model
        docs = list(self.db.prediction_history.find(query).sort("timestamp", -1).limit(limit))
        items = serialize_document(docs)
        return {"items": items, "total": self.db.prediction_history.count_documents(query)}

    def get_prediction_accuracy(self, model: Optional[str] = None, window_days: int = 30) -> Dict[str, Any]:
        self._ensure_db()
        if self.db is None:
            return {"total": 0, "avg_confidence": 0.0, "by_model": {}, "window_days": window_days}
        query: Dict[str, Any] = {}
        if model:
            query["model"] = model
        history = list(self.db.prediction_history.find(query).sort("timestamp", -1).limit(1000))
        if not history:
            return {"total": 0, "avg_confidence": 0.0, "by_model": {}}
        total = len(history)
        valid_confidences = [float(h.get("confidence", 0.0) or 0.0) for h in history if h.get("confidence") is not None]
        avg_confidence = round(sum(valid_confidences) / len(valid_confidences), 3) if valid_confidences else 0.0
        by_model: Dict[str, Any] = {}
        for h in history:
            m = h.get("model", "unknown")
            if m not in by_model:
                by_model[m] = {"count": 0, "conf_sum": 0.0, "valid_count": 0}
            by_model[m]["count"] += 1
            if h.get("confidence") is not None:
                by_model[m]["conf_sum"] += float(h.get("confidence") or 0.0)
                by_model[m]["valid_count"] += 1
        for m, agg in by_model.items():
            if agg["valid_count"]:
                agg["avg_confidence"] = round(agg["conf_sum"] / agg["valid_count"], 3)
            else:
                agg["avg_confidence"] = 0.0
            del agg["conf_sum"]
            del agg["valid_count"]
        return {"total": total, "avg_confidence": avg_confidence, "by_model": by_model, "window_days": window_days}

    def _dataset_feature_name(self, feature_name: str) -> str:
        return FEATURE_NAME_MAP.get(feature_name, feature_name)

    def _get_feature_value(self, name: str, features: Dict[str, Any]) -> Any:
        if name in features:
            return features[name]
        return features.get(self._dataset_feature_name(name))

    def _resolve_feature_value(self, column_name: str, features: Dict[str, Any]) -> Any:
        candidates = MODEL_COLUMN_ALIASES.get(column_name, [column_name])
        for candidate in candidates:
            if candidate in features and features[candidate] not in (None, ""):
                return features[candidate]
        return None

    def _prepare_model_features(self, model_name: str, features: Dict[str, Any]) -> List[float]:
        if model_name not in MODEL_REGISTRY:
            raise ValidationError(f"Unknown model: {model_name}")
        schema = MODEL_SCHEMAS.get(model_name)
        if not schema:
            raise ValidationError(f"Model schema unavailable for: {model_name}")

        ordered_values: List[float] = []
        for column in schema:
            value = self._resolve_feature_value(column, features)
            if value is None or value == "":
                stat_name = self._feature_stat_name_for_column(column)
                fallback = self._feature_stats.get(stat_name, {}).get("mean") if stat_name else None
                if fallback is None:
                    raise ValidationError(
                        f"Missing required feature(s) for {model_name}: {column}. "
                        "Provide explicit values for this exact model field or supply a legitimate source value."
                    )
                value = fallback
            try:
                ordered_values.append(float(value))
            except (TypeError, ValueError) as exc:
                raise ValidationError(f"Invalid numeric value for feature '{column}': {value}") from exc

        return ordered_values

    def _prepare_features(self, required: List[str], features: Dict[str, Any]) -> Dict[str, float]:
        prepared: Dict[str, float] = {}
        for name in required:
            raw = self._get_feature_value(name, features)
            if raw is None or raw == "":
                prepared[name] = float(self._feature_stats.get(name, {}).get("mean", 0.0))
            else:
                try:
                    prepared[name] = float(raw)
                except (TypeError, ValueError) as exc:
                    raise ValidationError(f"Invalid numeric value for feature '{name}': {raw}") from exc
        return prepared

    def _feature_stat_name_for_column(self, column_name: str) -> Optional[str]:
        mapping = {
            "Temperature_C": "temperature",
            "Humidity_%": "humidity",
            "Humidity_Percent": "humidity",
            "Rainfall_mm": "rainfall",
            "WindSpeed_kmh": "wind_speed",
            "Wind_Speed_kmh": "wind_speed",
            "Pressure_hPa": "pressure",
            "UV_Index": "uv_index",
            "CO2_ppm": "co2",
            "PM2_5_ug_m3": "pm2_5",
            "PM10_ug_m3": "pm10",
            "NO2_ppb": "no2",
            "SO2_ppb": "so2",
            "Ozone_ppb": "ozone",
            "AQI": "aqi",
            "IndustrialIndex": "industrial_index",
            "EnergyConsumption_MWh": "energy_consumption",
            "RenewableEnergy_%": "renewable_energy",
        }
        return mapping.get(column_name)

    def _build_fused_features(self, payload: Dict[str, Any], required: List[str]) -> Dict[str, float]:
        if not isinstance(payload, dict):
            return {}

        fused: Dict[str, float] = {}
        if not required:
            return fused

        weather_df = self._load_weather_dataset()
        sensor_df = self._load_sensor_dataset()
        satellite_df = self._load_satellite_dataset()

        if weather_df.empty:
            return fused

        weather_df = self._normalize_station_id(weather_df, "Station_ID")
        sensor_df = self._normalize_station_id(sensor_df, "Station_ID")
        satellite_df = self._normalize_station_id(satellite_df, "Station_ID")

        timestamp = self._coerce_timestamp(payload.get("timestamp") or payload.get("Timestamp_UTC") or payload.get("date"))
        lat = payload.get("latitude")
        lon = payload.get("longitude")

        weather_row = None
        if timestamp is not None:
            weather_row = self._match_weather_row(weather_df, lat, lon, timestamp)
        if weather_row is None:
            weather_row = self._match_weather_row(weather_df, lat, lon, None)
        if weather_row is None and not weather_df.empty:
            weather_row = weather_df.iloc[0].to_dict()
        if weather_row is None:
            return fused

        fused.update(self._map_weather_features(weather_row))

        if not sensor_df.empty:
            sensor_row = self._match_sensor_row(sensor_df, weather_row, timestamp)
            if sensor_row is not None:
                sensor_features = self._map_sensor_features(sensor_row)
                for key, value in sensor_features.items():
                    if key == "co2" and "co2" in fused:
                        fused[key] = value
                    elif key != "co2":
                        fused[key] = value

        if not satellite_df.empty:
            satellite_row = self._match_satellite_row(satellite_df, weather_row, timestamp)
            if satellite_row is not None:
                fused.update(self._map_satellite_features(satellite_row))

        return fused

    def _load_weather_dataset(self) -> pd.DataFrame:
        path = Config.DATA_DIR / "weather_ml.csv"
        if not path.exists():
            return pd.DataFrame()
        df = pd.read_csv(path)
        if "Timestamp_UTC" in df.columns:
            df = df.copy()
            df["Timestamp_UTC"] = pd.to_datetime(df["Timestamp_UTC"], errors="coerce")
        return df

    def _load_sensor_dataset(self) -> pd.DataFrame:
        path = Config.DATA_DIR / "environmental_sensors.csv"
        if not path.exists():
            return pd.DataFrame()
        df = pd.read_csv(path)
        if "Timestamp" in df.columns:
            df = df.copy()
            df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
        return df

    def _load_satellite_dataset(self) -> pd.DataFrame:
        path = Config.DATA_DIR / "satellite_metadata.csv"
        if not path.exists():
            return pd.DataFrame()
        df = pd.read_csv(path)
        if "Timestamp_UTC" in df.columns:
            df = df.copy()
            df["Timestamp_UTC"] = pd.to_datetime(df["Timestamp_UTC"], errors="coerce")
        return df

    def _coerce_timestamp(self, value: Any) -> Optional[pd.Timestamp]:
        if value is None or value == "":
            return None
        if isinstance(value, pd.Timestamp):
            return value
        if isinstance(value, datetime):
            return pd.Timestamp(value)
        try:
            ts = pd.to_datetime(str(value), errors="coerce")
            if getattr(ts, "tzinfo", None) is not None:
                return ts.tz_convert(None)
            return ts
        except Exception:
            return None

    def _normalize_station_id(self, df: pd.DataFrame, column: str) -> pd.DataFrame:
        if column not in df.columns:
            return df
        normalized = df.copy()
        normalized[column] = normalized[column].astype(str).str.extract(r"(\d+)")[0].fillna("")
        return normalized

    def _match_weather_row(self, weather_df: pd.DataFrame, lat: Any, lon: Any, timestamp: Optional[pd.Timestamp]) -> Optional[Dict[str, Any]]:
        if weather_df.empty:
            return None
        candidates = weather_df.copy()
        if lat is not None and lon is not None:
            try:
                lat_val = float(lat)
                lon_val = float(lon)
            except (TypeError, ValueError):
                lat_val = None
                lon_val = None
            if lat_val is not None and lon_val is not None:
                candidates = candidates.copy()
                candidates["lat_diff"] = (candidates.get("Latitude", pd.Series([np.nan] * len(candidates))) - lat_val).abs()
                candidates["lon_diff"] = (candidates.get("Longitude", pd.Series([np.nan] * len(candidates))) - lon_val).abs()
                candidates["geo_dist"] = np.sqrt(candidates["lat_diff"] ** 2 + candidates["lon_diff"] ** 2)
                candidates = candidates.sort_values(["geo_dist", "Timestamp_UTC"], na_position="last")
                nearest_row = candidates.iloc[0]
                station_id = nearest_row.get("Station_ID")
                if station_id is not None and timestamp is not None:
                    station_rows = weather_df[
                        weather_df.get("Station_ID", pd.Series([None] * len(weather_df))).astype(str).str.upper()
                        == str(station_id).upper()
                    ].copy()
                    if not station_rows.empty and "Timestamp_UTC" in station_rows.columns:
                        station_rows["Timestamp_UTC"] = pd.to_datetime(station_rows["Timestamp_UTC"], errors="coerce")
                        station_rows = station_rows.dropna(subset=["Timestamp_UTC"])
                        if not station_rows.empty:
                            nearest = station_rows.iloc[(station_rows["Timestamp_UTC"] - timestamp).abs().argmin()]
                            return nearest.to_dict()
                return nearest_row.to_dict()
        if timestamp is not None:
            ts_col = "Timestamp_UTC" if "Timestamp_UTC" in candidates.columns else "timestamp" if "timestamp" in candidates.columns else None
            if ts_col is not None:
                candidates = candidates.dropna(subset=[ts_col])
                if not candidates.empty:
                    candidates = candidates.copy()
                    candidates[ts_col] = pd.to_datetime(candidates[ts_col], errors="coerce")
                    candidates = candidates.sort_values(ts_col)
                    nearest = candidates.iloc[(candidates[ts_col] - timestamp).abs().argmin()]
                    return nearest.to_dict()
        return None

    def _match_sensor_row(self, sensor_df: pd.DataFrame, weather_row: Optional[Dict[str, Any]], timestamp: Optional[pd.Timestamp]) -> Optional[Dict[str, Any]]:
        if sensor_df.empty:
            return None

        station_id = weather_row.get("Station_ID") if weather_row else None
        timestamp_value = None
        if timestamp is not None:
            timestamp_value = timestamp
        elif weather_row and "Timestamp_UTC" in weather_row and isinstance(weather_row.get("Timestamp_UTC"), pd.Timestamp):
            timestamp_value = weather_row["Timestamp_UTC"]

        candidates = sensor_df.copy()
        if station_id is not None:
            candidates = candidates[candidates.get("Station_ID", pd.Series([None] * len(candidates))).astype(str).str.upper() == str(station_id).upper()]

        if timestamp_value is not None and "Timestamp" in candidates.columns:
            candidates = candidates.dropna(subset=["Timestamp"])
            if not candidates.empty:
                candidates = candidates.copy()
                candidates["Timestamp"] = pd.to_datetime(candidates["Timestamp"], errors="coerce")
                if getattr(timestamp_value, "tzinfo", None) is not None:
                    timestamp_value = timestamp_value.tz_convert(None) if getattr(timestamp_value, "tzinfo", None) is not None else timestamp_value
                    if getattr(candidates["Timestamp"].dt, "tz", None) is not None:
                        candidates["Timestamp"] = candidates["Timestamp"].dt.tz_convert(None)
                    else:
                        candidates["Timestamp"] = candidates["Timestamp"].dt.tz_localize(None)
                candidates["time_diff"] = (candidates["Timestamp"] - timestamp_value).abs()
                candidates = candidates.sort_values(["time_diff", "Timestamp"], na_position="last")
                row = candidates.iloc[0]
                return row.to_dict()

        if station_id is not None and "Timestamp" in candidates.columns:
            candidates = candidates.dropna(subset=["Timestamp"])
            if not candidates.empty:
                candidates = candidates.copy()
                candidates["Timestamp"] = pd.to_datetime(candidates["Timestamp"], errors="coerce")
                candidates = candidates.sort_values(["Timestamp"], ascending=False, na_position="last")
                row = candidates.iloc[0]
                return row.to_dict()

        return None

    def _match_satellite_row(self, satellite_df: pd.DataFrame, weather_row: Optional[Dict[str, Any]], timestamp: Optional[pd.Timestamp]) -> Optional[Dict[str, Any]]:
        if satellite_df.empty:
            return None

        station_id = weather_row.get("Station_ID") if weather_row else None
        candidates = satellite_df.copy()
        if station_id is not None and "Station_ID" in candidates.columns:
            candidates = candidates[candidates.get("Station_ID", pd.Series([None] * len(candidates))).astype(str).str.upper() == str(station_id).upper()]

        ts_col = "Timestamp_UTC" if "Timestamp_UTC" in candidates.columns else "timestamp" if "timestamp" in candidates.columns else None
        if ts_col is not None and timestamp is not None:
            candidates = candidates.dropna(subset=[ts_col])
            if not candidates.empty:
                candidates = candidates.copy()
                candidates[ts_col] = pd.to_datetime(candidates[ts_col], errors="coerce")
                if getattr(timestamp, "tzinfo", None) is not None:
                    timestamp = timestamp.tz_convert(None) if getattr(timestamp, "tzinfo", None) is not None else timestamp
                    if getattr(candidates[ts_col].dt, "tz", None) is not None:
                        candidates[ts_col] = candidates[ts_col].dt.tz_convert(None)
                    else:
                        candidates[ts_col] = candidates[ts_col].dt.tz_localize(None)
                candidates["time_diff"] = (candidates[ts_col] - timestamp).abs()
                candidates = candidates.sort_values(["time_diff", ts_col], na_position="last")
                row = candidates.iloc[0]
                return row.to_dict()

        if station_id is not None and ts_col is not None:
            candidates = candidates.dropna(subset=[ts_col])
            if not candidates.empty:
                candidates = candidates.copy()
                candidates[ts_col] = pd.to_datetime(candidates[ts_col], errors="coerce")
                candidates = candidates.sort_values([ts_col], ascending=False, na_position="last")
                row = candidates.iloc[0]
                return row.to_dict()

        return None

    def _map_weather_features(self, row: Dict[str, Any]) -> Dict[str, float]:
        mapping = {
            "temperature": row.get("Temperature_C"),
            "humidity": row.get("Humidity_Percent") if "Humidity_Percent" in row else row.get("Humidity_%"),
            "humidity_percent": row.get("Humidity_Percent") if "Humidity_Percent" in row else row.get("Humidity_%"),
            "pressure": row.get("Pressure_hPa"),
            "rainfall": row.get("Rainfall_mm"),
            "wind_speed": row.get("Wind_Speed_kmh") if "Wind_Speed_kmh" in row else row.get("WindSpeed_kmh"),
            "uv_index": row.get("UV_Index"),
            "co2": row.get("GHG_CO2_ppm") if "GHG_CO2_ppm" in row else row.get("CO2_ppm"),
            "aqi": row.get("AQI") if "AQI" in row else None,
            "industrial_index": row.get("IndustrialIndex"),
            "energy_consumption": row.get("EnergyConsumption_MWh"),
            "renewable_energy": row.get("RenewableEnergy_%"),
        }
        return {k: float(v) for k, v in mapping.items() if v is not None and not (isinstance(v, float) and math.isnan(v))}

    def _map_sensor_features(self, row: Dict[str, Any]) -> Dict[str, float]:
        mapping = {
            "co2": row.get("CO2_ppm"),
            "pm2_5": row.get("PM2_5_ug_m3"),
            "pm10": row.get("PM10_ug_m3"),
            "no2": row.get("NO2_ppb"),
            "so2": row.get("SO2_ppb"),
            "ozone": row.get("Ozone_ppb"),
        }
        return {k: float(v) for k, v in mapping.items() if v is not None and not (isinstance(v, float) and math.isnan(v))}

    def _map_satellite_features(self, row: Dict[str, Any]) -> Dict[str, float]:
        ndvi_value = row.get("NDVI_Index")
        if ndvi_value is None or ndvi_value == "":
            return {}
        try:
            return {"ndvi": float(ndvi_value)}
        except (TypeError, ValueError):
            return {}

    def _compute_feature_stats(self) -> Dict[str, Dict[str, float]]:
        stats: Dict[str, Dict[str, float]] = {
            "temperature": {"mean": 25.0, "std": 8.0},
            "humidity": {"mean": 60.0, "std": 20.0},
            "pressure": {"mean": 1013.0, "std": 10.0},
            "wind_speed": {"mean": 15.0, "std": 10.0},
            "rainfall": {"mean": 25.0, "std": 30.0},
            "aqi": {"mean": 100.0, "std": 60.0},
            "co2": {"mean": 410.0, "std": 40.0},
            "uv_index": {"mean": 5.0, "std": 3.0},
            "industrial_index": {"mean": 1.0, "std": 0.5},
            "energy_consumption": {"mean": 50.0, "std": 20.0},
            "renewable_energy": {"mean": 30.0, "std": 15.0},
        }
        return stats

    def _infer_confidence(self, model_name: str, model: Any, sample: np.ndarray, prediction: Any) -> Optional[float]:
        meta = MODEL_REGISTRY.get(model_name, {})
        if meta.get("type") != "classification":
            return None

        if hasattr(model, "predict_proba"):
            try:
                probs = model.predict_proba(sample)
                index = int(prediction)
                if 0 <= index < probs.shape[1]:
                    return float(probs[0, index])
                return float(np.max(probs[0]))
            except Exception:
                return None

        if hasattr(model, "decision_function"):
            try:
                scores = model.decision_function(sample)
                if isinstance(scores, np.ndarray):
                    scores = np.atleast_1d(scores)
                    probs = np.exp(scores - np.max(scores))
                    probs = probs / np.sum(probs)
                    return float(np.max(probs))
            except Exception:
                return None
        return None

    def _model_evaluation(self, model_name: str) -> Dict[str, Any]:
        metadata_path = Config.MODEL_DIR / "model_metadata.json"
        if not metadata_path.exists():
            return {}
        try:
            with metadata_path.open("r", encoding="utf-8") as f:
                metadata = json.load(f)
            return metadata.get(model_name, {}).get("metrics", {})
        except Exception:
            return {}

    def _recommendation_for(self, model_name: str, prediction: Any, class_label: Optional[str]) -> str:
        if model_name == "linear_regression":
            p = float(prediction)
            if p < 150:
                return "Carbon emission is within acceptable range. Continue monitoring."
            if p < 300:
                return "Carbon emission is elevated. Consider increasing renewable energy share and mitigation measures."
            return "Carbon emission is critically high. Immediate mitigation actions recommended: industrial emission controls, public transit expansion."
        if model_name == "decision_tree":
            label = class_label or str(prediction)
            if label == "Low":
                return "Climate severity is low. Continue routine monitoring."
            if label == "Medium":
                return "Climate severity moderate. Implement adaptive measures and public advisories."
            return "High climate severity detected. Activate emergency response protocols."
        if model_name == "knn":
            if class_label == "Yes":
                return "Heatwave conditions predicted. Advise staying hydrated, limiting outdoor activity, and cooling centers activation."
            return "No heatwave conditions. Standard monitoring recommended."
        return ""

    def _feature_importance(self, model_name: str, prepared: Dict[str, float]) -> Dict[str, float]:
        weights = {
            "linear_regression": {
                "temperature": 0.18,
                "humidity": 0.12,
                "aqi": 0.20,
                "co2": 0.18,
                "industrial_index": 0.14,
                "energy_consumption": 0.10,
                "renewable_energy": 0.08,
            },
            "decision_tree": {"temperature": 0.30, "humidity": 0.20, "rainfall": 0.25, "wind_speed": 0.10, "pressure": 0.15},
            "knn": {"temperature": 0.40, "humidity": 0.20, "aqi": 0.15, "uv_index": 0.25},
        }
        return dict(weights.get(model_name, {}))

    def _load_training_data(self, dataset_path: Optional[str]) -> pd.DataFrame:
        path = Path(dataset_path) if dataset_path else Config.DATA_DIR / "climate_dataset.csv"
        if not path.exists():
            raise MLModelError(f"Dataset not found: {path}")
        if path.suffix.lower() == ".csv":
            return pd.read_csv(path)
        if path.suffix.lower() in {".xlsx", ".xls"}:
            return pd.read_excel(path)
        raise ValidationError("Unsupported dataset format. Use CSV or Excel.")

    def _store_prediction(self, result: PredictionResult, user_id: Optional[str], city: Optional[str]) -> None:
        self._ensure_db()
        if self.db is None:
            return
        doc = result.to_dict()
        if user_id:
            doc["user_id"] = user_id
        if city:
            doc["city"] = city
        try:
            self.db.prediction_history.insert_one(doc)
        except Exception:
            pass


ml_service = MLService()
