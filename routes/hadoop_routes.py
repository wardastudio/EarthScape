from __future__ import annotations

from flask import Blueprint

from controllers import hadoop_controller as hadoop_ctrl

hadoop_bp = Blueprint("hadoop_api", __name__, url_prefix="/api/hadoop")

hadoop_bp.get("/status")(hadoop_ctrl.hadoop_status)
hadoop_bp.post("/process")(hadoop_ctrl.hadoop_process)
hadoop_bp.post("/import")(hadoop_ctrl.import_mapreduce_results)
hadoop_bp.get("/analytics/stations")(hadoop_ctrl.hadoop_station_analytics)
hadoop_bp.get("/analytics/risk")(hadoop_ctrl.hadoop_risk_analytics)
