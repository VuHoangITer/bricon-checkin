import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import config  # noqa - load .env truoc
from flask import Flask, send_from_directory
from flask_cors import CORS
from extensions import init_engine
import models  # noqa - dang ky tat ca models

from routes.auth    import auth_bp
from routes.stores  import stores_bp
from routes.checkin import checkin_bp
from routes.sessions import sessions_bp
from routes.calls import calls_bp
from routes.location import location_bp

app = Flask(__name__, static_folder="static")
app.config["SECRET_KEY"]            = config.JWT_SECRET
app.config["MAX_CONTENT_LENGTH"]    = 10 * 1024 * 1024
CORS(app)

# Ket noi DB
init_engine(config.DATABASE_URL)

# Dang ky blueprints
app.register_blueprint(auth_bp,    url_prefix="/api/auth")
app.register_blueprint(stores_bp,  url_prefix="/api/stores")
app.register_blueprint(checkin_bp,  url_prefix="/api/checkin")
app.register_blueprint(sessions_bp, url_prefix="/api/session")
app.register_blueprint(calls_bp,    url_prefix="/api/calls")
app.register_blueprint(location_bp,  url_prefix="/api/location")


# PWA files
@app.route("/static/manifest.json")
def manifest():
    return send_from_directory(
        os.path.join(os.path.dirname(__file__), "static"), "manifest.json")

@app.route("/static/sw.js")
def service_worker():
    resp = send_from_directory(
        os.path.join(os.path.dirname(__file__), "static"), "sw.js")
    resp.headers['Service-Worker-Allowed'] = '/'
    resp.headers['Cache-Control'] = 'no-cache'
    return resp

@app.route("/static/icon-<size>.png")
def icon(size):
    return send_from_directory(
        os.path.join(os.path.dirname(__file__), "static"), f"icon-{size}.png")

# Serve frontend
@app.route("/login")
def login_page():
    return send_from_directory(
        os.path.join(os.path.dirname(__file__), "static"), "login.html")

@app.route("/admin")
@app.route("/admin/")
def admin_page():
    return send_from_directory(
        os.path.join(os.path.dirname(__file__), "static", "admin"), "index.html")

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def frontend(path):
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if path and os.path.exists(os.path.join(static_dir, path)):
        return send_from_directory(static_dir, path)
    return send_from_directory(static_dir, "index.html")


if __name__ == "__main__":
    print(f"\nSales Field App: http://localhost:{config.PORT}\n")
    app.run(host="0.0.0.0", port=config.PORT, debug=True)