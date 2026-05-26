from flask import Blueprint, request, jsonify, g
from utils import require_auth
from datetime import datetime, timezone, timedelta
from extensions import SessionLocal
from models.user import User
import json, os

location_bp = Blueprint("location", __name__)
VN_TZ = timezone(timedelta(hours=7))

# Lưu vào file thay vì memory
_LOC_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "live_locations.json")

def _read():
    try:
        with open(_LOC_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def _write(data):
    with open(_LOC_FILE, "w") as f:
        json.dump(data, f)

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

    locs = _read()
    locs[str(g.user_id)] = {
        "lat":        lat,
        "lon":        lon,
        "full_name":  full_name,
        "role":       g.role,
        "updated_at": datetime.now(VN_TZ).isoformat(),
    }
    _write(locs)
    return jsonify({"ok": True})

@location_bp.get("/live")
@require_auth
def live():
    if g.role not in ("admin", "manager"):
        return jsonify({"error": "Không có quyền"}), 403
    return jsonify(list(_read().values()))