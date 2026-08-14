from __future__ import annotations

import secrets
from datetime import datetime

from flask import Blueprint, redirect, render_template, request, session, url_for

from controllers import auth_controller_v2 as auth_ctrl
from middleware.auth import login_required, role_required
from services.data_service import DataService
from utils.helpers import now_iso


main_bp = Blueprint("main", __name__)


def generate_csrf_token() -> str:
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(16)
    return session["_csrf_token"]


@main_bp.context_processor
def inject_global_vars():
    user = session.get("user")
    data_service = DataService()
    try:
        stats = data_service.get_dashboard_metrics()
    except Exception:
        stats = {
            "total_users": 0,
            "total_predictions": 0,
            "average_aqi": 0,
            "average_co2": 0,
            "recent_predictions": [],
            "top_polluted_cities": [],
            "weather_summary": [],
            "alerts": [],
        }
    alerts = stats.get("alerts", [])
    return {
        "current_user": user,
        "csrf_token": generate_csrf_token(),
        "notifications": alerts,
        "unread_notifications_count": len(alerts),
        "current_year": datetime.now().year,
        "current_time": now_iso(),
    }


@main_bp.route("/")
def index():
    user = session.get("user")
    if user:
        role = (user.get("role") or "").strip().lower()
        if role == "admin":
            return redirect(url_for("main.admin_dashboard"))
        if role == "analyst":
            return redirect(url_for("main.analyst_dashboard"))
        if role == "researcher":
            return redirect(url_for("main.researcher_dashboard"))
        if role == "guest":
            return redirect(url_for("main.guest_dashboard"))
    return render_template("landing/index.html")


@main_bp.route("/about")
def about():
    return render_template("about.html")


@main_bp.route("/contact")
def contact():
    return render_template("contact.html")


@main_bp.route("/faq")
def faq():
    return render_template("faq.html")


@main_bp.route("/empty-state")
def empty_state():
    return render_template("empty_state.html")


@main_bp.route("/activity-logs")
@login_required
def activity_logs():
    return render_template("activity_logs.html")


@main_bp.route("/unauthorized")
def unauthorized():
    return render_template("errors/unauthorized.html"), 401


@main_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        return auth_ctrl.login()
    return render_template("auth/login.html")


@main_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        return auth_ctrl.register()
    return render_template("auth/register.html")


@main_bp.route("/logout")
def logout():
    return auth_ctrl.logout()


@main_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        return auth_ctrl.forgot_password()
    return render_template("auth/forgot_password.html")


@main_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        return auth_ctrl.reset_password()
    return render_template("auth/reset_password.html")


@main_bp.route("/admin/dashboard")
@role_required("admin")
def admin_dashboard():
    service = DataService()
    stats = service.get_dashboard_metrics()
    users = service.find_documents("users", limit=5)
    datasets = service.find_documents("datasets", limit=5)
    audits = service.find_documents("audit_logs", sort={"created_at": -1}, limit=5)
    return render_template("admin/dashboard.html", users=users, datasets=datasets, audits=audits, stats=stats)


@main_bp.route("/admin/users")
@role_required("admin")
def admin_users():
    service = DataService()
    users = service.find_documents("users")
    return render_template("admin/users.html", users=users)


@main_bp.route("/admin/users/add")
@role_required("admin")
def admin_add_user():
    return render_template("admin/add_user.html")


@main_bp.route("/admin/users/edit")
@role_required("admin")
def admin_edit_user():
    return render_template("admin/edit_user.html", user=session.get("user") or {})


@main_bp.route("/admin/roles")
@role_required("admin")
def admin_roles():
    return render_template("admin/roles.html")


@main_bp.route("/admin/datasets")
@role_required("admin", "analyst")
def admin_datasets():
    service = DataService()
    datasets = service.find_documents("datasets", sort={"created_at": -1}, limit=50)
    return render_template("admin/datasets.html", datasets=datasets)


@main_bp.route("/admin/datasets/upload")
@role_required("admin", "analyst")
def admin_upload_dataset():
    return render_template("admin/upload_dataset.html")


@main_bp.route("/admin/datasets/approval")
@role_required("admin", "analyst")
def admin_dataset_approval():
    return render_template("admin/dataset_approval.html")


@main_bp.route("/admin/reports")
@role_required("admin", "analyst")
def admin_reports():
    return render_template("admin/reports.html")


@main_bp.route("/admin/notifications")
@login_required
def admin_notifications():
    return render_template("admin/notifications.html")


@main_bp.route("/admin/audit-logs")
@role_required("admin")
def admin_audit_logs():
    return render_template("admin/audit_logs.html")


@main_bp.route("/admin/monitoring")
@role_required("admin")
def admin_monitoring():
    return render_template("admin/monitoring.html")


