"""
API quan ly phien check-in (session-based checkin/checkout).
"""
import os
import io
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


def _stamp_photo(image_bytes: bytes, lat: float, lon: float,
                 user_name: str, store_name: str) -> bytes:
    """
    Stamp tọa độ GPS, thời gian, tên nhân viên lên góc dưới ảnh.
    Giống watermark của app giao hàng.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        W, H = img.size

        draw = ImageDraw.Draw(img)

        # Font size tỷ lệ theo chiều rộng ảnh
        font_size = max(20, W // 35)

        # Thử load font đẹp, fallback về default
        font = None
        font_bold = None
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "C:/Windows/Fonts/arial.ttf",
        ]
        for fp in font_paths:
            if os.path.exists(fp):
                try:
                    font      = ImageFont.truetype(fp, font_size)
                    font_bold = ImageFont.truetype(fp, int(font_size * 1.1))
                    break
                except: pass
        if not font:
            font = font_bold = ImageFont.load_default()

        # Nội dung stamp
        now_vn = datetime.now(VN_TZ)
        lines = [
            f"{lat:.6f}, {lon:.6f}",
            now_vn.strftime("%Y-%m-%d %H:%M:%S"),
            store_name,
            user_name,
        ]

        # Tính kích thước vùng stamp
        line_h   = font_size + 6
        pad      = 14
        box_h    = line_h * len(lines) + pad * 2
        box_w    = W  # full width

        # Vẽ nền đen mờ phía dưới
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ov_draw = ImageDraw.Draw(overlay)
        ov_draw.rectangle(
            [(0, H - box_h), (box_w, H)],
            fill=(0, 0, 0, 180)
        )
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(img)

        # Vẽ text
        y = H - box_h + pad
        for i, line in enumerate(lines):
            f = font_bold if i == 0 else font
            # Shadow
            draw.text((pad + 1, y + 1), line, font=f, fill=(0, 0, 0, 200))
            # Text màu vàng cho tọa độ, trắng cho còn lại
            color = "#FFD700" if i == 0 else "#FFFFFF"
            draw.text((pad, y), line, font=f, fill=color)
            y += line_h

        # Xuất về bytes JPEG
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=92)
        return out.getvalue()

    except Exception as e:
        print(f"Stamp ảnh lỗi (bỏ qua): {e}")
        return image_bytes


def _save_photo(file_storage, store_code: str, slot: str,
                lat: float = None, lon: float = None,
                user_name: str = "", store_name: str = "") -> str:
    """Upload ảnh lên Cloudinary kèm stamp GPS, hoặc lưu local."""
    import config as _config

    image_bytes = file_storage.read()

    # Stamp GPS + info lên ảnh
    if lat is not None and lon is not None:
        image_bytes = _stamp_photo(image_bytes, lat, lon, user_name, store_name)

    if _config.CLOUDINARY_CLOUD_NAME and _config.CLOUDINARY_CLOUD_NAME != "your_cloud_name":
        try:
            import cloudinary.uploader
            cloudinary.config(
                cloud_name = _config.CLOUDINARY_CLOUD_NAME,
                api_key    = _config.CLOUDINARY_API_KEY,
                api_secret = _config.CLOUDINARY_API_SECRET,
                secure     = True,
            )
            folder = f"salesfield/{store_code}"
            result = cloudinary.uploader.upload(
                io.BytesIO(image_bytes),
                folder = folder,
            )
            return result["secure_url"]
        except Exception as e:
            print(f"Cloudinary upload lỗi, fallback local: {e}")

    # Fallback: lưu local
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    ext = (file_storage.filename.rsplit(".", 1)[-1] or "jpg").lower()
    if ext not in ALLOWED: ext = "jpg"
    fname = f"s{slot}_{store_code}_{uuid.uuid4().hex[:8]}.{ext}"
    with open(os.path.join(UPLOAD_DIR, fname), 'wb') as f:
        f.write(image_bytes)
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
        existing = db.query(CheckinSession).filter_by(user_id=g.user_id).first()
        if existing:
            return jsonify({"error": "Ban dang co mot phien check-in chua hoan thanh"}), 409

        store = db.query(Store).filter_by(id=store_id).first()
        if not store:
            return jsonify({"error": "Cua hang khong ton tai"}), 404

        if g.role == "sales":
            ok = db.query(Assignment).filter_by(
                user_id=g.user_id, store_id=store_id, is_active=True).first()
            if not ok:
                return jsonify({"error": "Ban khong duoc phan cong cho cua hang nay"}), 403

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
    session_id = request.form.get("session_id")
    slot       = request.form.get("slot")
    lat        = request.form.get("latitude")
    lon        = request.form.get("longitude")
    photo      = request.files.get("photo")

    if not all([session_id, slot, lat, lon, photo]):
        return jsonify({"error": "Thieu thong tin"}), 400

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

        store = db.query(Store).filter_by(id=sess.store_id).first()
        within, dist = check_radius(lat, lon, store.latitude, store.longitude)
        if not within:
            return jsonify({"error": f"Ban dang cach cua hang {dist:.0f}m, phai o trong 200m de chup anh"}), 422

        # Lấy tên nhân viên để stamp
        user = db.query(
            __import__('models.user', fromlist=['User']).User
        ).filter_by(id=g.user_id).first()
        user_name  = user.full_name  if user  else g.user_id
        store_name = store.store_name if store else store.store_code

        # Upload ảnh kèm stamp GPS
        url = _save_photo(
            photo, store.store_code, slot,
            lat=lat, lon=lon,
            user_name=user_name,
            store_name=store_name,
        )
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
            if not sess.photo3_url or slot == "3":
                sess.photo3_url = url
                sess.photo3_lat = str(lat)
                sess.photo3_lon = str(lon)
                sess.photo3_at  = now
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

        within, dist = check_radius(lat, lon, store.latitude, store.longitude)
        if not within:
            return jsonify({
                "error": f"Ban dang cach cua hang {dist:.0f}m. Phai o trong 200m de check-out"
            }), 422

        min_minutes = _get_min_minutes(db)
        checkin_time = sess.checkin_at
        if checkin_time.tzinfo is None:
            checkin_time = checkin_time.replace(tzinfo=timezone.utc)
        now_utc = datetime.now(timezone.utc)
        elapsed_min = max(1, int((now_utc - checkin_time).total_seconds() / 60))
        early_checkout = elapsed_min < min_minutes

        if not sess.photo1_url:
            return jsonify({"error": "Chua co anh toan canh cua hang (Anh 1)"}), 422
        if not sess.photo3_url:
            return jsonify({"error": "Chua co anh san pham doi thu (Anh 3)"}), 422

        from datetime import date
        note_final = sess.note or ""
        if early_checkout:
            note_final = f"[CHECK-OUT SOM: {elapsed_min}/{min_minutes} phut] " + note_final

        slot3_urls = []
        if sess.photo_public_id:
            slot3_urls = [u for u in sess.photo_public_id.split("|") if u]
        elif sess.photo3_url:
            slot3_urls = [sess.photo3_url]

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
        store.last_checkin_date = date.today()
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


# ── DELETE force-clear ────────────────────────────────────────
@sessions_bp.delete("/force-clear")
@require_auth
def force_clear_session():
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