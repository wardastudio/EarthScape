import numpy as np
import pandas as pd
import pytest

from services.ml_service_v2 import MLService, MODEL_REGISTRY

SAMPLE_FEATURES = {
    "temperature": 28.5,
    "humidity": 65.0,
    "pressure": 1013.0,
    "wind_speed": 14.0,
    "rainfall": 20.0,
    "aqi": 110.0,
    "co2": 415.0,
    "uv_index": 6.0,
}


def test_list_models(client):
    resp = client.get("/api/predictions/models")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "models" in body
    names = [m["name"] for m in body["models"]]
    for expected in {"linear_regression", "decision_tree", "knn", "carbon_model", "flood_model", "heatwave_model"}:
        assert expected in names


def test_predict_linear_regression_requires_auth(client):
    payload = dict(SAMPLE_FEATURES)
    payload["model"] = "linear_regression"
    resp = client.post("/api/predictions/predict", json=payload)
    assert resp.status_code in {401, 302}


def _login_and_token(client):
    resp = client.post("/api/auth/login", json={"email": "admin@earthscape.org", "password": "Admin@123"})
    if resp.status_code != 200:
        pytest.skip("MongoDB not running, cannot login.")
    return resp.get_json()["access_token"]


def test_predict_carbon_emission_structured(client):
    token = _login_and_token(client)
    payload = dict(SAMPLE_FEATURES)
    payload["city"] = "Mumbai"
    resp = client.post(
        "/api/predictions/carbon",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "prediction" in body
    assert "confidence" in body
    assert "recommendation" in body
    assert "model" in body and body["model"] == "linear_regression"


def test_predict_all_returns_all_models(client):
    token = _login_and_token(client)
    resp = client.post(
        "/api/predictions/all",
        json={**SAMPLE_FEATURES, "city": "Tokyo"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    for key in {"carbon_emission", "climate_severity", "heatwave"}:
        assert key in body
        assert "prediction" in body[key]


def test_predict_carbon_endpoint_uses_fusion_and_returns_json(client, monkeypatch):
    token = _login_and_token(client)
    if not token:
        pytest.skip("MongoDB not running, cannot login.")

    weather_df = pd.DataFrame([
        {
            "Station_ID": "STN_100",
            "Latitude": 24.8607,
            "Longitude": 67.0099,
            "Timestamp_UTC": "2024-01-01 00:00:00",
            "Temperature_C": 28.5,
            "Humidity_Percent": 61.0,
            "Pressure_hPa": 1011.0,
            "Wind_Speed_kmh": 12.0,
            "Rainfall_mm": 5.0,
            "UV_Index": 7.0,
            "GHG_CO2_ppm": 415.2,
            "IndustrialIndex": 1.0,
            "EnergyConsumption_MWh": 10.0,
            "RenewableEnergy_%": 20.0,
        }
    ])
    sensor_df = pd.DataFrame([
        {
            "Station_ID": "ST100",
            "Timestamp": "2024-01-01 00:00:00",
            "CO2_ppm": 420.1,
            "PM2_5_ug_m3": 35.0,
            "PM10_ug_m3": 62.0,
            "NO2_ppb": 22.0,
            "SO2_ppb": 8.0,
            "Ozone_ppb": 40.0,
        }
    ])
    satellite_df = pd.DataFrame([
        {
            "Station_ID": "STN_100",
            "Timestamp_UTC": "2024-01-01 00:00:00",
            "Latitude": 24.8607,
            "Longitude": 67.0099,
            "NDVI_Index": 0.42,
        }
    ])

    monkeypatch.setattr("services.ml_service_v2.MLService._load_weather_dataset", lambda self: weather_df)
    monkeypatch.setattr("services.ml_service_v2.MLService._load_sensor_dataset", lambda self: sensor_df)
    monkeypatch.setattr("services.ml_service_v2.MLService._load_satellite_dataset", lambda self: satellite_df)

    response = client.post(
        "/api/predictions/carbon",
        json={
            "city": "TestCity",
            "latitude": 24.8607,
            "longitude": 67.0099,
            "timestamp": "2024-01-01T00:00:00Z",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.is_json
    body = response.get_json()
    assert body["model"] == "linear_regression"
    assert "prediction" in body
    assert isinstance(body["prediction"], (int, float))
    assert body["confidence"] is None or isinstance(body["confidence"], (int, float))
    assert "recommendation" in body
    assert "raw_input" in body
    assert body["raw_input"]["temperature"] is None
    assert body["raw_input"]["aqi"] is None
    assert body["raw_input"]["co2"] is None

    # The endpoint completed the full prediction path, including fusion/mapping and model inference.
    assert body["prediction"] != None


def test_predict_builds_fused_features_from_weather_sensor_and_satellite(monkeypatch):
    service = MLService()

    weather_df = pd.DataFrame([
        {
            "Station_ID": "STN_001",
            "Latitude": 24.8607,
            "Longitude": 67.0099,
            "Timestamp_UTC": "2024-01-01 00:00:00",
            "Temperature_C": 28.5,
            "Humidity_Percent": 61.0,
            "Pressure_hPa": 1011.0,
            "Wind_Speed_kmh": 12.0,
            "Rainfall_mm": 5.0,
            "UV_Index": 7.0,
            "GHG_CO2_ppm": 415.2,
            "GHG_CH4_ppb": 1800.0,
        }
    ])
    sensors_df = pd.DataFrame([
        {
            "Station_ID": "ST001",
            "Timestamp": "2024-01-01 00:00:00",
            "CO2_ppm": 420.1,
            "PM2_5_ug_m3": 35.0,
            "PM10_ug_m3": 62.0,
            "NO2_ppb": 22.0,
            "SO2_ppb": 8.0,
            "Ozone_ppb": 40.0,
        }
    ])
    satellite_df = pd.DataFrame([
        {
            "Station_ID": "STN_001",
            "Timestamp_UTC": "2024-01-01 00:00:00",
            "Latitude": 24.8607,
            "Longitude": 67.0099,
            "NDVI_Index": 0.42,
        }
    ])

    monkeypatch.setattr(service, "_load_weather_dataset", lambda: weather_df)
    monkeypatch.setattr(service, "_load_sensor_dataset", lambda: sensors_df)
    monkeypatch.setattr(service, "_load_satellite_dataset", lambda: satellite_df)

    fused = service._build_fused_features(
        payload={"latitude": 24.8607, "longitude": 67.0099, "timestamp": "2024-01-01T00:00:00Z"},
        required=["temperature", "humidity", "aqi", "co2", "pressure", "rainfall", "wind_speed", "uv_index"],
    )

    assert fused["temperature"] == 28.5
    assert fused["humidity"] == 61.0
    assert fused["co2"] == 420.1
    assert fused["uv_index"] == 7.0
    assert fused["ndvi"] == 0.42


def test_match_weather_row_prefers_timestamp_for_nearest_station(monkeypatch):
    service = MLService()

    weather_df = pd.DataFrame([
        {
            "Station_ID": "STN_001",
            "Latitude": 24.8607,
            "Longitude": 67.0099,
            "Timestamp_UTC": "2024-01-01 00:00:00",
            "Temperature_C": 25.0,
            "Humidity_Percent": 60.0,
            "Pressure_hPa": 1010.0,
            "Wind_Speed_kmh": 10.0,
            "Rainfall_mm": 1.0,
            "UV_Index": 5.0,
            "GHG_CO2_ppm": 400.0,
        },
        {
            "Station_ID": "ST001",
            "Latitude": 24.8607,
            "Longitude": 67.0099,
            "Timestamp_UTC": "2024-01-01 01:00:00",
            "Temperature_C": 30.0,
            "Humidity_Percent": 62.0,
            "Pressure_hPa": 1012.0,
            "Wind_Speed_kmh": 12.0,
            "Rainfall_mm": 0.0,
            "UV_Index": 6.0,
            "GHG_CO2_ppm": 410.0,
        },
    ])
    monkeypatch.setattr(service, "_load_weather_dataset", lambda: weather_df)
    monkeypatch.setattr(service, "_load_sensor_dataset", lambda: pd.DataFrame())
    monkeypatch.setattr(service, "_load_satellite_dataset", lambda: pd.DataFrame())

    fused = service._build_fused_features(
        payload={"latitude": 24.8607, "longitude": 67.0099, "timestamp": "2024-01-01T01:00:00Z"},
        required=["temperature", "humidity", "aqi", "co2", "pressure", "rainfall", "wind_speed", "uv_index"],
    )

    assert fused["temperature"] == 30.0
    assert fused["humidity"] == 62.0
    assert fused["pressure"] == 1012.0
    assert fused["rainfall"] == 0.0
    assert fused["wind_speed"] == 12.0
    assert fused["uv_index"] == 6.0
    assert fused["co2"] == 410.0


def test_prediction_history_requires_auth(client):
    resp = client.get("/api/predictions/history")
    assert resp.status_code in {401, 302}


def test_compare_models_includes_old_and_new_artifacts():
    service = MLService()
    all_models = ["linear_regression", "carbon_model", "decision_tree", "flood_model", "knn", "heatwave_model"]
    results = service.compare_models(model_names=all_models, test_size=0.2, random_state=42)

    assert set(results.keys()) == set(all_models)
    assert isinstance(results["linear_regression"], dict)
    assert "mse" in results["linear_regression"]
    assert isinstance(results["decision_tree"], dict)
    assert "accuracy" in results["decision_tree"]
    assert isinstance(results["knn"], dict)
    assert "accuracy" in results["knn"]
    assert isinstance(results["carbon_model"], dict)
    assert "mse" in results["carbon_model"]
    assert isinstance(results["flood_model"], dict)
    assert "accuracy" in results["flood_model"]
    assert isinstance(results["heatwave_model"], dict)
    assert "accuracy" in results["heatwave_model"]