@main_bp.route("/admin/backups")
@role_required("admin")
def admin_backups():
    return render_template("admin/backups.html")


@main_bp.route("/admin/settings")
@role_required("admin")
def admin_settings():
    return render_template("admin/settings.html")


@main_bp.route("/admin/profile")
@login_required
def admin_profile():
    return render_template("admin/profile.html", user=session.get("user") or {})


@main_bp.route("/analyst/dashboard")
@role_required("admin", "analyst")
def analyst_dashboard():
    service = DataService()
    stats = service.get_dashboard_metrics()
    datasets = service.find_documents("datasets", sort={"created_at": -1}, limit=3)
    try:
        alerts = service.find_documents("alerts", sort={"created_at": -1}, limit=2)
    except Exception:
        alerts = []
    from services.hadoop_service import hadoop_service
    try:
        hadoop_stations = hadoop_service.get_station_analytics()
        hadoop_risk = hadoop_service.get_risk_analytics()
    except Exception:
        hadoop_stations = {"stations": [], "count": 0}
        hadoop_risk = {"flood_risk_summary": {}, "heatwave_summary": {}, "total_stations": 0}
    return render_template(
        "analyst/dashboard.html",
        datasets=datasets,
        alerts=alerts,
        stats=stats,
        hadoop_stations=hadoop_stations,
        hadoop_risk=hadoop_risk,
    )


@main_bp.route("/analyst/predictions")
@role_required("admin", "analyst")
def analyst_predictions():
    service = DataService()
    history = service.find_documents("prediction_history", sort={"timestamp": -1}, limit=10)
    return render_template("analyst/predictions.html", recent_predictions=history)


@main_bp.route("/analyst/ml-insights")
@role_required("admin", "analyst")
def analyst_ml_insights():
    return render_template("analyst/ml_insights.html")


@main_bp.route("/analyst/anomalies")
@role_required("admin", "analyst")
def analyst_anomalies():
    return render_template("analyst/anomaly_detection.html")


@main_bp.route("/analyst/reports")
@role_required("admin", "analyst")
def analyst_reports():
    return render_template("analyst/reports.html")


@main_bp.route("/analyst/notifications")
@login_required
def analyst_notifications():
    return render_template("analyst/notifications.html")


@main_bp.route("/analyst/profile")
@login_required
def analyst_profile():
    return render_template("analyst/profile.html", user=session.get("user") or {})


@main_bp.route("/analyst/settings")
@login_required
def analyst_settings():
    return render_template("analyst/settings.html")


@main_bp.route("/analyst/trends")
@role_required("admin", "analyst", "researcher")
def analyst_trends():
    return render_template("analyst/climate_trends.html")


@main_bp.route("/analyst/climate-timeline")
@role_required("admin", "analyst", "researcher")
def analyst_climate_timeline():
    return render_template("analyst/climate_timeline.html")


@main_bp.route("/analyst/weather-analytics")
@role_required("admin", "analyst", "researcher")
def analyst_weather_analytics():
    return render_template("analyst/weather_analytics.html")


@main_bp.route("/search")
@login_required
def search_results():
    return render_template("search_results.html")


@main_bp.route("/maps/global-heatmap")
@role_required("admin", "analyst", "researcher")
def maps_global_heatmap():
    return render_template("maps/global_heatmap.html")


@main_bp.route("/maps/satellite-viewer")
@role_required("admin", "analyst", "researcher")
def maps_satellite_viewer():
    return render_template("maps/satellite_viewer.html")


@main_bp.route("/maps/sensors")
@role_required("admin", "analyst", "researcher")
def maps_sensors():
    return render_template("maps/sensors.html")


@main_bp.route("/maps/world-map")
@role_required("admin", "analyst", "researcher")
def maps_world_map():
    return render_template("maps/world_map.html")


@main_bp.route("/predict/carbon", methods=["GET", "POST"])
@role_required("admin", "analyst")
def predict_carbon():
    if request.method == "POST":
        from controllers.predictions_controller import predict_carbon
        return predict_carbon()
    service = DataService()
    history = service.find_documents("prediction_history", sort={"timestamp": -1}, limit=10)
    return render_template("analyst/predictions.html", recent_predictions=history)


@main_bp.route("/researcher/dashboard")
@role_required("admin", "analyst", "researcher")
def researcher_dashboard():
    service = DataService()
    stats = service.get_dashboard_metrics()
    datasets = service.find_documents("datasets", sort={"created_at": -1}, limit=3)
    return render_template("researcher/dashboard.html", datasets=datasets, stats=stats)


@main_bp.route("/guest/dashboard")
@role_required("admin", "analyst", "researcher", "guest")
def guest_dashboard():
    service = DataService()
    stats = service.get_dashboard_metrics()
    return render_template("guest/dashboard.html", stats=stats)
