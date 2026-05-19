import math, jwt
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import request, jsonify, g
import config

def create_token(user_id: str, role: str) -> str:
    payload = {"sub": user_id, "role": role}
    # Admin: token khong het han
    if role != "admin":
        payload["exp"] = datetime.now(timezone.utc) + timedelta(minutes=config.JWT_ACCESS_EXPIRE_MINUTES)
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        h = request.headers.get("Authorization", "")
        if not h.startswith("Bearer "):
            return jsonify({"error": "Chua dang nhap"}), 401
        try:
            p = jwt.decode(h[7:], config.JWT_SECRET, algorithms=["HS256"])
            g.user_id = p["sub"]
            g.role    = p["role"]
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Phien da het han"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Token khong hop le"}), 401
        return f(*args, **kwargs)
    return decorated

def haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin(math.radians(lat2-lat1)/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(math.radians(lon2-lon1)/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def check_radius(ulat, ulon, slat, slon):
    if slat is None or slon is None:
        return True, 0.0
    d = haversine(ulat, ulon, slat, slon)
    return d <= config.CHECKIN_RADIUS_METERS, round(d, 1)
