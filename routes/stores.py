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

# ══════════════════════════════════════════════════════════════
# LOCATION — Đặt / sửa tọa độ cửa hàng
# ══════════════════════════════════════════════════════════════

import os, uuid as _uuid
from utils import haversine

UPLOAD_DIR_LOC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "uploads")
ALLOWED_LOC    = {"jpg","jpeg","png","webp"}

def _save_loc_photo(file_storage, store_code: str) -> str:
    os.makedirs(UPLOAD_DIR_LOC, exist_ok=True)
    ext = (file_storage.filename.rsplit(".",1)[-1] or "jpg").lower()
    if ext not in ALLOWED_LOC: ext = "jpg"
    fname = f"loc_{store_code}_{_uuid.uuid4().hex[:8]}.{ext}"
    file_storage.save(os.path.join(UPLOAD_DIR_LOC, fname))
    return f"/static/uploads/{fname}"


@stores_bp.post("/<store_id>/location")
@require_auth
def update_location(store_id):
    """
    Đặt hoặc sửa tọa độ cửa hàng.
    multipart/form-data:
      latitude  : float  (bắt buộc)
      longitude : float  (bắt buộc)
      note      : str    (tuỳ chọn)
      photo     : file   (bắt buộc khi cửa hàng đã có tọa độ - action=fix)
    """
    from models.location_log import LocationLog

    lat_str = request.form.get("latitude")
    lon_str = request.form.get("longitude")
    note    = request.form.get("note", "").strip()
    photo   = request.files.get("photo")

    if not lat_str or not lon_str:
        return jsonify({"error": "Cần latitude và longitude"}), 400
    try:
        lat, lon = float(lat_str), float(lon_str)
    except ValueError:
        return jsonify({"error": "Tọa độ không hợp lệ"}), 400

    db = SessionLocal()
    try:
        # Kiểm tra quyền: sales chỉ sửa cửa hàng được giao
        store = db.query(Store).filter_by(id=store_id).first()
        if not store:
            return jsonify({"error": "Không tìm thấy cửa hàng"}), 404

        if g.role == "sales":
            ok = db.query(Assignment).filter_by(
                user_id=g.user_id, store_id=store_id, is_active=True).first()
            if not ok:
                return jsonify({"error": "Bạn không được phân công cho cửa hàng này"}), 403

        has_old = store.latitude is not None and store.longitude is not None
        action  = "fix" if has_old else "set"

        # Bắt buộc ảnh khi sửa (fix)
        if action == "fix" and not photo:
            return jsonify({"error": "Cần chụp ảnh xác nhận khi sửa vị trí"}), 422

        # Tính khoảng cách lệch
        delta_m = None
        if has_old:
            delta_m = haversine(store.latitude, store.longitude, lat, lon)

        # Lưu ảnh
        photo_url = None
        if photo and photo.filename:
            photo_url = _save_loc_photo(photo, store.store_code)

        # Ghi log
        log = LocationLog(
            store_id  = store_id,
            user_id   = g.user_id,
            action    = action,
            old_lat   = store.latitude,
            old_lon   = store.longitude,
            new_lat   = lat,
            new_lon   = lon,
            delta_m   = delta_m,
            photo_url = photo_url,
            note      = note or None,
        )
        db.add(log)

        # Cập nhật tọa độ store
        store.latitude  = lat
        store.longitude = lon
        db.commit()

        return jsonify({
            "message":  f"Đã {'sửa' if action=='fix' else 'đặt'} vị trí cửa hàng {store.store_name}",
            "action":   action,
            "delta_m":  round(delta_m, 1) if delta_m else None,
            "latitude": lat,
            "longitude": lon,
        })
    finally:
        db.close()


