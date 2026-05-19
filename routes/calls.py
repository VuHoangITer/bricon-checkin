"""
API quan ly log cuoc goi.

POST /api/calls/          -> log cuoc goi moi
GET  /api/calls/history   -> lich su cuoc goi (loc theo store_id, user_id)
DELETE /api/calls/<id>    -> xoa log (admin only)
"""
import uuid
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify, g
from extensions import SessionLocal
from models.call_log import CallLog
from models.store    import Store
from models.assignment import Assignment
from utils import require_auth

VN_TZ = timezone(timedelta(hours=7))

calls_bp = Blueprint("calls", __name__)


# ── POST log cuoc goi ─────────────────────────────────────────
@calls_bp.post("/")
@require_auth
def log_call():
    data     = request.get_json(silent=True) or {}
    store_id = data.get("store_id")
    note     = data.get("note", "").strip()

    if not store_id:
        return jsonify({"error": "Can store_id"}), 400

    db = SessionLocal()
    try:
        store = db.query(Store).filter_by(id=store_id).first()
        if not store:
            return jsonify({"error": "Cua hang khong ton tai"}), 404

        # Kiem tra phan cong (sales chi log cho cua hang duoc giao)
        # Telesales co the goi cho tat ca cua hang
        if g.role == "sales":
            ok = db.query(Assignment).filter_by(
                user_id=g.user_id, store_id=store_id, is_active=True).first()
            if not ok:
                return jsonify({"error": "Ban khong duoc phan cong cho cua hang nay"}), 403

        log = CallLog(
            id=uuid.uuid4(),
            store_id=store_id,
            user_id=g.user_id,
            called_at=datetime.now(VN_TZ),
            note=note or None,
        )
        db.add(log)
        db.commit()
        return jsonify({
            "message": f"Da ghi nhan cuoc goi den {store.store_name}",
            "call_id": str(log.id),
            "called_at": log.called_at.isoformat(),
        }), 201
    finally:
        db.close()


# ── GET history ───────────────────────────────────────────────
@calls_bp.get("/history")
@require_auth
def call_history():
    store_id = request.args.get("store_id")
    limit    = min(int(request.args.get("limit", 20)), 100)

    db = SessionLocal()
    try:
        q = db.query(CallLog)
        if store_id:
            q = q.filter_by(store_id=store_id)
        elif g.role in ("sales", "telesales"):
            # Chi thay cuoc goi cua minh
            q = q.filter_by(user_id=g.user_id)
        logs = q.order_by(CallLog.called_at.desc()).limit(limit).all()
        return jsonify({"data": [l.to_dict() for l in logs]})
    finally:
        db.close()


# ── DELETE log (admin/manager only) ──────────────────────────
@calls_bp.delete("/<call_id>")
@require_auth
def delete_call(call_id):
    if g.role not in ("admin", "manager"):
        return jsonify({"error": "Khong co quyen"}), 403
    db = SessionLocal()
    try:
        log = db.query(CallLog).filter_by(id=call_id).first()
        if not log:
            return jsonify({"error": "Khong tim thay"}), 404
        db.delete(log)
        db.commit()
        return jsonify({"message": "Da xoa log cuoc goi"})
    finally:
        db.close()


# ── GET/PUT activity days setting ─────────────────────────────
@calls_bp.get("/activity-days")
@require_auth
def get_activity_days():
    from models.settings import SystemSettings
    db = SessionLocal()
    try:
        row_ci   = db.query(SystemSettings).filter_by(id="checkin_activity_days").first()
        row_call = db.query(SystemSettings).filter_by(id="call_activity_days").first()
        # Backward compat: neu chua co thi lay activity_days chung
        row_old  = db.query(SystemSettings).filter_by(id="activity_days").first()
        default  = int(row_old.value) if row_old else 7
        return jsonify({
            "activity_days":         default,  # backward compat
            "checkin_activity_days": int(row_ci.value)   if row_ci   else default,
            "call_activity_days":    int(row_call.value) if row_call else default,
        })
    finally:
        db.close()

@calls_bp.put("/activity-days")
@require_auth
def put_activity_days():
    if g.role not in ("admin", "manager"):
        return jsonify({"error": "Khong co quyen"}), 403
    data = request.get_json(silent=True) or {}

    checkin_days = int(data.get("checkin_activity_days", data.get("activity_days", 7)))
    call_days    = int(data.get("call_activity_days",    data.get("activity_days", 7)))

    if not (1 <= checkin_days <= 30) or not (1 <= call_days <= 30):
        return jsonify({"error": "Phai tu 1 den 30 ngay"}), 400

    from models.settings import SystemSettings
    db = SessionLocal()
    try:
        for key, val in [("checkin_activity_days", checkin_days), ("call_activity_days", call_days)]:
            row = db.query(SystemSettings).filter_by(id=key).first()
            if row: row.value = str(val)
            else:   db.add(SystemSettings(id=key, value=str(val)))
        db.commit()
        return jsonify({
            "checkin_activity_days": checkin_days,
            "call_activity_days":    call_days,
        })
    finally:
        db.close()