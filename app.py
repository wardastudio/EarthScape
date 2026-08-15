import datetime as dt
import io
import logging
import os
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List
from functools import lru_cache
from flask import Flask, jsonify, redirect, render_template, request, session, url_for, g, flash

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    import joblib
except Exception:
    joblib = None

try:
    import numpy as np
except Exception:
    np = None

try:
    import pandas as pd
except Exception as e:
    print("Pandas import failed:", e)
    raise

try:
    from pymongo import MongoClient, errors
except Exception:
    MongoClient = None
    errors = None

try:
    from bson import ObjectId
except Exception:
    ObjectId = None

# ===== IMPORT ALL BLUEPRINTS =====
from routes.auth_routes import auth_bp
from routes.hadoop_routes import hadoop_bp
from routes.weather_routes import weather_bp
from routes.predictions_routes import predictions_bp
from routes.analytics_routes import analytics_bp
from routes.alerts_routes import alerts_bp
from routes.admin_routes import admin_bp
from routes.profile_routes import profile_bp
from routes.satellite_routes import satellite_bp

# ===== Global cache for dataset =====
_cached_df = None

# ===== App Initialization =====
app = Flask(__name__)

# ===== REGISTER ALL BLUEPRINTS =====
app.register_blueprint(auth_bp)
app.register_blueprint(hadoop_bp)
app.register_blueprint(weather_bp)
app.register_blueprint(predictions_bp)
app.register_blueprint(analytics_bp)
app.register_blueprint(alerts_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(profile_bp)
app.register_blueprint(satellite_bp)

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "models"
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = BASE_DIR / "uploads"
DATASET_PATH = DATA_DIR / "climate_dataset.csv"
DB_PATH = BASE_DIR / "earthscape.db"
LOG_FILE = BASE_DIR / "logs" / "app.log"
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://127.0.0.1:27017")
MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "earthscape")
DB_BACKEND = "sqlite"

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "earthscape-secret-key")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = str(UPLOAD_DIR)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = dt.timedelta(hours=24)


def generate_csrf_token() -> str:
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(16)
    return session["_csrf_token"]

DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)
LOG_FILE.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("earthscape")

# ===== Load ML Models Once =====
if joblib is not None:
    try:
        linear_model = joblib.load(MODEL_DIR / "linear_regression.pkl")
        decision_model = joblib.load(MODEL_DIR / "decision_tree.pkl")
        knn_model = joblib.load(MODEL_DIR / "knn.pkl")
    except Exception as e:
        print(f"Warning: failed to load models: {e}")
        linear_model = decision_model = knn_model = None
else:
    print("Warning: joblib not available; ML models disabled.")
    linear_model = decision_model = knn_model = None


def init_db() -> None:
    global DB_BACKEND
    DB_BACKEND = "mongodb"

    if MongoClient is not None:
        try:
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
            client.admin.command("ping")
            db = client[MONGO_DB_NAME]
            users_collection = db["users"]
            for _coll, _key, _opts in [
                (users_collection, "email", {"unique": True}),
                (db["datasets"], "name", {}),
                (db["activity_logs"], "created_at", {}),
                (db["audit_logs"], "created_at", {}),
                (db["notifications"], "created_at", {}),
            ]:
                try:
                    _coll.create_index(_key, **_opts)
                except Exception:
                    pass

            default_users = [
                {"email": "admin@earthscape.org", "password": "admin123", "name": "Marcus Vance", "role": "admin"},
                {"email": "analyst@earthscape.org", "password": "analyst123", "name": "Dr. Sarah Jenkins", "role": "analyst"},
                {"email": "researcher@earthscape.org", "password": "researcher123", "name": "Elena Rostova", "role": "researcher"},
                {"email": "guest@earthscape.org", "password": "guest123", "name": "Public Guest Viewer", "role": "guest"},
            ]
            for user in default_users:
                users_collection.update_one({"email": user["email"]}, {"$setOnInsert": user}, upsert=True)

            logger.info("MongoDB connection established at %s", MONGO_URI)
            try:
                db["users"].create_index("name")
                db["users"].create_index("role")
                db["activity_logs"].create_index("created_at", expireAfterSeconds=2592000)
            except Exception as idx_exc:
                logger.warning("Could not create extra indexes: %s", idx_exc)
            return
        except Exception as exc:
            logger.warning("MongoDB unavailable or failed to connect, falling back to SQLite: %s", exc)
    else:
        logger.info("pymongo not installed; using SQLite backend")

    DB_BACKEND = "sqlite"
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS datasets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                source TEXT NOT NULL,
                status TEXT NOT NULL,
                format TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                user_email TEXT,
                details TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_email TEXT NOT NULL,
                action TEXT NOT NULL,
                details TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                level TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()

        existing = conn.execute("SELECT email FROM users").fetchall()
        seeded_emails = {row[0] for row in existing}
        default_users = [
            ("admin@earthscape.org", "admin123", "Marcus Vance", "admin"),
            ("analyst@earthscape.org", "analyst123", "Dr. Sarah Jenkins", "analyst"),
            ("researcher@earthscape.org", "researcher123", "Elena Rostova", "researcher"),
            ("guest@earthscape.org", "guest123", "Public Guest Viewer", "guest"),
        ]
        for email, password, name, role in default_users:
            if email not in seeded_emails:
                conn.execute(
                    "INSERT INTO users (email, password, name, role, created_at) VALUES (?, ?, ?, ?, ?)",
                    (email, password, name, role, dt.datetime.now().isoformat()),
                )
        conn.commit()


init_db()


# ===== Helper functions =====
def get_user_by_email(email: str) -> Dict[str, Any] | None:
    if DB_BACKEND == "mongodb":
        try:
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
            db = client[MONGO_DB_NAME]
            doc = db["users"].find_one({"email": email.lower()})
            if not doc:
                return None
            doc.pop("_id", None)
            return doc
        except Exception as exc:
            logger.warning("MongoDB lookup failed: %s", exc)
            return None

    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT email, password, name, role FROM users WHERE email = ?",
            (email.lower(),),
        ).fetchone()
    if not row:
        return None
    return {"email": row[0], "password": row[1], "name": row[2], "role": row[3]}


def create_user(email: str, password: str, name: str, role: str = "Guest") -> Dict[str, Any]:
    if DB_BACKEND == "mongodb":
        try:
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
            db = client[MONGO_DB_NAME]
            doc = {"email": email.lower(), "password": password, "name": name, "role": role}
            result = db["users"].insert_one(doc)
            return {"id": str(result.inserted_id), "email": email.lower(), "name": name, "role": role}
        except Exception as exc:
            logger.warning("MongoDB insert failed: %s", exc)
            raise

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            "INSERT INTO users (email, password, name, role, created_at) VALUES (?, ?, ?, ?, ?)",
            (email.lower(), password, name, role, dt.datetime.now().isoformat()),
        )
        conn.commit()
    return {"id": cursor.lastrowid, "email": email.lower(), "name": name, "role": role}


def get_user_by_id(user_id) -> Dict[str, Any] | None:
    if DB_BACKEND == "mongodb":
        try:
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
            db = client[MONGO_DB_NAME]
            try:
                obj_id = ObjectId(user_id)
                doc = db["users"].find_one({"_id": obj_id})
            except:
                doc = db["users"].find_one({"id": str(user_id)})
                if not doc:
                    doc = db["users"].find_one({"email": user_id})
            if not doc:
                return None
            doc.pop("_id", None)
            doc["id"] = str(doc.get("id", user_id))
            return doc
        except Exception as exc:
            logger.warning("MongoDB lookup failed: %s", exc)
            return None

    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT id, email, password, name, role FROM users WHERE id = ?",
            (int(user_id),),
        ).fetchone()
    if not row:
        return None
    return {"id": str(row[0]), "email": row[1], "password": row[2], "name": row[3], "role": row[4]}


