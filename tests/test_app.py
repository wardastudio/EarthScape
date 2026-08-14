import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import app, create_dataset_record, get_activity_logs


def test_login_and_dashboard_redirects():
    client = app.test_client()
    response = client.post('/login', data={'email': 'admin@earthscape.org', 'password': 'admin123'}, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/admin/dashboard')


def test_predict_carbon_endpoint():
    client = app.test_client()
    response = client.post('/api/predict/carbon', json={
        'temperature': 28,
        'humidity': 65,
        'aqi': 120,
        'co2': 410,
        'industrial_index': 0.8,
        'energy_consumption': 70,
        'renewable_energy': 45
    })
    assert response.status_code == 200
    payload = response.get_json()
    assert 'prediction' in payload
    assert 'confidence' in payload


def test_dataset_and_activity_storage_helpers():
    record_id = create_dataset_record(name='Test Dataset', source='uploads/test.csv', status='Pending Review', format='CSV')
    assert record_id is not None
    logs = get_activity_logs(limit=5)
    assert isinstance(logs, list)
