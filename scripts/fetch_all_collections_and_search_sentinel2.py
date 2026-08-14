from __future__ import annotations
import os
from dotenv import load_dotenv
import requests


def main():
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

    url = f'{root}/collections?limit=100'
    sentinel_matches = []
    while url:
        resp = requests.get(url, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        cols = data.get('collections', [])
        for coll in cols:
            name = coll.get('id', '')
            title = coll.get('title', '')
            if 'sentinel' in name.lower() or 'sentinel' in title.lower():
                sentinel_matches.append((name, title))
        next_link = None
        for l in data.get('links', []):
            if l.get('rel') == 'next':
                next_link = l.get('href')
                break
        url = next_link

    print('sentinel matches found:', len(sentinel_matches))
    for m in sentinel_matches:
        print(m[0], '|', m[1])


if __name__ == '__main__':
    main()