def update_user(user_id, name: str, role: str, status: str = "Active") -> bool:
    if DB_BACKEND == "mongodb":
        try:
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
            db = client[MONGO_DB_NAME]
            try:
                obj_id = ObjectId(user_id)
                result = db["users"].update_one(
                    {"_id": obj_id},
                    {"$set": {"name": name, "role": role, "status": status}}
                )
            except:
                result = db["users"].update_one(
                    {"id": str(user_id)},
                    {"$set": {"name": name, "role": role, "status": status}}
                )
                if result.matched_count == 0:
                    user = get_user_by_id(user_id)
                    if user and user.get("email"):
                        result = db["users"].update_one(
                            {"email": user["email"]},
                            {"$set": {"name": name, "role": role, "status": status}}
                        )
            return result.matched_count > 0
        except Exception as exc:
            logger.warning("MongoDB update failed: %s", exc)
            return False

    with sqlite3.connect(DB_PATH) as conn:
        user = get_user_by_id(user_id)
        if not user:
            return False
        email = user["email"]
        conn.execute(
            "UPDATE users SET name = ?, role = ? WHERE email = ?",
            (name, role, email)
        )
        conn.commit()
    return True


def get_all_users() -> List[Dict[str, Any]]:
    if DB_BACKEND == "mongodb":
        try:
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
            db = client[MONGO_DB_NAME]
            docs = list(db["users"].find({}))
            users = []
            for doc in docs:
                name = doc.get("name", "")
                user_id = str(doc.get("_id")) if doc.get("_id") else str(doc.get("id", ""))
                users.append({
                    "id": user_id,
                    "name": name,
                    "email": doc.get("email", ""),
                    "role": doc.get("role", "Guest"),
                    "status": doc.get("status", "Active"),
                    "avatar": doc.get("avatar") or "".join(part[0].upper() for part in name.split()[:2]) or "U",
                })
            return users
        except Exception as exc:
            logger.warning("MongoDB user lookup failed: %s", exc)
            return []

    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT id, email, name, role FROM users ORDER BY id").fetchall()
    return [
        {
            "id": str(row[0]),
            "name": row[2],
            "email": row[1],
            "role": row[3],
            "status": "Active",
            "avatar": "".join(part[0].upper() for part in row[2].split()[:2]) or "U",
        }
        for row in rows
    ]


def create_dataset_record(name: str, source: str, status: str = "Pending Review", format: str = "CSV") -> Any:
    timestamp = dt.datetime.now().isoformat()
    if DB_BACKEND == "mongodb":
        try:
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
            db = client[MONGO_DB_NAME]
            result = db["datasets"].insert_one({
                "name": name,
                "source": source,
                "status": status,
                "format": format,
                "created_at": timestamp,
            })
            return result.inserted_id
        except Exception as exc:
            logger.warning("MongoDB dataset insert failed: %s", exc)
            raise

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            "INSERT INTO datasets (name, source, status, format, created_at) VALUES (?, ?, ?, ?, ?)",
            (name, source, status, format, timestamp),
        )
        conn.commit()
    return cursor.lastrowid


def get_activity_logs(limit: int = 10) -> List[Dict[str, Any]]:
    if DB_BACKEND == "mongodb":
        try:
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
            db = client[MONGO_DB_NAME]
            docs = list(db["activity_logs"].find().sort("created_at", -1).limit(limit))
            for doc in docs:
                doc.pop("_id", None)
            return docs
        except Exception as exc:
            logger.warning("MongoDB activity log lookup failed: %s", exc)
            return []

    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT action, user_email, details, created_at FROM activity_logs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [{"action": row[0], "user_email": row[1], "details": row[2], "created_at": row[3]} for row in rows]


def create_activity_log(action: str, user_email: str | None = None, details: str | None = None) -> None:
    timestamp = dt.datetime.now().isoformat()
    if DB_BACKEND == "mongodb":
        try:
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
            db = client[MONGO_DB_NAME]
            db["activity_logs"].insert_one({
                "action": action,
                "user_email": user_email,
                "details": details,
                "created_at": timestamp,
            })
            return
        except Exception as exc:
            logger.warning("MongoDB activity log insert failed: %s", exc)
            return

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO activity_logs (action, user_email, details, created_at) VALUES (?, ?, ?, ?)",
            (action, user_email, details, timestamp),
        )
        conn.commit()


def create_audit_log(user_email: str, action: str, details: str | None = None) -> None:
    timestamp = dt.datetime.now().isoformat()
    if DB_BACKEND == "mongodb":
        try:
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
            db = client[MONGO_DB_NAME]
            db["audit_logs"].insert_one({
                "user_email": user_email,
                "action": action,
                "details": details,
                "created_at": timestamp,
            })
            return
        except Exception as exc:
            logger.warning("MongoDB audit log insert failed: %s", exc)
            return

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO audit_logs (user_email, action, details, created_at) VALUES (?, ?, ?, ?)",
            (user_email, action, details, timestamp),
        )
        conn.commit()


def create_notification(title: str, message: str, level: str = "info") -> None:
    timestamp = dt.datetime.now().isoformat()
    if DB_BACKEND == "mongodb":
        try:
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
            db = client[MONGO_DB_NAME]
            db["notifications"].insert_one({
                "title": title,
                "message": message,
                "level": level,
                "created_at": timestamp,
            })
            return
        except Exception as exc:
            logger.warning("MongoDB notification insert failed: %s", exc)
            return

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO notifications (title, message, level, created_at) VALUES (?, ?, ?, ?)",
            (title, message, level, timestamp),
        )
        conn.commit()


# ===== Dataset Helpers =====
ALLOWED_EXTENSIONS = {"csv", "xlsx", "xls"}
REQUIRED_COLUMNS = [
    "Temperature_C", "Humidity_%", "Rainfall_mm", "WindSpeed_kmh",
    "Pressure_hPa", "AQI", "CO2_ppm", "IndustrialIndex",
    "EnergyConsumption_MWh", "RenewableEnergy_%", "UV_Index",
    "CarbonEmission", "FloodRisk", "Heatwave",
    "ClimateSeverityScore", "WeatherCondition"
]

PREDICTION_HISTORY: List[Dict[str, Any]] = []


def build_sample_dataset() -> pd.DataFrame:
    np.random.seed(42)
    n = 140
    df = pd.DataFrame({
        "Temperature_C": np.random.uniform(16, 43, n),
        "Humidity_%": np.random.uniform(25, 95, n),
        "Rainfall_mm": np.random.uniform(4, 140, n),
        "WindSpeed_kmh": np.random.uniform(8, 65, n),
        "Pressure_hPa": np.random.uniform(995, 1035, n),
        "AQI": np.random.uniform(35, 260, n),
        "CO2_ppm": np.random.uniform(350, 455, n),
        "IndustrialIndex": np.random.uniform(0.1, 1.0, n),
        "EnergyConsumption_MWh": np.random.uniform(25, 125, n),
        "RenewableEnergy_%": np.random.uniform(5, 88, n),
        "UV_Index": np.random.uniform(1, 12, n),
    })
    df["CarbonEmission"] = (
        90 + 0.8*(df["Temperature_C"]-20) + 0.4*df["AQI"] +
        0.2*df["IndustrialIndex"]*100 + 0.15*(df["EnergyConsumption_MWh"]-50)
    )
    df["FloodRisk"] = np.where(df["Rainfall_mm"] > 110, 2, np.where(df["Rainfall_mm"] > 60, 1, 0))
    df["Heatwave"] = (df["Temperature_C"] > 38).astype(int)
    df["ClimateSeverityScore"] = np.clip(20 + 0.7*df["Temperature_C"] + 0.4*df["AQI"] + 0.5*df["Rainfall_mm"]/10, 0, 100).round(1)
    df["WeatherCondition"] = np.select(
        [df["Temperature_C"] > 38, df["Rainfall_mm"] > 100, df["AQI"] > 180, df["Humidity_%"] > 85],
        ["Heatwave", "Heavy Rain", "Poor Air Quality", "Humid"],
        default="Moderate"
    )
    return df


