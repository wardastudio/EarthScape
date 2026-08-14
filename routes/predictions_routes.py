from __future__ import annotations

from flask import Blueprint

from controllers import predictions_controller as pred_ctrl
from middleware.auth import login_required, role_required


predictions_bp = Blueprint("predictions_api", __name__, url_prefix="/api/predictions")


predictions_bp.get("/models")(pred_ctrl.list_models)
predictions_bp.get("/history")(login_required(pred_ctrl.prediction_history))
predictions_bp.get("/accuracy")(pred_ctrl.prediction_accuracy)

predictions_bp.post("/predict")(login_required(pred_ctrl.predict))
predictions_bp.post("/carbon")(login_required(pred_ctrl.predict_carbon))
predictions_bp.post("/severity")(login_required(pred_ctrl.predict_severity))
predictions_bp.post("/heatwave")(login_required(pred_ctrl.predict_heatwave))
predictions_bp.post("/all")(login_required(pred_ctrl.predict_all))

predictions_bp.post("/models/<model_name>/evaluate")(role_required("analyst")(pred_ctrl.evaluate_model))
predictions_bp.post("/models/<model_name>/train")(role_required("analyst")(pred_ctrl.train_model))
