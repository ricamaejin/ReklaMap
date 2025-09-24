from flask import Blueprint, request, redirect, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from backend.database.models import User
from backend.database.db import db

complainant_bp = Blueprint("complainant", __name__, url_prefix="/complainant")

# -----------------------------
# SIGNUP ROUTE
# -----------------------------
@complainant_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        try:
            first_name = request.form.get("firstName")
            last_name = request.form.get("lastName")
            email = request.form.get("email")
            password = request.form.get("password")

            # Debug log
            print("📌 SIGNUP DATA:", first_name, last_name, email)

            # Validate required fields
            if not first_name or not last_name or not email or not password:
                return jsonify({"success": False, "message": "All fields are required!"}), 400

            # Check if user already exists
            if User.query.filter_by(email=email).first():
                return jsonify({"success": False, "message": "Email already registered!"}), 400

            # Hash password
            hashed_password = generate_password_hash(password)

            # Create new user
            new_user = User(
                first_name=first_name,
                last_name=last_name,
                email=email,
                password_hash=hashed_password
            )
            db.session.add(new_user)
            db.session.commit()

            return jsonify({"success": True, "message": "Sign-up successful!"})

        except Exception as e:
            db.session.rollback()
            print("❌ SIGNUP ERROR:", e)
            return jsonify({"success": False, "message": f"Server error: {e}"}), 500

    # GET → redirect to signup page
    return redirect("/portal/sign_up.html")


# -----------------------------
# LOGIN ROUTE
# -----------------------------
@complainant_bp.route("/login", methods=["POST"])
def login():
    try:
        email = request.form.get("email")
        password = request.form.get("password")

        if not email or not password:
            return jsonify({"success": False, "message": "Email and password required!"}), 400

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            session["user_id"] = user.user_id
            return jsonify({"success": True, "message": "Login successful!"})
        else:
            return jsonify({"success": False, "message": "Invalid email or password!"}), 401

    except Exception as e:
        print("❌ LOGIN ERROR:", e)
        return jsonify({"success": False, "message": f"Server error: {e}"}), 500
    
# -----------------------------
# PROFILE ROUTE 
# -----------------------------

@complainant_bp.route("/profile", methods=["GET"])
def profile():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "message": "Not logged in"}), 401

    user = User.query.get(user_id)
    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404

    return jsonify({
        "success": True,
        "user": {
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email
        }
    })


# -----------------------------
# LOGOUT ROUTE (Optional)
# -----------------------------
#@complainant_bp.route("/logout", methods=["POST"])
#def logout():
    session.pop("user_id", None)
    return jsonify({"success": True, "message": "Logged out!"})
