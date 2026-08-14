from __future__ import annotations

from typing import Any, Dict, List, Optional

from bson import ObjectId

from database import get_db
from utils.errors import NotFoundError, ValidationError
from utils.helpers import now_iso, serialize_document


NOTIFICATION_TYPES = {"info", "warning", "danger", "success", "weather_alert", "prediction_alert", "system"}
PRIORITY_LEVELS = {"low", "normal", "high", "critical"}


class NotificationService:
    def __init__(self) -> None:
        self.db = get_db()

    def create(
        self,
        user_id: str,
        title: str,
        message: str,
        notification_type: str = "info",
        priority: str = "normal",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        title = (title or "").strip()
        message = (message or "").strip()
        notification_type = (notification_type or "info").lower()
        priority = (priority or "normal").lower()
        if not title:
            raise ValidationError("Title is required")
        if not message:
            raise ValidationError("Message is required")
        if notification_type not in NOTIFICATION_TYPES:
            raise ValidationError(f"Invalid notification type. Allowed: {sorted(NOTIFICATION_TYPES)}")
        if priority not in PRIORITY_LEVELS:
            raise ValidationError(f"Invalid priority. Allowed: {sorted(PRIORITY_LEVELS)}")
        doc = {
            "user_id": user_id,
            "title": title,
            "message": message,
            "type": notification_type,
            "priority": priority,
            "metadata": metadata or {},
            "read": False,
            "read_at": None,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        result = self.db.notifications.insert_one(doc)
        doc["id"] = str(result.inserted_id)
        return serialize_document(doc)

    def create_weather_alert(
        self,
        user_id: str,
        city: str,
        alert_type: str,
        severity: str,
        description: str,
        forecast_timestamp: Optional[str] = None,
    ) -> Dict[str, Any]:
        title = f"Weather Alert: {alert_type} - {city}"
        message = f"{severity.upper()} - {description}"
        metadata = {"category": "weather", "city": city, "alert_type": alert_type, "severity": severity}
        if forecast_timestamp:
            metadata["forecast_timestamp"] = forecast_timestamp
        priority = "high" if severity.lower() in {"high", "extreme", "critical", "severe"} else "normal"
        return self.create(user_id, title, message, notification_type="weather_alert", priority=priority, metadata=metadata)

    def create_prediction_alert(
        self,
        user_id: str,
        model: str,
        city: Optional[str],
        prediction_summary: str,
        action_required: Optional[str] = None,
    ) -> Dict[str, Any]:
        title = f"Prediction Alert ({model})"
        if city:
            title += f" - {city}"
        message = prediction_summary + (f" Action: {action_required}" if action_required else "")
        metadata = {"category": "prediction", "model": model, "city": city, "action_required": action_required}
        return self.create(user_id, title, message, notification_type="prediction_alert", priority="normal", metadata=metadata)

    def list_for_user(
        self,
        user_id: str,
        only_unread: bool = False,
        notification_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        query: Dict[str, Any] = {"user_id": user_id}
        if only_unread:
            query["read"] = False
        if notification_type:
            query["type"] = notification_type.lower()
        skip = max(0, (page - 1) * page_size)
        cursor = self.db.notifications.find(query).skip(skip).limit(page_size).sort("created_at", -1)
        items = serialize_document(list(cursor))
        total = self.db.notifications.count_documents(query)
        unread_count = self.db.notifications.count_documents({"user_id": user_id, "read": False})
        return {
            "items": items,
            "total": total,
            "unread_count": unread_count,
            "page": page,
            "page_size": page_size,
        }

    def get(self, user_id: str, notification_id: str) -> Dict[str, Any]:
        doc = self.db.notifications.find_one({"_id": ObjectId(notification_id), "user_id": user_id})
        if not doc:
            raise NotFoundError("Notification not found")
        return serialize_document(doc)

    def mark_read(self, user_id: str, notification_id: str) -> Dict[str, Any]:
        result = self.db.notifications.update_one(
            {"_id": ObjectId(notification_id), "user_id": user_id},
            {"$set": {"read": True, "read_at": now_iso(), "updated_at": now_iso()}},
        )
        if result.matched_count == 0:
            raise NotFoundError("Notification not found")
        return {"message": "Marked as read"}

    def mark_all_read(self, user_id: str) -> Dict[str, Any]:
        result = self.db.notifications.update_many(
            {"user_id": user_id, "read": False},
            {"$set": {"read": True, "read_at": now_iso(), "updated_at": now_iso()}},
        )
        return {"message": f"Marked {result.modified_count} notifications as read", "count": result.modified_count}

    def delete(self, user_id: str, notification_id: str) -> Dict[str, Any]:
        result = self.db.notifications.delete_one({"_id": ObjectId(notification_id), "user_id": user_id})
        if result.deleted_count == 0:
            raise NotFoundError("Notification not found")
        return {"message": "Notification deleted"}

    def unread_count(self, user_id: str) -> Dict[str, Any]:
        count = self.db.notifications.count_documents({"user_id": user_id, "read": False})
        by_type = list(self.db.notifications.aggregate([
            {"$match": {"user_id": user_id, "read": False}},
            {"$group": {"_id": "$type", "count": {"$sum": 1}}},
        ]))
        breakdown = {item["_id"]: item["count"] for item in by_type}
        return {"count": count, "by_type": breakdown}


notification_service = NotificationService()
