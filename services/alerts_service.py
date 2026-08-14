from __future__ import annotations

from typing import Any, Dict, List, Optional

from bson import ObjectId

from database import get_db
from utils.errors import NotFoundError, ValidationError
from utils.helpers import now_iso, serialize_document


ALERT_SEVERITIES = {"low", "moderate", "high", "critical"}
ALERT_TYPES = {"weather", "prediction", "system", "pollution", "flood", "heatwave", "air_quality"}
ALERT_STATUSES = {"active", "acknowledged", "resolved", "dismissed"}


class AlertsService:
    def __init__(self) -> None:
        self.db = get_db()

    def _normalize_alert_document(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        alert = serialize_document(doc)
        alert["body"] = alert.get("body") or alert.get("description") or ""
        alert["time"] = alert.get("time") or alert.get("created_at") or alert.get("updated_at") or ""
        return alert

    def _normalize_alert_items(self, docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [self._normalize_alert_document(doc) for doc in docs]

    def create(
        self,
        user_id: Optional[str],
        title: str,
        description: str,
        alert_type: str = "weather",
        severity: str = "moderate",
        city: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        title = (title or "").strip()
        description = (description or "").strip()
        alert_type = (alert_type or "weather").lower()
        severity = (severity or "moderate").lower()
        if not title:
            raise ValidationError("Title is required")
        if not description:
            raise ValidationError("Description is required")
        if alert_type not in ALERT_TYPES:
            raise ValidationError(f"Invalid alert type. Allowed: {sorted(ALERT_TYPES)}")
        if severity not in ALERT_SEVERITIES:
            raise ValidationError(f"Invalid severity. Allowed: {sorted(ALERT_SEVERITIES)}")
        doc = {
            "user_id": user_id,
            "title": title,
            "description": description,
            "type": alert_type,
            "severity": severity,
            "city": city.lower().strip() if city else None,
            "metadata": metadata or {},
            "status": "active",
            "acknowledged_by": None,
            "acknowledged_at": None,
            "resolved_at": None,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        result = self.db.alerts.insert_one(doc)
        doc["id"] = str(result.inserted_id)
        return self._normalize_alert_document(doc)

    def list(
        self,
        user_id: Optional[str] = None,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        alert_type: Optional[str] = None,
        city: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        query: Dict[str, Any] = {}
        if user_id:
            query["user_id"] = user_id
        if status:
            s = status.lower()
            if s in ALERT_STATUSES:
                query["status"] = s
        if severity and severity.lower() in ALERT_SEVERITIES:
            query["severity"] = severity.lower()
        if alert_type and alert_type.lower() in ALERT_TYPES:
            query["type"] = alert_type.lower()
        if city:
            query["city"] = city.lower().strip()
        skip = max(0, (page - 1) * page_size)
        cursor = self.db.alerts.find(query).skip(skip).limit(page_size).sort("created_at", -1)
        items = self._normalize_alert_items(serialize_document(list(cursor)))
        total = self.db.alerts.count_documents(query)
        summary = list(self.db.alerts.aggregate([
            {"$match": query} if query else {"$match": {}},
            {"$group": {"_id": {"status": "$status", "severity": "$severity"}, "count": {"$sum": 1}}},
        ]))
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "summary": [
                {"status": s["_id"].get("status"), "severity": s["_id"].get("severity"), "count": s["count"]}
                for s in summary
            ],
            "active_count": self.db.alerts.count_documents({**query, "status": "active"}),
        }

    def get(self, alert_id: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        query: Dict[str, Any] = {"_id": ObjectId(alert_id)}
        if user_id:
            query["user_id"] = user_id
        doc = self.db.alerts.find_one(query)
        if not doc:
            raise NotFoundError("Alert not found")
        return self._normalize_alert_document(doc)

    def update_status(self, alert_id: str, status: str, acknowledged_by: Optional[str] = None) -> Dict[str, Any]:
        status = (status or "").lower()
        if status not in ALERT_STATUSES:
            raise ValidationError(f"Invalid status. Allowed: {sorted(ALERT_STATUSES)}")
        doc = self.db.alerts.find_one({"_id": ObjectId(alert_id)})
        if not doc:
            raise NotFoundError("Alert not found")
        update: Dict[str, Any] = {"status": status, "updated_at": now_iso()}
        if status == "acknowledged":
            update["acknowledged_at"] = now_iso()
            update["acknowledged_by"] = acknowledged_by
        if status == "resolved":
            update["resolved_at"] = now_iso()
            if acknowledged_by:
                update["acknowledged_by"] = acknowledged_by
                update["acknowledged_at"] = update["acknowledged_at"] or now_iso()
        self.db.alerts.update_one({"_id": ObjectId(alert_id)}, {"$set": update})
        return {"message": f"Alert status updated to {status}"}

    def delete(self, alert_id: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        query: Dict[str, Any] = {"_id": ObjectId(alert_id)}
        if user_id:
            query["user_id"] = user_id
        result = self.db.alerts.delete_one(query)
        if result.deleted_count == 0:
            raise NotFoundError("Alert not found")
        return {"message": "Alert deleted"}

    def create_weather_alert(
        self,
        user_id: Optional[str],
        city: str,
        condition: str,
        severity: str,
        description: str,
    ) -> Dict[str, Any]:
        return self.create(
            user_id=user_id,
            title=f"Weather Alert: {condition} in {city}",
            description=description,
            alert_type="weather",
            severity=severity,
            city=city,
            metadata={"condition": condition},
        )

    def create_prediction_alert(
        self,
        user_id: Optional[str],
        model: str,
        city: Optional[str],
        severity: str,
        description: str,
    ) -> Dict[str, Any]:
        title = f"Prediction Alert ({model})"
        if city:
            title += f" for {city}"
        return self.create(
            user_id=user_id,
            title=title,
            description=description,
            alert_type="prediction",
            severity=severity,
            city=city,
            metadata={"model": model},
        )


alerts_service = AlertsService()
