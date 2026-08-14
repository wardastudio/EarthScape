from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import Config
from services.data_service import DataService
from utils.errors import AppError, ValidationError
from utils.helpers import sanitize_input


class HadoopService:
    def __init__(self) -> None:
        self.data_dir = Path(Config.DATA_DIR).resolve()
        self.mapper_path = Path(__file__).resolve().parent.parent / "hadoop" / "mapper.py"
        self.reducer_path = Path(__file__).resolve().parent.parent / "hadoop" / "reducer.py"
        self.data_service = DataService()

    def _default_mapreduce_jsonl_path(self) -> Path:
        return Path(__file__).resolve().parent.parent / "hadoop" / "mapreduce_result.jsonl"

    def _flatten_mapreduce_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        flattened: Dict[str, Any] = {
            "station_id": record.get("station_id"),
            "record_count": record.get("record_count"),
            "source": record.get("source"),
        }
        for section in ("weather", "air_quality", "environment", "prediction", "risk"):
            section_data = record.get(section)
            if isinstance(section_data, dict):
                for key, value in section_data.items():
                    flattened[f"{section}_{key}"] = value
        return flattened

    def _parse_jsonl(self, path: Path) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as f:
            for raw_line in f:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    record = json.loads(raw_line)
                    if isinstance(record, dict):
                        records.append(record)
                except json.JSONDecodeError:
                    continue
        return records

    def _write_flattened_csv(self, records: List[Dict[str, Any]], csv_path: Path) -> None:
        if not records:
            return
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        flattened_records = [self._flatten_mapreduce_record(record) for record in records]
        fieldnames = sorted({key for record in flattened_records for key in record.keys()})
        with csv_path.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            for record in flattened_records:
                writer.writerow({key: record.get(key, "") for key in fieldnames})

    def _store_mapreduce_records(self, records: List[Dict[str, Any]]) -> int:
        count = 0
        db = self.data_service.db
        for record in records:
            station_id = record.get("station_id")
            query = {"station_id": station_id} if station_id is not None else {"station_id": None, "record_count": record.get("record_count")}
            db.mapreduce_aggregates.update_one(query, {"$set": record}, upsert=True)
            count += 1
        return count

    def _validate_dataset(self, dataset_path: Optional[str] = None) -> Path:
        if dataset_path:
            dataset_path = sanitize_input(dataset_path)
            p = Path(dataset_path)
            if p.is_absolute():
                candidate = p.resolve()
            else:
                candidate = (self.data_dir / dataset_path).resolve()
                if not str(candidate).startswith(str(self.data_dir)):
                    raise ValidationError("Invalid dataset path")
        else:
            candidate = self.data_dir / "current_dataset.csv"
            if not candidate.exists():
                candidate = self.data_dir / "weather_ml.csv"
            if not candidate.exists():
                candidate = self.data_dir / "weather_raw.csv"
            if not candidate.exists():
                candidate = self.data_dir / "climate_dataset.csv"
        if not candidate.exists() or not candidate.is_file():
            raise ValidationError("Dataset file does not exist")
        if candidate.suffix.lower() != ".csv":
            raise ValidationError("Only CSV datasets are supported")
        return candidate

    def _find_hadoop_streaming_jar(self) -> Optional[Path]:
        explicit = os.getenv("HADOOP_STREAMING_JAR")
        if explicit:
            explicit_path = Path(explicit).expanduser().resolve()
            if explicit_path.exists():
                return explicit_path
        hadoop_home = os.getenv("HADOOP_HOME")
        if hadoop_home:
            candidate = Path(hadoop_home) / "share" / "hadoop" / "tools" / "lib"
            if candidate.exists():
                for file in candidate.glob("hadoop-streaming*.jar"):
                    if file.is_file():
                        return file.resolve()
        return None

    def _find_hadoop_binary(self) -> Optional[str]:
        explicit = os.getenv("HADOOP_HOME")
        if explicit:
            binary = Path(explicit) / "bin" / "hadoop"
            if binary.exists():
                return str(binary.resolve())
        return shutil.which("hadoop")

    def detect_hadoop(self) -> Dict[str, Any]:
        jar_path = self._find_hadoop_streaming_jar()
        binary = self._find_hadoop_binary()
        return {
            "hadoop_binary_found": bool(binary),
            "streaming_jar_found": bool(jar_path),
            "hadoop_available": bool(binary and jar_path),
            "hadoop_binary_path": binary,
            "streaming_jar_path": str(jar_path) if jar_path else None,
        }

    def run_local_fallback(self, dataset: Path) -> Dict[str, Any]:
        start = time.time()
        with dataset.open("r", encoding="utf-8", newline="") as infile:
            with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as mapped:
                subprocess.run([self._python_executable(), str(self.mapper_path)], stdin=infile, stdout=mapped, check=True)
                mapped.seek(0)
                with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as reduced:
                    subprocess.run([self._python_executable(), str(self.reducer_path)], stdin=mapped, stdout=reduced, check=True)
                    reduced.seek(0)
                    return {
                        "execution_mode": "local_fallback",
                        "duration_seconds": round(time.time() - start, 3),
                        "results": [json.loads(line) for line in reduced if line.strip()],
                    }

    def _python_executable(self) -> str:
        return shutil.which("python") or shutil.which("python3") or "python"

    def run_hadoop_streaming(self, dataset: Path) -> Dict[str, Any]:
        jar_path = self._find_hadoop_streaming_jar()
        hadoop_bin = self._find_hadoop_binary()
        if not jar_path or not hadoop_bin:
            raise AppError("Hadoop or streaming JAR unavailable", status_code=503)
        output_dir = Path(tempfile.mkdtemp(prefix="earthscape_hadoop_"))
        start = time.time()
        try:
            command: List[str] = [
                hadoop_bin,
                "jar",
                str(jar_path),
                "-files",
                str(self.mapper_path) + "," + str(self.reducer_path),
                "-mapper",
                f"{self._python_executable()} {self.mapper_path}",
                "-reducer",
                f"{self._python_executable()} {self.reducer_path}",
                "-input",
                str(dataset),
                "-output",
                str(output_dir),
            ]
            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            part_file = next(output_dir.glob("part-*"), None)
            if not part_file or not part_file.exists():
                raise AppError("Hadoop Streaming output not found", status_code=500)
            with part_file.open("r", encoding="utf-8") as f:
                results = [json.loads(line) for line in f if line.strip()]
            return {
                "execution_mode": "hadoop_streaming",
                "duration_seconds": round(time.time() - start, 3),
                "results": results,
                "output_path": str(output_dir),
            }
        except subprocess.CalledProcessError as exc:
            raise AppError(f"Hadoop Streaming failed: {exc.stderr or exc.stdout}", status_code=500)
        finally:
            if output_dir.exists() and not any(output_dir.iterdir()):
                output_dir.rmdir()

    def process_dataset(self, dataset_path: Optional[str] = None) -> Dict[str, Any]:
        dataset = self._validate_dataset(dataset_path)
        detection = self.detect_hadoop()
        if detection["hadoop_available"]:
            try:
                result = self.run_hadoop_streaming(dataset)
                result.update({"hadoop_available": True, "streaming_jar_found": detection["streaming_jar_found"], "hadoop_binary_found": detection["hadoop_binary_found"]})
                return {"status": "success", **result}
            except AppError as exc:
                if exc.status_code == 503:
                    pass
                else:
                    raise
        fallback = self.run_local_fallback(dataset)
        return {
            "status": "success",
            "execution_mode": fallback["execution_mode"],
            "duration_seconds": fallback["duration_seconds"],
            "results": fallback["results"],
            "hadoop_available": detection["hadoop_available"],
            "streaming_jar_found": detection["streaming_jar_found"],
            "hadoop_binary_found": detection["hadoop_binary_found"],
            "warnings": ["Hadoop unavailable; using local fallback"] if not detection["hadoop_available"] else [],
        }

    def import_mapreduce_results(self, jsonl_path: Optional[str] = None) -> Dict[str, Any]:
        path = Path(jsonl_path).resolve() if jsonl_path else self._default_mapreduce_jsonl_path()
        if not path.exists() or not path.is_file():
            raise ValidationError(f"MapReduce result file not found: {path}")

        records = self._parse_jsonl(path)
        if not records:
            raise ValidationError("No valid MapReduce records found in JSONL file")

        output_csv = self.data_dir / "mapreduce_aggregates.csv"
        self._write_flattened_csv(records, output_csv)
        imported_count = self._store_mapreduce_records(records)
        dataset_record = self.data_service.create_document(
            "datasets",
            {
                "name": "MapReduce Aggregated Station Summary",
                "source": str(output_csv),
                "status": "Approved",
                "format": "CSV",
                "records": imported_count,
                "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        )
        return {
            "status": "success",
            "records_imported": imported_count,
            "dataset_path": str(output_csv),
            "dataset": dataset_record,
            "collection": "mapreduce_aggregates",
        }

    def get_station_analytics(self) -> Dict[str, Any]:
        db = self.data_service.db
        records = list(db.mapreduce_aggregates.find({}))
        if not records:
            return {"stations": [], "count": 0}
        stations = []
        for record in records:
            stations.append({
                "station_id": record.get("station_id"),
                "record_count": record.get("record_count"),
                "weather": record.get("weather", {}),
                "air_quality": record.get("air_quality", {}),
                "environment": record.get("environment", {}),
                "prediction": record.get("prediction", {}),
            })
        return {"stations": stations, "count": len(stations)}

    def get_risk_analytics(self) -> Dict[str, Any]:
        db = self.data_service.db
        records = list(db.mapreduce_aggregates.find({}))
        if not records:
            return {"flood_risk_summary": {}, "heatwave_summary": {}, "total_records": 0, "total_stations": 0}
        flood_low = 0
        flood_medium = 0
        flood_high = 0
        heatwave_yes = 0
        heatwave_no = 0
        total_records = 0
        for record in records:
            risk = record.get("risk", {})
            flood = risk.get("flood", {})
            heatwave = risk.get("heatwave", {})
            flood_low += flood.get("low", 0)
            flood_medium += flood.get("medium", 0)
            flood_high += flood.get("high", 0)
            heatwave_yes += heatwave.get("yes", 0)
            heatwave_no += heatwave.get("no", 0)
            total_records += record.get("record_count", 0)
        return {
            "flood_risk_summary": {
                "low": flood_low,
                "medium": flood_medium,
                "high": flood_high,
            },
            "heatwave_summary": {
                "yes": heatwave_yes,
                "no": heatwave_no,
            },
            "total_records": total_records,
            "total_stations": len(records),
        }


hadoop_service = HadoopService()
