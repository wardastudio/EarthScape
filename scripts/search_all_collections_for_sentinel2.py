from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
import json

import requests
from dotenv import load_dotenv


def main() -> None:
    load_dotenv()
    client_id = os.getenv("COPERNICUS_CLIENT_ID")
    client_secret = os.getenv("COPERNICUS_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise SystemExit("Missing credentials")

    token_resp = requests.post(
        "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token",
        data={"grant_type": "client_credentials"},
        auth=(client_id, client_secret),
        timeout=30,
    )
    token_resp.raise_for_status()
    token = token_resp.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    root = "https://stac.dataspace.copernicus.eu/v1"

    start = datetime.now(timezone.utc) - timedelta(days=365)
    now = datetime.now(timezone.utc)
    payload = {
        "datetime": f"{start.strftime('%Y-%m-%dT%H:%M:%SZ')}/{now.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "limit": 20,
        "query": {"eo:platform": {"eq": "Sentinel-2"}},
        "sortby": [{"field": "properties.datetime", "direction": "desc"}],
    }
    print(json.dumps(payload, indent=2))
    resp = requests.post(f"{root}/search", json=payload, headers=headers, timeout=120)
    print(resp.status_code)
    print(resp.text[:8000])
    if resp.status_code == 200:
        data = resp.json()
        features = data.get("features", [])
        print("features", len(features))
        for feat in features[:5]:
            print(feat.get("id"), feat.get("collection"), feat.get("properties", {}).get("platform"), feat.get("properties", {}).get("eo:cloud_cover"), feat.get("properties", {}).get("datetime"))


if __name__ == "__main__":
    main()
