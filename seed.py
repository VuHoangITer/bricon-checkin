"""
Du lieu mau cho Sales Field App.
Chay qua: python db init
"""
import bcrypt
from extensions import SessionLocal
from models.user  import User, UserRole
from models.store import Store, StoreType


def run_seed():
    db = SessionLocal()
    try:
        _seed_users(db)
        db.flush()
        _seed_stores(db)
        db.commit()
        print("\nSeed xong! Dang nhap: admin / admin123")
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def _seed_users(db):
    users = [
        dict(username="admin",      full_name="Administrator",  role=UserRole.admin,   password=b"admin123"),
        dict(username="manager1",   full_name="Nguyen Thi B",   role=UserRole.manager, password=b"123456"),
        dict(username="nhanvien1",  full_name="Nguyen Van A",   role=UserRole.sales,   password=b"123456", phone="0901234567"),
        dict(username="nhanvien2",  full_name="Tran Thi C",     role=UserRole.sales,   password=b"123456", phone="0902345678"),
    ]
    for u in users:
        if not db.query(User).filter_by(username=u["username"]).first():
            pw = bcrypt.hashpw(u.pop("password"), bcrypt.gensalt()).decode()
            db.add(User(**u, password_hash=pw))
            print(f"  User: {u['username']}")


def _seed_stores(db):
    stores = [
        # ── Cua hang ban le (xanh) ──
        dict(store_code="CH001", store_name="Cua hang Minh Tam",
             store_type=StoreType.retail,
             latitude=10.8231, longitude=106.6297,
             address="123 Le Van Sy, Q.3, TP.HCM",
             district="Quan 3", province="TP.HCM",
             owner_name="Tran Minh Tam", phone="0912345678"),

        dict(store_code="CH002", store_name="Cua hang Hoang Long",
             store_type=StoreType.retail,
             latitude=10.7769, longitude=106.6950,
             address="56 Nguyen Thi Minh Khai, Q.1",
             district="Quan 1", province="TP.HCM",
             owner_name="Le Hoang Long", phone="0923456789"),

        # ── Dai ly (vang) ──
        dict(store_code="DL001", store_name="Dai ly Phu Nhuan",
             store_type=StoreType.agent,
             latitude=10.8011, longitude=106.6819,
             address="45 Phan Dinh Phung, Q.Phu Nhuan",
             district="Phu Nhuan", province="TP.HCM",
             owner_name="Le Thi Hoa", phone="0987654321"),

        dict(store_code="DL002", store_name="Dai ly Binh Thanh",
             store_type=StoreType.agent,
             latitude=10.8120, longitude=106.7100,
             address="12 Dien Bien Phu, Q.Binh Thanh",
             district="Binh Thanh", province="TP.HCM",
             owner_name="Pham Van Duc", phone="0976543210"),

        # ── Nha phan phoi (do) ──
        dict(store_code="NPP001", store_name="NPP Go Vap",
             store_type=StoreType.distributor,
             latitude=10.8383, longitude=106.6658,
             address="88 Quang Trung, Q.Go Vap",
             district="Go Vap", province="TP.HCM",
             owner_name="Nguyen Van Thanh", phone="0977001122"),

        # ── Chua mua hang (trang) ──
        dict(store_code="CH003", store_name="Cua hang Tan Binh",
             store_type=StoreType.new,
             latitude=10.7975, longitude=106.6526,
             address="200 Hoang Van Thu, Q.Tan Binh",
             district="Tan Binh", province="TP.HCM"),

        dict(store_code="CH004", store_name="Cua hang Thu Duc",
             store_type=StoreType.new,
             latitude=10.8551, longitude=106.7538,
             address="33 Vo Van Ngan, TP.Thu Duc",
             district="Thu Duc", province="TP.HCM"),
    ]
    for s in stores:
        if not db.query(Store).filter_by(store_code=s["store_code"]).first():
            db.add(Store(**s))
            print(f"  Store: {s['store_code']} - {s['store_name']}")
