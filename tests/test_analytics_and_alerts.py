import pytest


def test_analytics_dashboard(client):
    resp = client.get("/api/analytics/dashboard")
    assert resp.status_code == 200
    body = resp.get_json()
    for key in {"total_records", "averages", "prediction_count", "user_count"}:
        assert key in body


def test_analytics_overview_unified_endpoint(client):
    resp = client.get("/api/analytics/overview")
    assert resp.status_code == 200
    assert resp.is_json
    body = resp.get_json()
    required_top = {
        "overview", "averages", "air_quality", "climate_severity",
        "mapreduce_aggregates", "risk_summary", "ml_predictions",
        "ml_models", "last_updated",
    }
    for key in required_top:
        assert key in body, f"Missing top-level key: {key}"


def test_analytics_overview_overview_section(client):
    resp = client.get("/api/analytics/overview")
    assert resp.status_code == 200
    body = resp.get_json()
    overview = body["overview"]
    for key in {"total_records", "weather_records", "prediction_count", "user_count", "alert_count", "station_count", "ml_models_available"}:
        assert key in overview, f"overview missing key: {key}"
    assert isinstance(overview["station_count"], int)
    assert isinstance(overview["ml_models_available"], int)
    assert overview["ml_models_available"] >= 1


def test_analytics_overview_averages(client):
    resp = client.get("/api/analytics/overview")
    assert resp.status_code == 200
    body = resp.get_json()
    averages = body["averages"]
    for key in {"temperature", "humidity", "rainfall", "wind_speed", "aqi", "co2"}:
        assert key in averages, f"averages missing key: {key}"
    for key, value in averages.items():
        assert isinstance(value, (int, float)), f"{key} value not numeric: {value}"


def test_analytics_overview_air_quality(client):
    resp = client.get("/api/analytics/overview")
    assert resp.status_code == 200
    body = resp.get_json()
    aq = body["air_quality"]
    for key in {"average_aqi", "average_co2", "aqi_samples", "co2_samples", "category"}:
        assert key in aq, f"air_quality missing key: {key}"
    valid_categories = {"Good", "Moderate", "Unhealthy for Sensitive Groups", "Unhealthy", "Very Unhealthy", "Hazardous", "Insufficient Data"}
    assert aq["category"] in valid_categories, f"Unexpected AQI category: {aq['category']}"


def test_analytics_overview_climate_severity(client):
    resp = client.get("/api/analytics/overview")
    assert resp.status_code == 200
    body = resp.get_json()
    sev = body["climate_severity"]
    for key in {"average_score", "level", "station_samples"}:
        assert key in sev, f"climate_severity missing key: {key}"
    levels = {"Minimal", "Mild", "Moderate", "Severe", "Critical", "Unknown"}
    assert sev["level"] in levels, f"Unexpected severity level: {sev['level']}"
    assert isinstance(sev["average_score"], (int, float))
    assert isinstance(sev["station_samples"], int)


def test_analytics_overview_mapreduce_aggregates(client):
    resp = client.get("/api/analytics/overview")
    assert resp.status_code == 200
    body = resp.get_json()
    mr = body["mapreduce_aggregates"]
    for key in {"status", "station_count", "stations"}:
        assert key in mr, f"mapreduce_aggregates missing key: {key}"
    status = mr["status"]
    for key in {"aggregates_available", "station_count", "total_records_processed"}:
        assert key in status, f"mapreduce_aggregates.status missing key: {key}"
    assert isinstance(status["aggregates_available"], bool)
    assert isinstance(mr["station_count"], int)
    assert isinstance(mr["stations"], list)


def test_analytics_overview_risk_summary(client):
    resp = client.get("/api/analytics/overview")
    assert resp.status_code == 200
    body = resp.get_json()
    risk = body["risk_summary"]
    for key in {"flood_risk", "heatwave", "total_records", "total_stations"}:
        assert key in risk, f"risk_summary missing key: {key}"

    flood = risk["flood_risk"]
    for key in {"counts", "percentages", "total_assessments", "dominant_risk"}:
        assert key in flood, f"risk_summary.flood_risk missing key: {key}"
    for pct_key in {"low", "medium", "high"}:
        assert pct_key in flood["percentages"]
        assert isinstance(flood["percentages"][pct_key], (int, float))

    heat = risk["heatwave"]
    for key in {"counts", "percentages", "total_assessments"}:
        assert key in heat, f"risk_summary.heatwave missing key: {key}"
    for pct_key in {"yes", "no"}:
        assert pct_key in heat["percentages"]
        assert isinstance(heat["percentages"][pct_key], (int, float))


def test_analytics_overview_ml_models(client):
    resp = client.get("/api/analytics/overview")
    assert resp.status_code == 200
    body = resp.get_json()
    ml = body["ml_models"]
    assert isinstance(ml, list)
    if ml:
        model = ml[0]
        for key in {"name", "type", "task", "description", "loaded"}:
            assert key in model, f"ml_models entry missing key: {key}"
        assert model["type"] in {"regression", "classification"}


def test_analytics_overview_ml_predictions(client):
    resp = client.get("/api/analytics/overview")
    assert resp.status_code == 200
    body = resp.get_json()
    ml_pred = body["ml_predictions"]
    assert isinstance(ml_pred, dict)
    for key in {"total", "avg_confidence", "by_model"}:
        assert key in ml_pred, f"ml_predictions missing key: {key}"
    assert isinstance(ml_pred["by_model"], dict)


