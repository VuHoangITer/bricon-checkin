import bcrypt
from flask import Blueprint, request, jsonify, g
from extensions import SessionLocal
from models.user import User, UserRole
from utils import create_token, require_auth

auth_bp = Blueprint("auth", __name__)

@auth_bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username or not password:
        return jsonify({"error": "Thieu username hoac password"}), 400
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(username=username, is_active=True).first()
        if not user or not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
            return jsonify({"error": "Sai tai khoan hoac mat khau"}), 401
        return jsonify({
            "access_token": create_token(str(user.id), user.role.value),
            "user": {"id": str(user.id), "username": user.username,
                     "full_name": user.full_name, "role": user.role.value}
        })
    finally:
        db.close()

@auth_bp.get("/me")
@require_auth
def me():
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(id=g.user_id).first()
        if not user:
            return jsonify({"error": "Khong tim thay"}), 404
        return jsonify({"id": str(user.id), "username": user.username,
                        "full_name": user.full_name, "role": user.role.value, "phone": user.phone})
    finally:
        db.close()

@auth_bp.get("/users")
@require_auth
def list_users():
    if g.role not in ("admin", "manager"):
        return jsonify({"error": "Khong co quyen"}), 403
    db = SessionLocal()
    try:
        users = db.query(User).filter_by(is_active=True).order_by(User.full_name).all()
        return jsonify([{"id": str(u.id), "username": u.username,
                         "full_name": u.full_name, "role": u.role.value, "phone": u.phone} for u in users])
    finally:
        db.close()

@auth_bp.post("/register")
@require_auth
def register():
    if g.role not in ("admin", "manager"):
        return jsonify({"error": "Khong co quyen"}), 403
    data = request.get_json(silent=True) or {}
    if not all(data.get(k) for k in ["username", "full_name", "password", "role"]):
        return jsonify({"error": "Thieu thong tin"}), 400
    db = SessionLocal()
    try:
        if db.query(User).filter_by(username=data["username"]).first():
            return jsonify({"error": "Username da ton tai"}), 409
        pw = bcrypt.hashpw(data["password"].encode(), bcrypt.gensalt()).decode()
        user = User(username=data["username"], full_name=data["full_name"],
                    phone=data.get("phone"), password_hash=pw, role=data["role"])
        db.add(user)
        db.commit()
        return jsonify({"id": str(user.id), "username": user.username}), 201
    finally:
        db.close()


@auth_bp.put("/users/<user_id>")
@require_auth
def update_user(user_id):
    if g.role not in ("admin", "manager"):
        return jsonify({"error": "Khong co quyen"}), 403
    data = request.get_json(silent=True) or {}
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(id=user_id).first()
        if not user:
            return jsonify({"error": "Khong tim thay nguoi dung"}), 404
        if data.get("full_name"):  user.full_name = data["full_name"].strip()
        if "phone" in data:        user.phone     = data["phone"].strip() or None
        if data.get("role") in ("admin", "manager", "sales", "telesales"):
            user.role = data["role"]
        if data.get("password"):
            user.password_hash = bcrypt.hashpw(
                data["password"].encode(), bcrypt.gensalt()
            ).decode()
        db.commit()
        return jsonify({
            "id":        str(user.id),
            "username":  user.username,
            "full_name": user.full_name,
            "role":      user.role.value,
            "phone":     user.phone,
        })
    finally:
        db.close()


@auth_bp.delete("/users/<user_id>")
@require_auth
def delete_user(user_id):
    if g.role not in ("admin", "manager"):
        return jsonify({"error": "Khong co quyen"}), 403
    if user_id == g.user_id:
        return jsonify({"error": "Khong the xoa chinh minh"}), 400
    db = SessionLocal()
    try:
        from models.checkin import Checkin
        user = db.query(User).filter_by(id=user_id).first()
        if not user:
            return jsonify({"error": "Khong tim thay"}), 404

        checkin_count = db.query(Checkin).filter_by(user_id=user_id).count()

        if checkin_count == 0:
            # Chua co check-in -> xoa han khoi DB
            db.delete(user)
            db.commit()
            return jsonify({"message": f"Da xoa han tai khoan {user.username}", "hard_delete": True})
        else:
            # Da co check-in -> soft delete
            user.is_active = False
            db.commit()
            return jsonify({"message": f"Tai khoan {user.username} da bi vo hieu hoa (co {checkin_count} check-in)", "hard_delete": False})
    finally:
        db.close()