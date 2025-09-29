from flask import Blueprint, request, jsonify, session, render_template, send_from_directory, current_app, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from backend.database.models import User, Overlapping, Registration, Complaint
from backend.database.db import db
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

    session["complaint_type"] = ctype
    return jsonify({"success": True, "message": "Complaint type saved in session."})

# -----------------------------
# Get complaint type from session
# -----------------------------
@complainant_bp.route("/get-complaint-type", methods=["GET"])
def get_complaint_type():
    ctype = session.get("complaint_type")
    return jsonify({"success": True, "type": ctype})

# -----------------------------
# OVERLAP FORM ROUTE
# -----------------------------
@complainant_bp.route('/new_overlap_form')
def new_overlap_form():
    user_id = session.get('user_id')
    if not user_id:
        return "Not logged in", 401

    registration = Registration.query.filter_by(user_id=user_id).first()
    if not registration:
        return "No registration found for user", 400

    complaint_id = f"{user_id}-{int(time.time())}"
    session['complaint_id'] = complaint_id
    session['registration_id'] = registration.registration_id

    html_dir = TEMPLATE_DIR
    return send_from_directory(html_dir, 'overlapping.html')

# -----------------------------
# Get overlap session data
# -----------------------------
@complainant_bp.route('/get_overlap_session_data')
def get_overlap_session_data():
    return jsonify({
        "complaint_id": session.get('complaint_id'),
        "registration_id": session.get('registration_id')
    })

# -----------------------------
# Submit overlap complaint
# -----------------------------
@complainant_bp.route("/submit_overlap", methods=["POST"])
def submit_overlap():
    try:
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"success": False, "message": "User not logged in"}), 401

        registration_id = request.form.get("registration_id")
        registration = Registration.query.get(registration_id)
        if not registration:
            return jsonify({"success": False, "message": "Parent registration does not exist"}), 400

        # Create Complaint entry
        new_complaint = Complaint(
            registration_id=registration.registration_id,
            type_of_complaint="Overlapping",
            status="Valid"
        )
        db.session.add(new_complaint)
        db.session.flush()

        # Parse form fields
        q1 = json.loads(request.form.get("q1") or "[]")
        q4 = json.loads(request.form.get("evidence") or "[]")
        q5 = json.loads(request.form.get("discover") or "[]")
        q9 = json.loads(request.form.get("other_claim") or "[]")
        q2 = request.form.get("current_status")
        q3 = request.form.get("occupancy_duration")
        q6 = request.form.get("construction_timeframe")
        q7 = request.form.get("who_else")
        q8 = request.form.get("involved_person_name")
        q10 = request.form.get("reported_to")
        q11 = request.form.get("inspection")
        q12 = request.form.get("report_result")
        q13 = request.form.get("impact")
        description = request.form.get("description")

        # Handle signature
        signature_file = request.files.get("signature")
        signature_filename = None
        if signature_file:
            signature_filename = secure_filename(signature_file.filename)
            save_path = os.path.join(UPLOAD_DIR, signature_filename)
            signature_file.save(save_path)
            print("Signature saved to:", save_path)  # ✅ Debug print

        # Save Overlapping
        new_overlap = Overlapping(
            complaint_id=new_complaint.complaint_id,
            registration_id=registration.registration_id,
            q1=json.dumps(q1),
            q2=q2,
            q3=q3,
            q4=json.dumps(q4),
            q5=json.dumps(q5),
            q6=q6,
            q7=q7,
            q8=q8,
            q9=json.dumps(q9),
            q10=q10,
            q11=q11,
            q12=q12,
            q13=q13,
            description=description,
            signature=signature_filename
        )

        db.session.add(new_overlap)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Overlap complaint submitted successfully!",
            "complaint_id": new_complaint.complaint_id
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Server error: {e}"}), 500

# -----------------------------
# View complaint
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

    overlap_data = None
    if complaint.type_of_complaint == "Overlapping":
        overlap_data = Overlapping.query.filter_by(complaint_id=complaint_id).first()
        if overlap_data:
            overlap_data.q1 = json.loads(overlap_data.q1 or "[]")
            overlap_data.q4 = json.loads(overlap_data.q4 or "[]")
            overlap_data.q5 = json.loads(overlap_data.q5 or "[]")
            overlap_data.q9 = json.loads(overlap_data.q9 or "[]")

    return render_template(
        "complaint_details_valid.html",
        complaint=complaint,
        overlap=overlap_data
    )

# -----------------------------
# Serve uploaded signatures
# -----------------------------
@complainant_bp.route("/uploads/signatures/<filename>")
def uploaded_signature(filename):
    # Make filename safe
    safe_filename = secure_filename(filename)

    # Use absolute path
    upload_dir = r"C:\Users\win10\Documents\GitHub\ReklaMap\backend\uploads\signatures"
    file_path = os.path.join(upload_dir, safe_filename)

    # Check if file exists
    if not os.path.isfile(file_path):
        print(f"Looking for: {file_path}")  # Debug line
        abort(404, description=f"File '{safe_filename}' not found")

    # Serve the file
    return send_from_directory(directory=upload_dir, path=safe_filename)