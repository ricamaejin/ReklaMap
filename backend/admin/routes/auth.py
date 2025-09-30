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
    try:
        employee_id = request.form.get("employee_id")
        password = request.form.get("password")
        
        print(f"[DEBUG] Login attempt - Employee ID: {employee_id}")
        print(f"[DEBUG] Password provided: {'Yes' if password else 'No'}")
        
        if not employee_id or not password:
            print("[DEBUG] Missing employee_id or password")
            return jsonify({"success": False, "message": "Employee ID and password are required"}), 400
        
        # Test database connectivity
        try:
            print("[DEBUG] Testing database connection...")
            admin = Admin.query.filter_by(employee_id=employee_id).first()
            print("[DEBUG] Database query completed successfully")
        except Exception as db_error:
            print(f"[ERROR] Database error: {str(db_error)}")
            return jsonify({"success": False, "message": "Database connection error"}), 500
        
        if admin:
            print(f"[DEBUG] Found admin: {admin.name}, Account type: {admin.account}")
            if check_password_hash(admin.password_hash, password):
                print(f"[DEBUG] Password verified for {admin.name}")
                
                session["employee_id"] = employee_id
                session["admin_id"] = admin.admin_id
                session["admin_name"] = admin.name
                session["account_type"] = admin.account
                
                # Redirect based on account type: 1=admin, 2=staff
                if admin.account == 2:  # Staff account
                    redirect_url = "/staff/complaints/assigned"
                    print(f"[DEBUG] Redirecting staff to: {redirect_url}")
                else:  # Admin account (account == 1)
                    redirect_url = url_for("auth.dashboard")
                    print(f"[DEBUG] Redirecting admin to: {redirect_url}")
                    
                return jsonify({"success": True, "redirect": redirect_url})
            else:
                print(f"[DEBUG] Password verification failed for {admin.name}")
                return jsonify({"success": False, "message": "Invalid employee ID or password"}), 401
        else:
            print(f"[DEBUG] No admin found with employee_id: {employee_id}")
            return jsonify({"success": False, "message": "Invalid employee ID or password"}), 401
            
    except Exception as e:
        print(f"[ERROR] Login exception: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": "Server error occurred"}), 500

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
