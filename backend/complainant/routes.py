from flask import Blueprint, request, jsonify, session, render_template, send_from_directory, current_app, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from backend.database.models import User, Overlapping, Registration, Complaint, LotDispute, BoundaryDispute
from backend.database.db import db
from backend.complainant.overlapping import get_form_structure
import os, json, time
from werkzeug.utils import secure_filename

# -----------------------------
# Paths
# -----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # backend/
TEMPLATE_DIR = os.path.join(BASE_DIR, "..", "..", "frontend", "complainant", "complaints")
TEMPLATE_DIR = os.path.normpath(TEMPLATE_DIR)

UPLOAD_DIR = os.path.join(BASE_DIR, "uploads", "signatures")  # backend/uploads/signatures
UPLOAD_DIR = os.path.normpath(UPLOAD_DIR)
os.makedirs(UPLOAD_DIR, exist_ok=True)

# -----------------------------
# Blueprint
# -----------------------------
complainant_bp = Blueprint(
    "complainant",
    __name__,
    url_prefix="/complainant",
    template_folder=TEMPLATE_DIR
)

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

            if not first_name or not last_name or not email or not password:
                return jsonify({"success": False, "message": "All fields are required!"}), 400

            if User.query.filter_by(email=email).first():
                return jsonify({"success": False, "message": "Email already registered!"}), 400

            hashed_password = generate_password_hash(password)
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
            return jsonify({"success": False, "message": f"Server error: {e}"}), 500

    return render_template("portal/sign_up.html")

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
# NOT REGISTERED ROUTE
# -----------------------------
@complainant_bp.route("/not_registered")
def not_registered():
    html_dir = os.path.join(current_app.root_path, "frontend", "complainant", "home")
    return send_from_directory(html_dir, "not_registered.html")

# -----------------------------
# Save complaint type in session
# -----------------------------
@complainant_bp.route("/set-complaint-type", methods=["POST"])
def set_complaint_type():
    data = request.get_json(silent=True) or request.form
    ctype = data.get("type")
    if not ctype:
        return jsonify({"success": False, "message": "Missing complaint type"}), 400

    session["type_of_complaint"] = ctype
    return jsonify({"success": True, "message": "Complaint type saved in session."})

# -----------------------------
# Get complaint type from session
# -----------------------------
@complainant_bp.route("/get-complaint-type", methods=["GET"])
def get_complaint_type():
    ctype = session.get("type_of_complaint")
    return jsonify({"success": True, "type": ctype})


# -----------------------------
# View complaint details
# -----------------------------

@complainant_bp.route("/complaint/<int:complaint_id>")
def view_complaint(complaint_id):
    user_id = session.get("user_id")
    if not user_id:
        return "Not logged in", 401

    complaint = Complaint.query.get_or_404(complaint_id)
    registration = Registration.query.get(complaint.registration_id)
    if not registration or registration.user_id != user_id:
        return "Unauthorized", 403

    # Get answers from the correct table
    answers = {}
    form_structure = get_form_structure(complaint.type_of_complaint)

    if complaint.type_of_complaint == "Overlapping":
        overlap = Overlapping.query.filter_by(complaint_id=complaint_id).first()
        if overlap:
            answers = {
                "q1": json.loads(overlap.q1 or "[]"),
                "q2": overlap.q2,
                "q3": overlap.q3,
                "q4": json.loads(overlap.q4 or "[]"),
                "q5": json.loads(overlap.q5 or "[]"),
                "q6": overlap.q6,
                "q7": overlap.q7,
                "q8": overlap.q8,
                "q9": json.loads(overlap.q9 or "[]"),
                "q10": overlap.q10,
                "q11": overlap.q11,
                "q12": overlap.q12,
                "q13": overlap.q13,
                "description": overlap.description,
                "signature": overlap.signature
            }
    # Add more complaint types here as needed

    return render_template(
        "complaint_details_valid.html" if complaint.status == "Valid" else "complaint_details_invalid.html",
        complaint=complaint,
        registration=registration,
        form_structure=form_structure,
        answers=answers
    )




