"""
API quan ly phien check-in (session-based checkin/checkout).

Flow:
  POST /api/session/start          -> bat dau check-in, tra ve session_id
  POST /api/session/photo          -> upload tung anh (1,2,3) kem GPS
  POST /api/session/checkout       -> ket thuc, validate du dieu kien
  GET  /api/session/active         -> lay session dang mo cua user
  GET  /api/session/settings       -> lay cai dat he thong (min_minutes)
  PUT  /api/session/settings       -> admin cap nhat cai dat
"""
import os
import uuid
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify, g
from extensions import SessionLocal
from models.settings  import SystemSettings, CheckinSession
from models.store     import Store
from models.assignment import Assignment
from models.checkin   import Checkin
from utils import require_auth, check_radius

VN_TZ = timezone(timedelta(hours=7))

sessions_bp = Blueprint("sessions", __name__)

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "uploads")
ALLOWED    = {"jpg","jpeg","png","webp"}

DEFAULT_MIN_MINUTES = 15


def _get_min_minutes(db) -> int:
    row = db.query(SystemSettings).filter_by(id="min_checkin_minutes").first()
    return int(row.value) if row else DEFAULT_MIN_MINUTES


def _save_photo(file_storage, prefix: str) -> str:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    ext = (file_storage.filename.rsplit(".",1)[-1] or "jpg").lower()
    if ext not in ALLOWED: ext = "jpg"
    fname = f"{prefix}_{uuid.uuid4().hex[:8]}.{ext}"
    file_storage.save(os.path.join(UPLOAD_DIR, fname))
    return f"/static/uploads/{fname}"


# ── GET settings ─────────────────────────────────────────────
@sessions_bp.get("/settings")
@require_auth
def get_settings():
    db = SessionLocal()
    try:
        return jsonify({"min_checkin_minutes": _get_min_minutes(db)})
    finally:
        db.close()


# ── PUT settings (admin only) ─────────────────────────────────
@sessions_bp.put("/settings")
@require_auth
def put_settings():
    if g.role not in ("admin", "manager"):
        return jsonify({"error": "Khong co quyen"}), 403
    data = request.get_json(silent=True) or {}
    minutes = int(data.get("min_checkin_minutes", DEFAULT_MIN_MINUTES))
    if minutes < 1 or minutes > 480:
        return jsonify({"error": "Thoi gian phai tu 1 den 480 phut"}), 400
    db = SessionLocal()
    try:
        row = db.query(SystemSettings).filter_by(id="min_checkin_minutes").first()
        if row:
            row.value = str(minutes)
        else:
            db.add(SystemSettings(id="min_checkin_minutes", value=str(minutes)))
        db.commit()
        return jsonify({"min_checkin_minutes": minutes})
    finally:
        db.close()


# ── GET active session ────────────────────────────────────────
@sessions_bp.get("/active")
@require_auth
def get_active():
    db = SessionLocal()
    try:
        sess = db.query(CheckinSession).filter_by(user_id=g.user_id).first()
        if not sess:
            return jsonify({"active": False})
        store = db.query(Store).filter_by(id=sess.store_id).first()
        elapsed = int((datetime.now(VN_TZ) - sess.checkin_at.replace(tzinfo=VN_TZ)
                       if sess.checkin_at.tzinfo is None
                       else datetime.now(VN_TZ) - sess.checkin_at).total_seconds() / 60)
        return jsonify({
            "active":      True,
            "session_id":  sess.id,
            "store_id":    sess.store_id,
            "store_name":  store.store_name if store else None,
            "store_code":  store.store_code if store else None,
            "checkin_at":  sess.checkin_at.isoformat(),
            "elapsed_min": elapsed,
            "photo1_url":  sess.photo1_url,
            "photo2_url":  sess.photo2_url,
            "photo3_url":  sess.photo3_url,
            "note":        sess.note,
        })
    finally:
        db.close()