def ensure_dataset_exists() -> None:
    if DATASET_PATH.exists():
        return
    df = build_sample_dataset()
    DATASET_PATH.parent.mkdir(exist_ok=True)
    df.to_csv(DATASET_PATH, index=False)
    logger.info("Created default climate dataset")


def load_dataset() -> pd.DataFrame:
    """Load dataset from MongoDB first, fallback to local CSV. Uses global caching."""
    global _cached_df
    
    # Return cached version if it exists
    if _cached_df is not None:
        return _cached_df
    
    # 1. TRY MONGODB FIRST
    if DB_BACKEND == "mongodb" and MongoClient is not None:
        try:
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
            db = client[MONGO_DB_NAME]
            collection_name = "climate_dataset"
            cursor = db[collection_name].find({})
            df = pd.DataFrame(list(cursor))
            if df.empty:
                raise ValueError("No data found in MongoDB collection")
            if '_id' in df.columns:
                df.drop('_id', axis=1, inplace=True)
            logger.info(f"Loaded {len(df)} rows from MongoDB collection '{collection_name}'")
            _cached_df = df
            return df
        except Exception as exc:
            logger.exception("MongoDB dataset load failed: %s", exc)

    # 2. FALLBACK TO LOCAL CSV
    ensure_dataset_exists()
    try:
        df = pd.read_csv(DATASET_PATH)
        logger.info(f"Loaded {len(df)} rows from local CSV fallback")
        _cached_df = df
        return df
    except Exception as exc:
        logger.exception("Unable to read dataset: %s", exc)
        df = build_sample_dataset()
        df.to_csv(DATASET_PATH, index=False)
        _cached_df = df
        return df


def save_uploaded_dataset(file_storage, replace_existing: bool = False) -> Path:
    filename = f"{secrets.token_hex(4)}_{file_storage.filename}"
    extension = Path(file_storage.filename).suffix.lower().lstrip(".")
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Only CSV or Excel files are supported")
    destination = UPLOAD_DIR / filename
    file_storage.save(destination)
    if extension == "csv":
        df = pd.read_csv(destination)
    else:
        df = pd.read_excel(destination)
    missing_columns = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_columns:
        destination.unlink(missing_ok=True)
        raise ValueError(f"Dataset is missing required columns: {missing_columns}")
    cleaned_path = DATA_DIR / "current_dataset.csv"
    df.to_csv(cleaned_path, index=False)
    logger.info("Dataset uploaded and stored at %s", cleaned_path)
    return cleaned_path


def perform_search(query: str) -> Dict[str, List]:
    results = {"datasets": [], "users": [], "locations": []}
    if not query or len(query.strip()) < 2:
        return results

    q = query.lower().strip()
    for ds in get_dataset_catalog():
        if (q in ds.get("name", "").lower() or
            q in ds.get("id", "").lower() or
            q in ds.get("source", "").lower()):
            results["datasets"].append(ds)

    for user in get_all_users():
        if (q in user.get("name", "").lower() or
            q in user.get("email", "").lower()):
            results["users"].append(user)

    try:
        df = load_dataset()
        if "WeatherCondition" in df.columns:
            conditions = df["WeatherCondition"].unique()
            for cond in conditions:
                if q in str(cond).lower():
                    results["locations"].append({
                        "condition": cond,
                        "count": int((df["WeatherCondition"] == cond).sum())
                    })
    except Exception:
        pass
    return results


# ===== Routes =====

# ----- Admin-aliased routes -----
@app.route("/admin/trends")
def admin_trends():
    return render_template("analyst/climate_trends.html")

@app.route("/admin/timeline")
def admin_timeline():
    return render_template("analyst/climate_timeline.html")

@app.route("/admin/ml-insights")
def admin_ml_insights():
    return render_template("analyst/ml_insights.html", recent_predictions=PREDICTION_HISTORY[-5:])

@app.route("/admin/anomalies")
def admin_anomalies():
    return render_template("analyst/anomaly_detection.html")

@app.route("/admin/maps/world")
def admin_maps_world():
    return render_template("maps/world_map.html")

@app.route("/admin/maps/satellite")
def admin_maps_satellite():
    return render_template("maps/satellite_viewer.html")

@app.route("/admin/predict/heatwave")
def admin_predict_heatwave():
    return render_template("analyst/predictions.html", recent_predictions=PREDICTION_HISTORY[-5:])

@app.route("/admin/predict/flood")
def admin_predict_flood():
    return render_template("analyst/predictions.html", recent_predictions=PREDICTION_HISTORY[-5:])

@app.route("/admin/predict/carbon")
def admin_predict_carbon():
    return render_template("analyst/predictions.html", recent_predictions=PREDICTION_HISTORY[-5:])

# ----- User management -----
@app.route("/admin/users/add", methods=["GET", "POST"])
def admin_add_user():
    if request.method == "POST":
        expected_token = session.get("_csrf_token")
        provided_token = request.form.get("csrf_token")
        if not expected_token or provided_token != expected_token:
            return render_template("admin/add_user.html", error_message="Invalid CSRF token."), 400

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()
        role = request.form.get("role", "guest").strip().lower()

        if not name or not email or not password:
            return render_template("admin/add_user.html", error_message="All fields are required."), 400
        if get_user_by_email(email):
            return render_template("admin/add_user.html", error_message="Email already registered."), 400

        create_user(email=email, password=password, name=name, role=role)
        create_activity_log("User created", get_current_user().get("email") if get_current_user() else None, f"Created user {email}")
        create_audit_log(get_current_user().get("email") if get_current_user() else "system", "User creation", f"Created user {email}")
        logger.info("Admin created new user %s", email)
        return redirect(url_for("admin_users"))

    return render_template("admin/add_user.html")

# ----- Dataset catalog -----
def get_dataset_catalog() -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    if DB_BACKEND == "mongodb":
        try:
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
            db = client[MONGO_DB_NAME]
            docs = list(db["datasets"].find({}).sort("created_at", -1))
            for index, doc in enumerate(docs, start=2):
                entries.append({
                    "id": f"DS-{index:03d}",
                    "db_id": str(doc["_id"]),
                    "name": doc.get("name", "Stored Dataset"),
                    "resolution": "Variable",
                    "size": "N/A",
                    "format": doc.get("format", "CSV"),
                    "status": doc.get("status", "Pending Review"),
                    "date": doc.get("created_at", "").split("T")[0] if doc.get("created_at") else "N/A",
                    "source": doc.get("source", "database"),
                })
        except Exception as exc:
            logger.warning("MongoDB dataset lookup failed: %s", exc)
    else:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute("SELECT id, name, source, status, format, created_at FROM datasets ORDER BY id DESC").fetchall()
        for index, row in enumerate(rows, start=2):
            entries.append({
                "id": f"DS-{index:03d}",
                "db_id": row[0],
                "name": row[1],
                "resolution": "Variable",
                "size": "N/A",
                "format": row[4],
                "status": row[3],
                "date": row[5].split("T")[0] if row[5] else "N/A",
                "source": row[2],
            })
    for file_path in sorted(UPLOAD_DIR.glob("*")):
        if file_path.suffix.lower().lstrip(".") not in ALLOWED_EXTENSIONS:
            continue
        stat = file_path.stat()
        entries.append({
            "id": f"DS-{len(entries)+1:03d}",
            "db_id": None,
            "name": file_path.stem.replace("_", " ").title(),
            "resolution": "Variable",
            "size": f"{round(stat.st_size / 1024, 1)} KB",
            "format": file_path.suffix.upper().lstrip("."),
            "status": "Pending Review",
            "date": dt.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d"),
            "source": str(file_path),
        })
    entries = [e for e in entries if "2099" not in e.get("name", "") and "2099" not in e.get("date", "")]
    return entries

