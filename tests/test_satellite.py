from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

import pytest

from services.satellite_service import SatelliteService, satellite_service
from services.satellite_service import CSV_COLUMNS
from utils.errors import ExternalAPIError, ValidationError


def test_validate_credentials_raises_when_missing_client_credentials(monkeypatch):
    service = SatelliteService()
    monkeypatch.setattr(service, "client_id", "")
    monkeypatch.setattr(service, "client_secret", "")
    with pytest.raises(ValidationError):
        service._get_oauth_token()


def test_get_oauth_token_uses_password_flow_for_download_credentials(monkeypatch):
    service = SatelliteService()
    service.client_id = "service-client"
    service.client_secret = "service-secret"
    service.username = "copernicus-user"
    service.password = "copernicus-pass"

    calls = []

    class FakeResponse:
        status_code = 200
        text = "{}"

        def json(self):
            return {"access_token": "password-token", "expires_in": 300}

    def fake_post(url, data=None, auth=None, timeout=None):
        calls.append({"url": url, "data": data, "auth": auth, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr("services.satellite_service.requests.post", fake_post)

    token = service._get_oauth_token(resource="https://download.dataspace.copernicus.eu")

    assert token == "password-token"
    assert len(calls) == 1
    assert calls[0]["data"]["grant_type"] == "password"
    assert calls[0]["data"]["client_id"] == "cdse-public"
    assert calls[0]["data"]["username"] == "copernicus-user"
    assert calls[0]["data"]["password"] == "copernicus-pass"


def test_resolve_product_uuid_queries_catalogue_by_name(monkeypatch):
    service = SatelliteService()
    calls = []

    class FakeResponse:
        status_code = 200
        text = "{}"

        def json(self):
            return {"value": [{"Id": "11111111-2222-3333-4444-555555555555"}]}

    def fake_get(url, headers=None, params=None, timeout=None):
        calls.append({"url": url, "headers": headers, "params": params, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr("services.satellite_service.requests.get", fake_get)
    monkeypatch.setattr(service, "_get_oauth_token", lambda *args, **kwargs: "catalogue-token")

    product_uuid = service._resolve_product_uuid("S2A_TEST_PRODUCT")

    assert product_uuid == "11111111-2222-3333-4444-555555555555"
    assert calls[0]["params"]["$filter"] == "Name eq 'S2A_TEST_PRODUCT'"
    assert calls[0]["headers"]["Authorization"] == "Bearer catalogue-token"


def test_normalize_item_returns_expected_keys():
    service = SatelliteService()
    feature = {
        "id": "S2A_MSIL1C_20260101T123019_N0400_R065_T15RWN_20260101T123018",
        "geometry": {"type": "Point", "coordinates": [67.0, 25.0]},
        "properties": {
            "datetime": "2026-01-01T12:30:19Z",
            "platform": "Sentinel-2",
            "processing:status": "processed",
        },
        "assets": {
            "B04": {"href": "https://example.com/S2A.tif"},
        },
    }
    row = service._normalize_item(feature)
    assert row["Image_ID"] == feature["id"]
    assert row["Satellite_Sensor"] == "Sentinel-2"
    assert row["Timestamp_UTC"] == "2026-01-01T12:30:19Z"
    assert row["Latitude"] == 25.0
    assert row["Longitude"] == 67.0
    assert row["HDFS_File_Path"] == "https://example.com/S2A.tif"
    for column in CSV_COLUMNS:
        assert column in row


def test_write_metadata_csv(tmp_path):
    service = SatelliteService()
    service.data_dir = tmp_path
    service.metadata_csv = tmp_path / "satellite_metadata.csv"
    rows = [
        {
            "Image_ID": "IMG_TEST",
            "HDFS_File_Path": "https://example.com/test.tif",
            "Satellite_Sensor": "Sentinel-2",
            "Timestamp_UTC": "2026-01-01T00:00:00Z",
            "Station_ID": "STN_TEST",
            "Latitude": 25.0,
            "Longitude": 67.0,
            "NDVI_Index": "",
            "GHG_CO2_ppm": "",
            "GHG_CH4_ppb": "",
            "Processing_Status": "processed",
        }
    ]
    service._write_metadata_csv(rows)
    assert service.metadata_csv.exists()
    content = service.metadata_csv.read_text(encoding="utf-8")
    reader = csv.DictReader(io.StringIO(content))
    assert reader.fieldnames == CSV_COLUMNS
    records = list(reader)
    assert len(records) == 1
    assert records[0]["Image_ID"] == "IMG_TEST"


def test_get_latest_products_writes_csv_and_returns_items(monkeypatch, tmp_path):
    service = SatelliteService()
    service.data_dir = tmp_path
    service.metadata_csv = tmp_path / "satellite_metadata.csv"
    token_value = "fake-token"
    feature = {
        "id": "S2A_TEST",
        "geometry": {"type": "Point", "coordinates": [67.0, 25.0]},
        "properties": {"datetime": "2026-01-01T12:00:00Z", "platform": "Sentinel-2"},
        "assets": {"B04": {"href": "https://example.com/S2A_TEST.tif"}},
    }

    monkeypatch.setattr(service, "_get_oauth_token", lambda: token_value)
    monkeypatch.setattr(service, "_call_stac_search", lambda token, latitude, longitude, radius_km, limit, days: [feature])

    result = service.get_latest_products(latitude=25.0, longitude=67.0, radius_km=10, limit=1, days=7)
    assert result["count"] == 1
    assert result["metadata_path"] == str(service.metadata_csv)
    assert service.metadata_csv.exists()
    assert result["items"][0]["Image_ID"] == "S2A_TEST"


def test_get_latest_products_sets_ndvi_when_download_succeeds(monkeypatch, tmp_path):
    service = SatelliteService()
    service.data_dir = tmp_path
    service.metadata_csv = tmp_path / "satellite_metadata.csv"
    feature = {
        "id": "S2A_TEST",
        "geometry": {"type": "Point", "coordinates": [67.0, 25.0]},
        "properties": {"datetime": "2026-01-01T12:00:00Z", "platform": "Sentinel-2"},
        "assets": {
            "B04_10m": {"alternate": {"https": {"href": "https://example.com/red.jp2"}}},
            "B08_10m": {"alternate": {"https": {"href": "https://example.com/nir.jp2"}}},
        },
    }

    monkeypatch.setattr(service, "_get_oauth_token", lambda *args, **kwargs: "fake-token")
    monkeypatch.setattr(service, "_call_stac_search", lambda token, latitude, longitude, radius_km, limit, days, collection=None: [feature])
    monkeypatch.setattr(service, "_download_and_compute_ndvi", lambda feature: 0.42)

    result = service.get_latest_products(latitude=25.0, longitude=67.0, radius_km=10, limit=1, days=7)
    assert result["items"][0]["NDVI_Index"] == "0.420000"


def test_download_asset_to_tempfile_streams_bytes(monkeypatch, tmp_path):
    service = SatelliteService()
    monkeypatch.setattr(service, "_get_download_token", lambda: "download-token")

    class FakeResponse:
        status_code = 200

        def iter_content(self, chunk_size=8192):
            yield b"ab"
            yield b"cd"

    def fake_get(url, headers=None, stream=None, timeout=None):
        return FakeResponse()

    monkeypatch.setattr("services.satellite_service.requests.get", fake_get)

    temp_path = service._download_asset_to_tempfile("https://example.com/band.jp2")

    assert temp_path.exists()
    assert temp_path.read_bytes() == b"abcd"


def test_odata_download_url_uses_product_uuid():
    service = SatelliteService()
    assert service._odata_product_download_url("abc123") == "https://download.dataspace.copernicus.eu/odata/v1/Products(abc123)/$value"


def test_get_latest_products_endpoint(client, monkeypatch):
    from services.satellite_service import satellite_service

    monkeypatch.setattr(satellite_service, "get_latest_products", lambda latitude, longitude, radius_km, limit, days: {
        "count": 1,
        "items": [{"Image_ID": "S2A_TEST"}],
        "metadata_path": "data/satellite_metadata.csv",
        "query": {
            "latitude": latitude,
            "longitude": longitude,
            "radius_km": radius_km,
            "limit": limit,
            "days": days,
        },
    })

    response = client.get("/api/satellite/latest?lat=25.0&lon=67.0&radius_km=10&limit=1&days=7")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["count"] == 1
    assert payload["items"][0]["Image_ID"] == "S2A_TEST"


def test_latest_satellite_products_invalid_params(client):
    response = client.get("/api/satellite/latest?lat=foo&lon=bar")
    assert response.status_code == 422
    payload = response.get_json()
    assert payload["error"] == "validation_error"
