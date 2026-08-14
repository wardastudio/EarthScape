from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
import json

import requests
from dotenv import load_dotenv


def print_json(data, max_chars=1200):
    text = json.dumps(data, indent=2)
    print(text[:max_chars])
    if len(text) > max_chars:
        print('...')


def main() -> None:
    load_dotenv()
    client_id = os.getenv('COPERNICUS_CLIENT_ID')
    client_secret = os.getenv('COPERNICUS_CLIENT_SECRET')
    if not client_id or not client_secret:
        raise SystemExit('Missing credentials')

    token_url = 'https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token'
    stac_root = 'https://stac.dataspace.copernicus.eu/v1'

    token_resp = requests.post(token_url, data={'grant_type': 'client_credentials'}, auth=(client_id, client_secret), timeout=30)
    print('token', token_resp.status_code)
    token = token_resp.json().get('access_token')
    if not token:
        raise SystemExit('No token returned')
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}

    start = datetime.now(timezone.utc) - timedelta(days=60)
    now = datetime.now(timezone.utc)
    bbox = [66.9, 24.8, 67.1, 24.92]

    print('=== search no query ===')
    payload = {
        'collections': ['ccm-optical'],
        'bbox': bbox,
        'datetime': f"{start.strftime('%Y-%m-%dT%H:%M:%SZ')}/{now.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        'limit': 5,
        'sortby': [{'field': 'properties.datetime', 'direction': 'desc'}],
    }
    resp = requests.post(f'{stac_root}/search', json=payload, headers=headers, timeout=60)
    print('status', resp.status_code)
    print(resp.text[:3200])
    if resp.status_code == 200:
        data = resp.json()
        print('features', len(data.get('features', [])))
        for idx, feat in enumerate(data.get('features', [])[:3], start=1):
            print('--- feature', idx, '---')
            print('id', feat.get('id'))
            print('collection', feat.get('collection'))
            print('properties keys', sorted(feat.get('properties', {}).keys()))
            print('assets keys', sorted(feat.get('assets', {}).keys()))
            print('sample props')
            sample = {k: feat.get('properties', {}).get(k) for k in ['datetime', 'platform', 'eo:platform', 'eo:cloud_cover', 's2:cloud_cover', 'eo:instrument', 'sentinel:product_id', 'eo:gsd']}
            print_json(sample, max_chars=1200)
            print('bbox', feat.get('bbox'))
            print('geometry type', feat.get('geometry', {}).get('type'))

    print('\n=== /collections/ccm-optical/items?bbox ===')
    resp = requests.get(
        f'{stac_root}/collections/ccm-optical/items',
        headers=headers,
        params={
            'bbox': ','.join(str(v) for v in bbox),
            'limit': 5,
        },
        timeout=60,
    )
    print('items status', resp.status_code)
    print(resp.text[:3200])


if __name__ == '__main__':
    main()
