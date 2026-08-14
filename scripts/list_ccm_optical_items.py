from __future__ import annotations

import os
from dotenv import load_dotenv
import requests


def main() -> None:
    load_dotenv()
    client_id = os.getenv('COPERNICUS_CLIENT_ID')
    client_secret = os.getenv('COPERNICUS_CLIENT_SECRET')
    if not client_id or not client_secret:
        raise SystemExit('Credentials missing')

    token_resp = requests.post(
        'https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token',
        data={'grant_type': 'client_credentials'},
        auth=(client_id, client_secret),
        timeout=30,
    )
    token_resp.raise_for_status()
    token = token_resp.json().get('access_token')
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    root = 'https://stac.dataspace.copernicus.eu/v1'

    resp = requests.get(f'{root}/collections/ccm-optical/items', headers=headers, params={'limit': 20}, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    features = data.get('features', [])
    print('features count', len(features))
    for idx, feat in enumerate(features, start=1):
        print('---', idx, '---')
        print('id', feat.get('id'))
        print('collection', feat.get('collection'))
        props = feat.get('properties', {})
        fields = [
            'platform', 'eo:platform', 'constellation', 'sat:constellation',
            'eo:instrument', 'mission', 'sensor', 'sat:instrument',
            'sentinel:product_id', 'eo:cloud_cover', 's2:cloud_cover', 'eo:gsd',
            'datetime', 'start_datetime', 'end_datetime', 'start_date', 'end_date',
        ]
        for f in fields:
            if f in props:
                print(f, props[f])
        print('property keys sample', sorted(list(props.keys()))[:50])
        print('asset keys', sorted(feat.get('assets', {}).keys()))
        print('bbox', feat.get('bbox'))
        print('geometry type', feat.get('geometry', {}).get('type'))


if __name__ == '__main__':
    main()
