import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app import app
from flask import url_for
from controllers import satellite_controller as sat_ctrl

with app.test_request_context('/api/satellite/latest?lat=24.86&lon=67.01&collection=sentinel-2-l2a'):
    resp = sat_ctrl.latest_satellite_products()
    print(type(resp))
    try:
        # resp may be (json, status)
        if isinstance(resp, tuple):
            data, status = resp
            print('status', status)
            print('data type', type(data))
        else:
            print('response direct', resp)
    except Exception as e:
        print('exception parsing response', e)
