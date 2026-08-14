from __future__ import annotations

import re
import requests

urls = [
    "https://dataspace.copernicus.eu/analyse/apis",
    "https://dataspace.copernicus.eu/analyse/openeo",
    "https://dataspace.copernicus.eu/browser",
]
patterns = [re.compile(r'https?://[^"\s<>]+', re.IGNORECASE), re.compile(r'"(https?://[^"\s<>]+)"')]
for url in urls:
    print("===== PAGE:", url)
    try:
        r = requests.get(url, timeout=30)
        print("STATUS", r.status_code)
        text = r.text
        lower = text.lower()
        stac_count = lower.count("stac")
        print("STAC occurrences", stac_count)
        for match in patterns[0].finditer(text):
            u = match.group(0)
            if "stac" in u.lower() or "api.dataspace" in u.lower() or "dataspace" in u.lower():
                print("URL", u)
        print("--- end page ---\n")
    except Exception as exc:
        print("ERROR", type(exc).__name__, exc)
        print()
