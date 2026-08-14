#!/usr/bin/env python3

import csv
import json
import sys
import re


def normalize_field(name):
    name = name.strip().lstrip("\ufeff")
    name = re.sub(r"(?<!_)([a-z0-9])([A-Z])", r"\1_\2", name)
    name = name.lower()
    name = name.replace("%", "percent")
    name = re.sub(r"[^a-z0-9]+", "_", name)
    return name.strip("_")


def parse_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def get(record, *names):
    for name in names:
        value = record.get(name)
        if value not in (None, ""):
            return value
    return None


def derive_weather_condition(record):
    condition = get(record, "weather_condition")
    if condition:
        return condition
    severity = parse_float(get(record, "climate_severity_score"))
    if severity is None:
        return "Unknown"
    if severity >= 90:
        return "Extreme"
    if severity >= 70:
        return "Severe"
    if severity >= 40:
        return "Moderate"
    return "Mild"


def derive_flood_risk(rainfall):
    if rainfall is None:
        return 0

    if rainfall >= 110:
        return 2
    elif rainfall >= 60:
        return 1
    return 0


def derive_heatwave(temperature):
    if temperature is None:
        return 0

    return 1 if temperature >= 38 else 0


def build_payload(record):

    station_id = get(record, "station_id")
    weather_condition = derive_weather_condition(record)
    temperature = parse_float(get(record, "temperature_c"))
    humidity = parse_float(get(record, "humidity_percent"))
    rainfall = parse_float(get(record, "rainfall_mm"))
    wind_speed = parse_float(get(record, "wind_speed_kmh"))
    pressure = parse_float(get(record, "pressure_hpa"))

    if None in (
        temperature,
        humidity,
        rainfall,
        wind_speed,
        pressure,
    ):
        return None

    uv_index = parse_float(get(record, "uv_index"))
    visibility = parse_float(get(record, "visibility_km"))
    co2 = parse_float(get(record, "co2_ppm"))
    pm25 = parse_float(get(record, "pm2_5_ug_m3"))
    pm10 = parse_float(get(record, "pm10_ug_m3"))
    no2 = parse_float(get(record, "no2_ppb"))
    so2 = parse_float(get(record, "so2_ppb"))
    ozone = parse_float(get(record, "ozone_ppb"))
    soil_moisture = parse_float(get(record, "soil_moisture_percent"))
    soil_temperature = parse_float(get(record, "soil_temperature_c"))
    water_temperature = parse_float(get(record, "water_temperature_c"))
    water_ph = parse_float(get(record, "water_ph"))
    water_turbidity = parse_float(get(record, "water_turbidity_ntu"))
    noise = parse_float(get(record, "noise_level_db"))
    ndvi = parse_float(get(record, "ndvi_index"))
    cloud_cover = parse_float(get(record, "cloud_cover_pct"))
    tomorrow_temp = parse_float(get(record, "tomorrow_temp_c"))
    rain_tomorrow = parse_int(get(record, "rain_tomorrow"))
    temp_anomaly = parse_float(get(record, "temp_anomaly_c"))
    anomaly_detect = parse_int(get(record, "temp_anomaly_detect"))

    payload = {
        "station_id": station_id,
        "weather_condition": weather_condition,
        "temperature": temperature,
        "humidity": humidity,
        "rainfall": rainfall,
        "wind_speed": wind_speed,
        "pressure": pressure,

        "uv_index": uv_index,
        "visibility": visibility,

        "co2": co2,
        "pm25": pm25,
        "pm10": pm10,
        "no2": no2,
        "so2": so2,
        "ozone": ozone,

        "soil_moisture": soil_moisture,
        "soil_temperature": soil_temperature,
        "water_temperature": water_temperature,
        "water_ph": water_ph,
        "water_turbidity": water_turbidity,
        "noise": noise,

        "ndvi": ndvi,
        "cloud_cover": cloud_cover,

        "tomorrow_temp": tomorrow_temp,
        "rain_tomorrow": rain_tomorrow,

        "temp_anomaly": temp_anomaly,
        "anomaly_detect": anomaly_detect,

        "flood_risk": derive_flood_risk(rainfall),
        "heatwave": derive_heatwave(temperature),
    }

    return payload


def map_stream(input_stream, output_stream):
    reader = csv.reader(input_stream)

    header = next(reader, None)
    if header is None:
        return

    normalized_header = [
        normalize_field(column)
        for column in header
    ]

    for row in reader:
        if not row:
            continue

        record = {
            normalized_header[i]: row[i].strip()
            for i in range(min(len(normalized_header), len(row)))
        }

        payload = build_payload(record)
        if payload is None:
            continue

        group_key = payload.get("weather_condition", "Unknown")
        for key in [group_key, "ALL"]:
            output_stream.write(
                f"{key}\t{json.dumps(payload, separators=(',', ':'))}\n"
            )


def main():
    map_stream(sys.stdin, sys.stdout)


if __name__ == "__main__":
    main()
