# MIGHT CHANGE PATHS 
# admin login copies flash msg in admin_login.html
# logout working

import os
from flask import Blueprint, request, redirect, url_for, flash, send_file, session

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

# Mock admins (for now)
mock_admins = {
    "12345": "password123",
    "67890": "secret456"
}

# Path to frontend
frontend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../frontend"))

@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        employee_id = request.form.get("employee_id")
        password = request.form.get("password")

        if employee_id in mock_admins and mock_admins[employee_id] == password:
            session["employee_id"] = employee_id
            flash("Login successful!", "success")
            return redirect(url_for("admin.dashboard"))
        else:
            flash("Invalid Employee ID or Password", "danger")
            return send_file(os.path.join(frontend_path, "portal", "admin_login.html"))

    return send_file(os.path.join(frontend_path, "portal", "admin_login.html"))

@admin_bp.route("/dashboard")
def dashboard():
    if "employee_id" not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for("admin.login"))
    return send_file(os.path.join(frontend_path, "admin", "map", "index.html"))

@admin_bp.route("/logout")
def logout():
    session.pop("employee_id", None)
    flash("You have been logged out.", "info")
    # Instead of requiring you to change the <a>, we just send the portal page directly
    return send_file(os.path.join(frontend_path, "portal", "index.html"))
