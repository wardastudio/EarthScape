from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
import json

import requests
from dotenv import load_dotenv


def print_json(data: object, max_chars: int = 2000) -> None:
    text = json.dumps(data, indent=2)
    print(text[:max_chars])
    if len(text) > max_chars:
        print('...')


def main() -> None:
    load_dotenv()
    client_id = os.getenv('COPERNICUS_CLIENT_ID')
    client_secret = os.getenv('COPERNICUS_CLIENT_SECRET')
    if not client_id or not client_secret:
        raise SystemExit('Missing COPERNICUS_CLIENT_ID or COPERNICUS_CLIENT_SECRET')

    token_url = 'https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token'
    stac_root = 'https://stac.dataspace.copernicus.eu/v1'

    token_resp = requests.post(
        token_url,
        data={'grant_type': 'client_credentials'},
        auth=(client_id, client_secret),
        timeout=30,
    )
    token_resp.raise_for_status()
    token = token_resp.json().get('access_token')
    if not token:
        raise SystemExit('No access token returned')

    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}

    print('=== STAC Root ===')
    root_resp = requests.get(f'{stac_root}/', headers=headers, timeout=30)
    print('root status', root_resp.status_code)
    print(root_resp.text[:800])

    print('\n=== Collections ===')
    collections_resp = requests.get(f'{stac_root}/collections', headers=headers, timeout=30)
    collections_resp.raise_for_status()
    collections = collections_resp.json().get('collections', [])
    print('collections total', len(collections))
    for coll in collections[:20]:
        print('-', coll.get('id'), '|', coll.get('title'))

    print('\n=== Collection ccm-optical metadata ===')
    ccm_resp = requests.get(f'{stac_root}/collections/ccm-optical', headers=headers, timeout=30)
    print('ccm-optical status', ccm_resp.status_code)
    print_json(ccm_resp.json(), max_chars=1600)

    bbox = [66.9, 24.8, 67.1, 24.92]
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=90)
    datetime_range = f"{start.strftime('%Y-%m-%dT%H:%M:%SZ')}/{now.strftime('%Y-%m-%dT%H:%M:%SZ')}"

    print('\n=== Search ccm-optical items with bbox only ===')
    payload = {
        'collections': ['ccm-optical'],
        'bbox': bbox,
        'datetime': datetime_range,
        'limit': 5,
        'sortby': [{'field': 'properties.datetime', 'direction': 'desc'}],
    }
    search_resp = requests.post(f'{stac_root}/search', json=payload, headers=headers, timeout=60)
    print('search status', search_resp.status_code)
    print(search_resp.text[:3200])
    if search_resp.status_code == 200:
        data = search_resp.json()
        print('features count', len(data.get('features', [])))
        for idx, feat in enumerate(data.get('features', [])[:3], start=1):
            print('\n--- feature', idx, '---')
            print('id', feat.get('id'))
            print('collection', feat.get('collection'))
            print('properties keys', sorted(feat.get('properties', {}).keys()))
            print('assets keys', sorted(feat.get('assets', {}).keys()))
            sample = {k: feat.get('properties', {}).get(k) for k in ['datetime', 'platform', 'eo:platform', 'eo:cloud_cover', 's2:cloud_cover', 'eo:instrument', 'eo:gsd', 'eo:epsg', 'sentinel:product_id', 'constellation']}
            print('sample props:')
            print_json(sample, max_chars=1200)
            print('bbox', feat.get('bbox'))
            print('geometry type', feat.get('geometry', {}).get('type'))

    print('\n=== Items endpoint ===')
    items_resp = requests.get(
        f'{stac_root}/collections/ccm-optical/items',
        headers=headers,
        params={
            'bbox': ','.join(str(x) for x in bbox),
            'limit': 5,
            'datetime': datetime_range,
        },
        timeout=60,
    )
    print('items endpoint status', items_resp.status_code)
    print(items_resp.text[:3200])


if __name__ == '__main__':
    main()
