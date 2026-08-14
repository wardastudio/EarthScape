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
        raise SystemExit('Missing credentials')

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
        raise SystemExit('No token returned')
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}

    print('=== root ===')
    root = requests.get(f'{stac_root}/', headers=headers, timeout=20)
    print(root.status_code)

    test_payloads = [
        {
            'name': 'Karachi small bbox 90d',
            'payload': {
                'collections': ['ccm-optical'],
                'bbox': [66.9, 24.8, 67.1, 24.92],
                'datetime': f"{(datetime.now(timezone.utc)-timedelta(days=90)).strftime('%Y-%m-%dT%H:%M:%SZ')}/{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
                'limit': 5,
                'sortby': [{'field': 'properties.datetime', 'direction': 'desc'}],
            },
        },
        {
            'name': 'Karachi larger bbox 90d',
            'payload': {
                'collections': ['ccm-optical'],
                'bbox': [66.0, 24.0, 68.0, 25.5],
                'datetime': f"{(datetime.now(timezone.utc)-timedelta(days=90)).strftime('%Y-%m-%dT%H:%M:%SZ')}/{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
                'limit': 5,
                'sortby': [{'field': 'properties.datetime', 'direction': 'desc'}],
            },
        },
        {
            'name': 'Global recent 5',
            'payload': {
                'collections': ['ccm-optical'],
                'datetime': f"{(datetime.now(timezone.utc)-timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%SZ')}/{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
                'limit': 5,
                'sortby': [{'field': 'properties.datetime', 'direction': 'desc'}],
            },
        },
        {
            'name': 'Global recent 50',
            'payload': {
                'collections': ['ccm-optical'],
                'datetime': f"{(datetime.now(timezone.utc)-timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%SZ')}/{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
                'limit': 50,
                'sortby': [{'field': 'properties.datetime', 'direction': 'desc'}],
            },
        },
    ]

    for test in test_payloads:
        print('\n===', test['name'], '===')
        r = requests.post(f'{stac_root}/search', json=test['payload'], headers=headers, timeout=60)
        print('status', r.status_code)
        text = r.text
        print(text[:2000])
        if r.status_code == 200:
            data = r.json()
            print('features', len(data.get('features', [])))
            for idx, feat in enumerate(data.get('features', [])[:3], start=1):
                print('\n--- feature', idx, '---')
                print('id', feat.get('id'))
                print('collection', feat.get('collection'))
                print('properties keys', sorted(feat.get('properties', {}).keys()))
                print('assets keys', sorted(feat.get('assets', {}).keys()))
                sample = {k: feat.get('properties', {}).get(k) for k in ['datetime', 'platform', 'eo:platform', 'eo:cloud_cover', 's2:cloud_cover', 'eo:instrument', 'eo:gsd', 'sat:constellation', 'sentinel:product_id', 'constellation', 'geometry']}
                print_json(sample, max_chars=1200)
                print('bbox', feat.get('bbox'))

    print('\n=== items list global 5 ===')
    r = requests.get(f'{stac_root}/collections/ccm-optical/items', headers=headers, params={'limit': 5}, timeout=60)
    print('status', r.status_code)
    print(r.text[:2000])


if __name__ == '__main__':
    main()
