import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from routes import satellite_routes
print('satellite_bp:', getattr(satellite_routes, 'satellite_bp', None))
print('blueprint url_prefix:', satellite_routes.satellite_bp.url_prefix)
print('blueprint rules:')
for r in satellite_routes.satellite_bp.deferred_functions:
    print('deferred:', r)
