import os
import uuid
from datetime import date
from flask import Blueprint, request, jsonify, g, current_app
from sqlalchemy import desc, func
from sqlalchemy.orm import joinedload
from extensions import SessionLocal
from models.store      import Store
from models.assignment import Assignment
from models.checkin    import Checkin
from utils import require_auth, check_radius

checkin_bp = Blueprint("checkin", __name__)

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "uploads")
ALLOWED_EXT = {"jpg", "jpeg", "png", "webp"}


def _save_photo_local(file_storage, store_code: str) -> tuple[str, str]:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    ext = file_storage.filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXT:
        ext = "jpg"
    filename = f"{store_code}_{uuid.uuid4().hex[:8]}.{ext}"
    save_path = os.path.join(UPLOAD_DIR, filename)
    file_storage.save(save_path)
    url = f"/static/uploads/{filename}"
    return url, filename


def _save_photo_cloudinary(file_storage, store_code: str) -> tuple[str, str]:
    import cloudinary.uploader
    import config
    cloudinary.config(
        cloud_name=config.CLOUDINARY_CLOUD_NAME,
        api_key=config.CLOUDINARY_API_KEY,
        api_secret=config.CLOUDINARY_API_SECRET,
        secure=True,
    )
    result = cloudinary.uploader.upload(
        file_storage.stream,
        folder=f"salesfield/{store_code}",
        transformation=[{"width": 1280, "height": 960, "crop": "limit", "quality": "auto:good"}],
    )
    return result["secure_url"], result["public_id"]


def _upload_photo(file_storage, store_code: str) -> tuple[str, str]:
    import config
    if config.CLOUDINARY_CLOUD_NAME and config.CLOUDINARY_CLOUD_NAME != "your_cloud_name":
        return _save_photo_cloudinary(file_storage, store_code)
    return _save_photo_local(file_storage, store_code)


@checkin_bp.post("/")
@require_auth
def do_checkin():
    store_id = request.form.get("store_id")
    lat = request.form.get("latitude")
    lon = request.form.get("longitude")
    if not store_id or lat is None or lon is None:
        return jsonify({"error": "Can store_id, latitude, longitude"}), 400
    try:
        lat, lon = float(lat), float(lon)
    except ValueError:
        return jsonify({"error": "Toa do khong hop le"}), 400

    db = SessionLocal()
    try:
        store = db.query(Store).filter_by(id=store_id).first()
        if not store:
            return jsonify({"error": "Cua hang khong ton tai"}), 404

        if g.role == "sales":
            if not db.query(Assignment).filter_by(
                user_id=g.user_id, store_id=store_id, is_active=True).first():
                return jsonify({"error": "Ban khong duoc phan cong cho cua hang nay"}), 403

        within, dist = check_radius(lat, lon, store.latitude, store.longitude)
        if not within:
            return jsonify({"error": f"Ban dang cach cua hang {dist:.0f}m (toi da 200m)"}), 422

        photo_url = photo_pid = None
        photo = request.files.get("photo")
        if photo and photo.filename:
            try:
                photo_url, photo_pid = _upload_photo(photo, store.store_code)
            except Exception as e:
                print(f"Upload anh loi: {e}")

        checkin = Checkin(
            store_id=store_id,
            user_id=g.user_id,
            latitude=lat,
            longitude=lon,
            accuracy_m=request.form.get("accuracy", type=float),
            description=request.form.get("description", "").strip() or None,
            photo_url=photo_url,
            photo_public_id=photo_pid,
            duration_min=request.form.get("duration", type=int),
        )
        db.add(checkin)
        store.last_checkin_date = date.today()
        db.commit()
        db.refresh(checkin)
        return jsonify({
            **checkin.to_dict(),
            "distance_m": dist,
            "message": f"Check-in thanh cong tai {store.store_name}",
        }), 201
    finally:
        db.close()


@checkin_bp.get("/history")
@require_auth
def history():
    store_id = request.args.get("store_id")
    limit    = min(int(request.args.get("limit", 20)), 100)
    offset   = int(request.args.get("offset", 0))
    db = SessionLocal()
    try:
        # Base query với eager load — tránh N+1
        q = db.query(Checkin).options(
            joinedload(Checkin.store),
            joinedload(Checkin.user),
        )
        if g.role == "sales":
            q = q.filter(Checkin.user_id == g.user_id)
        if store_id:
            q = q.filter(Checkin.store_id == store_id)

        # Đếm riêng không kéo data
        count_q = db.query(func.count(Checkin.id))
        if g.role == "sales":
            count_q = count_q.filter(Checkin.user_id == g.user_id)
        if store_id:
            count_q = count_q.filter(Checkin.store_id == store_id)
        total = count_q.scalar()

        rows = q.order_by(desc(Checkin.checkin_at)).offset(offset).limit(limit).all()
        return jsonify({
            "total": total, "limit": limit, "offset": offset,
            "data": [r.to_dict() for r in rows],
        })
    finally:
        db.close()


@checkin_bp.delete("/<checkin_id>")
@require_auth
def delete_checkin(checkin_id):
    if g.role not in ("admin", "manager"):
        return jsonify({"error": "Khong co quyen"}), 403
    db = SessionLocal()
    try:
        checkin = db.query(Checkin).filter_by(id=checkin_id).first()
        if not checkin:
            return jsonify({"error": "Khong tim thay"}), 404

        def _delete_local(url):
            if not url or not url.startswith("/static/uploads/"):
                return
            path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                url.lstrip("/")
            )
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                print(f"Loi xoa file {path}: {e}")

        _delete_local(checkin.photo_url)
        _delete_local(checkin.photo2_url)

        if checkin.photo_public_id:
            for entry in checkin.photo_public_id.split("|"):
                entry = entry.strip()
                if not entry:
                    continue
                if entry.startswith("/static/uploads/"):
                    _delete_local(entry)
                elif "/" in entry and not entry.startswith("http"):
                    try:
                        import cloudinary.uploader
                        import config
                        cloudinary.config(
                            cloud_name=config.CLOUDINARY_CLOUD_NAME,
                            api_key=config.CLOUDINARY_API_KEY,
                            api_secret=config.CLOUDINARY_API_SECRET,
                        )
                        cloudinary.uploader.destroy(entry)
                    except Exception as e:
                        print(f"Loi xoa Cloudinary {entry}: {e}")
        else:
            _delete_local(checkin.photo3_url)

        store_id = checkin.store_id
        db.delete(checkin)
        db.flush()

        latest = db.query(Checkin).filter_by(store_id=store_id) \
                   .order_by(desc(Checkin.checkin_at)).first()
        store = db.query(Store).filter_by(id=store_id).first()
        if store:
            store.last_checkin_date = latest.checkin_at.date() if latest else None

        db.commit()
        return jsonify({"message": "Da xoa check-in"})
    finally:
        db.close()