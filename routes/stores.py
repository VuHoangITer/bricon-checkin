from flask import Blueprint, request, jsonify, g
from datetime import datetime, timezone, timedelta
from extensions import SessionLocal
from models.store      import Store, StoreType, StoreStatus
from models.assignment import Assignment
from utils import require_auth

stores_bp = Blueprint("stores", __name__)


def _user_stores(db, user_id, role):
    q = db.query(Store).filter(Store.status != StoreStatus.inactive)
    if role == "sales":
        ids = db.query(Assignment.store_id).filter_by(user_id=user_id, is_active=True).subquery()
        q = q.filter(Store.id.in_(ids))
    return q


def _auto_store_code(db, store_type: str) -> str:
    """Sinh ma cua hang tu dong: CH001, DL001, NPP001, MOI001."""
    prefix_map = {
        "retail":      "CH",
        "agent":       "DL",
        "distributor": "NPP",
        "new":         "MOI",
    }
    prefix = prefix_map.get(store_type, "CH")
    # Dem so luong store co cung prefix
    count = db.query(Store).filter(Store.store_code.like(f"{prefix}%")).count()
    # Tang dan den khi khong trung
    for i in range(count + 1, count + 9999):
        code = f"{prefix}{i:03d}"
        if not db.query(Store).filter_by(store_code=code).first():
            return code
    return f"{prefix}{count + 1:03d}"


@stores_bp.get("/geojson")
@require_auth
def geojson():
    from models.checkin  import Checkin
    from models.call_log import CallLog
    from models.settings import SystemSettings
    db = SessionLocal()
    try:
        stores = _user_stores(db, g.user_id, g.role).all()

        row_ci   = db.query(SystemSettings).filter_by(id="checkin_activity_days").first()
        row_call = db.query(SystemSettings).filter_by(id="call_activity_days").first()
        row_old  = db.query(SystemSettings).filter_by(id="activity_days").first()
        default_days   = int(row_old.value)  if row_old  else 7
        checkin_days   = int(row_ci.value)   if row_ci   else default_days
        call_days      = int(row_call.value) if row_call else default_days

        now = datetime.now(timezone.utc)
        checkin_cutoff = now - timedelta(days=checkin_days)
        call_cutoff    = now - timedelta(days=call_days)

        checked_ids = {str(r[0]) for r in db.query(Checkin.store_id).filter(Checkin.checkin_at >= checkin_cutoff).all()}
        called_ids  = {str(r[0]) for r in db.query(CallLog.store_id).filter(CallLog.called_at  >= call_cutoff).all()}

        from sqlalchemy import func

        # FIX: last_call lấy toàn bộ lịch sử, không filter cutoff
        last_call_map = {
            str(r[0]): r[1]
            for r in db.query(CallLog.store_id, func.max(CallLog.called_at))
                       .group_by(CallLog.store_id).all()
        }

        # FIX: thêm checkin_at vào map để inject last_checkin chính xác
        last_checkin_map = {}
        for r in db.query(
            Checkin.store_id, Checkin.photo_url, Checkin.photo2_url,
            Checkin.photo3_url, Checkin.photo_public_id, Checkin.checkin_at
        ).order_by(Checkin.checkin_at.desc()).all():
            sid = str(r[0])
            if sid not in last_checkin_map:
                last_checkin_map[sid] = {
                    "photo_url":        r[1],
                    "photo2_url":       r[2],
                    "photo3_url":       r[3],
                    "photo_public_id":  r[4],
                    "checkin_at":       r[5],   # ← THÊM
                }

        features = []
        for s in stores:
            if not s.latitude or not s.longitude:
                continue
            gj  = s.to_geojson()
            sid = str(s.id)
            has_checkin = sid in checked_ids
            has_call    = sid in called_ids
            if has_checkin and has_call:
                gj["properties"]["activity"] = "both"
            elif has_checkin:
                gj["properties"]["activity"] = "checkin"
            elif has_call:
                gj["properties"]["activity"] = "call"
            else:
                gj["properties"]["activity"] = "none"

            lc = last_call_map.get(sid)
            gj["properties"]["last_call"] = lc.isoformat() if lc else None

            lci = last_checkin_map.get(sid, {})
            gj["properties"]["last_photo_url"]       = lci.get("photo_url")
            gj["properties"]["last_photo2_url"]      = lci.get("photo2_url")
            gj["properties"]["last_photo3_url"]      = lci.get("photo3_url")
            gj["properties"]["last_photo_public_id"] = lci.get("photo_public_id")

            # FIX: override last_checkin bằng timestamp thực từ bảng checkins
            actual_ci = lci.get("checkin_at")
            if actual_ci:
                # Đảm bảo có timezone info trước khi isoformat
                if actual_ci.tzinfo is None:
                    actual_ci = actual_ci.replace(tzinfo=timezone.utc)
                gj["properties"]["last_checkin"] = actual_ci.isoformat()

            features.append(gj)

        return jsonify({"type": "FeatureCollection", "features": features})
    finally:
        db.close()


