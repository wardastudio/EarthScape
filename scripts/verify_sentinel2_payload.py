from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
import json

import requests
from dotenv import load_dotenv


def print_json(data, max_chars=1000):
    text = json.dumps(data, indent=2)
    print(text[:max_chars])
    if len(text) > max_chars:
        print('...')


def main() -> None:
    load_dotenv()
    client_id = os.getenv('COPERNICUS_CLIENT_ID')
    client_secret = os.getenv('COPERNICUS_CLIENT_SECRET')
    assert client_id and client_secret

    token_url = 'https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token'
    stac_root = 'https://stac.dataspace.copernicus.eu/v1'

    token_resp = requests.post(token_url, data={'grant_type':'client_credentials'}, auth=(client_id, client_secret), timeout=30)
    print('token_status', token_resp.status_code)
    token = token_resp.json().get('access_token')
    print('has_token', bool(token))
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}

    print('\n=== collections ===')
    resp = requests.get(f'{stac_root}/collections', headers=headers, timeout=30)
    print(resp.status_code)
    data = resp.json()
    print('collection count', len(data.get('collections', [])))
    for c in data.get('collections', [])[:10]:
        print(c.get('id'), c.get('title'))
    print_json(data.get('collections', [])[0] if data.get('collections') else {})

    print('\n=== collection ccm-optical ===')
    resp = requests.get(f'{stac_root}/collections/ccm-optical', headers=headers, timeout=30)
    print(resp.status_code)
    print_json(resp.json())

    print('\n=== search ===')
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=30)
    payload = {
        'collections': ['ccm-optical'],
        'bbox': [66.90, 24.80, 67.10, 24.92],
        'datetime': f"{start.strftime('%Y-%m-%dT%H:%M:%SZ')}/{now.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        'limit': 5,
        'query': {'eo:platform': {'eq': 'Sentinel-2'}},
        'sortby': [{'field': 'properties.datetime', 'direction': 'desc'}],
    }
    print_json(payload, max_chars=2000)
    resp = requests.post(f'{stac_root}/search', json=payload, headers=headers, timeout=60)
    print('search_status', resp.status_code)
    print(resp.text[:4000])
    if resp.status_code == 200:
        data = resp.json()
        print('features_count', len(data.get('features', [])))
        for feat in data.get('features', [])[:2]:
            print('--- feature ---')
            print('id', feat.get('id'))
            print('collection', feat.get('collection'))
            print('properties_keys', sorted(feat.get('properties', {}).keys()))
            print('assets_keys', sorted(feat.get('assets', {}).keys()))
            print('geometry type', feat.get('geometry', {}).get('type'))
            print('bbox', feat.get('bbox'))
            print('properties sample', {k: feat.get('properties', {}).get(k) for k in ['datetime','platform','eo:cloud_cover','s2:cloud_cover','sentinel:product_id','eo:instrument']})


if __name__ == '__main__':
    main()
