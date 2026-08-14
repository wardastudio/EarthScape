from __future__ import annotations

import re
import socket
from urllib.parse import urlparse

import requests

candidates = [
    "https://browser.stac.dataspace.copernicus.eu/",
    "https://browser.stac.dataspace.copernicus.eu/api",
    "https://browser.stac.dataspace.copernicus.eu/api/stac/v1",
    "https://browser.stac.dataspace.copernicus.eu/api/stac/v1/search",
    "https://browser.dataspace.copernicus.eu/",
    "https://browser.dataspace.copernicus.eu/api",
    "https://browser.dataspace.copernicus.eu/api/stac/v1/search",
    "https://browser.dataspace.copernicus.eu/stac/search",
    "https://browser.dataspace.copernicus.eu/api/stac/search",
    "https://api.stac.dataspace.copernicus.eu/",
    "https://api.stac.dataspace.copernicus.eu/search",
    "https://api.stac.dataspace.copernicus.eu/api/stac/v1/search",
    "https://stac.dataspace.copernicus.eu/",
    "https://stac.dataspace.copernicus.eu/api/stac/v1/search",
    "https://stac.dataspace.copernicus.eu/search",
    "https://stac.dataspace.copernicus.eu/api",
    "https://example.dataspace.copernicus.eu/",
]

for url in candidates:
    parsed = urlparse(url)
    host = parsed.hostname or ""
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
        ctype = resp.headers.get("Content-Type", "")
        print("  CONTENT-TYPE", ctype)
        text = resp.text.lower()
        if "stac" in text or "api" in text:
            matches = [m.group(0) for m in re.finditer(r'https?://[^"\s<>]+', resp.text) if "stac" in m.group(0).lower() or "dataspace" in m.group(0).lower()]
            print("  LINKS", matches[:10])
    except Exception as e:
        print("  HTTP ERR", type(e).__name__, e)
    print()
