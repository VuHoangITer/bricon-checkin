from flask import Blueprint, request, jsonify, g
from extensions import SessionLocal
from models.user import User
from utils import require_auth
from datetime import datetime, timezone, timedelta

location_bp = Blueprint("location", __name__)
VN_TZ = timezone(timedelta(hours=7))

_live_locations = {}

@location_bp.post("/ping")
@require_auth
def ping():
    data = request.get_json(silent=True) or {}
    lat = data.get("lat")
    lon = data.get("lon")
    if lat is None or lon is None:
        return jsonify({"error": "Thiếu tọa độ"}), 400

    db = SessionLocal()
    try:
        user = db.query(User).filter_by(id=g.user_id).first()
        full_name = user.full_name if user else "—"
    finally:
        db.close()

    _live_locations[str(g.user_id)] = {
        "lat":        lat,
        "lon":        lon,
        "full_name":  full_name,
        "role":       g.role,
        "updated_at": datetime.now(VN_TZ).isoformat(),
    }
    return jsonify({"ok": True})

@location_bp.get("/live")
@require_auth
def live():
    if g.role not in ("admin", "manager"):
        return jsonify({"error": "Không có quyền"}), 403
    return jsonify(list(_live_locations.values()))