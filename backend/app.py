import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import os
from flask import Flask, send_from_directory
from sqlalchemy import text
from backend.database.db import db
from backend.database.models import Admin
from backend.admin.routes import admin_bp

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

# Serve main portal page
@app.route("/")
def home():
    # Optionally, serve your main frontend page here
    return app.send_static_file("portal/index.html")

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

@app.route('/db_test')
def db_test():
    try:
        db.session.execute(text('SELECT 1'))
        return "Database connection is working!"
    except Exception as e:
        return f"Database connection failed: {e}"


if __name__ == "__main__":
    app.run(debug=True)
