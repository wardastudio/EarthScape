import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "earthscape-climate-secret-key-change-in-production")
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017")
    MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "earthscape")
    MODEL_DIR = BASE_DIR / "models"
    DATA_DIR = BASE_DIR / "data"
    UPLOAD_DIR = BASE_DIR / "uploads"
    LOG_DIR = BASE_DIR / "logs"
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    ALLOWED_EXTENSIONS = {"csv", "xlsx", "xls", "png", "jpg", "jpeg", "pdf", "geojson"}
    RATE_LIMIT = int(os.getenv("RATE_LIMIT", "120"))
    JWT_SECRET = os.getenv("JWT_SECRET", "earthscape-jwt-secret-change-in-production")
    JWT_REFRESH_SECRET = os.getenv("JWT_REFRESH_SECRET", "earthscape-jwt-refresh-change-in-production")
    JWT_ACCESS_TTL = int(os.getenv("JWT_ACCESS_TTL", "3600"))
    JWT_REFRESH_TTL = int(os.getenv("JWT_REFRESH_TTL", "604800"))
    OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
    COPERNICUS_CLIENT_ID = os.getenv("COPERNICUS_CLIENT_ID", "")
    COPERNICUS_CLIENT_SECRET = os.getenv("COPERNICUS_CLIENT_SECRET", "")
    COPERNICUS_USERNAME = os.getenv("COPERNICUS_USERNAME", "")
    COPERNICUS_PASSWORD = os.getenv("COPERNICUS_PASSWORD", "")
    COPERNICUS_OAUTH_TOKEN_URL = os.getenv(
        "COPERNICUS_OAUTH_TOKEN_URL",
        "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token",
    )
    COPERNICUS_STAC_SEARCH_URL = os.getenv(
        "COPERNICUS_STAC_SEARCH_URL",
        "https://stac.dataspace.copernicus.eu/v1/search",
    )
    COPERNICUS_STAC_COLLECTION = os.getenv("COPERNICUS_STAC_COLLECTION", "ccm-optical")
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")
    HADOOP_HOME = os.getenv("HADOOP_HOME", "")
    HADOOP_STREAMING_JAR = os.getenv("HADOOP_STREAMING_JAR", "")
    ENV = os.getenv("FLASK_ENV", "development")
    TESTING = False
