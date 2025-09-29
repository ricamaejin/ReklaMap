import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import os
from flask import Flask, send_from_directory
from flask import Flask, send_from_directory
from sqlalchemy import text

# backend

# backend
from backend.database.db import db
from backend.database.models import Admin
from backend.admin.routes.auth import auth_bp
from backend.admin.routes.map import map_bp
from backend.admin.routes.complaints import complaints_bp
from backend.admin.routes.areas import areas_bp
from backend.admin.routes.beneficiaries import beneficiaries_bp
from backend.admin.routes.blocks import blocks_bp
from backend.admin.routes.search import search_bp
from backend.admin.routes.policies import policies_bp
from backend.complainant.routes import complainant_bp
from backend.complainant.memreg import mem_reg_bp
# Complainant complaints API blueprint
from backend.complainant.complaints_api import complaints_bp as complainant_complaints_bp
from backend.complainant.nonmemreg import nonmemreg_bp


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
app.register_blueprint(auth_bp)
app.register_blueprint(map_bp)
app.register_blueprint(complaints_bp)
app.register_blueprint(areas_bp)
app.register_blueprint(beneficiaries_bp)
app.register_blueprint(blocks_bp)
app.register_blueprint(search_bp)
app.register_blueprint(policies_bp)

# Register complainant blueprint
app.register_blueprint(complainant_bp)
app.register_blueprint(mem_reg_bp)
app.register_blueprint(complainant_complaints_bp)
app.register_blueprint(nonmemreg_bp)

# Serve main portal page
@app.route("/")
def home():
    # Optionally, serve your main frontend page here
    return app.send_static_file("portal/index.html")
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

# Add this route to test your specific admin query
@app.route("/test-admin-query")
def test_admin_query():
    try:
        admin = Admin.query.filter_by(employee_id="12345").first()
        if admin:
            return {
                "found": True,
                "employee_id": admin.employee_id,
                "name": admin.name,
                "has_password_hash": bool(admin.password_hash)
            }
        else:
            return {"found": False}
    except Exception as e:
        return {"error": str(e)}

@app.route('/db_test')
def db_test():
    try:
        db.session.execute(text('SELECT 1'))
        return "Database connection is working!"
    except Exception as e:
        return f"Database connection failed: {e}"

# Add this route to test your specific admin query
@app.route("/test-admin-query")
def test_admin_query():
    try:
        admin = Admin.query.filter_by(employee_id="12345").first()
        if admin:
            return {
                "found": True,
                "employee_id": admin.employee_id,
                "name": admin.name,
                "has_password_hash": bool(admin.password_hash)
            }
        else:
            return {"found": False}
    except Exception as e:
        return {"error": str(e)}

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

if __name__ == "__main__":
    app.run(debug=True)
