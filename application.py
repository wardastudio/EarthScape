from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config
from database import ensure_indexes
from utils.errors import AppError
from utils.helpers import get_client_ip
from utils.logging_setup import log_api_request, setup_logger


def create_app(config_class: Any = Config) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(config_class)
    app.json.ensure_ascii = False

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)

    origins = app.config.get("CORS_ORIGINS", "*")
    if origins == "*":
        CORS(app, resources={r"/api/*": {"origins": "*", "supports_credentials": False}})
    else:
        CORS(app, resources={r"/api/*": {"origins": origins.split(","), "supports_credentials": True}})

    os.makedirs(app.config["UPLOAD_DIR"], exist_ok=True)
    os.makedirs(app.config["LOG_DIR"], exist_ok=True)
    os.makedirs(app.config["DATA_DIR"], exist_ok=True)

    setup_logger("earthscape", level=logging.INFO)
    app.logger.setLevel(logging.INFO)

    from routes.main import main_bp
    from routes.auth_routes import auth_bp
    from routes.weather_routes import weather_bp
    from routes.predictions_routes import predictions_bp
    from routes.analytics_routes import analytics_bp
    from routes.alerts_routes import alerts_bp
    from routes.profile_routes import profile_bp
    from routes.admin_routes import admin_bp
    from routes.hadoop_routes import hadoop_bp
    from routes.satellite_routes import satellite_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(weather_bp)
    app.register_blueprint(predictions_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(alerts_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(hadoop_bp)
    app.register_blueprint(satellite_bp)

    @app.before_request
    def _before_request() -> None:
        request._start_time = time.perf_counter()
        request._client_ip = get_client_ip()
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.path.startswith("/api/"):
            pass
        if not request.path.startswith("/static/") and not request.path.startswith("/uploads/"):
            pass

    @app.after_request
    def _after_request(response):
        duration_ms = 0.0
        if hasattr(request, "_start_time"):
            duration_ms = int((time.perf_counter() - request._start_time) * 1000)
        if not request.path.startswith("/static/") and not request.path.startswith("/uploads/"):
            user_id = None
            try:
                from flask import session, g
                user_id = getattr(g, "user_id", None) or (session.get("user") or {}).get("id")
            except Exception:
                pass
            error = None
            if response.status_code >= 400:
                error = f"HTTP {response.status_code}"
            log_api_request(
                method=request.method,
                endpoint=request.path,
                status_code=response.status_code,
                response_time_ms=duration_ms,
                user_id=user_id,
                ip=getattr(request, "_client_ip", None),
                error=error,
            )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["X-Response-Time-Ms"] = str(duration_ms)
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return response

    @app.errorhandler(AppError)
    def _handle_app_error(exc: AppError):
        app.logger.error("AppError %s: %s | %s", exc.status_code, exc.error_type, exc.message)
        if request.path.startswith("/api/") or request.is_json:
            return jsonify(exc.to_dict()), exc.status_code
        try:
            if exc.status_code == 404:
                return render_template("errors/404.html"), 404
            if exc.status_code in {401, 403}:
                return render_template("errors/unauthorized.html"), exc.status_code
            return render_template("errors/500.html"), 500
        except Exception:
            return jsonify(exc.to_dict()), exc.status_code

    @app.errorhandler(HTTPException)
    def _handle_http_exception(exc: HTTPException):
        code = exc.code or 500
        message = exc.description or str(exc)
        if code == 404:
            error_type = "not_found"
        elif code == 401:
            error_type = "authentication_error"
        elif code == 403:
            error_type = "forbidden"
        elif code == 422:
            error_type = "validation_error"
        elif code == 429:
            error_type = "too_many_requests"
        else:
            error_type = "http_error"
        if code >= 500:
            app.logger.exception("HTTPException %s: %s", code, message)
        if request.path.startswith("/api/") or request.is_json:
            return jsonify({"error": error_type, "message": message}), code
        try:
            if code == 404:
                return render_template("errors/404.html"), 404
            if code in {401, 403}:
                return render_template("errors/unauthorized.html"), code
            return render_template("errors/500.html"), code
        except Exception:
            return jsonify({"error": error_type, "message": message}), code

    @app.errorhandler(Exception)
    def _handle_unexpected(exc: Exception):
        app.logger.exception("Unhandled exception: %s", exc)
        if request.path.startswith("/api/") or request.is_json:
            return jsonify({"error": "internal_error", "message": "An unexpected error occurred."}), 500
        try:
            return render_template("errors/500.html"), 500
        except Exception:
            return jsonify({"error": "internal_error", "message": "An unexpected error occurred."}), 500

    @app.get("/health")
    def _health_check():
        from database import get_db
        db_status = "unknown"
        try:
            db = get_db()
            db.command("ping")
            db_status = "ok"
        except Exception as exc:
            app.logger.error("Health check DB error: %s", exc)
            db_status = f"error: {exc}"
        return jsonify({
            "status": "ok" if db_status == "ok" else "degraded",
            "database": db_status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": "2.0.0",
        }), 200 if db_status == "ok" else 503

    try:
        ensure_indexes()
        app.logger.info("Database indexes and seed data ensured successfully.")
    except Exception as exc:
        app.logger.warning("Database initialization deferred (MongoDB not available?): %s", exc)

    return app


app = create_app()


if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "1") == "1"
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", "5000"))
    app.run(debug=debug, host=host, port=port)