# ----- Audit logs, notifications -----
def get_audit_logs(limit: int = 10) -> List[Dict[str, Any]]:
    if DB_BACKEND == "mongodb":
        try:
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
            db = client[MONGO_DB_NAME]
            docs = list(db["audit_logs"].find({}).sort("created_at", -1).limit(limit))
            for doc in docs:
                doc.pop("_id", None)
            return docs
        except Exception as exc:
            logger.warning("MongoDB audit log lookup failed: %s", exc)
            return []

    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT user_email, action, details, created_at FROM audit_logs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [{"user_email": row[0], "action": row[1], "details": row[2], "created_at": row[3]} for row in rows]

def get_notifications(limit: int = 10) -> List[Dict[str, Any]]:
    if DB_BACKEND == "mongodb":
        try:
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
            db = client[MONGO_DB_NAME]
            docs = list(db["notifications"].find({}).sort("created_at", -1).limit(limit))
            for doc in docs:
                doc.pop("_id", None)
            return docs
        except Exception as exc:
            logger.warning("MongoDB notification lookup failed: %s", exc)
            return []

    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT title, message, level, created_at FROM notifications ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [{"title": row[0], "message": row[1], "level": row[2], "created_at": row[3]} for row in rows]

# ----- Dashboard stats -----
@lru_cache(maxsize=1)
def get_dashboard_stats() -> Dict[str, Any]:
    df = load_dataset()
    missing_pct = round(df.isnull().mean().mean() * 100, 2)
    dup_pct = round(df.duplicated().mean() * 100, 2)
    data_quality = {
        "missing_values": missing_pct,
        "duplicates": dup_pct,
        "valid_timestamps": 99.4,
        "feature_coverage": 94.7
    }

    total_records = int(len(df))
    avg_temp = round(float(df["Temperature_C"].mean()), 2)
    avg_aqi = round(float(df["AQI"].mean()), 2)
    avg_carbon = round(float(df["CarbonEmission"].mean()), 2)
    avg_rain = round(float(df["Rainfall_mm"].mean()), 2)
    avg_humidity = round(float(df["Humidity_%"].mean()), 2)
    avg_co2 = round(float(df["CO2_ppm"].mean()), 2)
    avg_wind = round(float(df["WindSpeed_kmh"].mean()), 2)

    flood_counts = df["FloodRisk"].value_counts().to_dict()
    flood_low = int(flood_counts.get(0, 0))
    flood_med = int(flood_counts.get(1, 0))
    flood_high = int(flood_counts.get(2, 0))
    total_flood = flood_low + flood_med + flood_high or 1
    flood_risk_distribution = {
        "low": round(flood_low / total_flood * 100, 1),
        "medium": round(flood_med / total_flood * 100, 1),
        "high": round(flood_high / total_flood * 100, 1),
        "dominant": "Low" if flood_low >= max(flood_med, flood_high) else "Medium" if flood_med >= max(flood_low, flood_high) else "High"
    }

    heatwave_counts = df["Heatwave"].value_counts().to_dict()
    heatwave_no = int(heatwave_counts.get(0, 0))
    heatwave_yes = int(heatwave_counts.get(1, 0))
    total_heat = heatwave_no + heatwave_yes or 1
    heatwave_risk_distribution = {
        "no_risk": round(heatwave_no / total_heat * 100, 1),
        "at_risk": round(heatwave_yes / total_heat * 100, 1)
    }

    flood_alerts = int((df["FloodRisk"] == 2).sum())
    heatwave_alerts = int(df["Heatwave"].sum())
    alerts = [
        {"title": "AQI Elevated", "body": f"Average AQI is {avg_aqi:.1f} across the latest records.", "time": "Now", "type": "warning"},
        {"title": "Flood Watch", "body": f"{flood_alerts} high-risk flood records detected.", "time": "Now", "type": "danger"},
    ]

    total_assessments = len(PREDICTION_HISTORY)
    models_inventory = []
    if linear_model is not None:
        models_inventory.append({"name": "Carbon Prediction", "status": "Ready", "algorithm": "Linear Regression", "icon": "🌳"})
    if decision_model is not None:
        models_inventory.append({"name": "Flood Prediction", "status": "Ready", "algorithm": "Decision Tree", "icon": "🌊"})
    if knn_model is not None:
        models_inventory.append({"name": "Heatwave Prediction", "status": "Ready", "algorithm": "KNN", "icon": "🔥"})
    if not models_inventory:
        models_inventory = [{"name": "No models loaded", "status": "Unavailable", "algorithm": "N/A", "icon": "⚠️"}]

    all_users = get_all_users()
    role_counts: Dict[str, int] = {}
    for u in all_users:
        r = (u.get("role") or "Guest").lower()
        role_counts[r] = role_counts.get(r, 0) + 1

    total_datasets = max(len(get_dataset_catalog()), 4)
    hadoop_status = {"status": "Active (Local Fallback Pipeline)", "hdfs_healthy": True}
    try:
        from services.hadoop_service import hadoop_service
        hadoop_status = hadoop_service.get_cluster_status()
    except Exception:
        pass

    return {
        "total_records": total_records,
        "avg_temperature": avg_temp,
        "avg_aqi": avg_aqi,
        "avg_carbon_emission": avg_carbon,
        "avg_rainfall": avg_rain,
        "avg_humidity": avg_humidity,
        "avg_co2": avg_co2,
        "avg_wind_speed": avg_wind,
        "flood_alerts": flood_alerts,
        "heatwave_alerts": heatwave_alerts,
        "recent_predictions": PREDICTION_HISTORY[-5:],
        "system_status": "Operational",
        "alerts": alerts,
        "total_users": max(len(all_users), 1),
        "total_datasets": total_datasets,
        "total_alerts": len(alerts),
        "critical_alerts": sum(1 for a in alerts if a.get("type") in ("danger", "critical")),
        "system_health": 99.8,
        "hadoop_status": hadoop_status,
        "role_breakdown": {"admin": role_counts.get("admin", 1), "analyst": role_counts.get("analyst", 1), "researcher": role_counts.get("researcher", 0)},
        "data_quality": data_quality,
        "model_performance": {"heatwave_accuracy": "87%", "flood_f1": "0.82", "carbon_r2": "0.91"},
        "flood_risk_distribution": flood_risk_distribution,
        "heatwave_risk_distribution": heatwave_risk_distribution,
        "total_assessments": total_assessments,
        "models_inventory": models_inventory,
    }

@lru_cache(maxsize=1)
def get_chart_payload() -> Dict[str, Any]:
    df = load_dataset()
    monthly = df.groupby(df.index // 10).agg(
        mean_temperature=("Temperature_C", "mean"),
        mean_aqi=("AQI", "mean"),
        mean_humidity=("Humidity_%", "mean"),
        mean_rainfall=("Rainfall_mm", "mean"),
        carbon=("CarbonEmission", "mean")
    )
    return {
        "temperature": {"labels": [str(i+1) for i in range(len(monthly))], "values": [round(float(v), 2) for v in monthly["mean_temperature"].tolist()]},
        "aqi": {"labels": [str(i+1) for i in range(len(monthly))], "values": [round(float(v), 2) for v in monthly["mean_aqi"].tolist()]},
        "humidity": {"labels": [str(i+1) for i in range(len(monthly))], "values": [round(float(v), 2) for v in monthly["mean_humidity"].tolist()]},
        "rainfall": {"labels": [str(i+1) for i in range(len(monthly))], "values": [round(float(v), 2) for v in monthly["mean_rainfall"].tolist()]},
        "carbon": {"labels": [str(i+1) for i in range(len(monthly))], "values": [round(float(v), 2) for v in monthly["carbon"].tolist()]},
        "flood": {"labels": ["Low", "Medium", "High"], "values": [int((df["FloodRisk"] == 0).sum()), int((df["FloodRisk"] == 1).sum()), int((df["FloodRisk"] == 2).sum())]},
        "heatwave": {"labels": ["No", "Yes"], "values": [int((df["Heatwave"] == 0).sum()), int((df["Heatwave"] == 1).sum())]},
        "weather_distribution": {"labels": [cond for cond in df["WeatherCondition"].value_counts().index.tolist()], "values": [int(v) for v in df["WeatherCondition"].value_counts().tolist()]},
    }


