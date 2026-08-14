from __future__ import annotations
import sys
from pathlib import Path
import os
import json

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from application import app

client = app.test_client()

# Karachi coords and explicit collection
params = {
    'lat': '24.86',
    'lon': '67.01',
    'radius_km': '30',
    'limit': '10',
    'days': '30',
    'collection': 'sentinel-2-l2a',
}
resp = client.get('/api/satellite/latest', query_string=params)
print('status', resp.status_code)
try:
    data = resp.get_json()
    print('count', data.get('count'))
    for item in data.get('items', [])[:5]:
        print(item.get('Image_ID'), item.get('Satellite_Sensor'), item.get('Timestamp_UTC'), item.get('HDFS_File_Path'))
except Exception as e:
    print('failed to parse json:', e)
    print(resp.data[:1000])