# ── POST start ────────────────────────────────────────────────
@sessions_bp.post("/start")
@require_auth
def start_session():
    if g.role == "telesales":
        return jsonify({"error": "Telesales không thực hiện check-in thực địa"}), 403
    data = request.get_json(silent=True) or {}
    store_id = data.get("store_id")
    lat = data.get("latitude")
    lon = data.get("longitude")
    if not store_id or lat is None or lon is None:
        return jsonify({"error": "Can store_id, latitude, longitude"}), 400
    try:
        lat, lon = float(lat), float(lon)
    except ValueError:
        return jsonify({"error": "Toa do khong hop le"}), 400

    db = SessionLocal()
    try:
        # Kiem tra da co session chua
        existing = db.query(CheckinSession).filter_by(user_id=g.user_id).first()
        if existing:
            return jsonify({"error": "Ban dang co mot phien check-in chua hoan thanh"}), 409

        store = db.query(Store).filter_by(id=store_id).first()
        if not store:
            return jsonify({"error": "Cua hang khong ton tai"}), 404

        # Kiem tra phan cong
        if g.role == "sales":
            ok = db.query(Assignment).filter_by(
                user_id=g.user_id, store_id=store_id, is_active=True).first()
            if not ok:
                return jsonify({"error": "Ban khong duoc phan cong cho cua hang nay"}), 403

        # Kiem tra GPS
        within, dist = check_radius(lat, lon, store.latitude, store.longitude)
        if not within:
            return jsonify({"error": f"Ban dang cach cua hang {dist:.0f}m (toi da 200m)"}), 422

        sess = CheckinSession(
            id=str(uuid.uuid4()),
            user_id=g.user_id,
            store_id=store_id,
            checkin_at=datetime.now(VN_TZ),
            checkin_lat=str(lat),
            checkin_lon=str(lon),
        )
        db.add(sess)
        db.commit()
        return jsonify({
            "session_id": sess.id,
            "checkin_at": sess.checkin_at.isoformat(),
            "store_name": store.store_name,
            "min_checkin_minutes": _get_min_minutes(db),
        }), 201
    finally:
        db.close()


# ── POST photo ────────────────────────────────────────────────
@sessions_bp.post("/photo")
@require_auth
def upload_photo():
    """
    multipart/form-data:
      session_id : str
      slot       : 1 | 2 | 3
      latitude   : float
      longitude  : float
      photo      : file
    """
    session_id = request.form.get("session_id")
    slot       = request.form.get("slot")
    lat        = request.form.get("latitude")
    lon        = request.form.get("longitude")
    photo      = request.files.get("photo")

    if not all([session_id, slot, lat, lon, photo]):
        return jsonify({"error": "Thieu thong tin"}), 400
    # Slot: 1, 2, 3, 3_1, 3_2, 3_3, 3_4 (3_x la cac anh doi thu bo sung)
    base_slot = slot.split('_')[0]
    if base_slot not in ("1","2","3"):
        return jsonify({"error": "Slot khong hop le"}), 400

    try:
        lat, lon = float(lat), float(lon)
    except ValueError:
        return jsonify({"error": "Toa do khong hop le"}), 400

    db = SessionLocal()
    try:
        sess = db.query(CheckinSession).filter_by(
            id=session_id, user_id=g.user_id).first()
        if not sess:
            return jsonify({"error": "Khong tim thay phien check-in"}), 404

        # Kiem tra GPS khi chup anh
        store = db.query(Store).filter_by(id=sess.store_id).first()
        within, dist = check_radius(lat, lon, store.latitude, store.longitude)
        if not within:
            return jsonify({"error": f"Ban dang cach cua hang {dist:.0f}m, phai o trong 200m de chup anh"}), 422

        # Luu anh
        url = _save_photo(photo, f"s{slot}_{sess.store_id[:6]}")
        now = datetime.now(VN_TZ)

        if base_slot == "1":
            sess.photo1_url = url
            sess.photo1_lat = str(lat)
            sess.photo1_lon = str(lon)
            sess.photo1_at  = now
        elif base_slot == "2":
            sess.photo2_url = url
            sess.photo2_lat = str(lat)
            sess.photo2_lon = str(lon)
            sess.photo2_at  = now
        else:
            # Slot 3, 3_1, 3_2... luu vao photo3_url va photo_public_id
            if not sess.photo3_url or slot == "3":
                sess.photo3_url = url
                sess.photo3_lat = str(lat)
                sess.photo3_lon = str(lon)
                sess.photo3_at  = now
            # Luu cac anh phu vao photo_public_id (pipe separated)
            existing = [u for u in (sess.photo_public_id or "").split("|") if u and not u.startswith("/static/uploads/s2")]
            # Gop tat ca anh slot 3 lai
            all_slot3 = [u for u in (sess.photo_public_id or "").split("|") if u] if sess.photo_public_id else []
            if url not in all_slot3:
                all_slot3.append(url)
            sess.photo_public_id = "|".join(all_slot3)

        db.commit()
        return jsonify({"url": url, "slot": slot, "distance_m": dist})
    finally:
        db.close()


# ── POST update note ──────────────────────────────────────────
@sessions_bp.post("/note")
@require_auth
def update_note():
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    note = data.get("note","").strip()
    db = SessionLocal()
    try:
        sess = db.query(CheckinSession).filter_by(id=session_id, user_id=g.user_id).first()
        if not sess: return jsonify({"error": "Khong tim thay"}), 404
        sess.note = note
        db.commit()
        return jsonify({"ok": True})
    finally:
        db.close()


