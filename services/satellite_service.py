from __future__ import annotations

import csv
import math
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import requests

from config import Config
from utils.cache import TTLCache
from utils.errors import ExternalAPIError, ValidationError

CSV_COLUMNS = [
    "Image_ID",
    "HDFS_File_Path",
    "Satellite_Sensor",
    "Timestamp_UTC",
    "Station_ID",
    "Latitude",
    "Longitude",
    "Cloud_Cover_pct",
    "GSD_m",
    "Product_Type",
    "Published_At",
    "Instruments",
    "Band_B02_href",
    "Band_B03_href",
    "Band_B04_href",
    "Band_B08_href",
    "Visual_href",
    "NDVI_Index",
    "GHG_CO2_ppm",
    "GHG_CH4_ppb",
    "Processing_Status",
]


class SatelliteService:
    def __init__(self) -> None:
        self.token_url = str(getattr(Config, "COPERNICUS_OAUTH_TOKEN_URL", ""))
        self.search_url = str(getattr(Config, "COPERNICUS_STAC_SEARCH_URL", ""))
        self.collection = str(getattr(Config, "COPERNICUS_STAC_COLLECTION", "sentinel-2-l2a"))
        self.client_id = str(getattr(Config, "COPERNICUS_CLIENT_ID", ""))
        self.client_secret = str(getattr(Config, "COPERNICUS_CLIENT_SECRET", ""))
        self.username = str(getattr(Config, "COPERNICUS_USERNAME", ""))
        self.password = str(getattr(Config, "COPERNICUS_PASSWORD", ""))
        self.data_dir = Path(Config.DATA_DIR)
        self.metadata_csv = self.data_dir / "satellite_metadata.csv"
        self._token_cache = TTLCache(max_size=1, default_ttl=300)

    def _validate_credentials(self) -> None:
        if not self.client_id or not self.client_secret:
            raise ValidationError("Copernicus client credentials are not configured")
        if not self.token_url:
            raise ValidationError("Copernicus OAuth token URL is not configured")
        if not self.search_url:
            raise ValidationError("Copernicus STAC search URL is not configured")

    def _token_cache_key(self, resource: str | None = None, audience: str | None = None) -> str:
        if resource:
            return f"token:resource:{resource}"
        if audience:
            return f"token:audience:{audience}"
        return "token"

    def _get_oauth_token(self, resource: str | None = None, audience: str | None = None) -> str:
        cache_key = self._token_cache_key(resource=resource, audience=audience)
        cached = self._token_cache.get(cache_key)
        if cached:
            return cached

        if resource or audience:
            if self.username and self.password:
                payload = {
                    "grant_type": "password",
                    "client_id": "cdse-public",
                    "username": self.username,
                    "password": self.password,
                }
                try:
                    response = requests.post(self.token_url, data=payload, timeout=20)
                except Exception as exc:
                    raise ExternalAPIError(f"Failed to request Copernicus OAuth token: {exc}") from exc

                if response.status_code != 200:
                    raise ExternalAPIError(
                        f"Copernicus OAuth token request failed ({response.status_code}): {response.text}"
                    )
            else:
                self._validate_credentials()
                payload = {"grant_type": "client_credentials"}
                if resource:
                    payload["resource"] = resource
                    payload["scope"] = "openid"
                elif audience:
                    payload["audience"] = audience
                    payload["scope"] = "openid"

                try:
                    response = requests.post(
                        self.token_url,
                        data=payload,
                        auth=(self.client_id, self.client_secret),
                        timeout=20,
                    )
                except Exception as exc:
                    raise ExternalAPIError(f"Failed to request Copernicus OAuth token: {exc}") from exc

                if response.status_code != 200:
                    try:
                        fallback_payload = {
                            "grant_type": "client_credentials",
                            "client_id": self.client_id,
                            "client_secret": self.client_secret,
                        }
                        if resource:
                            fallback_payload["resource"] = resource
                            fallback_payload["scope"] = "openid"
                        elif audience:
                            fallback_payload["audience"] = audience
                            fallback_payload["scope"] = "openid"
                        response = requests.post(
                            self.token_url,
                            data=fallback_payload,
                            timeout=20,
                        )
                    except Exception as exc:
                        raise ExternalAPIError(f"Failed to request Copernicus OAuth token: {exc}") from exc

                if response.status_code != 200:
                    raise ExternalAPIError(
                        f"Copernicus OAuth token request failed ({response.status_code}): {response.text}"
                    )
        else:
            self._validate_credentials()
            payload = {"grant_type": "client_credentials"}
            if resource:
                payload["resource"] = resource
                payload["scope"] = "openid"
            elif audience:
                payload["audience"] = audience
                payload["scope"] = "openid"

            try:
                response = requests.post(
                    self.token_url,
                    data=payload,
                    auth=(self.client_id, self.client_secret),
                    timeout=20,
                )
            except Exception as exc:
                raise ExternalAPIError(f"Failed to request Copernicus OAuth token: {exc}") from exc

            if response.status_code != 200:
                try:
                    fallback_payload = {
                        "grant_type": "client_credentials",
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                    }
                    if resource:
                        fallback_payload["resource"] = resource
                        fallback_payload["scope"] = "openid"
                    elif audience:
                        fallback_payload["audience"] = audience
                        fallback_payload["scope"] = "openid"
                    response = requests.post(
                        self.token_url,
                        data=fallback_payload,
                        timeout=20,
                    )
                except Exception as exc:
                    raise ExternalAPIError(f"Failed to request Copernicus OAuth token: {exc}") from exc

            if response.status_code != 200:
                raise ExternalAPIError(
                    f"Copernicus OAuth token request failed ({response.status_code}): {response.text}"
                )

        token_payload = response.json()
        token = token_payload.get("access_token")
        expires_in = int(token_payload.get("expires_in", 300))
        if not token:
            raise ExternalAPIError("Copernicus OAuth response did not include an access token")

        ttl = max(30, expires_in - 30)
        self._token_cache.set(cache_key, token, ttl=ttl)
        return token

    def _best_asset_href(self, asset: Any) -> str:
        if not isinstance(asset, dict):
            return ""
        alternate = asset.get("alternate")
        if isinstance(alternate, dict):
            https_asset = alternate.get("https")
            if isinstance(https_asset, dict):
                href = https_asset.get("href")
                if isinstance(href, str) and href:
                    return href
        href = asset.get("href")
        return href if isinstance(href, str) else ""

    def _get_download_token(self) -> str:
        return self._get_oauth_token(resource="https://download.dataspace.copernicus.eu")

    def _resolve_product_uuid(self, product_name: str) -> str:
        if not product_name:
            raise ExternalAPIError("Missing Copernicus product name for catalogue lookup")

        token = self._get_download_token()
        url = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
        params = {"$filter": f"Name eq '{product_name}'", "$top": 1}
        headers = {"Authorization": f"Bearer {token}"}
        try:
            response = requests.get(url, headers=headers, params=params, timeout=60)
        except Exception as exc:
            raise ExternalAPIError(f"Failed to query Copernicus catalogue for product UUID: {exc}") from exc

        if response.status_code != 200:
            raise ExternalAPIError(
                f"Copernicus catalogue lookup failed ({response.status_code}): {response.text}"
            )

        payload = response.json()
        values = payload.get("value") or []
        if not isinstance(values, list) or not values:
            raise ExternalAPIError(f"Copernicus catalogue returned no product for name {product_name}")

        product_id = values[0].get("Id") or values[0].get("id")
        if not product_id:
            raise ExternalAPIError(f"Copernicus catalogue response did not include a product Id for {product_name}")
        return str(product_id)

    def _extract_product_uuid(self, feature: Dict[str, Any]) -> str:
        if not isinstance(feature, dict):
            raise ExternalAPIError("Feature payload must be a dictionary")

        properties = feature.get("properties", {}) or {}
        private = properties.get("_private", {}) or {}
        if isinstance(private, dict):
            product_uuid = private.get("product_uuid")
            if isinstance(product_uuid, str) and product_uuid:
                return product_uuid
            product_name = private.get("product_name")
            if isinstance(product_name, str) and product_name:
                return self._resolve_product_uuid(product_name)

        assets = feature.get("assets", {}) or {}
        if isinstance(assets, dict):
            for asset in assets.values():
                if not isinstance(asset, dict):
                    continue
                alternate = asset.get("alternate", {}) or {}
                https_asset = alternate.get("https", {}) or {}
                href = https_asset.get("href") or asset.get("href")
                if isinstance(href, str) and href:
                    match = re.search(r"/Products\(([^)]+)\)", href)
                    if match:
                        return match.group(1)

        feature_id = feature.get("id")
        if isinstance(feature_id, str) and feature_id:
            return self._resolve_product_uuid(feature_id)

        raise ExternalAPIError("Feature does not expose a Copernicus product UUID")

    def _odata_product_download_url(self, product_uuid: str) -> str:
        if not product_uuid:
            raise ExternalAPIError("Missing Copernicus product UUID for OData download")
        return f"https://download.dataspace.copernicus.eu/odata/v1/Products({product_uuid})/$value"

    def _download_asset_to_tempfile(self, href: str) -> Path:
        if not href or not href.startswith("http"):
            raise ExternalAPIError(f"Unsupported asset URL for download: {href}")

        token = self._get_download_token()
        headers = {"Authorization": f"Bearer {token}"}
        try:
            response = requests.get(href, headers=headers, stream=True, timeout=120)
        except Exception as exc:
            raise ExternalAPIError(f"Failed to request Copernicus asset download: {exc}") from exc

        if response.status_code != 200:
            raise ExternalAPIError(
                f"Failed to download Copernicus asset ({response.status_code}): {response.text}"
            )

        temp_file = Path(tempfile.mktemp(suffix=Path(href).suffix or ".jp2"))
        with temp_file.open("wb") as fp:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    fp.write(chunk)
        return temp_file

    def _compute_ndvi_from_files(self, red_path: Path, nir_path: Path) -> float:
        try:
            import rasterio
            from rasterio.enums import Resampling
        except Exception as exc:
            raise ExternalAPIError(f"rasterio required to compute NDVI: {exc}") from exc

        with rasterio.Env():
            with rasterio.open(str(red_path)) as src_red, rasterio.open(str(nir_path)) as src_nir:
                width = min(src_red.width, src_nir.width)
                height = min(src_red.height, src_nir.height)
                out_w = min(512, width)
                out_h = min(512, height)
                red = src_red.read(1, out_shape=(out_h, out_w), resampling=Resampling.average, masked=True).astype("float32")
                nir = src_nir.read(1, out_shape=(out_h, out_w), resampling=Resampling.average, masked=True).astype("float32")

                valid_mask = (~red.mask) & (~nir.mask)
                valid_mask &= ((nir + red) != 0)
                if not np.any(valid_mask):
                    raise ExternalAPIError("no valid NDVI pixels (division by zero or masked values)")

                ndvi = np.full(red.shape, np.nan, dtype="float32")
                ndvi[valid_mask] = (nir[valid_mask] - red[valid_mask]) / (nir[valid_mask] + red[valid_mask])
                valid_ndvi = ndvi[~np.isnan(ndvi)]
                if valid_ndvi.size == 0:
                    raise ExternalAPIError("computed NDVI is NaN")
                return float(np.mean(valid_ndvi))

    def _download_and_compute_ndvi(self, feature: Dict[str, Any]) -> float:
        assets = feature.get("assets", {}) or {}
        if not isinstance(assets, dict):
            raise ExternalAPIError("Invalid feature assets for NDVI computation")

        alt_red = assets.get("B04_10m") or assets.get("B04") or {}
        alt_nir = assets.get("B08_10m") or assets.get("B08") or {}
        red_href = self._best_asset_href(alt_red)
        nir_href = self._best_asset_href(alt_nir)
        if not red_href or not nir_href:
            raise ExternalAPIError("Feature is missing B04 or B08 assets for NDVI computation")

        with tempfile.TemporaryDirectory() as tmpdir:
            red_path = Path(tmpdir) / "red.jp2"
            nir_path = Path(tmpdir) / "nir.jp2"
            red_file = self._download_asset_to_tempfile(red_href)
            nir_file = self._download_asset_to_tempfile(nir_href)
            try:
                red_file.replace(red_path)
                nir_file.replace(nir_path)
                return self._compute_ndvi_from_files(red_path, nir_path)
            finally:
                if red_file.exists():
                    red_file.unlink(missing_ok=True)
                if nir_file.exists():
                    nir_file.unlink(missing_ok=True)

    def _bbox_from_latlng(self, latitude: float, longitude: float, radius_km: float) -> List[float]:
        latitude = max(min(latitude, 90.0), -90.0)
        radius_km = max(radius_km, 1.0)
        delta_lat = radius_km / 111.0
        cos_lat = max(math.cos(math.radians(latitude)), 0.0001)
        delta_lon = radius_km / (111.0 * cos_lat)
        return [
            longitude - delta_lon,
            latitude - delta_lat,
            longitude + delta_lon,
            latitude + delta_lat,
        ]

    def _normalize_geometry(self, geometry: Dict[str, Any]) -> tuple[float, float]:
        if not geometry or not isinstance(geometry, dict):
            return 0.0, 0.0

        geometry_type = geometry.get("type", "")
        coordinates = geometry.get("coordinates", [])
        if geometry_type == "Point" and len(coordinates) >= 2:
            return float(coordinates[1]), float(coordinates[0])

        if geometry_type == "Polygon" and coordinates:
            ring = coordinates[0]
            if ring:
                xs = [float(point[0]) for point in ring if len(point) >= 2]
                ys = [float(point[1]) for point in ring if len(point) >= 2]
                if xs and ys:
                    return sum(ys) / len(ys), sum(xs) / len(xs)

        if geometry_type == "MultiPolygon" and coordinates:
            first_ring = coordinates[0][0] if coordinates[0] else []
            if first_ring:
                xs = [float(point[0]) for point in first_ring if len(point) >= 2]
                ys = [float(point[1]) for point in first_ring if len(point) >= 2]
                if xs and ys:
                    return sum(ys) / len(ys), sum(xs) / len(xs)

        return 0.0, 0.0

    def _normalize_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        properties = item.get("properties", {}) or {}
        assets = item.get("assets", {}) or {}
        geometry = item.get("geometry", {}) or {}

        asset_url = ""
        if isinstance(assets, dict):
            # choose a primary asset href for backward compatibility (visual/analytic then bands)
            for key in ("visual", "analytic", "B04", "B03", "B02"):
                asset = assets.get(key)
                if asset and isinstance(asset, dict):
                    asset_url = self._best_asset_href(asset)
                    break
            if not asset_url and assets:
                first_asset = next(iter(assets.values()))
                if isinstance(first_asset, dict):
                    asset_url = self._best_asset_href(first_asset)

        # gather explicit band and visual asset hrefs for provenance
        band_b02 = ""
        band_b03 = ""
        band_b04 = ""
        band_b08 = ""
        visual = ""
        if isinstance(assets, dict):
            # helper to get href from asset value
            def _asset_href(v):
                return self._best_asset_href(v) if isinstance(v, dict) else ""

            # first try direct keys
            band_b02 = _asset_href(assets.get("B02") or assets.get("02") or assets.get("band_2") or {})
            band_b03 = _asset_href(assets.get("B03") or assets.get("03") or assets.get("band_3") or {})
            band_b04 = _asset_href(assets.get("B04") or assets.get("04") or assets.get("band_4") or {})
            band_b08 = _asset_href(assets.get("B08") or assets.get("08") or assets.get("band_8") or {})
            visual = _asset_href(assets.get("visual") or assets.get("thumbnail") or assets.get("analytic") or {})

            # if any band hrefs missing, scan all assets for likely band names or filenames
            if not (band_b02 and band_b03 and band_b04 and band_b08):
                for k, v in assets.items():
                    href = _asset_href(v) or ""
                    ku = (k or "").upper()
                    hu = href.upper()
                    if not band_b02 and "B02" in ku:
                        band_b02 = href
                    if not band_b03 and "B03" in ku:
                        band_b03 = href
                    if not band_b04 and "B04" in ku:
                        band_b04 = href
                    if not band_b08 and "B08" in ku:
                        band_b08 = href
                    if not visual and ("VISUAL" in ku or "THUMB" in ku or "ANALYTIC" in ku or "VISUAL" in hu or "THUMB" in hu or "ANALYTIC" in hu):
                        visual = href
                    # break early if all found
                    if band_b02 and band_b03 and band_b04 and band_b08 and visual:
                        break

        latitude, longitude = self._normalize_geometry(geometry)

        timestamp = (
            properties.get("datetime")
            or properties.get("start_datetime")
            or properties.get("start_date")
            or ""
        )
        if isinstance(timestamp, datetime):
            timestamp = timestamp.astimezone(timezone.utc).isoformat()

        processing_status = (
            properties.get("processing:status")
            or properties.get("odc:processing_status")
            or properties.get("sat:processing_status")
            or properties.get("quality_status")
            or "available"
        )

        station_id = (
            properties.get("platform")
            or properties.get("constellation")
            or properties.get("sat:constellation")
            or item.get("collection")
            or item.get("id", "")
        )

        sensor = str(properties.get("platform") or properties.get("constellation") or self.collection)

        return {
            "Image_ID": str(item.get("id", "")),
            "HDFS_File_Path": str(asset_url),
            "Satellite_Sensor": sensor,
            "Timestamp_UTC": str(timestamp),
            "Station_ID": str(station_id),
            "Latitude": latitude,
            "Longitude": longitude,
            "Cloud_Cover_pct": properties.get("eo:cloud_cover", ""),
            "GSD_m": properties.get("gsd", ""),
            "Product_Type": properties.get("product:type", ""),
            "Published_At": properties.get("published", ""),
            "Instruments": properties.get("instruments", ""),
            "Band_B02_href": band_b02,
            "Band_B03_href": band_b03,
            "Band_B04_href": band_b04,
            "Band_B08_href": band_b08,
            "Visual_href": visual,
            "NDVI_Index": "",
            "GHG_CO2_ppm": "",
            "GHG_CH4_ppb": "",
            "Processing_Status": str(processing_status),
        }

    def _call_stac_search(
        self,
        token: str,
        latitude: float,
        longitude: float,
        radius_km: float,
        limit: int,
        days: int,
        collection: str | None = None,
    ) -> List[Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=max(days, 1))
        bbox = self._bbox_from_latlng(latitude, longitude, radius_km)
        collection_to_use = collection or self.collection
        payload = {
            "collections": [collection_to_use],
            "bbox": bbox,
            "datetime": f"{start.strftime('%Y-%m-%dT%H:%M:%SZ')}/{now.strftime('%Y-%m-%dT%H:%M:%SZ')}",
            "limit": max(1, min(limit, 100)),
            "sortby": [{"field": "properties.datetime", "direction": "desc"}],
        }
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        try:
            response = requests.post(self.search_url, json=payload, headers=headers, timeout=30)
        except Exception as exc:
            raise ExternalAPIError(f"Copernicus STAC search request failed: {exc}") from exc

        if response.status_code != 200:
            raise ExternalAPIError(
                f"Copernicus STAC search failed ({response.status_code}): {response.text}"
            )

        data = response.json()
        features = data.get("features") or []
        if not isinstance(features, list):
            raise ExternalAPIError("Unexpected Copernicus STAC search response structure")
        return features

    def _write_metadata_csv(self, rows: List[Dict[str, Any]]) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with self.metadata_csv.open("w", encoding="utf-8", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key, "") for key in CSV_COLUMNS})

    def get_latest_products(
        self,
        latitude: float,
        longitude: float,
        radius_km: float = 20.0,
        limit: int = 10,
        days: int = 14,
        collection: str | None = None,
    ) -> Dict[str, Any]:
        token = self._get_oauth_token()
        if collection is None:
            features = self._call_stac_search(token, latitude, longitude, radius_km, limit, days)
        else:
            features = self._call_stac_search(token, latitude, longitude, radius_km, limit, days, collection)

        metadata_rows = []
        for feature in features:
            row = self._normalize_item(feature)
            try:
                ndvi_value = self._download_and_compute_ndvi(feature)
            except Exception:
                ndvi_value = None
            if isinstance(ndvi_value, (int, float)) and not math.isnan(float(ndvi_value)):
                row["NDVI_Index"] = f"{float(ndvi_value):.6f}"
            metadata_rows.append(row)

        self._write_metadata_csv(metadata_rows)
        return {
            "count": len(metadata_rows),
            "items": metadata_rows,
            "metadata_path": str(self.metadata_csv),
            "query": {
                "latitude": latitude,
                "longitude": longitude,
                "radius_km": radius_km,
                "limit": limit,
                "days": days,
                "collection": collection or self.collection,
            },
        }


satellite_service = SatelliteService()
