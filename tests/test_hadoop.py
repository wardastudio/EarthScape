from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from config import Config
from hadoop import mapper, reducer
from services.hadoop_service import hadoop_service


def test_mapper_valid_row_emits_group_and_all():
    csv_data = io.StringIO(
        "Temperature_C,Humidity_%,Rainfall_mm,WindSpeed_kmh,Pressure_hPa,AQI,CO2_ppm,IndustrialIndex,EnergyConsumption_MWh,RenewableEnergy_%,UV_Index,CarbonEmission,FloodRisk,Heatwave,ClimateSeverityScore,WeatherCondition\n"
        "30,55,12,20,1010,90,400,0.5,80,25,5,150,1,0,65.0,Moderate\n"
    )
    output = io.StringIO()
    mapper.map_stream(csv_data, output)
    lines = [line.strip() for line in output.getvalue().splitlines() if line.strip()]
    assert len(lines) == 2
    groups = {line.split("\t", 1)[0] for line in lines}
    assert groups == {"Moderate", "ALL"}


def test_mapper_skips_header_and_malformed_rows():
    csv_data = io.StringIO(
        "Temperature_C,Humidity_%,Rainfall_mm,WindSpeed_kmh,Pressure_hPa,AQI,CO2_ppm,IndustrialIndex,EnergyConsumption_MWh,RenewableEnergy_%,UV_Index,CarbonEmission,FloodRisk,Heatwave,ClimateSeverityScore,WeatherCondition\n"
        "bad,55,12,20,1010,90,400,0.5,80,25,5,150,1,0,65.0,Moderate\n"
        "30,55,12,20,1010,90,400,0.5,80,25,5,150,1,0,65.0,\n"
        "25,60,10,18,1008,85,390,0.4,75,30,4,145,0,1,62.0,Heatwave\n"
    )
    output = io.StringIO()
    mapper.map_stream(csv_data, output)
    lines = [line for line in output.getvalue().splitlines() if line.strip()]
    assert len(lines) == 4
    assert any(line.startswith("Moderate\t") for line in lines)
    assert any(line.startswith("ALL\t") for line in lines)


def test_reducer_aggregates_group_statistics():
    valid_payload = {
        "temperature": 30.0,
        "humidity": 55.0,
        "rainfall": 12.0,
        "wind_speed": 20.0,
        "pressure": 1010.0,
        "co2": 400.0,
        "flood_risk": 1,
        "heatwave": 0,
    }
    input_data = io.StringIO(
        f"Moderate\t{json.dumps(valid_payload)}\n"
        f"Moderate\t{json.dumps(valid_payload)}\n"
    )
    output = io.StringIO()
    reducer.reduce_stream(input_data, output)
    lines = [json.loads(line) for line in output.getvalue().splitlines() if line.strip()]
    assert len(lines) == 1
    summary = lines[0]
    assert summary["group"] == "Moderate"
    assert summary["count"] == 2
    assert summary["average_temperature"] == 30.0
    assert summary["total_rainfall"] == 24.0
    assert summary["flood_risk_counts"]["medium"] == 2
    assert summary["heatwave_counts"]["no"] == 2


def test_reducer_skips_invalid_json_and_missing_values():
    input_data = io.StringIO(
        "Moderate\tbadjson\n"
        "Moderate\t{}\n"
        "Moderate\t{\"temperature\": 20, \"humidity\": 50, \"rainfall\": 5, \"wind_speed\": 10, \"pressure\": 1010, \"co2\": 380, \"flood_risk\": 0, \"heatwave\": 1}\n"
    )
    output = io.StringIO()
    reducer.reduce_stream(input_data, output)
    lines = [json.loads(line) for line in output.getvalue().splitlines() if line.strip()]
    assert len(lines) == 1
    assert lines[0]["group"] == "Moderate"
    assert lines[0]["count"] == 1


def test_local_fallback_execution_uses_same_mapper_reducer(tmp_path):
    dataset = tmp_path / "weather_dataset.csv"
    dataset.write_text(
        "Station_ID,Temperature_C,Humidity_%,Rainfall_mm,WindSpeed_kmh,Pressure_hPa,AQI,CO2_ppm,IndustrialIndex,EnergyConsumption_MWh,RenewableEnergy_%,UV_Index,CarbonEmission,FloodRisk,Heatwave,ClimateSeverityScore,WeatherCondition\n"
        "STN-001,30.0,55.0,12.0,20.0,1010.0,90.0,400.0,0.5,80.0,25.0,5.0,150.0,1,0,65.0,Moderate\n"
        "STN-002,30.0,55.0,12.0,20.0,1010.0,90.0,400.0,0.5,80.0,25.0,5.0,150.0,1,0,65.0,Moderate\n"
    )
    result = hadoop_service.run_local_fallback(dataset)
    assert result["execution_mode"] == "local_fallback"
    assert isinstance(result["duration_seconds"], float)
    assert isinstance(result["results"], list)
    assert any(item["group"] == "ALL" for item in result["results"])


