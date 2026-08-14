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
    stac_url = os.getenv(
        "COPERNICUS_STAC_SEARCH_URL",
        "https://api.dataspace.copernicus.eu/api/stac/v1/search",
    )

    if not client_id or not client_secret:
        raise SystemExit("Missing COPERNICUS_CLIENT_ID or COPERNICUS_CLIENT_SECRET")

    print("=== OAuth request ===")
    token_resp = requests.post(
        token_url,
        data={"grant_type": "client_credentials"},
        auth=(client_id, client_secret),
        timeout=30,
    )
    print("TOKEN_STATUS", token_resp.status_code, token_resp.reason)
    if token_resp.status_code != 200:
        print("TOKEN_BODY", token_resp.text)
        raise SystemExit("OAuth failed")

    token = token_resp.json().get("access_token")
    if not token:
        print("TOKEN_BODY", token_resp.text)
        raise SystemExit("OAuth response missing access_token")

    print("=== STAC search ===")
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=30)
    bbox = [66.90, 24.80, 67.10, 24.92]
    payload = {
        "collections": ["Sentinel-2"],
        "bbox": bbox,
        "datetime": f"{start.strftime('%Y-%m-%dT%H:%M:%SZ')}/{now.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "limit": 5,
        "sortby": [{"field": "properties.datetime", "direction": "desc"}],
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    search_resp = requests.post(stac_url, json=payload, headers=headers, timeout=60)
    print("SEARCH_STATUS", search_resp.status_code, search_resp.reason)
    if search_resp.status_code != 200:
        print("SEARCH_BODY", search_resp.text)
        raise SystemExit("STAC search failed")

    data = search_resp.json()
    features = data.get("features", [])
    print("FEATURE_COUNT", len(features))
    for idx, feature in enumerate(features[:3], start=1):
        props = feature.get("properties", {})
        geom = feature.get("geometry")
        assets = feature.get("assets", {}) or {}
        print(f"--- feature {idx} ---")
        print("ID", feature.get("id"))
        print("COLLECTION", feature.get("collection"))
        print("PLATFORM", props.get("platform") or props.get("constellation") or props.get("sat:constellation"))
        print("DATETIME", props.get("datetime") or props.get("start_datetime") or props.get("start_date"))
        print("CLOUD_COVER", props.get("eo:cloud_cover") or props.get("cloud_cover") or props.get("s2:cloud_cover"))
        print(
            "TILE_ID",
            props.get("sentinel:tile_id")
            or props.get("s2:tileid")
            or props.get("sentinel:grid_square")
            or props.get("sentinel:utm_zone"),
        )
        if geom:
            print("GEOMETRY_TYPE", geom.get("type"))
            print("GEOMETRY_COORDS", geom.get("coordinates"))
        if feature.get("bbox"):
            print("BBOX", feature.get("bbox"))
        for link_key in ["self", "thumbnail", "B04", "B02", "visual", "analytic"]:
            if link_key in assets:
                print(f"LINK_{link_key.upper()}", assets[link_key].get("href"))
        if feature.get("links"):
            print("LINKS_COUNT", len(feature.get("links", [])))


if __name__ == "__main__":
    main()