def test_analytics_overview_last_updated(client):
    resp = client.get("/api/analytics/overview")
    assert resp.status_code == 200
    body = resp.get_json()
    assert isinstance(body["last_updated"], str)
    assert len(body["last_updated"]) > 0


def test_analytics_overview_vs_hadoop_stations_consistency(client):
    overview_resp = client.get("/api/analytics/overview")
    hadoop_resp = client.get("/api/hadoop/analytics/stations")
    assert overview_resp.status_code == 200
    assert hadoop_resp.status_code == 200
    overview_body = overview_resp.get_json()
    hadoop_body = hadoop_resp.get_json()
    assert overview_body["overview"]["station_count"] == hadoop_body.get("count", 0)
    assert overview_body["mapreduce_aggregates"]["station_count"] == hadoop_body.get("count", 0)


def test_analytics_overview_vs_hadoop_risk_consistency(client):
    overview_resp = client.get("/api/analytics/overview")
    risk_resp = client.get("/api/hadoop/analytics/risk")
    assert overview_resp.status_code == 200
    assert risk_resp.status_code == 200
    overview_body = overview_resp.get_json()
    risk_body = risk_resp.get_json()
    overview_flood = overview_body["risk_summary"]["flood_risk"]["counts"]
    original_flood = risk_body.get("flood_risk_summary", {})
    for key in ("low", "medium", "high"):
        assert overview_flood.get(key) == original_flood.get(key), f"Flood risk mismatch for {key}"
    overview_heat = overview_body["risk_summary"]["heatwave"]["counts"]
    original_heat = risk_body.get("heatwave_summary", {})
    for key in ("yes", "no"):
        assert overview_heat.get(key) == original_heat.get(key), f"Heatwave mismatch for {key}"


def test_analytics_overview_hadoop_dataset_averages_fallback(client, monkeypatch):
    from services.analytics_service import analytics_service
    from services.hadoop_service import hadoop_service

    def _empty_stations():
        return {"stations": [], "count": 0}

    def _empty_risk():
        return {"flood_risk_summary": {}, "heatwave_summary": {}, "total_records": 0, "total_stations": 0}

    monkeypatch.setattr(hadoop_service, "get_station_analytics", _empty_stations)
    monkeypatch.setattr(hadoop_service, "get_risk_analytics", _empty_risk)
    result = analytics_service.get_unified_analytics()
    assert result["mapreduce_aggregates"]["station_count"] == 0
    assert result["mapreduce_aggregates"]["status"]["aggregates_available"] is False
    avg = result["averages"]
    assert isinstance(avg["temperature"], (int, float))
    valid_aqi = {"Good", "Moderate", "Unhealthy for Sensitive Groups", "Unhealthy", "Very Unhealthy", "Hazardous", "Insufficient Data"}
    assert result["air_quality"]["category"] in valid_aqi


@pytest.mark.parametrize("path", [
    "/api/analytics/trends/temperature",
    "/api/analytics/trends/humidity",
    "/api/analytics/trends/rainfall",
    "/api/analytics/trends/pressure",
    "/api/analytics/trends/wind",
])
def test_trend_endpoints(client, path):
    resp = client.get(path)
    assert resp.status_code == 200
    body = resp.get_json()
    assert "labels" in body or "values" in body or "summary" in body


def test_all_trends(client):
    resp = client.get("/api/analytics/trends")
    assert resp.status_code == 200
    body = resp.get_json()
    for key in {"temperature", "humidity", "rainfall", "pressure", "wind"}:
        assert key in body


def test_monthly_statistics(client):
    resp = client.get("/api/analytics/monthly")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "months" in body
    assert "temperature" in body


def test_historical_analysis(client):
    resp = client.get("/api/analytics/historical")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "metrics" in body


def test_prediction_accuracy(client):
    resp = client.get("/api/analytics/prediction-accuracy")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "total" in body
    assert "avg_confidence" in body
    assert "by_model" in body


def test_weather_distribution(client):
    resp = client.get("/api/analytics/weather-distribution")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "labels" in body
    assert "values" in body


def test_carbon_vs_temperature(client):
    resp = client.get("/api/analytics/carbon-vs-temperature?samples=20")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "count" in body
    assert "temperature" in body
    assert "carbon_emission" in body


def test_alerts_crud_unauthenticated(client):
    resp = client.get("/api/alerts")
    assert resp.status_code in {401, 302}
    resp = client.post("/api/alerts", json={"title": "t", "description": "d"})
    assert resp.status_code in {401, 302}


def test_admin_routes_require_auth(client):
    resp = client.get("/api/admin/dashboard")
    assert resp.status_code in {401, 302}
    resp = client.get("/api/admin/users")
    assert resp.status_code in {401, 302}
    resp = client.get("/api/admin/audit-logs")
    assert resp.status_code in {401, 302}
    resp = client.get("/api/admin/settings")
    assert resp.status_code in {401, 302}


def test_notification_endpoints_require_auth(client):
    resp = client.get("/api/profile/notifications")
    assert resp.status_code in {401, 302}
    resp = client.get("/api/profile/notifications/unread-count")
    assert resp.status_code in {401, 302}
    resp = client.post("/api/profile/feedback", json={"rating": 5, "message": "Great"})
    assert resp.status_code in {401, 302}
