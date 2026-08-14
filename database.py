from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import bcrypt
from bson import ObjectId
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.collection import Collection
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from config import Config

logger = logging.getLogger(__name__)

client: Optional[MongoClient] = None


class DummyCursor:
    def __init__(self, docs: List[Dict[str, Any]]) -> None:
        self._docs = docs

    def sort(self, key: str, direction: int = 1) -> "DummyCursor":
        self._docs.sort(key=lambda doc: doc.get(key), reverse=(direction < 0))
        return self

    def skip(self, skip: int) -> "DummyCursor":
        if skip and skip > 0:
            self._docs = self._docs[skip:]
        return self

    def limit(self, limit: int) -> "DummyCursor":
        self._docs = self._docs[: limit or len(self._docs)]
        return self

    def __iter__(self):
        return iter(self._docs)

    def __len__(self) -> int:
        return len(self._docs)


class DummyCollection:
    def __init__(self) -> None:
        self._documents: List[Dict[str, Any]] = []

    def _match_value(self, value: Any, condition: Any) -> bool:
        if isinstance(condition, dict):
            if "$regex" in condition:
                pattern = condition["$regex"]
                options = condition.get("$options", "")
                flags = re.IGNORECASE if "i" in options else 0
                if not isinstance(value, str):
                    return False
                return re.search(pattern, value, flags) is not None
            if "$eq" in condition:
                return value == condition["$eq"]
            if "$in" in condition:
                return value in condition["$in"]
            if "$ne" in condition:
                return value != condition["$ne"]
            return False
        return value == condition

    def _matches(self, doc: Dict[str, Any], query: Optional[Dict[str, Any]]) -> bool:
        if not query:
            return True
        for key, condition in query.items():
            if key == "$or" and isinstance(condition, list):
                if not any(self._matches(doc, subquery) for subquery in condition):
                    return False
                continue
            value = doc.get(key)
            if not self._match_value(value, condition):
                return False
        return True

    def find(self, query: Optional[Dict[str, Any]] = None) -> DummyCursor:
        query = query or {}
        matches = [doc.copy() for doc in self._documents if self._matches(doc, query)]
        return DummyCursor(matches)

    def find_one(self, query: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        query = query or {}
        for doc in self._documents:
            if self._matches(doc, query):
                return doc.copy()
        return None

    def count_documents(self, query: Optional[Dict[str, Any]] = None) -> int:
        query = query or {}
        return sum(1 for doc in self._documents if self._matches(doc, query))

    def insert_one(self, document: Dict[str, Any]) -> Any:
        doc = document.copy()
        if "_id" not in doc:
            doc["_id"] = ObjectId()
        self._documents.append(doc)

        class InsertResult:
            inserted_id = doc["_id"]

        return InsertResult()

    def delete_one(self, query: Dict[str, Any]) -> Any:
        for index, doc in enumerate(self._documents):
            if self._matches(doc, query):
                del self._documents[index]

                class DeleteResult:
                    deleted_count = 1

                return DeleteResult()
        class DeleteResult:
            deleted_count = 0

        return DeleteResult()

    def update_one(self, query: Dict[str, Any], update: Dict[str, Any], upsert: bool = False) -> Any:
        matched_doc = None
        for doc in self._documents:
            if self._matches(doc, query):
                matched_doc = doc
                break

        if matched_doc is None:
            if upsert:
                new_doc: Dict[str, Any] = {"_id": ObjectId()}
                for key, value in query.items():
                    if not key.startswith("$"):
                        new_doc[key] = value
                if "$setOnInsert" in update:
                    new_doc.update(update["$setOnInsert"])
                self._documents.append(new_doc)

                class UpsertResult:
                    matched_count = 0
                    modified_count = 0
                    upserted_id = new_doc["_id"]

                return UpsertResult()

            class UpdateResult:
                matched_count = 0
                modified_count = 0

            return UpdateResult()

        modified = False
        for op, changes in update.items():
            if op == "$set":
                for key, value in changes.items():
                    if matched_doc.get(key) != value:
                        modified = True
                    matched_doc[key] = value
            elif op == "$setOnInsert":
                continue
            elif op == "$addToSet":
                for key, value in changes.items():
                    existing = matched_doc.get(key, [])
                    if not isinstance(existing, list):
                        existing = [existing]
                    if value not in existing:
                        existing.append(value)
                        modified = True
                    matched_doc[key] = existing
            elif op == "$pull":
                for key, value in changes.items():
                    current = matched_doc.get(key, [])
                    if isinstance(current, list):
                        if isinstance(value, dict) and "$in" in value:
                            filtered = [item for item in current if item not in value["$in"]]
                        else:
                            filtered = [item for item in current if item != value]
                        if filtered != current:
                            modified = True
                        matched_doc[key] = filtered
        class UpdateResult:
            matched_count = 1
            modified_count = 1 if modified else 0

        return UpdateResult()

    def aggregate(self, pipeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        docs = [doc.copy() for doc in self._documents]
        for stage in pipeline:
            if "$group" in stage:
                group_spec = stage["$group"]
                grouped: Dict[Any, Dict[str, Any]] = {}
                for doc in docs:
                    key_value = doc.get(group_spec["_id"].lstrip("$"), None)
                    group = grouped.setdefault(key_value, {"_id": key_value})
                    for field, operation in group_spec.items():
                        if field == "_id":
                            continue
                        if "$avg" in operation:
                            field_name = operation["$avg"].lstrip("$")
                            group[field] = group.get(field, 0.0) + float(doc.get(field_name, 0.0))
                            group.setdefault("__count", 0)
                            group["__count"] += 1
                        elif "$sum" in operation:
                            field_name = operation["$sum"].lstrip("$")
                            group[field] = group.get(field, 0) + int(doc.get(field_name, 0))
                result: List[Dict[str, Any]] = []
                for group in grouped.values():
                    if "__count" in group:
                        count = group.pop("__count")
                        if "avg_aqi" in group:
                            group["avg_aqi"] = group["avg_aqi"] / count if count else 0.0
                    result.append(group)
                docs = result
            elif "$sort" in stage:
                sort_spec = stage["$sort"]
                for key, direction in sort_spec.items():
                    docs.sort(key=lambda doc: doc.get(key), reverse=(direction < 0))
            elif "$limit" in stage:
                docs = docs[: stage["$limit"]]
        return docs

    def create_index(self, index_spec: Any, **kwargs: Any) -> None:
        return None


class DummyDatabase:
    def __init__(self, name: str) -> None:
        self._name = name
        self._collections: Dict[str, DummyCollection] = {}

    def __getitem__(self, name: str) -> DummyCollection:
        if name not in self._collections:
            self._collections[name] = DummyCollection()
        return self._collections[name]

    def __getattr__(self, name: str) -> DummyCollection:
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]

    def command(self, operation: str) -> Dict[str, Any]:
        if operation == "ping":
            return {"ok": 1}
        return {"ok": 1}


class DummyMongoClient:
    def __init__(self) -> None:
        self._databases: Dict[str, DummyDatabase] = {}

    def __getitem__(self, name: str) -> DummyDatabase:
        if name not in self._databases:
            self._databases[name] = DummyDatabase(name)
        return self._databases[name]

    @property
    def admin(self) -> "DummyAdmin":
        return DummyAdmin()


class DummyAdmin:
    def command(self, operation: str) -> Dict[str, Any]:
        if operation == "ping":
            return {"ok": 1}
        return {"ok": 1}


def get_db():
    global client
    if client is None:
        try:
            candidate = MongoClient(
                Config.MONGO_URI,
                serverSelectionTimeoutMS=2000,
                connectTimeoutMS=2000,
                socketTimeoutMS=2000,
            )
            candidate.admin.command("ping")
            client = candidate
        except (ConnectionFailure, ServerSelectionTimeoutError, Exception) as exc:
            logger.warning("MongoDB connection failed: %s", exc)
            logger.warning("Falling back to in-memory database emulation.")
            client = DummyMongoClient()
    return client[Config.MONGO_DB_NAME]


def _hash_pw(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


COLLECTION_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "users": {
        "indexes": [
            [("email", ASCENDING)],
            [("role", ASCENDING)],
            [("created_at", DESCENDING)],
        ],
        "unique_indexes": [
            [("email", ASCENDING)],
        ],
    },
    "admins": {
        "indexes": [
            [("email", ASCENDING)],
            [("created_at", DESCENDING)],
        ],
        "unique_indexes": [
            [("email", ASCENDING)],
        ],
    },
    "prediction_history": {
        "indexes": [
            [("user_id", ASCENDING)],
            [("model", ASCENDING)],
            [("city", ASCENDING)],
            [("timestamp", DESCENDING)],
        ],
    },
    "alerts": {
        "indexes": [
            [("user_id", ASCENDING)],
            [("city", ASCENDING)],
            [("severity", ASCENDING)],
            [("created_at", DESCENDING)],
        ],
    },
    "saved_cities": {
        "indexes": [
            [("user_id", ASCENDING)],
            [("city", ASCENDING)],
            [("created_at", DESCENDING)],
        ],
        "unique_indexes": [
            [("user_id", ASCENDING), ("city", ASCENDING)],
        ],
    },
    "notifications": {
        "indexes": [
            [("user_id", ASCENDING)],
            [("read", ASCENDING)],
            [("type", ASCENDING)],
            [("created_at", DESCENDING)],
        ],
    },
    "audit_logs": {
        "indexes": [
            [("user_id", ASCENDING)],
            [("user_email", ASCENDING)],
            [("action", ASCENDING)],
            [("created_at", DESCENDING)],
        ],
    },
    "feedback": {
        "indexes": [
            [("user_id", ASCENDING)],
            [("created_at", DESCENDING)],
        ],
    },
    "cities": {
        "indexes": [
            [("name", ASCENDING)],
            [("country", ASCENDING)],
            [("region", ASCENDING)],
        ],
    },
    "weather_data": {
        "indexes": [
            [("city", ASCENDING)],
            [("timestamp", DESCENDING)],
        ],
    },
    "air_quality": {
        "indexes": [
            [("city", ASCENDING)],
            [("timestamp", DESCENDING)],
        ],
    },
    "carbon_predictions": {
        "indexes": [
            [("city", ASCENDING)],
            [("date", DESCENDING)],
        ],
    },
    "emission_reports": {
        "indexes": [
            [("city", ASCENDING)],
            [("date", DESCENDING)],
        ],
    },
    "environment_reports": {
        "indexes": [
            [("city", ASCENDING)],
            [("date", DESCENDING)],
        ],
    },
    "activity_logs": {
        "indexes": [
            [("timestamp", DESCENDING)],
        ],
    },
    "settings": {
        "indexes": [
            [("key", ASCENDING)],
        ],
        "unique_indexes": [
            [("key", ASCENDING)],
        ],
    },
    "datasets": {
        "indexes": [
            [("name", ASCENDING)],
            [("created_at", DESCENDING)],
        ],
    },
    "mapreduce_aggregates": {
        "indexes": [
            [("station_id", ASCENDING)],
            [("uploaded_at", DESCENDING)],
        ],
    },
    "api_logs": {
        "indexes": [
            [("timestamp", DESCENDING)],
        ],
    },
    "system_logs": {
        "indexes": [
            [("timestamp", DESCENDING)],
        ],
    },
}


def ensure_indexes() -> None:
    db = get_db()
    if db is None:
        logger.warning("MongoDB unavailable, skipping ensure_indexes.")
        return
    for name, schema in COLLECTION_SCHEMAS.items():
        collection: Collection = db[name]
        for index_spec in schema.get("indexes", []):
            try:
                collection.create_index(index_spec)
            except Exception as exc:
                logger.warning("Failed creating index on %s: %s", name, exc)
        for index_spec in schema.get("unique_indexes", []):
            try:
                collection.create_index(index_spec, unique=True)
            except Exception as exc:
                logger.warning("Failed creating unique index on %s: %s", name, exc)
    seed_defaults()


def seed_defaults() -> None:
    db = get_db()
    if db is None:
        logger.warning("MongoDB unavailable, skipping seed_defaults.")
        return
    now = datetime.now(timezone.utc).isoformat()

    if db.users.count_documents({"email": "admin@earthscape.org"}) == 0:
        db.users.insert_one({
            "full_name": "System Administrator",
            "email": "admin@earthscape.org",
            "phone": "+15550000000",
            "password": _hash_pw("Admin@123"),
            "role": "admin",
            "profile_image": "",
            "email_verified": True,
            "is_active": True,
            "last_login": None,
            "refresh_tokens": [],
            "created_at": now,
            "updated_at": now,
        })

    if db.users.count_documents({"email": "analyst@earthscape.org"}) == 0:
        db.users.insert_one({
            "full_name": "Dr. Sarah Jenkins",
            "email": "analyst@earthscape.org",
            "phone": "+15550000001",
            "password": _hash_pw("Analyst@123"),
            "role": "analyst",
            "profile_image": "",
            "email_verified": True,
            "is_active": True,
            "last_login": None,
            "refresh_tokens": [],
            "created_at": now,
            "updated_at": now,
        })

    if db.users.count_documents({"email": "researcher@earthscape.org"}) == 0:
        db.users.insert_one({
            "full_name": "Elena Rostova",
            "email": "researcher@earthscape.org",
            "phone": "+15550000002",
            "password": _hash_pw("Research@123"),
            "role": "researcher",
            "profile_image": "",
            "email_verified": True,
            "is_active": True,
            "last_login": None,
            "refresh_tokens": [],
            "created_at": now,
            "updated_at": now,
        })

    if db.users.count_documents({"email": "guest@earthscape.org"}) == 0:
        db.users.insert_one({
            "full_name": "Public Guest Viewer",
            "email": "guest@earthscape.org",
            "phone": "+15550000003",
            "password": _hash_pw("Guest@123"),
            "role": "guest",
            "profile_image": "",
            "email_verified": True,
            "is_active": True,
            "last_login": None,
            "refresh_tokens": [],
            "created_at": now,
            "updated_at": now,
        })

    if db.settings.count_documents({"key": "app"}) == 0:
        db.settings.insert_one({
            "key": "app",
            "value": {"name": "EarthScape Climate Intelligence", "theme": "dark"},
            "updated_at": now,
        })

    if db.cities.count_documents({}) == 0:
        db.cities.insert_many([
            {"name": "London", "country": "UK", "region": "Europe", "latitude": 51.5074, "longitude": -0.1278},
            {"name": "New York", "country": "USA", "region": "North America", "latitude": 40.7128, "longitude": -74.0060},
            {"name": "Mumbai", "country": "India", "region": "Asia", "latitude": 19.0760, "longitude": 72.8777},
            {"name": "Tokyo", "country": "Japan", "region": "Asia", "latitude": 35.6762, "longitude": 139.6503},
            {"name": "Paris", "country": "France", "region": "Europe", "latitude": 48.8566, "longitude": 2.3522},
            {"name": "Sydney", "country": "Australia", "region": "Oceania", "latitude": -33.8688, "longitude": 151.2093},
            {"name": "Cairo", "country": "Egypt", "region": "Africa", "latitude": 30.0444, "longitude": 31.2357},
            {"name": "Sao Paulo", "country": "Brazil", "region": "South America", "latitude": -23.5505, "longitude": -46.6333},
            {"name": "Toronto", "country": "Canada", "region": "North America", "latitude": 43.6532, "longitude": -79.3832},
            {"name": "Berlin", "country": "Germany", "region": "Europe", "latitude": 52.5200, "longitude": 13.4050},
            {"name": "Singapore", "country": "Singapore", "region": "Asia", "latitude": 1.3521, "longitude": 103.8198},
            {"name": "Dubai", "country": "UAE", "region": "Middle East", "latitude": 25.2048, "longitude": 55.2708},
            {"name": "Moscow", "country": "Russia", "region": "Europe", "latitude": 55.7558, "longitude": 37.6173},
            {"name": "Lagos", "country": "Nigeria", "region": "Africa", "latitude": 6.5244, "longitude": 3.3792},
            {"name": "Shanghai", "country": "China", "region": "Asia", "latitude": 31.2304, "longitude": 121.4737},
        ])
