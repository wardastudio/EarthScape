import pytest
from database import get_db


def test_analyst_dashboard_shows_datasets_and_alerts(client):
    db = get_db()
    # Use far-future timestamps so test records are always newer than any existing data,
    # guaranteeing they appear in the sort={"created_at": -1}, limit=N window.
    future = "2099-12-31T23:59:59"
    ds = {"name": "Test Dataset 2099", "format": "CSV", "status": "Approved", "created_at": future, "size": "10MB", "resolution": "Hourly"}
    db.datasets.insert_one(ds)
    alert = {"title": "Test Alert 2099", "description": "This is a test body.", "type": "danger", "created_at": future}
    db.alerts.insert_one(alert)

    # set a researcher in session to satisfy role_required decorator
    with client.session_transaction() as sess:
        sess["user"] = {"id": "1", "role": "researcher"}

    resp = client.get("/analyst/dashboard")
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert "Test Dataset 2099" in text
    assert "Test Alert 2099" in text
    assert "This is a test body." in text


def test_analytics_trends_api(client):
    resp = client.get("/api/analytics/trends")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, dict)
    # temperature trends should be present (possibly empty lists)
    assert "temperature" in data
    temp = data["temperature"]
    assert isinstance(temp, dict)
    assert "labels" in temp and "values" in temp