# ── POST checkout ─────────────────────────────────────────────
@sessions_bp.post("/checkout")
@require_auth
def checkout():
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    lat = data.get("latitude")
    lon = data.get("longitude")
    if not session_id or lat is None or lon is None:
        return jsonify({"error": "Can session_id, latitude, longitude"}), 400
    try:
        lat, lon = float(lat), float(lon)
    except ValueError:
        return jsonify({"error": "Toa do khong hop le"}), 400

    db = SessionLocal()
    try:
        sess = db.query(CheckinSession).filter_by(
            id=session_id, user_id=g.user_id).first()
        if not sess:
            return jsonify({"error": "Khong tim thay phien check-in"}), 404

        store = db.query(Store).filter_by(id=sess.store_id).first()

        # 1. Kiem tra GPS checkout
        within, dist = check_radius(lat, lon, store.latitude, store.longitude)
        if not within:
            return jsonify({
                "error": f"Ban dang cach cua hang {dist:.0f}m. Phai o trong 200m de check-out"
            }), 422

        # 2. Tinh thoi gian
        min_minutes = _get_min_minutes(db)
        checkin_time = sess.checkin_at
        if checkin_time.tzinfo is None:
            checkin_time = checkin_time.replace(tzinfo=timezone.utc)
        now_utc = datetime.now(timezone.utc)
        elapsed_min = max(1, int((now_utc - checkin_time).total_seconds() / 60))
        early_checkout = elapsed_min < min_minutes

        # 3. Kiem tra anh bat buoc (slot 1 va slot 3)
        if not sess.photo1_url:
            return jsonify({"error": "Chua co anh toan canh cua hang (Anh 1)"}), 422
        if not sess.photo3_url:
            return jsonify({"error": "Chua co anh san pham doi thu (Anh 3)"}), 422

        # 4. Luu checkin chinh thuc
        from datetime import date
        note_final = sess.note or ""
        if early_checkout:
            note_final = f"[CHECK-OUT SOM: {elapsed_min}/{min_minutes} phut] " + note_final
        # Gom tat ca anh slot3: dung sess.photo_public_id (da chua day du)
        # neu khong co thi fallback ve photo3_url
        slot3_urls = []
        if sess.photo_public_id:
            slot3_urls = [u for u in sess.photo_public_id.split("|") if u]
        elif sess.photo3_url:
            slot3_urls = [sess.photo3_url]

        # photo2_url luu rieng, slot3 luu het vao photo_public_id
        all_extra = [u for u in [sess.photo2_url] + slot3_urls if u]

        checkin = Checkin(
            store_id=sess.store_id,
            user_id=g.user_id,
            latitude=float(sess.checkin_lat),
            longitude=float(sess.checkin_lon),
            description=note_final,
            photo_url=sess.photo1_url,
            photo2_url=sess.photo2_url,
            photo3_url=slot3_urls[0] if slot3_urls else None,
            checkin_at=sess.checkin_at,
            duration_min=elapsed_min,
            photo_public_id="|".join(slot3_urls) if slot3_urls else None,
        )
        db.add(checkin)

        # Cap nhat store
        store.last_checkin_date = date.today()

        # Xoa session
        db.delete(sess)
        db.commit()

        msg = f"Check-out thanh cong! Thoi gian: {elapsed_min} phut"
        if early_checkout:
            msg = f"Check-out som ({elapsed_min}/{min_minutes} phut). Da ghi chu vao bao cao."
        return jsonify({
            "message": msg,
            "duration_min": elapsed_min,
            "early_checkout": early_checkout,
        })
    finally:
        db.close()


# ── DELETE session (huy check-in) ────────────────────────────
@sessions_bp.delete("/cancel")
@require_auth
def cancel_session():
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    db = SessionLocal()
    try:
        sess = db.query(CheckinSession).filter_by(
            id=session_id, user_id=g.user_id).first()
        if not sess:
            return jsonify({"error": "Khong tim thay"}), 404
        db.delete(sess)
        db.commit()
        return jsonify({"message": "Da huy check-in"})
    finally:
        db.close()


# ── DELETE force-clear (xoa session bi ket, khong can session_id) ──
@sessions_bp.delete("/force-clear")
@require_auth
def force_clear_session():
    """
    Xoa tat ca session dang mo cua user hien tai.
    Dung khi user bi ket va khong vao duoc working screen.
    """
    db = SessionLocal()
    try:
        sessions = db.query(CheckinSession).filter_by(user_id=g.user_id).all()
        count = len(sessions)
        for s in sessions:
            db.delete(s)
        db.commit()
        return jsonify({"message": f"Da xoa {count} phien check-in bi ket", "count": count})
    finally:
        db.close()