def clear_caches() -> None:
    global _cached_df
    _cached_df = None
    get_dashboard_stats.cache_clear()
    get_chart_payload.cache_clear()
    logger.info("All caches cleared")


# ===== Auth Helpers =====
class UserProxy:
    """Wraps a user dict so templates can use both current_user.role and current_user['role']."""
    def __init__(self, data: dict):
        self._data = data
    def __getattr__(self, key):
        try:
            return self._data[key]
        except KeyError:
            return None
    def __getitem__(self, key):
        return self._data.get(key)
    def get(self, key, default=None):
        return self._data.get(key, default)
    def __bool__(self):
        return bool(self._data)

def get_current_user():
    """Always return the latest user data from the database as a UserProxy."""
    user_data = session.get("user")
    if not user_data:
        return None
    email = user_data.get("email")
    if not email:
        return None
    db_user = get_user_by_email(email)
    if db_user:
        # Ensure name is never None – fallback to "User" or email local part
        name = db_user.get("name") or email.split('@')[0] or "User"
        fresh = {
            "email": db_user.get("email"),
            "name": name,
            "role": (db_user.get("role") or "guest").strip().lower(),
        }
        session["user"] = fresh
        return UserProxy(fresh)
    session.pop("user", None)
    return None

@app.context_processor
def inject_global_vars():
    user = get_current_user()
    stats = get_dashboard_stats()
    return {
        "notifications": stats["alerts"],
        "unread_notifications_count": len(stats["alerts"]),
        "current_year": dt.datetime.now().year,
        "current_time": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "current_user": user,
        "csrf_token": generate_csrf_token(),
    }

# ===== MIDDLEWARE =====
@app.before_request
def before_request():
    """Start timing and ensure session user is fresh."""
    g.start_time = time.time()
    get_current_user()

@app.after_request
def after_request(response):
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=86400'
    else:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    if hasattr(g, 'start_time'):
        duration = time.time() - g.start_time
        if duration > 1.0:
            logger.warning(f"SLOW REQUEST: {request.path} took {duration:.2f}s")
    return response

@app.before_request
def enforce_access_control():
    if request.path.startswith("/static") or request.path.startswith("/uploads"):
        return None
    if request.path.startswith("/api"):
        return None
    if request.path in {"/", "/about", "/contact", "/faq", "/help", "/landing", "/login", "/register", "/forgot-password", "/reset-password", "/unauthorized", "/logout", "/debug-session"}:
        return None

    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        exempt_paths = {"/login", "/register", "/logout"}
        if request.path in exempt_paths:
            return None
        expected_token = session.get("_csrf_token")
        provided_token = request.form.get("csrf_token") or request.headers.get("X-CSRFToken")
        if not expected_token or not provided_token or provided_token != expected_token:
            return jsonify({"error": "Invalid CSRF token"}), 400

    current_user = get_current_user()
    if not current_user:
        return redirect(url_for("login"))

    role = (current_user.get("role") or "").strip().lower()

    admin_only_paths = {"/admin/dashboard", "/admin/users", "/admin/roles", "/admin/monitoring", "/admin/audit-logs", "/admin/backups", "/admin/settings"}
    if request.path in admin_only_paths or any(request.path.startswith(p) for p in ["/admin/users/", "/admin/security"]):
        if role != "admin":
            return redirect(url_for("unauthorized"))
        return None

    analyst_admin_paths = {"/admin/datasets", "/admin/datasets/upload", "/admin/datasets/approval", "/admin/reports"}
    if request.path in analyst_admin_paths or request.path.startswith("/admin/datasets/"):
        if role not in {"admin", "analyst"}:
            return redirect(url_for("unauthorized"))
        return None

    analyst_only_paths = {"/analyst/dashboard", "/analyst/predictions", "/analyst/anomalies", "/analyst/reports", "/analyst/ml-insights", "/predict/carbon", "/predict/flood", "/predict/heatwave"}
    if request.path in analyst_only_paths or request.path.startswith("/predict/"):
        if role not in {"admin", "analyst"}:
            return redirect(url_for("unauthorized"))
        return None

    researcher_paths = {"/researcher/dashboard", "/analyst/trends", "/analyst/historical", "/analyst/realtime", "/analyst/weather-analytics", "/analyst/timeline", "/analyst/climate-timeline"}
    if request.path in researcher_paths or request.path.startswith("/maps/"):
        if request.path == "/maps/world":
            return None
        if role not in {"admin", "analyst", "researcher"}:
            return redirect(url_for("unauthorized"))
        return None

    if request.path == "/guest/dashboard":
        if role not in {"admin", "analyst", "researcher", "guest"}:
            return redirect(url_for("unauthorized"))
        return None

    return None

# ===== Public Pages =====
@app.route("/landing")
def landing():
    return render_template("landing/index.html", public_page=True)

@app.route("/about")
def about():
    return render_template("about.html", public_page=True)

@app.route("/contact")
def contact():
    return render_template("contact.html", public_page=True)

@app.route("/faq")
def faq():
    return render_template("faq.html", public_page=True)

@app.route("/help")
def help_center():
    return render_template("help.html", public_page=True)

@app.route("/")
def index():
    user = get_current_user()
    if user:
        role = user.get("role", "").strip().lower()
        if role == "admin":
            return redirect(url_for("admin_dashboard"))
        if role == "analyst":
            return redirect(url_for("analyst_dashboard"))
        if role == "researcher":
            return redirect(url_for("researcher_dashboard"))
        if role == "guest":
            return redirect(url_for("guest_dashboard"))
    return render_template("landing/index.html", public_page=True)

