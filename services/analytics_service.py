from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from database import get_db
from utils.helpers import now_iso, serialize_document


METRIC_COLUMNS = [
    ("Temperature", "temperature", "°C"),
    ("Humidity", "humidity", "%"),
    ("Rainfall", "rainfall", "mm"),
    ("Pressure", "pressure", "hPa"),
    ("Wind Speed", "wind_speed", "km/h"),
    ("AQI", "aqi", "index"),
    ("CO2", "co2", "ppm"),
]


class AnalyticsService:
    def __init__(self) -> None:
        self.db = get_db()

    def _load_dataset(self) -> Any:
        import pandas as pd
        from pathlib import Path
        from config import Config
        path = Config.DATA_DIR / "climate_dataset.csv"
        if not path.exists():
            return pd.DataFrame()
        try:
            return pd.read_csv(path)
        except Exception:
            return pd.DataFrame()

    def _sample_metrics_from_df(self, df: Any, key_map: Dict[str, str]) -> Dict[str, List[float]]:
        import pandas as pd
        series: Dict[str, List[float]] = {}
        for logical, col in key_map.items():
            if col in df.columns:
                s = pd.to_numeric(df[col], errors="coerce").dropna()
                series[logical] = s.tail(140).tolist()
            else:
                series[logical] = []
        return series

    def _colmap(self) -> Dict[str, str]:
        return {
            "temperature": "Temperature_C",
            "humidity": "Humidity_%",
            "rainfall": "Rainfall_mm",
            "pressure": "Pressure_hPa",
            "wind_speed": "WindSpeed_kmh",
            "aqi": "AQI",
            "co2": "CO2_ppm",
            "uv_index": "UV_Index",
            "carbon_emission": "CarbonEmission",
            "renewable_energy": "RenewableEnergy_%",
        }

    def temperature_trends(self, interval: str = "weekly") -> Dict[str, Any]:
        df = self._load_dataset()
        colmap = self._colmap()
        temps = self._sample_metrics_from_df(df, {"temperature": colmap["temperature"]})["temperature"]
        groups = self._group_metric(temps, interval)
        labels = [str(i + 1) for i in range(len(groups))]
        return {
            "metric": "Temperature",
            "unit": "°C",
            "interval": interval,
            "labels": labels,
            "values": [round(g["avg"], 2) for g in groups],
            "min_values": [round(g["min"], 2) for g in groups],
            "max_values": [round(g["max"], 2) for g in groups],
            "summary": self._summary(temps, "°C"),
        }

    def humidity_trends(self, interval: str = "weekly") -> Dict[str, Any]:
        df = self._load_dataset()
        values = self._sample_metrics_from_df(df, {"humidity": self._colmap()["humidity"]})["humidity"]
        groups = self._group_metric(values, interval)
        return {
            "metric": "Humidity",
            "unit": "%",
            "interval": interval,
            "labels": [str(i + 1) for i in range(len(groups))],
            "values": [round(g["avg"], 2) for g in groups],
            "summary": self._summary(values, "%"),
        }

    def rainfall_trends(self, interval: str = "weekly") -> Dict[str, Any]:
        df = self._load_dataset()
        values = self._sample_metrics_from_df(df, {"rainfall": self._colmap()["rainfall"]})["rainfall"]
        groups = self._group_metric(values, interval)
        return {
            "metric": "Rainfall",
            "unit": "mm",
            "interval": interval,
            "labels": [str(i + 1) for i in range(len(groups))],
            "values": [round(g["sum"], 2) for g in groups],
            "summary": self._summary(values, "mm"),
        }

    def pressure_trends(self, interval: str = "weekly") -> Dict[str, Any]:
        df = self._load_dataset()
        values = self._sample_metrics_from_df(df, {"pressure": self._colmap()["pressure"]})["pressure"]
        groups = self._group_metric(values, interval)
        return {
            "metric": "Pressure",
            "unit": "hPa",
            "interval": interval,
            "labels": [str(i + 1) for i in range(len(groups))],
            "values": [round(g["avg"], 2) for g in groups],
            "summary": self._summary(values, "hPa"),
        }

    def wind_trends(self, interval: str = "weekly") -> Dict[str, Any]:
        df = self._load_dataset()
        values = self._sample_metrics_from_df(df, {"wind_speed": self._colmap()["wind_speed"]})["wind_speed"]
        groups = self._group_metric(values, interval)
        return {
            "metric": "Wind Speed",
            "unit": "km/h",
            "interval": interval,
            "labels": [str(i + 1) for i in range(len(groups))],
            "values": [round(g["avg"], 2) for g in groups],
            "summary": self._summary(values, "km/h"),
        }

    def all_trends(self, interval: str = "weekly") -> Dict[str, Any]:
        return {
            "interval": interval,
            "temperature": self.temperature_trends(interval),
            "humidity": self.humidity_trends(interval),
            "rainfall": self.rainfall_trends(interval),
            "pressure": self.pressure_trends(interval),
            "wind": self.wind_trends(interval),
        }

    def monthly_statistics(self, year: Optional[int] = None) -> Dict[str, Any]:
        df = self._load_dataset()
        colmap = self._colmap()
        monthly = defaultdict(lambda: defaultdict(list))
        if df.empty:
            n = 12
            return {
                "year": year or datetime.now().year,
                "months": [f"{i:02d}" for i in range(1, n + 1)],
                "temperature": [0.0] * n,
                "humidity": [0.0] * n,
                "rainfall": [0.0] * n,
                "aqi": [0.0] * n,
                "carbon_emission": [0.0] * n,
            }
        series = self._sample_metrics_from_df(df, colmap)
        n_samples = len(series.get("temperature") or [])
        per = max(1, n_samples // 12)
        result = defaultdict(list)
        for metric_name, values in series.items():
            buckets = [values[i:i + per] for i in range(0, len(values), per)]
            while len(buckets) < 12:
                buckets.append([])
            for b in buckets[:12]:
                if metric_name == "rainfall":
                    agg = round(sum(b), 2) if b else 0.0
                else:
                    agg = round(sum(b) / len(b), 2) if b else 0.0
                result[metric_name].append(agg)
        months = [(datetime.now().replace(day=1) - timedelta(days=30 * (11 - i))).strftime("%b") for i in range(12)]
        return {
            "year": year or datetime.now().year,
            "months": months,
            "temperature": result.get("temperature", []),
            "humidity": result.get("humidity", []),
            "rainfall": result.get("rainfall", []),
            "pressure": result.get("pressure", []),
            "wind_speed": result.get("wind_speed", []),
            "aqi": result.get("aqi", []),
            "co2": result.get("co2", []),
            "carbon_emission": result.get("carbon_emission", []),
        }

    def historical_analysis(self, start_period: Optional[int] = None, end_period: Optional[int] = None) -> Dict[str, Any]:
        df = self._load_dataset()
        colmap = self._colmap()
        series = self._sample_metrics_from_df(df, colmap)
        if start_period is None:
            start_period = 0
        if end_period is None:
            end_period = max(len(v) for v in series.values()) if series else 0
        sliced: Dict[str, List[float]] = {k: v[start_period:end_period] for k, v in series.items()}
        analysis: Dict[str, Any] = {"start_index": start_period, "end_index": end_period, "metrics": {}}
        for metric, values in sliced.items():
            if values:
                analysis["metrics"][metric] = self._summary(values, self._unit_for(metric))
            else:
                analysis["metrics"][metric] = {"count": 0}
        df_stored = list(self.db.weather_data.find({}).sort("timestamp", -1).limit(200))
        analysis["live_records_count"] = len(df_stored)
        analysis["historical_dataset_size"] = max(len(v) for v in series.values()) if series else 0
        return analysis

    def prediction_accuracy(self, model: Optional[str] = None) -> Dict[str, Any]:
        from services.ml_service_v2 import ml_service
        return ml_service.get_prediction_accuracy(model=model)

    def dashboard_overview(self) -> Dict[str, Any]:
        df = self._load_dataset()
        colmap = self._colmap()
        series = self._sample_metrics_from_df(df, colmap)
        summary: Dict[str, Any] = {
            "total_records": max(len(v) for v in series.values()) if series else 0,
            "averages": {},
            "totals": {},
            "weather_records": self.db.weather_data.count_documents({}),
            "prediction_count": self.db.prediction_history.count_documents({}),
            "user_count": self.db.users.count_documents({}),
            "alert_count": self.db.alerts.count_documents({}),
        }
        for metric, values in series.items():
            if values:
                summary["averages"][metric] = round(sum(values) / len(values), 2)
                if metric == "rainfall":
                    summary["totals"][metric] = round(sum(values), 2)
        from services.ml_service_v2 import ml_service
        summary["prediction_accuracy"] = ml_service.get_prediction_accuracy()
        summary["last_updated"] = now_iso()
        return summary

    def weather_distribution(self) -> Dict[str, Any]:
        df = self._load_dataset()
        if df.empty or "WeatherCondition" not in df.columns:
            return {"labels": [], "values": []}
        counts = df["WeatherCondition"].value_counts()
        return {"labels": counts.index.tolist(), "values": counts.values.tolist()}

    def carbon_vs_temperature(self, samples: int = 100) -> Dict[str, Any]:
        df = self._load_dataset()
        colmap = self._colmap()
        series = self._sample_metrics_from_df(df, {"temperature": colmap["temperature"], "carbon_emission": colmap["carbon_emission"]})
        temps = series["temperature"][:samples]
        carbons = series["carbon_emission"][:samples]
        return {"temperature": temps, "carbon_emission": carbons, "count": min(len(temps), len(carbons))}

    def pollution_ranking(self, limit: int = 10) -> Dict[str, Any]:
        aqi = list(self.db.air_quality.aggregate([
            {"$group": {"_id": "$city", "avg_aqi": {"$avg": "$aqi"}, "count": {"$sum": 1}}},
            {"$sort": {"avg_aqi": -1}},
            {"$limit": limit},
        ]))
        return {"top_polluted": [{"city": item["_id"] or "Unknown", "avg_aqi": round(float(item.get("avg_aqi", 0)), 2), "samples": int(item.get("count", 0))} for item in aqi]}

    def get_unified_analytics(self) -> Dict[str, Any]:
        from services.hadoop_service import hadoop_service
        from services.ml_service_v2 import ml_service
        dashboard = self.dashboard_overview()
        station_data = hadoop_service.get_station_analytics()
        risk_data = hadoop_service.get_risk_analytics()
        stations = station_data.get("stations", [])

        hadoop_averages: Dict[str, float] = {}
        climate_severity_scores: List[float] = []
        air_quality_samples: Dict[str, List[float]] = {
            "aqi": [],
            "co2": [],
        }
        hadoop_status = {
            "aggregates_available": len(stations) > 0,
            "station_count": len(stations),
            "total_records_processed": sum(int(s.get("record_count", 0) or 0) for s in stations),
        }

        if stations:
            weather_metrics = {
                "temperature": [],
                "humidity": [],
                "rainfall": [],
                "wind_speed": [],
            }
            env_metrics: Dict[str, List[float]] = {
                "soil_moisture": [],
            }
            for s in stations:
                weather = s.get("weather") or {}
                for metric, bucket in weather_metrics.items():
                    val = weather.get(f"average_{metric}")
                    if val is None and metric == "wind_speed":
                        val = weather.get("average_wind")
                    if isinstance(val, (int, float)):
                        bucket.append(float(val))
                air = s.get("air_quality") or {}
                for key in ("average_aqi", "avg_aqi"):
                    v = air.get(key)
                    if isinstance(v, (int, float)):
                        air_quality_samples["aqi"].append(float(v))
                        break
                for key in ("average_co2", "avg_co2"):
                    v = air.get(key)
                    if isinstance(v, (int, float)):
                        air_quality_samples["co2"].append(float(v))
                        break
                env = s.get("environment") or {}
                sm = env.get("average_soil_moisture")
                if isinstance(sm, (int, float)):
                    env_metrics["soil_moisture"].append(float(sm))
                prediction = s.get("prediction") or {}
                sev = prediction.get("average_climate_severity")
                if sev is None:
                    sev = prediction.get("climate_severity_score") or prediction.get("severity_score")
                if isinstance(sev, (int, float)):
                    climate_severity_scores.append(float(sev))

            def _mean(vals: List[float]) -> float:
                return round(sum(vals) / len(vals), 2) if vals else 0.0

            hadoop_averages = {
                "temperature": _mean(weather_metrics["temperature"]),
                "humidity": _mean(weather_metrics["humidity"]),
                "rainfall": _mean(weather_metrics["rainfall"]),
                "wind_speed": _mean(weather_metrics["wind_speed"]),
                "soil_moisture": _mean(env_metrics["soil_moisture"]),
            }

        air_quality: Dict[str, Any] = {
            "average_aqi": round(sum(air_quality_samples["aqi"]) / len(air_quality_samples["aqi"]), 2) if air_quality_samples["aqi"] else dashboard.get("averages", {}).get("aqi", 0.0),
            "average_co2": round(sum(air_quality_samples["co2"]) / len(air_quality_samples["co2"]), 2) if air_quality_samples["co2"] else dashboard.get("averages", {}).get("co2", 0.0),
            "aqi_samples": len(air_quality_samples["aqi"]),
            "co2_samples": len(air_quality_samples["co2"]),
        }

        if air_quality["average_aqi"]:
            aqi_val = air_quality["average_aqi"]
            if aqi_val <= 50:
                air_quality["category"] = "Good"
            elif aqi_val <= 100:
                air_quality["category"] = "Moderate"
            elif aqi_val <= 150:
                air_quality["category"] = "Unhealthy for Sensitive Groups"
            elif aqi_val <= 200:
                air_quality["category"] = "Unhealthy"
            elif aqi_val <= 300:
                air_quality["category"] = "Very Unhealthy"
            else:
                air_quality["category"] = "Hazardous"
        else:
            air_quality["category"] = "Insufficient Data"

        severity_avg = round(sum(climate_severity_scores) / len(climate_severity_scores), 2) if climate_severity_scores else 0.0
        if severity_avg == 0.0:
            severity_avg = dashboard.get("averages", {}).get("carbon_emission", 0.0)
        if severity_avg >= 80:
            severity_level = "Critical"
        elif severity_avg >= 60:
            severity_level = "Severe"
        elif severity_avg >= 40:
            severity_level = "Moderate"
        elif severity_avg >= 20:
            severity_level = "Mild"
        elif severity_avg > 0:
            severity_level = "Minimal"
        else:
            severity_level = "Unknown"
        climate_severity = {
            "average_score": severity_avg,
            "level": severity_level,
            "station_samples": len(climate_severity_scores),
        }

        flood_summary = risk_data.get("flood_risk_summary", {})
        flood_total = int(flood_summary.get("low", 0)) + int(flood_summary.get("medium", 0)) + int(flood_summary.get("high", 0))
        if flood_total > 0:
            flood_risk_pct = {
                "low": round(int(flood_summary.get("low", 0)) * 100 / flood_total, 2),
                "medium": round(int(flood_summary.get("medium", 0)) * 100 / flood_total, 2),
                "high": round(int(flood_summary.get("high", 0)) * 100 / flood_total, 2),
            }
        else:
            flood_risk_pct = {"low": 0.0, "medium": 0.0, "high": 0.0}
        heatwave_summary = risk_data.get("heatwave_summary", {})
        heatwave_total = int(heatwave_summary.get("yes", 0)) + int(heatwave_summary.get("no", 0))
        if heatwave_total > 0:
            heatwave_risk_pct = {
                "yes": round(int(heatwave_summary.get("yes", 0)) * 100 / heatwave_total, 2),
                "no": round(int(heatwave_summary.get("no", 0)) * 100 / heatwave_total, 2),
            }
        else:
            heatwave_risk_pct = {"yes": 0.0, "no": 0.0}

        try:
            model_list = ml_service.list_models()
        except Exception:
            model_list = []
        ml_models_available = len(model_list)

        dataset_avg = dashboard.get("averages", {})
        unified_averages = {
            "temperature": hadoop_averages.get("temperature") or dataset_avg.get("temperature", 0.0),
            "humidity": hadoop_averages.get("humidity") or dataset_avg.get("humidity", 0.0),
            "rainfall": hadoop_averages.get("rainfall") or dataset_avg.get("rainfall", 0.0),
            "wind_speed": hadoop_averages.get("wind_speed") or dataset_avg.get("wind_speed", 0.0),
            "aqi": air_quality["average_aqi"],
            "co2": air_quality["average_co2"],
            "soil_moisture": hadoop_averages.get("soil_moisture", 0.0),
        }

        return {
            "overview": {
                "total_records": dashboard.get("total_records", 0),
                "weather_records": dashboard.get("weather_records", 0),
                "prediction_count": dashboard.get("prediction_count", 0),
                "user_count": dashboard.get("user_count", 0),
                "alert_count": dashboard.get("alert_count", 0),
                "station_count": station_data.get("count", 0),
                "ml_models_available": ml_models_available,
            },
            "averages": unified_averages,
            "hadoop_averages": hadoop_averages,
            "dataset_averages": dashboard.get("averages", {}),
            "totals": dashboard.get("totals", {}),
            "air_quality": air_quality,
            "climate_severity": climate_severity,
            "mapreduce_aggregates": {
                "status": hadoop_status,
                "station_count": station_data.get("count", 0),
                "stations": stations[:50],
            },
            "risk_summary": {
                "flood_risk": {
                    "counts": flood_summary,
                    "percentages": flood_risk_pct,
                    "total_assessments": flood_total,
                    "dominant_risk": max(flood_summary, key=lambda k: int(flood_summary.get(k, 0) or 0)) if flood_total else "unknown",
                },
                "heatwave": {
                    "counts": heatwave_summary,
                    "percentages": heatwave_risk_pct,
                    "total_assessments": heatwave_total,
                },
                "total_records": risk_data.get("total_records", 0),
                "total_stations": risk_data.get("total_stations", 0),
            },
            "ml_predictions": dashboard.get("prediction_accuracy", {}),
            "ml_models": [
                {
                    "name": m.get("name"),
                    "type": m.get("type"),
                    "task": m.get("task"),
                    "description": m.get("description"),
                    "loaded": m.get("loaded", False),
                }
                for m in model_list
            ],
            "last_updated": dashboard.get("last_updated", now_iso()),
        }

    @staticmethod
    def _group_metric(values: List[float], interval: str) -> List[Dict[str, float]]:
        if not values:
            return []
        group_sizes = {"daily": 1, "weekly": 7, "biweekly": 14, "monthly": 30}
        per = group_sizes.get(interval, 10)
        n = len(values)
        num_groups = max(1, math.ceil(n / per))
        groups: List[Dict[str, float]] = []
        for i in range(num_groups):
            start = i * per
            end = min(start + per, n)
            bucket = values[start:end]
            if bucket:
                groups.append({"avg": sum(bucket) / len(bucket), "min": min(bucket), "max": max(bucket), "sum": sum(bucket)})
            else:
                groups.append({"avg": 0.0, "min": 0.0, "max": 0.0, "sum": 0.0})
        return groups

    @staticmethod
    def _summary(values: List[float], unit: str) -> Dict[str, Any]:
        if not values:
            return {"count": 0, "unit": unit}
        return {
            "count": len(values),
            "unit": unit,
            "mean": round(sum(values) / len(values), 2),
            "min": round(min(values), 2),
            "max": round(max(values), 2),
            "range": round(max(values) - min(values), 2),
        }

    @staticmethod
    def _unit_for(metric: str) -> str:
        mapping = {
            "temperature": "°C", "humidity": "%", "rainfall": "mm",
            "pressure": "hPa", "wind_speed": "km/h", "aqi": "index",
            "co2": "ppm", "uv_index": "index", "carbon_emission": "kt",
            "renewable_energy": "%", "flood_risk": "level", "heatwave": "bool",
        }
        return mapping.get(metric, "")


analytics_service = AnalyticsService()
