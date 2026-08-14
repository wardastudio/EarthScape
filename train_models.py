import json
from pathlib import Path
from typing import Any, Dict, List

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LinearRegression
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                             mean_absolute_error, mean_squared_error, precision_score,
                             recall_score, r2_score)
from sklearn.model_selection import train_test_split
from sklearn.neighbors import KNeighborsClassifier
from sklearn.tree import DecisionTreeClassifier

BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data" / "climate_dataset.csv"
MODEL_DIR = BASE_DIR / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

MODEL_DEFINITIONS = {
    "linear_regression": {
        "file": "linear_regression.pkl",
        "type": "regression",
        "features": [
            "Temperature_C",
            "Humidity_%",
            "AQI",
            "CO2_ppm",
            "IndustrialIndex",
            "EnergyConsumption_MWh",
            "RenewableEnergy_%",
        ],
        "target": "CarbonEmission",
    },
    "decision_tree": {
        "file": "decision_tree.pkl",
        "type": "classification",
        "features": [
            "Temperature_C",
            "Humidity_%",
            "Rainfall_mm",
            "WindSpeed_kmh",
            "Pressure_hPa",
        ],
        "target": "FloodRisk",
    },
    "knn": {
        "file": "knn.pkl",
        "type": "classification",
        "features": [
            "Temperature_C",
            "Humidity_%",
            "AQI",
            "UV_Index",
        ],
        "target": "Heatwave",
    },
}

REQUIRED_COLUMNS = [
    "Temperature_C",
    "Humidity_%",
    "Rainfall_mm",
    "WindSpeed_kmh",
    "Pressure_hPa",
    "AQI",
    "CO2_ppm",
    "IndustrialIndex",
    "EnergyConsumption_MWh",
    "RenewableEnergy_%",
    "UV_Index",
    "CarbonEmission",
    "FloodRisk",
    "Heatwave",
    "ClimateSeverityScore",
    "WeatherCondition",
]


def load_dataset(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")
    df = pd.read_csv(path)
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Dataset is missing required columns: {missing}")
    df = df.copy()
    conversions = [col for col in df.columns if col != "WeatherCondition"]
    df[conversions] = df[conversions].apply(pd.to_numeric, errors="coerce")
    rows_before = len(df)
    df = df.dropna(subset=conversions)
    rows_after = len(df)
    if rows_after < rows_before:
        print(f"Dropped {rows_before - rows_after} rows with invalid numeric values.")
    if len(df) < 10:
        raise ValueError("Not enough valid rows in the dataset after cleaning.")
    return df


def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, Any]:
    mse = mean_squared_error(y_true, y_pred)
    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "mse": float(mse),
        "rmse": float(np.sqrt(mse)),
        "r2": float(r2_score(y_true, y_pred)),
    }


def classification_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, Any]:
    labels = sorted(np.unique(np.concatenate([y_true, y_pred])))
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, average="weighted", zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, average="weighted", zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist(),
        "labels": [int(label) for label in labels],
    }


def train_model(name: str, definition: Dict[str, Any], df: pd.DataFrame) -> Dict[str, Any]:
    features = definition["features"]
    target = definition["target"]
    X = df[features].astype(float).values
    y = df[target].astype(float).values
    if definition["type"] == "classification":
        y = y.astype(int)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    if name == "linear_regression":
        model = LinearRegression()
    elif name == "decision_tree":
        model = DecisionTreeClassifier(max_depth=5, random_state=42)
    else:
        model = KNeighborsClassifier(n_neighbors=5)
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    if definition["type"] == "regression":
        metrics = regression_metrics(y_test, y_pred)
    else:
        metrics = classification_metrics(y_test.astype(int), y_pred.astype(int))
    model_path = MODEL_DIR / definition["file"]
    joblib.dump(model, model_path)
    print(f"Saved {name} to {model_path}")
    return {
        "model": name,
        "file": str(model_path),
        "features": features,
        "target": target,
        "type": definition["type"],
        "metrics": metrics,
        "train_samples": int(len(X_train)),
        "test_samples": int(len(X_test)),
    }


def main() -> None:
    df = load_dataset(DATA_PATH)
    results: Dict[str, Any] = {}
    for name, definition in MODEL_DEFINITIONS.items():
        print(f"Training {name}...")
        results[name] = train_model(name, definition, df)
        print(json.dumps(results[name], indent=2))
        print()
    metadata_path = MODEL_DIR / "model_metadata.json"
    with metadata_path.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Saved metadata to {metadata_path}")


if __name__ == "__main__":
    main()