def test_hadoop_status_endpoint(client):
    response = client.get("/api/hadoop/status")
    assert response.status_code == 200
    payload = response.get_json()
    assert "hadoop_available" in payload
    assert "streaming_jar_found" in payload
    assert "hadoop_binary_found" in payload


def test_hadoop_process_endpoint_local_fallback(monkeypatch, client, tmp_path):
    monkeypatch.setattr(hadoop_service, "detect_hadoop", lambda: {
        "hadoop_binary_found": False,
        "streaming_jar_found": False,
        "hadoop_available": False,
        "hadoop_binary_path": None,
        "streaming_jar_path": None,
    })
    dataset = tmp_path / "weather_dataset.csv"
    dataset.write_text(
        "Station_ID,Temperature_C,Humidity_%,Rainfall_mm,WindSpeed_kmh,Pressure_hPa,AQI,CO2_ppm,IndustrialIndex,EnergyConsumption_MWh,RenewableEnergy_%,UV_Index,CarbonEmission,FloodRisk,Heatwave,ClimateSeverityScore,WeatherCondition\n"
        "STN-001,30.0,55.0,12.0,20.0,1010.0,90.0,400.0,0.5,80.0,25.0,5.0,150.0,1,0,65.0,Moderate\n"
        "STN-002,30.0,55.0,12.0,20.0,1010.0,90.0,400.0,0.5,80.0,25.0,5.0,150.0,1,0,65.0,Moderate\n"
    )
    response = client.post("/api/hadoop/process", json={"dataset_path": str(dataset)})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "success"
    assert payload["execution_mode"] == "local_fallback"
    assert payload["hadoop_available"] is False
    assert any(item["group"] == "ALL" for item in payload["results"])


def test_hadoop_process_invalid_path(client):
    response = client.post("/api/hadoop/process", json={"dataset_path": "../secret.csv"})
    assert response.status_code == 422
    payload = response.get_json()
    assert payload["error"] == "validation_error"


def test_import_mapreduce_results_service(tmp_path):
    import time
    import json
    unique_station = f"TEST-STN-{int(time.time())}"
    jsonl_file = tmp_path / "mapreduce_result.jsonl"
    record = {
        "station_id": unique_station,
        "record_count": 15,
        "weather": {"average_temperature": 25.0},
        "air_quality": {"average_co2": 420.0},
        "environment": {"average_soil_moisture": 15.0},
        "prediction": {
            "average_tomorrow_temperature": 27.5,
            "rain_tomorrow": {"yes": 4, "no": 11},
            "temperature_anomaly": {"detected": 2, "not_detected": 13},
        },
        "risk": {
            "flood": {"low": 10, "medium": 3, "high": 2},
            "heatwave": {"yes": 5, "no": 10},
        },
    }
    jsonl_file.write_text(json.dumps(record) + "\n")
    result = hadoop_service.import_mapreduce_results(str(jsonl_file))
    assert result["status"] == "success"
    assert result["records_imported"] == 1
    assert result["collection"] == "mapreduce_aggregates"
    assert "dataset" in result
    db = hadoop_service.data_service.db
    assert db.mapreduce_aggregates.count_documents({"station_id": unique_station}) == 1
    stored = list(db.mapreduce_aggregates.find({"station_id": unique_station}))
    assert len(stored) == 1
    assert stored[0]["station_id"] == unique_station


def test_hadoop_import_endpoint(client, tmp_path):
    jsonl_file = tmp_path / "mapreduce_result.jsonl"
    jsonl_file.write_text(
        "{\"station_id\": \"STN-002\", \"record_count\": 10, \"weather\": {\"average_temperature\": 23.0}, \"air_quality\": {\"average_co2\": 390.0}, \"environment\": {\"average_soil_moisture\": 18.0}, \"prediction\": {\"average_tomorrow_temperature\": 26.0, \"rain_tomorrow\": {\"yes\": 3, \"no\": 7}, \"temperature_anomaly\": {\"detected\": 1, \"not_detected\": 9}}, \"risk\": {\"flood\": {\"low\": 8, \"medium\": 1, \"high\": 1}, \"heatwave\": {\"yes\": 2, \"no\": 8}}}\n"
    )
    response = client.post("/api/hadoop/import", json={"jsonl_path": str(jsonl_file)})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "success"
    assert payload["records_imported"] == 1
    assert payload["collection"] == "mapreduce_aggregates"
