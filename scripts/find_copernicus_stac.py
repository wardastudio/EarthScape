from __future__ import annotations

import re
import socket
from urllib.parse import urlparse

import requests

candidates = [
    "https://dataspace.copernicus.eu/analyse/apis",
    "https://dataspace.copernicus.eu/analyse/openeo",
    "https://dataspace.copernicus.eu/api",
    "https://dataspace.copernicus.eu/browser",
    "https://identity.dataspace.copernicus.eu/",
    "https://api.dataspace.copernicus.eu/",
    "https://api.copernicus.eu/",
    "https://api.copernicus.eu/stac/v1/search",
    "https://dataspace.copernicus.eu/api/stac/v1/search",
    "https://api.dataspace.copernicus.eu/api/stac/v1/search",
    "https://stac.dataspace.copernicus.eu/search",
    "https://services.dataspace.copernicus.eu/stac/search",
    "https://services.dataspace.copernicus.eu/api/stac/v1/search",
    "https://openeo.dataspace.copernicus.eu/",
]

for url in candidates:
    parsed = urlparse(url)
    host = parsed.hostname
    print("URL:", url)
    if host:
        try:
            addr = socket.getaddrinfo(host, 443)
            print("  RESOLVE OK", host, len(addr), "records")
        except Exception as e:
            print("  RESOLVE ERR", host, type(e).__name__, e)
    try:
        resp = requests.get(url, timeout=20)
        print("  HTTP", resp.status_code, resp.reason)
        if resp.status_code == 200:
            txt = resp.text.lower()
            if "stac" in txt or "api.dataspace" in txt or "dataspace" in txt:
                print("  CONTAINS STAC TERM")
            if "api" in txt or "stac" in txt:
                matches = [m.group(0) for m in re.finditer(r'https?://[^"\s<>]+', resp.text) if "stac" in m.group(0).lower() or "dataspace" in m.group(0).lower()]
                if matches:
                    print("  LINKS", matches[:5])
    except Exception as e:
        print("  HTTP ERR", type(e).__name__, e)
    print()
