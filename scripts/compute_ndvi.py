import csv
import sys
import os
import math
from pathlib import Path
from datetime import datetime

import requests

DATA_DIR = Path(os.path.dirname(__file__)).resolve().parents[0] / "data"
METADATA_CSV = DATA_DIR / "satellite_metadata.csv"
PROVENANCE_CSV = DATA_DIR / "ndvi_provenance.csv"

HEAD_TIMEOUT = 20


def scheme_of(href: str) -> str:
    if not href:
        return ""
    if href.startswith("http://") or href.startswith("https://"):
        return "http"
    if href.startswith("s3://"):
        return "s3"
    return "other"


def check_accessible(href: str) -> None:
    if not href:
        raise RuntimeError("missing href")
    sch = scheme_of(href)
    if sch == "s3":
        raise RuntimeError(f"s3 scheme not directly accessible: {href}")
    if sch != "http":
        raise RuntimeError(f"unsupported URL scheme: {href}")

    try:
        # prefer HEAD to avoid downloading large files
        r = requests.head(href, allow_redirects=True, timeout=HEAD_TIMEOUT)
    except Exception as exc:
        raise RuntimeError(f"request failed: {exc}") from exc
    if r.status_code == 405:
        # some endpoints don't allow HEAD; try GET with small range
        try:
            r = requests.get(href, headers={"Range": "bytes=0-1023"}, stream=True, timeout=HEAD_TIMEOUT)
        except Exception as exc:
            raise RuntimeError(f"GET (range) failed: {exc}") from exc
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code} when accessing {href}: {r.text[:200]}")


def compute_ndvi_from_hrefs(red_href: str, nir_href: str) -> float:
    try:
        import rasterio
        from rasterio.enums import Resampling
    except Exception as exc:
        raise RuntimeError(f"rasterio required to compute NDVI: {exc}") from exc

    # open both with rasterio and read a downsampled window to save memory
    with rasterio.Env():
        with rasterio.open(red_href) as src_red, rasterio.open(nir_href) as src_nir:
            # ensure same shape and transform; if not, read small window via overview
            width = min(src_red.width, src_nir.width)
            height = min(src_red.height, src_nir.height)
            # choose out_shape small to reduce memory
            out_w = min(512, width)
            out_h = min(512, height)
            red = src_red.read(1, out_shape=(out_h, out_w), resampling=Resampling.average).astype('float32')
            nir = src_nir.read(1, out_shape=(out_h, out_w), resampling=Resampling.average).astype('float32')

            denom = nir + red
            valid = denom != 0
            ndvi = (nir - red) / denom
            if not valid.any():
                raise RuntimeError("no valid NDVI pixels (division by zero)")
            # compute mean NDVI over valid pixels
            mean_ndvi = float(ndvi[valid].mean())
            if math.isnan(mean_ndvi):
                raise RuntimeError("computed NDVI is NaN")
            return mean_ndvi


def main():
    if not METADATA_CSV.exists():
        print(f"metadata csv not found: {METADATA_CSV}")
        sys.exit(2)

    rows = []
    with METADATA_CSV.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        for r in reader:
            rows.append(r)

    prov_rows = []
    updated = False
    for i, row in enumerate(rows):
        image_id = row.get("Image_ID", "")
        red = row.get("Band_B04_href", "")
        nir = row.get("Band_B08_href", "")
        if not red or not nir:
            # skip rows without both bands
            continue
        try:
            check_accessible(red)
        except Exception as exc:
            print(f"Asset access failure for RED ({image_id}): {exc}")
            sys.exit(3)
        try:
            check_accessible(nir)
        except Exception as exc:
            print(f"Asset access failure for NIR ({image_id}): {exc}")
            sys.exit(3)

        # compute NDVI
        try:
            ndvi_val = compute_ndvi_from_hrefs(red, nir)
        except Exception as exc:
            print(f"NDVI computation failed for {image_id}: {exc}")
            sys.exit(4)

        # record provenance and update row
        ts = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        prov_rows.append({
            "Image_ID": image_id,
            "Band_B04_href": red,
            "Band_B08_href": nir,
            "NDVI": f"{ndvi_val:.6f}",
            "Processed_At": ts,
            "Algorithm_Version": "ndvi-v1",
        })
        row["NDVI_Index"] = f"{ndvi_val:.6f}"
        updated = True

    if not updated:
        print("No rows with both Band_B04_href and Band_B08_href found; nothing to do.")
        sys.exit(0)

    # write provenance CSV (append if exists)
    write_header = not PROVENANCE_CSV.exists()
    PROVENANCE_CSV.parent.mkdir(parents=True, exist_ok=True)
    with PROVENANCE_CSV.open("a", encoding="utf-8", newline="") as pf:
        writer = csv.DictWriter(pf, fieldnames=["Image_ID", "Band_B04_href", "Band_B08_href", "NDVI", "Processed_At", "Algorithm_Version"])
        if write_header:
            writer.writeheader()
        for pr in prov_rows:
            writer.writerow(pr)

    # rewrite metadata CSV with updated NDVI_Index values
    with METADATA_CSV.open("w", encoding="utf-8", newline="") as mf:
        writer = csv.DictWriter(mf, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    print(f"NDVI computed for {len(prov_rows)} images; provenance written to {PROVENANCE_CSV}")


if __name__ == "__main__":
    main()
