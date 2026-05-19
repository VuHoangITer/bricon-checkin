import os

def load_env():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

load_env()

DATABASE_URL              = os.environ.get("DATABASE_URL", "")
JWT_SECRET                = os.environ.get("JWT_SECRET", "dev_secret")
JWT_ACCESS_EXPIRE_MINUTES = int(os.environ.get("JWT_ACCESS_EXPIRE_MINUTES", 60))
CHECKIN_RADIUS_METERS     = float(os.environ.get("CHECKIN_RADIUS_METERS", 200))
CLOUDINARY_CLOUD_NAME     = os.environ.get("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_API_KEY        = os.environ.get("CLOUDINARY_API_KEY", "")
CLOUDINARY_API_SECRET     = os.environ.get("CLOUDINARY_API_SECRET", "")
PORT                      = int(os.environ.get("PORT", 5000))
