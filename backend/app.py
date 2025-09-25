import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import os
from flask import Flask, send_from_directory, render_template
from sqlalchemy import text
from backend.database.db import db
from backend.database.models import Admin
from backend.admin.routes import admin_bp
from backend.complainant.routes import complainant_bp

# Set static_folder to your frontend directory, static_url_path to ""
frontend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../frontend"))
app = Flask(__name__, static_folder=frontend_path, static_url_path="")

# for db (not in use atm; don't know where this is applied)
app.secret_key = "your_secret_key"

# ✅ Correct Database configuration
app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+pymysql://root:reklaMap123%2B@72.60.108.94:3306/reklamap"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# ✅ Initialize db with app
db.init_app(app)

# Register blueprints
app.register_blueprint(admin_bp)

# Register complainant blueprint
app.register_blueprint(complainant_bp)

# Serve main portal page
@app.route("/")
def home():
    return send_from_directory(frontend_path, "portal/index.html")

# Serve ANY static file from frontend (css, js, images, svg, etc.)
@app.route("/<path:filename>")
def serve_frontend_files(filename):
    return send_from_directory(frontend_path, filename)

# TESTING PURPOSES (ex. http://127.0.0.1:5000/db_test to test db conn)
@app.route("/test-admins")
def test_admins():
    admins = Admin.query.all()
    result = [admin.employee_id for admin in admins]
    return {"admins": result}

@app.route("/test-users")
def test_users():
    from backend.database.models import User
    users = User.query.all()
    if not users:
        return "No users found in the database."
    return "<br>".join([f"{u.user_id}: {u.email}" for u in users])

@app.route("/debug-users")
def debug_users():
    from sqlalchemy import text
    result = db.session.execute(text("SHOW TABLES")).fetchall()
    return {"tables": [r[0] for r in result]}

@app.route('/db_test')
def db_test():
    try:
        db.session.execute(text('SELECT 1'))
        return "Database connection is working!"
    except Exception as e:
        return f"Database connection failed: {e}"

if __name__ == "__main__":
    app.run(debug=True)
