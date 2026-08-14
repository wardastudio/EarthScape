from __future__ import annotations

import os
from datetime import datetime, timezone
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

    payload = {
        "collections": ["ccm-optical"],
        "bbox": [66.9, 24.8, 67.1, 24.92],
        "datetime": "2024-01-01T00:00:00Z/2026-08-03T00:00:00Z",
        "limit": 50,
        "query": {"eo:platform": {"eq": "Sentinel-2"}},
        "sortby": [{"field": "properties.datetime", "direction": "desc"}],
    }
    print(json.dumps(payload, indent=2))
    resp = requests.post(f"{root}/search", json=payload, headers=headers, timeout=120)
    print(resp.status_code)
    print(resp.text[:8000])
    if resp.status_code == 200:
        data = resp.json()
        print("features", len(data.get("features", [])))
        for idx, feat in enumerate(data.get("features", [])[:5], start=1):
            print("--- feature", idx, "---")
            print("id", feat.get("id"))
            print("collection", feat.get("collection"))
            print("properties keys", sorted(feat.get("properties", {}).keys()))
            print("assets keys", sorted(feat.get("assets", {}).keys()))
            print("sample properties", {k: feat.get("properties", {}).get(k) for k in ["datetime", "eo:platform", "platform", "eo:instrument", "eo:cloud_cover", "s2:cloud_cover", "eo:gsd", "sentinel:product_id"]})


if __name__ == "__main__":
    main()