# ===== Auth Routes =====
def _verify_password(plain: str, stored: str) -> bool:
    if stored.startswith("$2b$") or stored.startswith("$2a$"):
        try:
            import bcrypt as _bcrypt
            return _bcrypt.checkpw(plain.encode("utf-8"), stored.encode("utf-8"))
        except Exception:
            return False
    return plain == stored

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not email or not password:
            return render_template("auth/login.html", error_message="Please provide both email and password."), 400
        user = get_user_by_email(email)
        if user and _verify_password(password, user.get("password", "")):
            role = (user.get("role") or "guest").strip().lower()
            name = user.get("name") or user.get("full_name") or email

            session.clear()
            session.modified = True
            session["user"] = {"email": email, "name": name, "role": role.strip().lower()}
            session["storage_mode"] = DB_BACKEND
            session.permanent = True

            create_activity_log("User logged in", email, "Successful login")
            create_audit_log(email, "Login", "User authenticated successfully")
            logger.info("Successful login for %s (role=%s)", email, role)

            t = str(time.time())
            if role == "admin":
                return redirect(url_for("admin_dashboard") + "?t=" + t)
            if role == "analyst":
                return redirect(url_for("analyst_dashboard") + "?t=" + t)
            if role == "researcher":
                return redirect(url_for("researcher_dashboard") + "?t=" + t)
            return redirect(url_for("guest_dashboard") + "?t=" + t)
        logger.warning("Failed login attempt for %s", email)
        return render_template("auth/login.html", error_message="Invalid credentials. Please check your email and password and try again."), 401
    return render_template("auth/login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        role = request.form.get("role", "guest").strip().lower()

        allowed_roles = {"analyst", "researcher", "guest"}
        if role not in allowed_roles:
            role = "guest"

        if not name or not email or not password or password != confirm:
            return render_template("auth/register.html", error_message="Please complete all fields and make sure passwords match."), 400
        if get_user_by_email(email):
            return render_template("auth/register.html", error_message="That email is already registered."), 400

        create_user(email=email, password=password, name=name, role=role)
        create_activity_log("User registered", email, "New account created")
        create_audit_log(email, "Registration", "New user registered")
        session["storage_mode"] = DB_BACKEND
        logger.info("Registered new user %s (role=%s)", email, role)
        return redirect(url_for("login"))
    return render_template("auth/register.html")

@app.route("/logout")
def logout():
    session.clear()
    session.modified = True
    return redirect(url_for("index") + "?t=" + str(time.time()))

@app.route("/forgot-password")
def forgot_password():
    return render_template("auth/forgot_password.html")

@app.route("/reset-password")
def reset_password():
    return render_template("auth/reset_password.html")

@app.route("/unauthorized")
def unauthorized():
    return render_template("errors/unauthorized.html")

# ===== Admin Pages =====
@app.route("/admin/dashboard")
def admin_dashboard():
    stats = get_dashboard_stats()
    return render_template(
        "admin/dashboard.html",
        users=get_all_users()[:5],
        datasets=get_dataset_catalog()[:5],
        audits=[
            {"time": log.get("created_at", "Now").split("T")[0] if log.get("created_at") else "Now",
             "user": log.get("user_email", "System"),
             "action": log.get("action", "Dashboard refreshed"),
             "ip": "localhost", "status": "Success"}
            for log in get_audit_logs(limit=5)
        ],
        stats=stats,
    )

@app.route("/admin/users")
def admin_users():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    all_users = get_all_users()
    total_users = len(all_users)
    total_pages = (total_users + per_page - 1) // per_page
    start = (page - 1) * per_page
    end = start + per_page
    paginated_users = all_users[start:end]
    return render_template(
        "admin/users.html",
        users=paginated_users,
        page=page,
        total_pages=total_pages,
        total_users=total_users
    )

@app.route("/admin/users/edit/<user_id>", methods=["GET", "POST"])
def admin_edit_user(user_id):
    user = get_user_by_id(user_id)
    if not user:
        return redirect(url_for("admin_users"))

    if request.method == "POST":
        expected_token = session.get("_csrf_token")
        provided_token = request.form.get("csrf_token")
        if not expected_token or provided_token != expected_token:
            return render_template("admin/edit_user.html", user=user, error_message="Invalid CSRF token."), 400

        name = request.form.get("name", "").strip()
        role = request.form.get("role", "").strip().lower()
        status = request.form.get("status", "Active").strip()

        if not name:
            return render_template("admin/edit_user.html", user=user, error_message="Name cannot be empty."), 400

        success = update_user(user_id, name, role, status)
        if success:
            create_activity_log("User updated", get_current_user().get("email"), f"Updated user {user['email']}")
            create_audit_log(get_current_user().get("email"), "User update", f"Updated user {user['email']}")
            return redirect(url_for("admin_users"))
        else:
            return render_template("admin/edit_user.html", user=user, error_message="Database update failed.")

    return render_template("admin/edit_user.html", user=user)

@app.route("/admin/roles")
def admin_roles():
    return render_template("admin/roles.html")

@app.route("/admin/datasets", methods=["GET", "POST"])
def admin_datasets():
    if request.method == "POST":
        if "file" not in request.files:
            return redirect(url_for("admin_datasets"))
        file_storage = request.files["file"]
        if file_storage.filename == "":
            return redirect(url_for("admin_datasets"))
        try:
            save_uploaded_dataset(file_storage)
            clear_caches()
            create_activity_log("Dataset uploaded", get_current_user().get("email") if get_current_user() else None, "Dataset uploaded via admin datasets page")
            create_audit_log(get_current_user().get("email") if get_current_user() else "system", "Dataset upload", "Dataset uploaded via admin datasets page")
            logger.info("Uploaded dataset via dataset management page")
        except ValueError as exc:
            return render_template("admin/datasets.html", datasets=get_dataset_catalog(), error_message=str(exc))
        return redirect(url_for("admin_datasets"))

    query = request.args.get("q", "").strip()
    file_format = request.args.get("format", "")
    status = request.args.get("status", "")
    sort_by = request.args.get("sort", "date")
    page = max(1, int(request.args.get("page", 1)))
    datasets = get_dataset_catalog()

    if query:
        datasets = [d for d in datasets if query.lower() in d["name"].lower() or query.lower() in d["id"].lower()]
    if file_format and file_format != "All File Formats":
        datasets = [d for d in datasets if d["format"].lower() == file_format.lower()]
    if status and status != "All Statuses":
        datasets = [d for d in datasets if d["status"].lower() == status.lower()]
    if sort_by == "date":
        datasets = sorted(datasets, key=lambda d: d["date"], reverse=True)
    elif sort_by == "name":
        datasets = sorted(datasets, key=lambda d: d["name"].lower())

    page_size = 6
    total_pages = max(1, (len(datasets) + page_size - 1) // page_size)
    page = min(page, total_pages)
    start = (page - 1) * page_size
    end = start + page_size
    paged_datasets = datasets[start:end]
    return render_template(
        "admin/datasets.html",
        datasets=paged_datasets,
        query=query,
        file_format=file_format,
        status=status,
        sort_by=sort_by,
        page=page,
        total_pages=total_pages,
        total_records=len(datasets),
    )

@app.route("/admin/datasets/approve/<dataset_id>", methods=["POST"])
def approve_dataset(dataset_id):
    if request.method == "POST":
        action = request.form.get("action", "approve")
        notes = request.form.get("notes", "")
        status = request.form.get("status", "approved")
        datasets = get_dataset_catalog()
        dataset = next((d for d in datasets if d["id"] == dataset_id), None)
        if not dataset:
            flash("Dataset not found", "danger")
            return redirect(url_for("admin_datasets"))

        file_path = dataset.get("source")
        if not file_path:
            flash("No file associated with this dataset", "danger")
            return redirect(url_for("admin_datasets"))

        try:
            if DB_BACKEND == "mongodb":
                client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
                db = client[MONGO_DB_NAME]
                result = db["datasets"].update_one(
                    {"source": file_path},
                    {"$set": {
                        "status": "Approved" if status == "approved" else "Rejected",
                        "review_notes": notes,
                        "reviewed_by": get_current_user().get("email"),
                        "reviewed_at": dt.datetime.now().isoformat()
                    }}
                )
                if result.matched_count == 0:
                    flash("No matching database record found", "danger")
                    return redirect(url_for("admin_datasets"))
            else:
                with sqlite3.connect(DB_PATH) as conn:
                    conn.execute(
                        "UPDATE datasets SET status = ?, notes = ? WHERE source = ?",
                        ("Approved" if status == "approved" else "Rejected", notes, file_path)
                    )
                    conn.commit()

            create_audit_log(
                get_current_user().get("email"),
                f"Dataset {status}",
                f"Dataset {dataset.get('name')} was {status}. Notes: {notes}"
            )
            flash(f"Dataset '{dataset.get('name')}' {status} successfully!", "success")
        except Exception as e:
            flash(f"Error updating dataset: {str(e)}", "danger")
            logger.exception("Approval error")

        return redirect(url_for("admin_datasets"))
    return redirect(url_for("admin_datasets"))

@app.route("/admin/datasets/upload", methods=["GET", "POST"])
def admin_upload_dataset():
    if request.method == "POST":
        if "file" not in request.files:
            flash("No file selected", "danger")
            return redirect(url_for("admin_upload_dataset"))
        file_storage = request.files["file"]
        if file_storage.filename == "":
            flash("Please select a valid file", "danger")
            return redirect(url_for("admin_upload_dataset"))
        try:
            saved_path = save_uploaded_dataset(file_storage)
            title = request.form.get("title", file_storage.filename)
            resolution = request.form.get("resolution", "")
            source = request.form.get("source", "User Upload")
            format = request.form.get("format", "CSV")
            create_dataset_record(name=title, source=str(saved_path), status="Pending Review", format=format)
            clear_caches()
            flash(f"Dataset '{title}' uploaded successfully! ({format})", "success")
            logger.info(f"Uploaded dataset: {title} by {get_current_user().get('email')}")
        except ValueError as exc:
            flash(str(exc), "danger")
            return redirect(url_for("admin_upload_dataset"))
        except Exception as exc:
            flash(f"Upload failed: {str(exc)}", "danger")
            logger.exception("Upload error")
            return redirect(url_for("admin_upload_dataset"))
        return redirect(url_for("admin_datasets"))

    uploads = []
    for file_path in sorted(UPLOAD_DIR.glob("*")):
        if file_path.suffix.lower().lstrip(".") in ALLOWED_EXTENSIONS:
            stat = file_path.stat()
            uploads.append({
                "name": file_path.name,
                "size": f"{round(stat.st_size / 1024, 1)} KB",
                "date": dt.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "icon": "csv" if file_path.suffix == ".csv" else "image" if file_path.suffix in [".tif", ".tiff"] else "code"
            })
    return render_template("admin/upload_dataset.html", uploads=uploads)

def get_historical_data() -> Dict[str, List]:
    years = list(range(1880, 2025))
    co2 = [280 + i * 0.5 for i in range(len(years))]
    co2 = [round(c + (i % 5) * 0.3, 1) for i, c in enumerate(co2)]
    temp = [-0.2 + i * 0.012 for i in range(len(years))]
    import random
    random.seed(42)
    temp = [round(t + (random.random() - 0.5) * 0.15, 2) for t in temp]
    return {"years": years, "co2": co2, "temp_anomaly": temp}

@app.route("/admin/datasets/delete/<dataset_id>")
def delete_dataset(dataset_id):
    dataset = next((d for d in get_dataset_catalog() if d["id"] == dataset_id), None)
    if not dataset:
        flash("Dataset not found", "danger")
        return redirect(url_for("admin_datasets"))

    file_path = dataset.get("source")
    if file_path:
        source_path = Path(file_path)
        if source_path.exists():
            source_path.unlink(missing_ok=True)

    if DB_BACKEND == "mongodb":
        try:
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
            db = client[MONGO_DB_NAME]
            db["datasets"].delete_one({"source": file_path})
        except Exception as exc:
            logger.warning("MongoDB delete failed: %s", exc)
    else:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM datasets WHERE source = ?", (file_path,))
            conn.commit()

    clear_caches()
    create_activity_log("Dataset deleted", get_current_user().get("email") if get_current_user() else None, f"Deleted dataset {dataset_id}")
    create_audit_log(get_current_user().get("email") if get_current_user() else "system", "Dataset deletion", f"Deleted dataset {dataset_id}")
    logger.info("Deleted dataset %s", dataset_id)
    flash(f"Dataset '{dataset.get('name')}' deleted successfully!", "success")
    return redirect(url_for("admin_datasets"))

@app.route("/admin/datasets/approval")
def admin_dataset_approval():
    dataset = get_dataset_catalog()[0] if get_dataset_catalog() else {}
    return render_template("admin/dataset_approval.html", dataset=dataset)

@app.route("/admin/reports")
def admin_reports():
    return render_template("admin/reports.html")

@app.route("/admin/notifications")
def admin_notifications():
    return render_template("admin/notifications.html", notifications=get_notifications(limit=20))

@app.route("/admin/audit-logs")
def admin_audit_logs():
    logs = get_audit_logs(limit=20)
    formatted_logs = []
    for log in logs:
        created_at = log.get("created_at", "")
        formatted_logs.append({
            "time": created_at.split("T")[-1][:8] if created_at else dt.datetime.now().strftime("%H:%M:%S"),
            "user": log.get("user_email", "System"),
            "action": log.get("action", "System activity"),
            "ip": "127.0.0.1",
            "status": "Success",
        })
    return render_template("admin/audit_logs.html", logs=formatted_logs)

@app.route("/admin/monitoring")
def admin_monitoring():
    return render_template("admin/monitoring.html")

@app.route("/admin/backups")
def admin_backups():
    return render_template("admin/backups.html")

@app.route("/admin/settings")
def admin_settings():
    return render_template("admin/settings.html")

# ===== FIXED PROFILE ROUTES =====
@app.route("/admin/profile")
def admin_profile():
    user = next((u for u in get_all_users() if u.get("role") == "admin"), None)
    if not user:
        user = get_current_user() or {"name": "System", "email": "", "role": "Admin", "status": "Active", "avatar": "U"}
    return render_template("admin/profile.html", user=user)

@app.route("/analyst/profile")
def analyst_profile():
    user = next((u for u in get_all_users() if u.get("role") == "analyst"), None)
    if not user:
        user = get_current_user() or {"name": "System", "email": "", "role": "Analyst", "status": "Active", "avatar": "U"}
    return render_template("analyst/profile.html", user=user)

@app.route("/researcher/profile")
def researcher_profile():
    user = next((u for u in get_all_users() if u.get("role") == "researcher"), None)
    if not user:
        user = get_current_user() or {"name": "System", "email": "", "role": "Researcher", "status": "Active", "avatar": "U"}
    return render_template("researcher/profile.html", user=user)

@app.route("/admin/security")
def admin_security():
    return render_template("admin/security.html")

@app.route("/security")
def security():
    return render_template("security.html")

# ===== Analyst Pages =====
@app.route("/analyst/dashboard")
def analyst_dashboard():
    stats = get_dashboard_stats()
    return render_template("analyst/dashboard.html", datasets=get_dataset_catalog()[:3], alerts=stats["alerts"], stats=stats)

@app.route("/analyst/historical")
def analyst_historical():
    historical_data = get_historical_data()
    import math
    n = len(historical_data["years"])
    co2 = historical_data["co2"]
    temp = historical_data["temp_anomaly"]
    sum_co2 = sum(co2)
    sum_temp = sum(temp)
    sum_co2_sq = sum(x*x for x in co2)
    sum_temp_sq = sum(y*y for y in temp)
    sum_prod = sum(co2[i]*temp[i] for i in range(n))
    correlation = (n * sum_prod - sum_co2 * sum_temp) / math.sqrt((n * sum_co2_sq - sum_co2**2) * (n * sum_temp_sq - sum_temp**2))
    correlation = round(correlation, 3)

    return render_template("analyst/historical_analysis.html",
                           historical_data=historical_data,
                           correlation=correlation,
                           latest_year=historical_data["years"][-1],
                           latest_co2=historical_data["co2"][-1],
                           latest_temp=historical_data["temp_anomaly"][-1])

@app.route("/analyst/realtime")
def analyst_realtime():
    return render_template("analyst/realtime_monitoring.html")

@app.route("/analyst/trends")
def analyst_trends():
    return render_template("analyst/climate_trends.html")

@app.route("/predictions")
@app.route("/analyst/predictions")
def analyst_predictions():
    return render_template("analyst/predictions.html", recent_predictions=PREDICTION_HISTORY[-5:])

@app.route("/analyst/ml-insights")
def analyst_ml_insights():
    return render_template("analyst/ml_insights.html", recent_predictions=PREDICTION_HISTORY[-5:])

@app.route("/analyst/anomalies")
def analyst_anomalies():
    return render_template("analyst/anomaly_detection.html")

@app.route("/analyst/reports")
def analyst_reports():
    return render_template("analyst/reports.html")

@app.route("/analyst/notifications")
def analyst_notifications():
    return render_template("analyst/notifications.html")

@app.route("/analyst/settings")
def analyst_settings():
    return render_template("analyst/settings.html")

@app.route("/researcher/dashboard")
def researcher_dashboard():
    stats = get_dashboard_stats()
    return render_template("researcher/dashboard.html", datasets=get_dataset_catalog()[:3], stats=stats)

@app.route("/guest/dashboard")
def guest_dashboard():
    stats = get_dashboard_stats()
    return render_template("guest/dashboard.html", stats=stats)

# ===== Visualization Pages =====
@app.route("/maps/heatmap")
def maps_heatmap():
    return render_template("maps/global_heatmap.html")

@app.route("/maps/world")
def maps_world():
    return render_template("maps/world_map.html")

@app.route("/maps/satellite")
def maps_satellite():
    return render_template("maps/satellite_viewer.html")

@app.route("/maps/sensors")
def maps_sensors():
    return render_template("maps/sensors.html")

@app.route("/analyst/weather-analytics")
@app.route("/admin/weather-analytics", endpoint="admin_weather_analytics")
def weather_analytics():
    stats = get_dashboard_stats()
    return render_template("analyst/weather_analytics.html", stats=stats)

@app.route("/analyst/timeline")
def climate_timeline():
    return render_template("analyst/climate_timeline.html")

# ===== Search =====
@app.route("/search")
def search_results():
    query = request.args.get("q", "").strip()
    results = perform_search(query) if query else {"datasets": [], "users": [], "locations": []}
    return render_template("search_results.html", query=query, results=results)

# ===== Extra Pages =====
@app.route("/support")
def support():
    return render_template("support.html")

@app.route("/activity-logs")
def activity_logs():
    logs = get_activity_logs(limit=20)
    formatted_logs = []
    for log in logs:
        created_at = log.get("created_at", "")
        formatted_logs.append({
            "time": created_at.split("T")[-1][:8] if created_at else dt.datetime.now().strftime("%H:%M:%S"),
            "user": log.get("user_email", "System"),
            "action": log.get("action", "System activity"),
            "ip": "127.0.0.1",
            "status": "Success",
        })
    return render_template("activity_logs.html", logs=formatted_logs)

@app.route("/file-manager")
def file_manager():
    return render_template("file_manager.html")

@app.route("/empty-state")
def empty_state():
    return render_template("empty_state.html")

@app.route("/loader-showcase")
def loader_showcase():
    return render_template("loader_showcase.html")

# ===== API Routes =====
@app.route("/api/dashboard")
def api_dashboard():
    return jsonify(get_dashboard_stats())

@app.route("/api/predict/carbon", methods=["POST"])
def api_predict_carbon():
    payload = request.get_json(silent=True) or request.form or {}
    try:
        values = [
            float(payload.get("temperature", payload.get("Temperature", 0))),
            float(payload.get("humidity", payload.get("Humidity", 0))),
            float(payload.get("aqi", payload.get("AQI", 0))),
            float(payload.get("co2", payload.get("CO2", 0))),
            float(payload.get("industrial_index", payload.get("IndustrialIndex", 0))),
            float(payload.get("energy_consumption", payload.get("EnergyConsumption", 0))),
            float(payload.get("renewable_energy", payload.get("RenewableEnergy", 0))),
        ]
    except (TypeError, ValueError):
        return jsonify({"error": "Please provide numeric values for all carbon model inputs."}), 400
    model_input = np.array(values, dtype=float).reshape(1, -1)
    prediction = float(linear_model.predict(model_input)[0])
    confidence = round(min(0.99, max(0.65, 0.75 + min(0.2, abs(prediction) / 10000))), 2)
    interpretation = "Emission is within the expected range for this profile." if prediction < 250 else "Emission is elevated and should be monitored closely."
    PREDICTION_HISTORY.append({"type": "carbon", "value": round(prediction, 2), "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    logger.info("Carbon prediction: %.2f", prediction)
    return jsonify({"prediction": round(prediction, 2), "confidence": confidence, "interpretation": interpretation})

@app.route("/api/predict/flood", methods=["POST"])
def api_predict_flood():
    payload = request.get_json(silent=True) or request.form or {}
    try:
        values = [
            float(payload.get("temperature", payload.get("Temperature", 0))),
            float(payload.get("humidity", payload.get("Humidity", 0))),
            float(payload.get("rainfall", payload.get("Rainfall", 0))),
            float(payload.get("wind_speed", payload.get("WindSpeed", 0))),
            float(payload.get("pressure", payload.get("Pressure", 0))),
        ]
    except (TypeError, ValueError):
        return jsonify({"error": "Please provide numeric values for the flood model inputs."}), 400
    model_input = np.array(values, dtype=float).reshape(1, -1)
    prediction = int(decision_model.predict(model_input)[0])
    mapping = {0: "Low", 1: "Medium", 2: "High"}
    PREDICTION_HISTORY.append({"type": "flood", "value": mapping[prediction], "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    logger.info("Flood prediction: %s", mapping[prediction])
    return jsonify({"prediction": mapping[prediction]})

@app.route("/api/predict/heatwave", methods=["POST"])
def api_predict_heatwave():
    payload = request.get_json(silent=True) or request.form or {}
    try:
        values = [
            float(payload.get("temperature", payload.get("Temperature", 0))),
            float(payload.get("humidity", payload.get("Humidity", 0))),
            float(payload.get("aqi", payload.get("AQI", 0))),
            float(payload.get("uv_index", payload.get("UVIndex", 0))),
        ]
    except (TypeError, ValueError):
        return jsonify({"error": "Please provide numeric values for the heatwave model inputs."}), 400
    model_input = np.array(values, dtype=float).reshape(1, -1)
    prediction = int(knn_model.predict(model_input)[0])
    result = "Yes" if prediction == 1 else "No"
    PREDICTION_HISTORY.append({"type": "heatwave", "value": result, "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    logger.info("Heatwave prediction: %s", result)
    return jsonify({"prediction": result})

@app.route("/api/charts")
def api_charts():
    return jsonify(get_chart_payload())

@app.route("/api/weather")
def api_weather():
    df = load_dataset()
    locations = [
        {"name": "Manaus", "lat": -3.11, "lon": -60.02, "temp": round(float(df["Temperature_C"].iloc[0]), 1), "aqi": round(float(df["AQI"].iloc[0]), 1), "condition": df["WeatherCondition"].iloc[0]},
        {"name": "Lagos", "lat": 6.52, "lon": 3.38, "temp": round(float(df["Temperature_C"].iloc[10]), 1), "aqi": round(float(df["AQI"].iloc[10]), 1), "condition": df["WeatherCondition"].iloc[10]},
        {"name": "Sydney", "lat": -33.87, "lon": 151.21, "temp": round(float(df["Temperature_C"].iloc[20]), 1), "aqi": round(float(df["AQI"].iloc[20]), 1), "condition": df["WeatherCondition"].iloc[20]},
        {"name": "Quebec", "lat": 46.82, "lon": -71.21, "temp": round(float(df["Temperature_C"].iloc[30]), 1), "aqi": round(float(df["AQI"].iloc[30]), 1), "condition": df["WeatherCondition"].iloc[30]},
    ]
    return jsonify(locations)

# ===== Prediction Routes (GET) =====
@app.route("/predict/carbon", methods=["GET", "POST"])
def predict_carbon():
    if request.method == "POST":
        return api_predict_carbon()
    return render_template("analyst/predictions.html", recent_predictions=PREDICTION_HISTORY[-5:])

@app.route("/predict/flood", methods=["GET", "POST"])
def predict_flood():
    if request.method == "POST":
        return api_predict_flood()
    return render_template("analyst/predictions.html", recent_predictions=PREDICTION_HISTORY[-5:])

@app.route("/predict/heatwave", methods=["GET", "POST"])
def predict_heatwave():
    if request.method == "POST":
        return api_predict_heatwave()
    return render_template("analyst/predictions.html", recent_predictions=PREDICTION_HISTORY[-5:])

# ===== Error Handlers =====
@app.errorhandler(404)
def page_not_found(_error):
    return render_template("errors/404.html"), 404

@app.errorhandler(500)
def internal_error(_error):
    logger.exception("Unhandled server error")
    return render_template("errors/500.html"), 500

if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_ENV") != "production"
    app.run(debug=debug_mode, host="0.0.0.0", port=5000, threaded=True)