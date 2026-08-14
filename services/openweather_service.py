from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

import requests

from config import Config
from utils.errors import ExternalAPIError, NotFoundError, ValidationError
from utils.helpers import now_iso


class OpenWeatherService:
    def __init__(self) -> None:
        self.api_key = getattr(Config, "OPENWEATHER_API_KEY", "") or ""
        self.base_url = "https://api.openweathermap.org/data/2.5"
        self.timeout = 20

    def get_current_weather(
        self,
        city: Optional[str] = None,
        country: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> Dict[str, Any]:
        if not self.api_key:
            raise ExternalAPIError("OpenWeather API key is not configured")

        params: Dict[str, Any] = {
            "appid": self.api_key,
            "units": "metric",
        }

        if latitude is not None and longitude is not None:
            params["lat"] = latitude
            params["lon"] = longitude
        elif city:
            query = city.strip()
            if not query:
                raise ValidationError("City name is required")
            if country:
                query = f"{query},{country.strip()}"
            params["q"] = query
        else:
            raise ValidationError("City name or latitude/longitude coordinates are required")

        try:
            response = requests.get(f"{self.base_url}/weather", params=params, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except requests.exceptions.HTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            body = exc.response.text if exc.response is not None else str(exc)
            if status == 404:
                raise NotFoundError("Location not found", details={"body": body}) from exc
            if status in {401, 403}:
                raise ExternalAPIError("OpenWeather API authentication failed", details={"body": body}) from exc
            raise ExternalAPIError(f"OpenWeather API returned HTTP {status}", details={"body": body}) from exc
        except requests.exceptions.Timeout as exc:
            raise ExternalAPIError("OpenWeather API request timed out") from exc
        except requests.exceptions.RequestException as exc:
            raise ExternalAPIError(f"OpenWeather API request failed: {exc}") from exc
        except ValueError as exc:
            raise ExternalAPIError("OpenWeather API returned invalid JSON") from exc

        return self._normalize_current_weather(payload)

    def _normalize_current_weather(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        weather_item = (payload.get("weather") or [{}])[0]
        main = payload.get("main", {}) or {}
        wind = payload.get("wind", {}) or {}
        sys = payload.get("sys", {}) or {}
        rain = payload.get("rain", {}) or {}
        clouds = payload.get("clouds", {}) or {}
        coord = payload.get("coord", {}) or {}

        timestamp = payload.get("dt")
        timestamp_iso = (
            datetime.utcfromtimestamp(int(timestamp)).isoformat() + "Z"
            if timestamp
            else now_iso()
        )

        city = payload.get("name") or ""
        country = sys.get("country") or ""
        latitude = coord.get("lat")
        longitude = coord.get("lon")
        rainfall = rain.get("1h") or rain.get("3h") or 0.0
        visibility = payload.get("visibility")

        return {
            "source": "openweather",
            "api_available": True,
            "provider": "OpenWeather",
            "city": city,
            "country": country,
            "latitude": float(latitude) if latitude is not None else None,
            "longitude": float(longitude) if longitude is not None else None,
            "temperature": {
                "celsius": float(main.get("temp", 0.0) or 0.0),
                "fahrenheit": round(float(main.get("temp", 0.0) or 0.0) * 9 / 5 + 32, 1),
                "feels_like_c": float(main.get("feels_like", 0.0) or 0.0),
                "feels_like_f": round(float(main.get("feels_like", 0.0) or 0.0) * 9 / 5 + 32, 1),
                "min_c": float(main.get("temp_min", 0.0) or 0.0),
                "max_c": float(main.get("temp_max", 0.0) or 0.0),
            },
            "humidity_pct": int(main.get("humidity", 0) or 0),
            "pressure_hpa": int(main.get("pressure", 0) or 0),
            "wind": {
                "speed_ms": float(wind.get("speed", 0.0) or 0.0),
                "speed_kmh": round(float(wind.get("speed", 0.0) or 0.0) * 3.6, 1),
                "direction_deg": int(wind.get("deg", 0) or 0),
            },
            "rainfall_mm": float(rainfall),
            "cloud_cover_pct": int(clouds.get("all", 0) or 0),
            "visibility_km": round(float(visibility or 0) / 1000, 1),
            "condition": weather_item.get("main") or weather_item.get("description") or "Unknown",
            "icon": weather_item.get("icon") or "01d",
            "sunrise": self._format_unix_time(sys.get("sunrise")),
            "sunset": self._format_unix_time(sys.get("sunset")),
            "timestamp": timestamp_iso,
        }

    @staticmethod
    def _format_unix_time(value: Any) -> Optional[str]:
        try:
            if value is None:
                return None
            return datetime.utcfromtimestamp(int(value)).strftime("%H:%M")
        except Exception:
            return None
