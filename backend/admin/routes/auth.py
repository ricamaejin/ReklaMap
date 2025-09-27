# admin login copies flash msg in admin_login.html
# admin login routes w db still not working; can insert from flask shell to phpmyadmin, only data w pw hash can login (test admin)
# logout working, but logging in again then choose role would not direct to admin_login again (FIXED)

import os
from flask import Blueprint, request, redirect, url_for, session, jsonify, send_file
from werkzeug.security import check_password_hash
from backend.database.models import Admin

auth_bp = Blueprint("auth", __name__, url_prefix="/admin")

# Path to frontend
frontend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../frontend"))

@auth_bp.route("/login", methods=["POST"])
def login():
    employee_id = request.form.get("employee_id")
    password = request.form.get("password")

    admin = Admin.query.filter_by(employee_id=employee_id).first()

    if admin and check_password_hash(admin.password_hash, password):
        session["employee_id"] = employee_id
        session["admin_name"] = admin.name
        return jsonify({"success": True, "redirect": url_for("auth.dashboard")})
    else:
        return jsonify({"success": False, "message": "Invalid employee ID or password"}), 401

@auth_bp.route("/dashboard")
def dashboard():
    if "employee_id" not in session:
        return redirect(url_for("auth.login"))
    return send_file(os.path.join(frontend_path, "admin", "map", "index.html"))

@auth_bp.route("/current-user")
def current_user():
    if "employee_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    admin = Admin.query.filter_by(employee_id=session["employee_id"]).first()
    if admin:
        return jsonify({"name": admin.name, "employee_id": admin.employee_id})
    else:
        return jsonify({"error": "Admin not found"}), 404

@auth_bp.route("/logout")
def logout():
    session.pop("employee_id", None)
    return send_file(os.path.join(frontend_path, "portal", "index.html"))