@stores_bp.get("/")
@require_auth
def list_stores():
    db = SessionLocal()
    try:
        from models.call_log import CallLog
        from sqlalchemy import func
        q = _user_stores(db, g.user_id, g.role)
        if t := request.args.get("type"): q = q.filter(Store.store_type == t)
        if s := request.args.get("q", "").strip():
            q = q.filter(Store.store_name.ilike(f"%{s}%") | Store.store_code.ilike(f"%{s}%"))
        stores = q.order_by(Store.store_name).all()

        last_call_map = {
            str(r[0]): r[1]
            for r in db.query(CallLog.store_id, func.max(CallLog.called_at))
                       .group_by(CallLog.store_id).all()
        }

        result = []
        for s in stores:
            props = s.to_geojson()["properties"]
            lc = last_call_map.get(str(s.id))
            props["last_call"] = lc.isoformat() if lc else None
            result.append(props)
        return jsonify(result)
    finally:
        db.close()


@stores_bp.get("/<store_id>")
@require_auth
def get_store(store_id):
    db = SessionLocal()
    try:
        store = _user_stores(db, g.user_id, g.role).filter(Store.id == store_id).first()
        if not store: return jsonify({"error": "Khong tim thay"}), 404
        return jsonify(store.to_geojson())
    finally:
        db.close()


@stores_bp.post("/check-name")
@require_auth
def check_name():
    """Kiem tra ten cua hang co bi trung khong."""
    name = (request.get_json(silent=True) or {}).get("name", "").strip()
    if not name:
        return jsonify({"duplicate": False})
    db = SessionLocal()
    try:
        exists = db.query(Store).filter(
            Store.store_name.ilike(name)
        ).first()
        return jsonify({"duplicate": bool(exists), "existing": exists.store_name if exists else None})
    finally:
        db.close()


@stores_bp.post("/auto-code")
@require_auth
def auto_code():
    """Tra ve ma cua hang tu dong theo loai."""
    store_type = (request.get_json(silent=True) or {}).get("store_type", "new")
    db = SessionLocal()
    try:
        code = _auto_store_code(db, store_type)
        return jsonify({"code": code})
    finally:
        db.close()


@stores_bp.post("/")
@require_auth
def create_store():
    if g.role == "telesales":
        return jsonify({"error": "Telesales không được tạo cửa hàng"}), 403
    data = request.get_json(silent=True) or {}
    store_name = (data.get("store_name") or "").strip()
    store_type = (data.get("store_type") or "new").strip()

    if not store_name:
        return jsonify({"error": "Cần nhập tên cửa hàng"}), 400
    if store_type not in ("new", "retail", "agent", "distributor"):
        return jsonify({"error": "Loại cửa hàng không hợp lệ"}), 400

    db = SessionLocal()
    try:
        # Kiem tra trung ten
        dup = db.query(Store).filter(Store.store_name.ilike(store_name)).first()
        if dup:
            return jsonify({"error": f"Tên '{dup.store_name}' đã tồn tại (mã {dup.store_code})"}), 409

        # Auto ma neu chua co
        store_code = (data.get("store_code") or "").strip().upper()
        if not store_code:
            store_code = _auto_store_code(db, store_type)

        # Kiem tra trung ma (phong truong hop user tu nhap)
        if db.query(Store).filter_by(store_code=store_code).first():
            return jsonify({"error": f"Mã {store_code} đã tồn tại"}), 409

        store = Store(
            store_code=store_code,
            store_name=store_name,
            store_type=store_type,
            address=data.get("address"),
            ward=data.get("ward"),
            district=data.get("district"),
            province=data.get("province"),
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            owner_name=data.get("owner_name"),
            phone=data.get("phone"),
            created_by=g.user_id,
        )
        db.add(store)
        db.flush()
        if g.role == "sales":
            db.add(Assignment(user_id=g.user_id, store_id=store.id,
                              assigned_by=g.user_id, note="Tự tạo khi đi thực địa"))
        db.commit()
        db.refresh(store)
        return jsonify(store.to_geojson()), 201
    finally:
        db.close()


