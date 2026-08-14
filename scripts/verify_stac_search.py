from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv


def main() -> None:
    load_dotenv()
    client_id = os.getenv("COPERNICUS_CLIENT_ID")
    client_secret = os.getenv("COPERNICUS_CLIENT_SECRET")
    token_url = os.getenv(
        "COPERNICUS_OAUTH_TOKEN_URL",
        "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token",
    )
    stac_root = os.getenv("COPERNICUS_STAC_ROOT", "https://stac.dataspace.copernicus.eu/v1")

    if not client_id or not client_secret:
        raise SystemExit("Missing COPERNICUS_CLIENT_ID or COPERNICUS_CLIENT_SECRET")

    print("=== OAuth ===")
    token_resp = requests.post(
        token_url,
        data={"grant_type": "client_credentials"},
        auth=(client_id, client_secret),
        timeout=30,
    )
    print("token status", token_resp.status_code)
    print(token_resp.text[:400])
    token = token_resp.json().get("access_token")
    if not token:
        raise SystemExit("No token")

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    print("=== collections ===")
    coll_resp = requests.get(f"{stac_root}/collections", headers=headers, timeout=30)
    print(coll_resp.status_code)
    print(coll_resp.text[:800])

    print("=== search ===")
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=14)
    payload = {
        "collections": ["ccm-optical"],
        "bbox": [66.90, 24.80, 67.10, 24.92],
        "datetime": f"{start.strftime('%Y-%m-%dT%H:%M:%SZ')}/{now.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "limit": 5,
        "query": {"eo:platform": "Sentinel-2"},
        "sortby": [{"field": "properties.datetime", "direction": "desc"}],
    }
    search_resp = requests.post(f"{stac_root}/search", json=payload, headers=headers, timeout=60)
    print(search_resp.status_code)
    print(search_resp.text[:1600])

    if search_resp.status_code == 200:
        data = search_resp.json()
        print("features", len(data.get("features", [])))
        for feat in data.get("features", [])[:2]:
            print(feat.get("id"), feat.get("collection"), feat.get("properties", {}).get("datetime"))


if __name__ == "__main__":
    main()
