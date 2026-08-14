from __future__ import annotations

import random
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests

from config import Config
from database import get_db
from services.openweather_service import OpenWeatherService
from utils.cache import TTLCache, cache_manager, get_or_create, make_key
from utils.errors import ExternalAPIError, NotFoundError, ValidationError
from utils.helpers import now_iso, serialize_document
from utils.logging_setup import log_weather_api


class WeatherService:
    def __init__(self) -> None:
        self.db = get_db()
        self._cache: TTLCache = cache_manager.get_cache("weather", max_size=5000, default_ttl=600)
        self._geocode_cache: TTLCache = cache_manager.get_cache("geocode", max_size=1000, default_ttl=86400)
        self._air_quality_cache: TTLCache = cache_manager.get_cache("air_quality", max_size=5000, default_ttl=900)
        self.weather_api_key = getattr(Config, "OPENWEATHER_API_KEY", None) or None
        self.base_url = "https://api.openweathermap.org/data/2.5"
        self.openweather = OpenWeatherService()

    def search_city(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        query = (query or "").strip().lower()
        if not query:
            raise ValidationError("Search query is required")
        if len(query) < 2:
            raise ValidationError("Search query must be at least 2 characters")

        cache_key = make_key("search", query, limit)
        cached = self._cache.get(cache_key)
        if cached is not None:
            log_weather_api("search_city", cache_key, cache_hit=True)
            return cached

        db_matches = list(
            self.db.cities.find(
                {"name": {"$regex": f".*{query}.*", "$options": "i"}}
            ).limit(limit)
        )
        if db_matches:
            results = serialize_document(db_matches)
            self._cache.set(cache_key, results, ttl=1800)
            return results

        fallback = self._generate_city_suggestions(query, limit)
        self._cache.set(cache_key, fallback, ttl=1800)
        return fallback

    def get_coordinates(self, city: str, country: Optional[str] = None) -> Dict[str, Any]:
        city = (city or "").strip().lower()
        if not city:
            raise ValidationError("City name is required")

        cache_key = make_key("coords", city, country)
        cached = self._geocode_cache.get(cache_key)
        if cached is not None:
            log_weather_api("get_coordinates", cache_key, cache_hit=True)
            return cached

        db_match = self.db.cities.find_one({"name": {"$regex": f"^{city}$", "$options": "i"}})
        coords: Dict[str, Any]
        if db_match:
            coords = {
                "city": db_match.get("name", city.title()),
                "country": db_match.get("country", country or ""),
                "region": db_match.get("region", ""),
                "latitude": float(db_match.get("latitude", self._default_lat(city))),
                "longitude": float(db_match.get("longitude", self._default_lon(city))),
            }
        else:
            coords = {
                "city": city.title(),
                "country": country or "",
                "region": "",
                "latitude": self._default_lat(city),
                "longitude": self._default_lon(city),
            }

        self._geocode_cache.set(cache_key, coords, ttl=86400)
        return coords

    def get_current_weather(
        self,
        city: str = "",
        country: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> Dict[str, Any]:
        city = (city or "").strip()
        if not city and (latitude is None or longitude is None):
            raise ValidationError("City name or latitude/longitude coordinates are required")

        cache_key = make_key("current", city, country, latitude, longitude)
        start = time.time()

        def fetch() -> Dict[str, Any]:
            coords = self.get_coordinates(city, country) if city else {"latitude": latitude, "longitude": longitude, "city": "", "country": country or ""}
            weather = self._fetch_current_weather(city, coords, latitude=latitude, longitude=longitude)
            self.db.weather_data.update_one(
                {"city": (weather.get("city") or city).lower(), "timestamp": weather["timestamp"]},
                {"$setOnInsert": weather},
                upsert=True,
            )
            return weather

        result, hit = get_or_create(self._cache, cache_key, fetch, ttl=600)
        duration = int((time.time() - start) * 1000)
        log_weather_api("get_current_weather", cache_key, success=True, cache_hit=hit, response_time_ms=duration)
        return result

    def get_forecast(self, city: str, days: int = 7, country: Optional[str] = None) -> Dict[str, Any]:
        city = (city or "").strip()
        days = max(1, min(14, int(days or 7)))
        if not city:
            raise ValidationError("City name is required")

        cache_key = make_key("forecast", city, days, country)
        start = time.time()

        def fetch() -> Dict[str, Any]:
            coords = self.get_coordinates(city, country)
            if self.weather_api_key:
                try:
                    return self._call_weather_forecast(city, coords, days)
                except Exception as exc:
                    log_weather_api("fetch_forecast", city, success=False, error=str(exc))
            return self._generate_forecast(city, coords, days)

        result, hit = get_or_create(self._cache, cache_key, fetch, ttl=1800)
        duration = int((time.time() - start) * 1000)
        log_weather_api("get_forecast", cache_key, success=True, cache_hit=hit, response_time_ms=duration)
        return result

    def get_air_quality(self, city: str, country: Optional[str] = None) -> Dict[str, Any]:
        city = (city or "").strip()
        if not city:
            raise ValidationError("City name is required")

        cache_key = make_key("aqi", city, country)
        start = time.time()

        def fetch() -> Dict[str, Any]:
            coords = self.get_coordinates(city, country)
            aqi = self._generate_air_quality(city, coords)
            self.db.air_quality.update_one(
                {"city": city.lower(), "timestamp": aqi["timestamp"]},
                {"$setOnInsert": aqi},
                upsert=True,
            )
            return aqi

        result, hit = get_or_create(self._air_quality_cache, cache_key, fetch, ttl=900)
        duration = int((time.time() - start) * 1000)
        log_weather_api("get_air_quality", cache_key, success=True, cache_hit=hit, response_time_ms=duration)
        return result

    def get_saved_cities(self, user_id: str) -> List[Dict[str, Any]]:
        docs = list(self.db.saved_cities.find({"user_id": user_id}).sort("created_at", -1))
        return serialize_document(docs)

    def save_city(self, user_id: str, city: str, country: Optional[str] = None, nickname: Optional[str] = None) -> Dict[str, Any]:
        city = (city or "").strip()
        if not city:
            raise ValidationError("City name is required")
        coords = self.get_coordinates(city, country)
        doc = {
            "user_id": user_id,
            "city": city,
            "country": coords.get("country", country or ""),
            "nickname": nickname or city.title(),
            "latitude": coords["latitude"],
            "longitude": coords["longitude"],
            "created_at": now_iso(),
        }
        result = self.db.saved_cities.update_one(
            {"user_id": user_id, "city": city.lower()},
            {"$setOnInsert": doc},
            upsert=True,
        )
        return serialize_document(doc)

    def delete_saved_city(self, user_id: str, city_id: str) -> bool:
        from bson import ObjectId
        result = self.db.saved_cities.delete_one({"_id": ObjectId(city_id), "user_id": user_id})
        return result.deleted_count > 0

    def _fetch_current_weather(
        self,
        city: str,
        coords: Dict[str, Any],
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> Dict[str, Any]:
        if self.weather_api_key:
            try:
                if latitude is not None and longitude is not None:
                    return self.openweather.get_current_weather(latitude=latitude, longitude=longitude)
                return self.openweather.get_current_weather(city=city, country=coords.get("country", ""), latitude=latitude, longitude=longitude)
            except (ExternalAPIError, NotFoundError, ValidationError):
                raise
            except Exception as exc:
                log_weather_api("fetch_current", city, success=False, error=str(exc))
        return self._generate_current_weather(city, coords)

    def _call_weather_api(self, city: str, coords: Dict[str, Any]) -> Dict[str, Any]:
        params = {
            "q": f"{city},{coords.get('country', '').strip()}" if coords.get("country") else city,
            "appid": self.weather_api_key,
            "units": "metric",
        }
        try:
            response = requests.get(f"{self.base_url}/weather", params=params, timeout=20)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise ExternalAPIError(f"Weather API current weather request failed: {exc}") from exc

        return self._normalize_openweather_current(payload, coords, city)

    def _call_weather_forecast(self, city: str, coords: Dict[str, Any], days: int) -> Dict[str, Any]:
        params = {
            "q": f"{city},{coords.get('country', '').strip()}" if coords.get("country") else city,
            "appid": self.weather_api_key,
            "units": "metric",
        }
        try:
            response = requests.get(f"{self.base_url}/forecast", params=params, timeout=20)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise ExternalAPIError(f"Weather API forecast request failed: {exc}") from exc

        return self._normalize_openweather_forecast(payload, city, days)

    def _normalize_openweather_current(self, payload: Dict[str, Any], coords: Dict[str, Any], city: str) -> Dict[str, Any]:
        weather = payload.get("weather", [{}])[0] if payload.get("weather") else {}
        main = payload.get("main", {})
        wind = payload.get("wind", {})
        sys = payload.get("sys", {})
        rain = payload.get("rain", {}) or {}
        clouds = payload.get("clouds", {}) or {}

        timestamp = payload.get("dt")
        if timestamp:
            timestamp_iso = datetime.utcfromtimestamp(int(timestamp)).isoformat() + "Z"
        else:
            timestamp_iso = now_iso()

        icon = weather.get("icon") or "01d"
        condition = weather.get("main") or weather.get("description") or "Clear"
        country = sys.get("country") or coords.get("country", "")
        latitude = payload.get("coord", {}).get("lat", coords.get("latitude", 0.0))
        longitude = payload.get("coord", {}).get("lon", coords.get("longitude", 0.0))
        rainfall = rain.get("1h") or rain.get("3h") or 0.0

        return {
            "city": payload.get("name") or city.title(),
            "country": country,
            "latitude": float(latitude),
            "longitude": float(longitude),
            "source": "openweather",
            "api_available": True,
            "temperature": {
                "celsius": float(main.get("temp", 0.0)),
                "fahrenheit": round(float(main.get("temp", 0.0)) * 9 / 5 + 32, 1),
                "feels_like_c": float(main.get("feels_like", 0.0)),
                "feels_like_f": round(float(main.get("feels_like", 0.0)) * 9 / 5 + 32, 1),
                "min_c": float(main.get("temp_min", 0.0)),
                "max_c": float(main.get("temp_max", 0.0)),
            },
            "humidity_pct": int(main.get("humidity", 0) or 0),
            "pressure_hpa": int(main.get("pressure", 0) or 0),
            "wind": {
                "speed_kmh": round(float(wind.get("speed", 0.0)) * 3.6, 1),
                "speed_ms": float(wind.get("speed", 0.0)),
                "direction_deg": int(wind.get("deg", 0) or 0),
                "direction_label": self._wind_label(int(wind.get("deg", 0) or 0)),
            },
            "rainfall_mm": float(rainfall),
            "cloud_cover_pct": int(clouds.get("all", 0) or 0),
            "uv_index": None,
            "visibility_km": round(float(payload.get("visibility", 0) or 0) / 1000, 1),
            "condition": condition,
            "icon": icon,
            "sunrise": datetime.utcfromtimestamp(int(sys.get("sunrise", 0))).strftime("%H:%M") if sys.get("sunrise") else self._sunrise_time(city),
            "sunset": datetime.utcfromtimestamp(int(sys.get("sunset", 0))).strftime("%H:%M") if sys.get("sunset") else self._sunset_time(city),
            "timestamp": timestamp_iso,
        }

    def _normalize_openweather_forecast(self, payload: Dict[str, Any], city: str, days: int) -> Dict[str, Any]:
        entries = payload.get("list", [])
        day_groups: Dict[str, Dict[str, Any]] = {}
        for item in entries:
            dt_txt = item.get("dt_txt")
            if not dt_txt:
                continue
            date_key = dt_txt.split(" ")[0]
            if date_key not in day_groups:
                day_groups[date_key] = {
                    "date": date_key,
                    "high_c": float(item.get("main", {}).get("temp_max", 0.0) or 0.0),
                    "low_c": float(item.get("main", {}).get("temp_min", 0.0) or 0.0),
                    "rainfall_mm": 0.0,
                    "humidity": [],
                    "conditions": [],
                    "icons": [],
                    "precip_count": 0,
                    "observations": 0,
                }
            group = day_groups[date_key]
            temp_max = float(item.get("main", {}).get("temp_max", 0.0) or 0.0)
            temp_min = float(item.get("main", {}).get("temp_min", 0.0) or 0.0)
            group["high_c"] = max(group["high_c"], temp_max)
            group["low_c"] = min(group["low_c"], temp_min)
            rain_value = float(item.get("rain", {}).get("3h", 0.0) or 0.0)
            if rain_value > 0:
                group["rainfall_mm"] += rain_value
                group["precip_count"] += 1
            humidity_value = item.get("main", {}).get("humidity")
            if humidity_value is not None:
                group["humidity"].append(int(humidity_value))
            weather = item.get("weather", [{}])[0] if item.get("weather") else {}
            condition = weather.get("main") or weather.get("description")
            if condition:
                group["conditions"].append(condition)
            icon = weather.get("icon")
            if icon:
                group["icons"].append(icon)
            group["observations"] += 1

        sorted_dates = sorted(day_groups.keys())[:days]
        items: List[Dict[str, Any]] = []
        for date_key in sorted_dates:
            group = day_groups[date_key]
            avg_humidity = int(sum(group["humidity"]) / len(group["humidity"])) if group["humidity"] else 0
            condition = max(set(group["conditions"]), key=group["conditions"].count) if group["conditions"] else "Clear"
            icon = group["icons"][-1] if group["icons"] else "01d"
            try:
                date_obj = datetime.fromisoformat(group["date"])
                day_label = date_obj.strftime("%A")
            except Exception:
                day_label = group["date"]
            items.append({
                "date": group["date"],
                "day": day_label,
                "temperature": {
                    "high_c": round(group["high_c"], 1),
                    "low_c": round(group["low_c"], 1),
                    "high_f": round(group["high_c"] * 9 / 5 + 32, 1),
                    "low_f": round(group["low_c"] * 9 / 5 + 32, 1),
                },
                "humidity_pct": avg_humidity,
                "rainfall_mm": round(group["rainfall_mm"], 1),
                "condition": condition,
                "icon": icon,
                "precipitation_chance_pct": int(100 * group["precip_count"] / group["observations"]) if group["observations"] else 0,
            })

        city_info = payload.get("city", {}) or {}
        return {
            "city": city_info.get("name", city.title()),
            "country": city_info.get("country", ""),
            "days": len(items),
            "items": items,
            "source": "openweather",
            "api_available": True,
        }

    def _generate_current_weather(self, city: str, coords: Dict[str, Any]) -> Dict[str, Any]:
        seed = sum(ord(c) for c in city.lower())
        rng = random.Random(seed + int(time.time() // 3600))
        temp_c = round(rng.uniform(8.0, 38.0), 1)
        feels_like = round(temp_c + rng.uniform(-2, 3), 1)
        humidity = rng.randint(25, 95)
        pressure = rng.randint(995, 1035)
        wind_speed = round(rng.uniform(2.0, 55.0), 1)
        wind_deg = rng.randint(0, 359)
        rainfall = round(rng.uniform(0, 80.0), 1) if rng.random() < 0.35 else 0.0
        cloud_cover = rng.randint(0, 100)
        uv_index = round(rng.uniform(0.5, 11.0), 1)
        visibility = rng.randint(2, 15)
        conditions = ["Clear", "Cloudy", "Partly Cloudy", "Rainy", "Foggy", "Thunderstorm", "Sunny", "Overcast"]
        condition = rng.choice(conditions)
        return {
            "city": city.title(),
            "country": coords.get("country", ""),
            "latitude": coords["latitude"],
            "longitude": coords["longitude"],
            "source": "fallback",
            "api_available": False,
            "temperature": {
                "celsius": temp_c,
                "fahrenheit": round(temp_c * 9 / 5 + 32, 1),
                "feels_like_c": feels_like,
                "feels_like_f": round(feels_like * 9 / 5 + 32, 1),
                "min_c": round(temp_c - rng.uniform(2, 6), 1),
                "max_c": round(temp_c + rng.uniform(2, 8), 1),
            },
            "humidity_pct": humidity,
            "pressure_hpa": pressure,
            "wind": {
                "speed_kmh": wind_speed,
                "speed_ms": round(wind_speed / 3.6, 1),
                "direction_deg": wind_deg,
                "direction_label": self._wind_label(wind_deg),
            },
            "rainfall_mm": rainfall,
            "cloud_cover_pct": cloud_cover,
            "uv_index": uv_index,
            "visibility_km": visibility,
            "condition": condition,
            "icon": self._weather_icon(condition),
            "sunrise": self._sunrise_time(city),
            "sunset": self._sunset_time(city),
            "timestamp": now_iso(),
        }

    def _generate_forecast(self, city: str, coords: Dict[str, Any], days: int) -> Dict[str, Any]:
        seed = sum(ord(c) for c in city.lower())
        rng = random.Random(seed + 7)
        from datetime import datetime, timedelta
        items: List[Dict[str, Any]] = []
        today = datetime.now().date()
        current = self._generate_current_weather(city, coords)
        base_temp = current["temperature"]["celsius"]
        for d in range(days):
            date = today + timedelta(days=d)
            variance = rng.uniform(-5, 5)
            high_c = round(base_temp + rng.uniform(1, 7) + variance, 1)
            low_c = round(base_temp - rng.uniform(2, 8) + variance, 1)
            conditions = ["Clear", "Cloudy", "Partly Cloudy", "Rainy", "Sunny", "Thunderstorm", "Overcast", "Foggy"]
            condition = rng.choice(conditions)
            items.append({
                "date": date.isoformat(),
                "day": date.strftime("%A"),
                "temperature": {
                    "high_c": high_c,
                    "low_c": low_c,
                    "high_f": round(high_c * 9 / 5 + 32, 1),
                    "low_f": round(low_c * 9 / 5 + 32, 1),
                },
                "humidity_pct": rng.randint(25, 95),
                "rainfall_mm": round(rng.uniform(0, 80.0), 1) if rng.random() < 0.35 else 0.0,
                "wind_speed_kmh": round(rng.uniform(2.0, 55.0), 1),
                "uv_index": round(rng.uniform(0.5, 11.0), 1),
                "condition": condition,
                "icon": self._weather_icon(condition),
                "precipitation_chance_pct": rng.randint(0, 95),
            })
        return {"city": city.title(), "country": coords.get("country", ""), "days": days, "items": items}

    def _generate_air_quality(self, city: str, coords: Dict[str, Any]) -> Dict[str, Any]:
        seed = sum(ord(c) for c in city.lower()) * 3
        rng = random.Random(seed + int(time.time() // 7200))
        aqi = rng.randint(15, 280)
        pm25 = round(rng.uniform(5, 150), 1)
        pm10 = round(pm25 * rng.uniform(1.2, 2.0), 1)
        no2 = round(rng.uniform(5, 120), 1)
        so2 = round(rng.uniform(2, 80), 1)
        co = round(rng.uniform(0.2, 8.0), 2)
        ozone = round(rng.uniform(10, 180), 1)
        return {
            "city": city.title(),
            "country": coords.get("country", ""),
            "latitude": coords["latitude"],
            "longitude": coords["longitude"],
            "aqi": aqi,
            "aqi_level": self._aqi_label(aqi),
            "pollutants": {
                "pm25": {"value": pm25, "unit": "µg/m³"},
                "pm10": {"value": pm10, "unit": "µg/m³"},
                "no2": {"value": no2, "unit": "ppb"},
                "so2": {"value": so2, "unit": "ppb"},
                "co": {"value": co, "unit": "ppm"},
                "ozone": {"value": ozone, "unit": "ppb"},
            },
            "health_advice": self._aqi_advice(aqi),
            "timestamp": now_iso(),
        }

    def _generate_city_suggestions(self, query: str, limit: int) -> List[Dict[str, Any]]:
        cities = [
            {"name": "London", "country": "UK", "region": "Europe"},
            {"name": "New York", "country": "USA", "region": "North America"},
            {"name": "Mumbai", "country": "India", "region": "Asia"},
            {"name": "Tokyo", "country": "Japan", "region": "Asia"},
            {"name": "Paris", "country": "France", "region": "Europe"},
            {"name": "Sydney", "country": "Australia", "region": "Oceania"},
            {"name": "Cairo", "country": "Egypt", "region": "Africa"},
            {"name": "Sao Paulo", "country": "Brazil", "region": "South America"},
            {"name": "Toronto", "country": "Canada", "region": "North America"},
            {"name": "Berlin", "country": "Germany", "region": "Europe"},
            {"name": "Singapore", "country": "Singapore", "region": "Asia"},
            {"name": "Dubai", "country": "UAE", "region": "Middle East"},
            {"name": "Moscow", "country": "Russia", "region": "Europe"},
            {"name": "Lagos", "country": "Nigeria", "region": "Africa"},
            {"name": "Shanghai", "country": "China", "region": "Asia"},
        ]
        filtered = [c for c in cities if query in c["name"].lower() or query in c["country"].lower()]
        if not filtered:
            filtered = cities
        return filtered[:limit]

    @staticmethod
    def _default_lat(city: str) -> float:
        hashed = sum(ord(c) * i for i, c in enumerate(city.lower(), 1)) % 18000
        return round((hashed / 100.0) - 90.0, 6)

    @staticmethod
    def _default_lon(city: str) -> float:
        hashed = sum(ord(c) * (i + 3) for i, c in enumerate(city.lower(), 1)) % 36000
        return round((hashed / 100.0) - 180.0, 6)

    @staticmethod
    def _wind_label(deg: int) -> str:
        directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        index = round(deg / 45) % 8
        return directions[index]

    @staticmethod
    def _weather_icon(condition: str) -> str:
        mapping = {
            "Clear": "01d", "Sunny": "01d", "Cloudy": "03d",
            "Partly Cloudy": "02d", "Rainy": "10d", "Thunderstorm": "11d",
            "Foggy": "50d", "Overcast": "04d", "Snow": "13d",
        }
        return mapping.get(condition, "01d")

    @staticmethod
    def _aqi_label(aqi: int) -> str:
        if aqi <= 50:
            return "Good"
        if aqi <= 100:
            return "Moderate"
        if aqi <= 150:
            return "Unhealthy for Sensitive Groups"
        if aqi <= 200:
            return "Unhealthy"
        if aqi <= 300:
            return "Very Unhealthy"
        return "Hazardous"

    @staticmethod
    def _aqi_advice(aqi: int) -> str:
        if aqi <= 50:
            return "Air quality is satisfactory."
        if aqi <= 100:
            return "Acceptable air quality; sensitive groups should limit prolonged outdoor exertion."
        if aqi <= 150:
            return "Sensitive groups should reduce prolonged outdoor exertion."
        if aqi <= 200:
            return "Everyone should reduce prolonged outdoor exertion."
        if aqi <= 300:
            return "Avoid all outdoor physical activities."
        return "Health alert: everyone should avoid any outdoor exertion."

    @staticmethod
    def _sunrise_time(city: str) -> str:
        minutes = 300 + (sum(ord(c) for c in city.lower()) % 90)
        hour = minutes // 60
        minute = minutes % 60
        return f"{hour:02d}:{minute:02d}"

    @staticmethod
    def _sunset_time(city: str) -> str:
        minutes = 1080 - (sum(ord(c) for c in city.lower()) % 120)
        hour = minutes // 60
        minute = minutes % 60
        return f"{hour:02d}:{minute:02d}"

    def invalidate_cache(self, pattern: Optional[str] = None) -> int:
        if pattern:
            removed = 0
            for cache in [self._cache, self._geocode_cache, self._air_quality_cache]:
                removed += cache.size()
                cache.clear()
            return removed
        self._cache.clear()
        self._geocode_cache.clear()
        self._air_quality_cache.clear()
        return 0


weather_service = WeatherService()