@stores_bp.put("/<store_id>")
@require_auth
def update_store(store_id):
    db = SessionLocal()
    try:
        store = _user_stores(db, g.user_id, g.role).filter(Store.id == store_id).first()
        if not store: return jsonify({"error": "Khong tim thay"}), 404
        data = request.get_json(silent=True) or {}
        for f in ["store_name","store_type","address","ward","district","province",
                  "latitude","longitude","owner_name","phone","status"]:
            if f in data: setattr(store, f, data[f])
        db.commit()
        return jsonify(store.to_geojson())
    finally:
        db.close()


@stores_bp.get("/assignments")
@require_auth
def list_assignments():
    if g.role not in ("admin","manager"): return jsonify({"error": "Khong co quyen"}), 403
    db = SessionLocal()
    try:
        rows = db.query(Assignment).filter_by(is_active=True).all()
        return jsonify([{"id": str(r.id), "user_id": str(r.user_id),
                         "user_name": r.user.full_name if r.user else None,
                         "store_id": str(r.store_id),
                         "store_name": r.store.store_name if r.store else None,
                         "store_code": r.store.store_code if r.store else None} for r in rows])
    finally:
        db.close()


@stores_bp.post("/assignments")
@require_auth
def assign_store():
    if g.role not in ("admin","manager"): return jsonify({"error": "Khong co quyen"}), 403
    data = request.get_json(silent=True) or {}
    if not data.get("user_id") or not data.get("store_id"):
        return jsonify({"error": "Can user_id va store_id"}), 400
    db = SessionLocal()
    try:
        ex = db.query(Assignment).filter_by(user_id=data["user_id"], store_id=data["store_id"]).first()
        if ex: ex.is_active = True
        else: db.add(Assignment(user_id=data["user_id"], store_id=data["store_id"],
                                assigned_by=g.user_id, note=data.get("note")))
        db.commit()
        return jsonify({"message": "Da phan cong"}), 201
    finally:
        db.close()


@stores_bp.delete("/assignments/<assignment_id>")
@require_auth
def remove_assignment(assignment_id):
    if g.role not in ("admin", "manager"):
        return jsonify({"error": "Khong co quyen"}), 403
    db = SessionLocal()
    try:
        row = db.query(Assignment).filter_by(id=assignment_id).first()
        if not row:
            return jsonify({"error": "Khong tim thay"}), 404
        row.is_active = False
        db.commit()
        return jsonify({"message": "Da huy phan cong"})
    finally:
        db.close()


@stores_bp.delete("/<store_id>")
@require_auth
def delete_store(store_id):
    if g.role not in ("admin", "manager"):
        return jsonify({"error": "Khong co quyen"}), 403
    db = SessionLocal()
    try:
        from models.checkin import Checkin
        store = db.query(Store).filter_by(id=store_id).first()
        if not store:
            return jsonify({"error": "Khong tim thay"}), 404
        checkin_count = db.query(Checkin).filter_by(store_id=store_id).count()
        if checkin_count == 0:
            # Xoa han khoi DB
            db.query(Assignment).filter_by(store_id=store_id).delete()
            db.delete(store)
            db.commit()
            return jsonify({"message": f"Da xoa han cua hang {store.store_name}", "hard_delete": True})
        else:
            # Co checkin -> soft delete
            store.status = "inactive"
            db.commit()
            return jsonify({"message": f"Da an cua hang {store.store_name} (co {checkin_count} check-in)", "hard_delete": False})
    finally:
        db.close()