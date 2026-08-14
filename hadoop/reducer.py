#!/usr/bin/env python3

import json
import sys


def initialize():

    return {
        "count": 0,

        "temperature_sum": 0.0,
        "humidity_sum": 0.0,
        "rainfall_sum": 0.0,
        "wind_speed_sum": 0.0,
        "pressure_sum": 0.0,

        "uv_sum": 0.0,
        "visibility_sum": 0.0,

        "co2_sum": 0.0,
        "pm25_sum": 0.0,
        "pm10_sum": 0.0,
        "no2_sum": 0.0,
        "so2_sum": 0.0,
        "ozone_sum": 0.0,

        "soil_moisture_sum": 0.0,
        "soil_temperature_sum": 0.0,

        "water_temperature_sum": 0.0,
        "water_ph_sum": 0.0,
        "water_turbidity_sum": 0.0,

        "noise_sum": 0.0,
        "ndvi_sum": 0.0,
        "cloud_cover_sum": 0.0,

        "tomorrow_temp_sum": 0.0,

        "rain_tomorrow_yes": 0,
        "rain_tomorrow_no": 0,

        "anomaly_detected": 0,
        "anomaly_not_detected": 0,

        "flood_risk": {
            "low": 0,
            "medium": 0,
            "high": 0,
        },

        "heatwave": {
            "yes": 0,
            "no": 0,
        },
    }


def add_number(agg, record, field, sum_field):

    value = record.get(field)

    if value is not None:
        try:
            agg[sum_field] += float(value)
        except (TypeError, ValueError):
            pass


def add_record(agg, record):

    agg["count"] += 1

    fields = [
        ("temperature", "temperature_sum"),
        ("humidity", "humidity_sum"),
        ("rainfall", "rainfall_sum"),
        ("wind_speed", "wind_speed_sum"),
        ("pressure", "pressure_sum"),

        ("uv_index", "uv_sum"),
        ("visibility", "visibility_sum"),

        ("co2", "co2_sum"),
        ("pm25", "pm25_sum"),
        ("pm10", "pm10_sum"),
        ("no2", "no2_sum"),
        ("so2", "so2_sum"),
        ("ozone", "ozone_sum"),

        ("soil_moisture", "soil_moisture_sum"),
        ("soil_temperature", "soil_temperature_sum"),

        ("water_temperature", "water_temperature_sum"),
        ("water_ph", "water_ph_sum"),
        ("water_turbidity", "water_turbidity_sum"),

        ("noise", "noise_sum"),
        ("ndvi", "ndvi_sum"),
        ("cloud_cover", "cloud_cover_sum"),

        ("tomorrow_temp", "tomorrow_temp_sum"),
    ]

    for field, sum_field in fields:
        add_number(agg, record, field, sum_field)

    rain_tomorrow = record.get("rain_tomorrow")

    if rain_tomorrow == 1:
        agg["rain_tomorrow_yes"] += 1
    else:
        agg["rain_tomorrow_no"] += 1

    anomaly = record.get("anomaly_detect")

    if anomaly == 1:
        agg["anomaly_detected"] += 1
    else:
        agg["anomaly_not_detected"] += 1

    flood = int(record.get("flood_risk", 0) or 0)

    if flood >= 2:
        agg["flood_risk"]["high"] += 1
    elif flood == 1:
        agg["flood_risk"]["medium"] += 1
    else:
        agg["flood_risk"]["low"] += 1

    heatwave = int(record.get("heatwave", 0) or 0)

    if heatwave == 1:
        agg["heatwave"]["yes"] += 1
    else:
        agg["heatwave"]["no"] += 1


def average(agg, field):

    count = agg["count"]

    if count == 0:
        return 0

    return round(agg[field] / count, 2)


def emit(station, agg, output_stream=None):

    count = agg["count"]
    if count == 0:
        return

    result = {
        "group": station,
        "count": count,
        "station_id": station,
        "record_count": count,
        "average_temperature": average(agg, "temperature_sum"),
        "total_rainfall": round(agg["rainfall_sum"], 2),
        "flood_risk_counts": agg["flood_risk"],
        "heatwave_counts": agg["heatwave"],
        "weather": {
            "average_temperature": average(
                agg, "temperature_sum"
            ),
            "average_humidity": average(
                agg, "humidity_sum"
            ),
            "total_rainfall": round(
                agg["rainfall_sum"], 2
            ),
            "average_wind_speed": average(
                agg, "wind_speed_sum"
            ),
            "average_pressure": average(
                agg, "pressure_sum"
            ),
            "average_uv_index": average(
                agg, "uv_sum"
            ),
            "average_visibility": average(
                agg, "visibility_sum"
            ),
        },
        "air_quality": {
            "average_co2": average(
                agg, "co2_sum"
            ),
            "average_pm25": average(
                agg, "pm25_sum"
            ),
            "average_pm10": average(
                agg, "pm10_sum"
            ),
            "average_no2": average(
                agg, "no2_sum"
            ),
            "average_so2": average(
                agg, "so2_sum"
            ),
            "average_ozone": average(
                agg, "ozone_sum"
            ),
        },
        "environment": {
            "average_soil_moisture": average(
                agg, "soil_moisture_sum"
            ),
            "average_soil_temperature": average(
                agg, "soil_temperature_sum"
            ),
            "average_water_temperature": average(
                agg, "water_temperature_sum"
            ),
            "average_water_ph": average(
                agg, "water_ph_sum"
            ),
            "average_water_turbidity": average(
                agg, "water_turbidity_sum"
            ),
            "average_noise": average(
                agg, "noise_sum"
            ),
            "average_ndvi": average(
                agg, "ndvi_sum"
            ),
            "average_cloud_cover": average(
                agg, "cloud_cover_sum"
            ),
        },
        "prediction": {
            "average_tomorrow_temperature": average(
                agg, "tomorrow_temp_sum"
            ),
            "rain_tomorrow": {
                "yes": agg["rain_tomorrow_yes"],
                "no": agg["rain_tomorrow_no"],
            },
            "temperature_anomaly": {
                "detected": agg["anomaly_detected"],
                "not_detected": agg["anomaly_not_detected"],
            },
        },
        "risk": {
            "flood": agg["flood_risk"],
            "heatwave": agg["heatwave"],
        },
    }

    line = json.dumps(result)
    if output_stream is not None:
        output_stream.write(f"{line}\n")
    else:
        print(line)


def _is_valid_record(record):
    if not isinstance(record, dict):
        return False
    required_fields = [
        "temperature",
        "humidity",
        "rainfall",
        "wind_speed",
        "pressure",
    ]
    return all(record.get(field) is not None for field in required_fields)


def reduce_stream(input_stream, output_stream):
    current_station = None
    aggregation = initialize()

    for line in input_stream:
        line = line.strip()
        if not line:
            continue
        try:
            station, payload_text = line.split("\t", 1)
            record = json.loads(payload_text)
        except (ValueError, json.JSONDecodeError):
            continue

        if not _is_valid_record(record):
            continue

        if current_station is not None and station != current_station:
            emit(current_station, aggregation, output_stream)
            aggregation = initialize()

        current_station = station
        add_record(aggregation, record)

    if current_station is not None:
        emit(current_station, aggregation, output_stream)


def main():
    reduce_stream(sys.stdin, sys.stdout)


if __name__ == "__main__":
    main()
