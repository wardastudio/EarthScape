from __future__ import annotations

import os
import sys
from dotenv import load_dotenv
import requests


def main() -> None:
    load_dotenv()
    client_id = os.getenv('COPERNICUS_CLIENT_ID')
    client_secret = os.getenv('COPERNICUS_CLIENT_SECRET')
    if not client_id or not client_secret:
        raise SystemExit('Missing credentials')

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

    resp = requests.get(f'{root}/collections', headers=headers, params={'limit': 100}, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    cols = data.get('collections', [])
    print('total collections', len(cols))
    for coll in cols:
        name = coll.get('id')
        title = coll.get('title')
        print(name, '|', title)
    if 'links' in data and data['links']:
        for link in data['links']:
            if link.get('rel') == 'next':
                print('NEXT', link.get('href'))

    keywords = ['sentinel', 'sentinel-2', 'sentinel2', 'S2', 'Sentinel']
    print('\n=== matching names/titles ===')
    for coll in cols:
        name = str(coll.get('id', ''))
        title = str(coll.get('title', ''))
        if any(k.lower() in name.lower() or k.lower() in title.lower() for k in keywords):
            print(name, '|', title)


if __name__ == '__main__':
    main()