@stores_bp.get("/<store_id>/location-logs")
@require_auth
def get_location_logs(store_id):
    """Lấy lịch sử thay đổi tọa độ của một cửa hàng."""
    from models.location_log import LocationLog
    db = SessionLocal()
    try:
        logs = db.query(LocationLog)\
                 .filter_by(store_id=store_id)\
                 .order_by(LocationLog.created_at.desc())\
                 .limit(20).all()
        return jsonify([l.to_dict() for l in logs])
    finally:
        db.close()


@stores_bp.get("/location-logs/all")
@require_auth
def all_location_logs():
    """Admin: xem toàn bộ log thay đổi tọa độ (mới nhất trước)."""
    if g.role not in ("admin", "manager"):
        return jsonify({"error": "Không có quyền"}), 403
    from models.location_log import LocationLog
    limit = min(int(request.args.get("limit", 50)), 200)
    db = SessionLocal()
    try:
        logs = db.query(LocationLog)\
                 .order_by(LocationLog.created_at.desc())\
                 .limit(limit).all()
        return jsonify([l.to_dict() for l in logs])
    finally:
        db.close()


@stores_bp.get("/no-coords")
@require_auth
def stores_no_coords():
    """Danh sách cửa hàng chưa có tọa độ (dùng cho filter sidebar)."""
    db = SessionLocal()
    try:
        q = _user_stores(db, g.user_id, g.role)
        stores = q.filter(
            (Store.latitude  == None) | (Store.longitude == None)
        ).order_by(Store.store_name).all()
        return jsonify([{
            "id":   str(s.id),
            "code": s.store_code,
            "name": s.store_name,
            "type": s.store_type.value,
        } for s in stores])
    finally:
        db.close()


@stores_bp.delete("/location-logs/<log_id>")
@require_auth
def delete_location_log(log_id):
    if g.role not in ("admin", "manager"):
        return jsonify({"error": "Không có quyền"}), 403
    from models.location_log import LocationLog
    import os
    db = SessionLocal()
    try:
        log = db.query(LocationLog).filter_by(id=log_id).first()
        if not log:
            return jsonify({"error": "Không tìm thấy"}), 404
        # Xóa ảnh local nếu có
        if log.photo_url and log.photo_url.startswith("/static/uploads/"):
            path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                log.photo_url.lstrip("/")
            )
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
        db.delete(log)
        db.commit()
        return jsonify({"message": "Đã xóa log"})
    finally:
        db.close()


# ── GET ảnh từ Cloudinary ─────────────────────────────────────
@stores_bp.get("/cloudinary-photos")
@require_auth
def cloudinary_photos():
    """
    Lấy danh sách ảnh từ Cloudinary folder salesfield/.
    Admin/Manager only.
    """
    if g.role not in ("admin", "manager"):
        return jsonify({"error": "Không có quyền"}), 403

    try:
        import cloudinary
        import cloudinary.api
        import config

        cloudinary.config(
            cloud_name  = config.CLOUDINARY_CLOUD_NAME,
            api_key     = config.CLOUDINARY_API_KEY,
            api_secret  = config.CLOUDINARY_API_SECRET,
        )

        next_cursor = request.args.get("next_cursor")
        max_results = int(request.args.get("max_results", 50))

        params = {
            "type":        "upload",
            "prefix":      "salesfield/",
            "max_results": max_results,
            "context":     True,
        }
        if next_cursor:
            params["next_cursor"] = next_cursor

        result = cloudinary.api.resources(**params)

        photos = []
        for r in result.get("resources", []):
            photos.append({
                "public_id":   r["public_id"],
                "url":         r["secure_url"],
                "created_at":  r.get("created_at"),
                "bytes":       r.get("bytes", 0),
                "width":       r.get("width"),
                "height":      r.get("height"),
                "folder":      r["public_id"].rsplit("/", 1)[0],  # salesfield/CH001
            })

        return jsonify({
            "photos":      photos,
            "total":       result.get("rate_limit_remaining"),
            "next_cursor": result.get("next_cursor"),  # dùng để phân trang
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500