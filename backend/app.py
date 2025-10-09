import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask import Flask, send_from_directory
from sqlalchemy import text

# backend
from backend.database.db import db
from backend.database.models import Admin
from backend.admin.routes.auth import auth_bp
from backend.admin.routes.map import map_bp
from backend.admin.routes.complaints import complaints_bp
from backend.admin.routes.timeline import timeline_bp
from backend.admin.routes.areas import areas_bp
from backend.admin.routes.beneficiaries import beneficiaries_bp
from backend.admin.routes.blocks import blocks_bp
from backend.admin.routes.search import search_bp
from backend.admin.routes.policies import policies_bp
from backend.complainant.routes import complainant_bp
from backend.staff.routes import staff_bp
from backend.shared.routes import shared_bp
from backend.complainant.memreg import mem_reg_bp
from backend.complainant.complaints_api import complaints_bp as complainant_complaints_bp
from backend.complainant.nonmemreg import nonmemreg_bp
from backend.complainant.famreg import famreg_bp
# Overlapping blueprint
from backend.complainant.overlapping import overlapping_bp
# Lot Dispute blueprint
from backend.complainant.lot_dispute import lot_dispute_bp
# Boundary Dispute blueprint
from backend.complainant.boundary_dispute import boundary_dispute_bp


# Set static_folder to your frontend directory, static_url_path to ""
frontend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../frontend"))
# Added template_folder=frontend_path so Flask can also look for templates in frontend_path.
# This won't affect existing routes unless you explicitly use render_template with files from that folder.
app = Flask(__name__, static_folder=frontend_path, static_url_path="", template_folder=frontend_path)

# for db (not in use atm; don't know where this is applied)
app.secret_key = "your_secret_key"

# ✅ Correct Database configuration
app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+pymysql://root:reklaMap123%2B@72.60.108.94:3306/reklamap"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# ✅ Initialize db with app
db.init_app(app)

# Add custom Jinja2 filters
@app.template_filter('split')
def split_filter(value, delimiter=','):
    """Split a string by delimiter and return a list"""
    if not value:
        return []
    return str(value).split(delimiter)

@app.template_filter('from_json')
def from_json_filter(value):
    """Parse JSON string and return Python object"""
    if not value:
        return []
    try:
        import json
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(map_bp)
app.register_blueprint(complaints_bp)
app.register_blueprint(timeline_bp)
app.register_blueprint(areas_bp)
app.register_blueprint(beneficiaries_bp)
app.register_blueprint(blocks_bp)
app.register_blueprint(search_bp)
app.register_blueprint(policies_bp)

app.register_blueprint(complainant_bp)
app.register_blueprint(mem_reg_bp)
app.register_blueprint(complainant_complaints_bp)
app.register_blueprint(nonmemreg_bp)
app.register_blueprint(famreg_bp)
app.register_blueprint(overlapping_bp)
app.register_blueprint(lot_dispute_bp)
app.register_blueprint(boundary_dispute_bp)

# Register staff and shared blueprints
app.register_blueprint(staff_bp)
app.register_blueprint(shared_bp)

# Serve main portal page
@app.route("/")
def home():
    # Optionally, serve your main frontend page here
    return app.send_static_file("portal/index.html")
    # Optionally, serve your main frontend page here
    return app.send_static_file("portal/index.html")

# Serve static assets only (css, js, images, svg, etc.)
@app.route("/<path:filename>")
def serve_frontend_files(filename):
    # Only serve files from asset folders
    asset_folders = ["css", "js", "images", "svg"]
    if any(filename.startswith(folder + "/") for folder in asset_folders):
        return send_from_directory(frontend_path, filename)
    # Otherwise, let blueprints handle the route
    return "Not Found", 404

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
