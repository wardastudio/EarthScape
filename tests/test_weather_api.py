import pytest


def test_weather_search_requires_query(client):
    resp = client.get("/api/weather/search")
    assert resp.status_code == 422


def test_weather_search_returns_results(client):
    resp = client.get("/api/weather/search?q=lon")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "items" in body
    assert isinstance(body["items"], list)


def test_weather_current_requires_city(client):
    resp = client.get("/api/weather/current")
    assert resp.status_code == 422


def test_weather_current_returns_structured(client):
    resp = client.get("/api/weather/current?city=London")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "temperature" in body
    assert "humidity_pct" in body
    assert "timestamp" in body
    temp = body["temperature"]
    assert "celsius" in temp
    assert "fahrenheit" in temp


def test_weather_forecast_days_parameter(client):
    resp = client.get("/api/weather/forecast?city=London&days=3")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["days"] == 3
    assert len(body["items"]) == 3


def test_air_quality_returns_pollutants(client):
    resp = client.get("/api/weather/air-quality?city=Mumbai")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "aqi" in body
    assert "aqi_level" in body
    assert "pollutants" in body
    for key in {"pm25", "pm10", "no2", "co", "ozone"}:
        assert key in body["pollutants"]


def test_coordinates(client):
    resp = client.get("/api/weather/coordinates?city=Tokyo")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "latitude" in body
    assert "longitude" in body


def test_weather_summary(client):
    resp = client.get("/api/weather/summary?city=Paris")
    assert resp.status_code == 200
    body = resp.get_json()
    for key in {"current", "air_quality", "forecast_5d"}:
        assert key in body


def test_saved_cities_requires_auth(client):
    resp = client.get("/api/weather/saved-cities")
    assert resp.status_code in {401, 302}
