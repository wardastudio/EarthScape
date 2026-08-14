import sys
from pathlib import Path

# Ensure project root is on sys.path so `services` can be imported
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from services.satellite_service import satellite_service


# Karachi coordinates
latitude = 24.86
longitude = 67.01

result = satellite_service.get_latest_products(latitude, longitude, radius_km=30, limit=20, days=30, collection='sentinel-2-l2a')
print('count', result.get('count'))
for i, item in enumerate(result.get('items', [])[:5]):
    print(i+1, item['Image_ID'], item['Satellite_Sensor'], item['Timestamp_UTC'], item['HDFS_File_Path'])
print('metadata:', result.get('metadata_path'))
