
from flask import Blueprint, request, jsonify, session, render_template, send_from_directory, current_app, abort, redirect
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from backend.database.models import User, Overlapping, Registration, Complaint, LotDispute, BoundaryDispute, RegistrationFamOfMember
from backend.database.db import db
from backend.complainant.overlapping import get_form_structure as get_overlap_form_structure
from backend.complainant.lot_dispute import get_form_structure as get_lot_form_structure
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

def get_area_name(area_id):
    """Get area name from area_id"""
    if not area_id:
        return ""
    try:
        from backend.database.models import Area
        area = Area.query.get(int(area_id))
        return area.area_name if area else str(area_id)
    except (ValueError, TypeError):
        return str(area_id)

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
    # Use BASE_DIR to get the correct path
    html_dir = os.path.join(BASE_DIR, "..", "..", "frontend", "complainant", "home")
    html_dir = os.path.normpath(html_dir)
    return send_from_directory(html_dir, "not_registered.html")

# -----------------------------
# View Profile Registered Route
# -----------------------------
@complainant_bp.route("/profile/view")
def view_profile_registered():
    # Use BASE_DIR to get the correct path
    html_dir = os.path.join(BASE_DIR, "..", "..", "frontend", "complainant", "home")
    html_dir = os.path.normpath(html_dir)
    return send_from_directory(html_dir, "view_profile_registered.html")

# -----------------------------
# Profile Registration Route
# -----------------------------
@complainant_bp.route("/profile/registration", methods=["GET"])
def profile_registration():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "message": "Not logged in"}), 401

    registration = Registration.query.filter_by(user_id=user_id).first()
    if not registration:
        return jsonify({"success": False, "registered": False, "message": "No registration found"})

    # Convert registration data to dictionary
    reg_data = {
        "category": registration.category,
        "last_name": registration.last_name,
        "first_name": registration.first_name,
        "middle_name": registration.middle_name,
        "suffix": registration.suffix,
        "date_of_birth": registration.date_of_birth.strftime("%Y-%m-%d") if registration.date_of_birth else "",
        "sex": registration.sex,
        "citizenship": registration.citizenship,
        "age": registration.age,
        "phone_number": registration.phone_number,
        "year_of_residence": registration.year_of_residence,
        "current_address": registration.current_address,
        "civil_status": registration.civil_status,
        "hoa": get_area_name(registration.hoa) if registration.hoa else "",
        "block_no": registration.block_no,
        "lot_no": registration.lot_no,
        "lot_size": registration.lot_size,
        "recipient_of_other_housing": registration.recipient_of_other_housing,
        "relationship": ""  # This will be overwritten for family members
    }

    # For family members, add parent info and relationship if available
    if registration.category == "family_of_member":
        fam_member = RegistrationFamOfMember.query.filter_by(registration_id=registration.registration_id).first()
        if fam_member:
            # Update the relationship from the fam_member table
            reg_data["relationship"] = fam_member.relationship
            
            reg_data["parent_info"] = {
                "last_name": fam_member.last_name,
                "first_name": fam_member.first_name,
                "middle_name": fam_member.middle_name,
                "suffix": fam_member.suffix,
                "date_of_birth": fam_member.date_of_birth.strftime("%Y-%m-%d") if fam_member.date_of_birth else "",
                "sex": fam_member.sex,
                "citizenship": fam_member.citizenship,
                "age": fam_member.age,
                "phone_number": fam_member.phone_number,
                "year_of_residence": fam_member.year_of_residence,
                "civil_status": registration.civil_status,  # This comes from main registration
                "current_address": registration.current_address,  # This comes from main registration
                "hoa": get_area_name(registration.hoa) if registration.hoa else "",  # HOA info comes from main registration
                "block_no": registration.block_no,  # Block info comes from main registration  
                "lot_no": registration.lot_no,  # Lot info comes from main registration
                "lot_size": registration.lot_size,  # Lot size comes from main registration
            }

    return jsonify({
        "success": True,
        "registered": True,
        "registration": reg_data
    })


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
    # Select form structure provider by complaint type
    if complaint.type_of_complaint == "Overlapping":
        form_structure = get_overlap_form_structure("Overlapping")
    elif complaint.type_of_complaint == "Lot Dispute":
        form_structure = get_lot_form_structure("Lot Dispute")
    else:
        form_structure = []

    if complaint.type_of_complaint == "Overlapping":
        overlap = Overlapping.query.filter_by(complaint_id=complaint_id).first()
        if overlap:
            # New DB: q1 CSV current_status, q2 JSON pairs
            # q2 -> pairs list
            q2_pairs = []
            try:
                # overlap.q2 is JSON-typed; if driver returns dict/list, use directly; if string, parse
                if isinstance(overlap.q2, (list, dict)):
                    q2_pairs = overlap.q2 if isinstance(overlap.q2, list) else [overlap.q2]
                else:
                    q2_pairs = json.loads(overlap.q2 or "[]")
            except Exception:
                q2_pairs = []
            # q1 -> current_status list for checkbox rendering
            q1_list = []
            if overlap.q1:
                q1_list = [s.strip() for s in str(overlap.q1).split(',') if s.strip()]
            answers = {
                "q1": q1_list,
                "q2": q2_pairs,
                "q3": overlap.q3,
                "q4": (overlap.q4 if isinstance(overlap.q4, list) else json.loads(overlap.q4 or "[]") if overlap.q4 else []),
                "q5": (overlap.q5 if isinstance(overlap.q5, list) else json.loads(overlap.q5 or "[]") if overlap.q5 else []),
                # q6 is now plain string
                "q6": overlap.q6,
                "q7": overlap.q7,
                "q8": overlap.q8,
                "q9": (overlap.q9 if isinstance(overlap.q9, list) else json.loads(overlap.q9 or "[]") if overlap.q9 else []),
                "q10": overlap.q10,
                "q11": overlap.q11,
                "q12": overlap.q12,
                "q13": overlap.q13,
                "description": overlap.description,
                "signature": overlap.signature
            }
            # Derive whether someone claimed overlap (Yes/No)
            # If a sentinel '__yes_no_details__' exists, it means user picked Yes without selecting specific details.
            try:
                q9_list = answers.get("q9") or []
                if isinstance(q9_list, str):
                    # tolerate string-encoded JSON
                    q9_list = json.loads(q9_list or "[]")
                has_yes = False
                if isinstance(q9_list, list):
                    has_yes = len(q9_list) > 0
                    # Special-case sentinel
                    if not has_yes and "__yes_no_details__" in q9_list:
                        has_yes = True
                answers["q9_approach"] = "yes" if has_yes else "no"
            except Exception:
                answers["q9_approach"] = "no"
    elif complaint.type_of_complaint == "Lot Dispute":
        # Build answers for Lot Dispute
        lot = LotDispute.query.filter_by(complaint_id=complaint_id).first()
        if lot:
            # q5 is stored as JSON in DB (may be a JSON string) -> parse to list
            try:
                q5_list = lot.q5 if isinstance(lot.q5, list) else json.loads(lot.q5 or "[]")
            except Exception:
                q5_list = []
            # q3 is a date
            q3_val = lot.q3.strftime("%Y-%m-%d") if lot.q3 else ""
            answers = {
                "q1": lot.q1,
                "q2": lot.q2,
                "q3": q3_val,
                "q4": lot.q4,
                "q5": q5_list,
                "q6": lot.q6,
                "q7": lot.q7,
                "q8": lot.q8,
                "q9": lot.q9,
                # Prefer lot-level description/signature, fallback to complaint/registration
                "description": (getattr(lot, "description", None) or complaint.description or ""),
                "signature": (getattr(lot, "signature", None) or registration.signature_path or ""),
            }
    # Add more complaint types here as needed
    
    # For family members, add parent info and relationship
    parent_info = None
    relationship = None
    print(f"[DEBUG] Registration category: {registration.category}")
    if registration.category == "family_of_member":
        print("[DEBUG] Processing family member...")
        fam_member = RegistrationFamOfMember.query.filter_by(registration_id=registration.registration_id).first()
        print(f"[DEBUG] Found fam_member: {fam_member}")
        if fam_member:
            relationship = fam_member.relationship
            print(f"[DEBUG] Relationship: {relationship}")
            
            def safe(val):
                if not val:
                    return ""
                val_str = str(val).strip()
                if val_str.lower() in {"na", "n/a", "none"}:
                    return ""
                return val_str
            
            # Parent info from fam_member table
            parent_name_parts = [safe(fam_member.first_name), safe(fam_member.middle_name), safe(fam_member.last_name), safe(fam_member.suffix)]
            parent_full_name = " ".join([part for part in parent_name_parts if part])
            
            parent_info = {
                "full_name": parent_full_name,
                "first_name": fam_member.first_name,
                "middle_name": fam_member.middle_name,
                "last_name": fam_member.last_name,
                "suffix": fam_member.suffix,
                "date_of_birth": fam_member.date_of_birth,
                "sex": fam_member.sex,
                "citizenship": fam_member.citizenship,
                "age": fam_member.age,
                "phone_number": fam_member.phone_number,
                "year_of_residence": fam_member.year_of_residence,
            }
            print(f"[DEBUG] Created parent_info: {parent_info}")
        else:
            print("[DEBUG] No fam_member found")
    else:
        print("[DEBUG] Not a family member")
    
    print(f"[DEBUG] Final values - parent_info: {parent_info is not None}, relationship: {relationship}")
    
    # Determine whether to show Overlapping-specific Q9 follow-up (checkbox block)
    form_structure_display = form_structure
    if complaint.type_of_complaint == "Overlapping":
        try:
            show_q9_followup = False
            if answers:
                # Primary: explicit derived flag
                if answers.get("q9_approach") == "yes":
                    show_q9_followup = True
                else:
                    # Fallback: inspect q9 list (handles sentinel and actual selections)
                    q9_list = answers.get("q9") or []
                    if isinstance(q9_list, str):
                        try:
                            q9_list = json.loads(q9_list or "[]")
                        except Exception:
                            q9_list = []
                    if isinstance(q9_list, list) and ("__yes_no_details__" in q9_list or len(q9_list) > 0):
                        show_q9_followup = True
            if not show_q9_followup:
                form_structure_display = [f for f in form_structure if f.get("name") != "q9"]
        except Exception:
            form_structure_display = form_structure

    return render_template(
        "complaint_details_valid.html" if complaint.status == "Valid" else "complaint_details_invalid.html",
        complaint=complaint,
        registration=registration,
        form_structure=form_structure_display,
        answers=answers,
        parent_info=parent_info,
        relationship=relationship,
        get_area_name=get_area_name
    )

# -----------------------------
# Utility route: Handle complaint type selection and registration check
# -----------------------------
@complainant_bp.route("/start-complaint", methods=["POST"])
def start_complaint():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "message": "Not logged in"}), 401
    complaint_type = request.form.get("type") or request.json.get("type")
    if not complaint_type:
        return jsonify({"success": False, "message": "Complaint type required"}), 400
    session["type_of_complaint"] = complaint_type
    registration = Registration.query.filter_by(user_id=user_id).first()
    if registration:
        # Registration exists, redirect to complaint form
        if complaint_type == "Overlapping":
            return redirect("/complainant/overlapping/new_overlap_form")
        elif complaint_type == "Lot Dispute":
            # Route belongs to the lot_dispute blueprint
            return redirect("/complainant/lot_dispute/new_lot_dispute_form")
        elif complaint_type == "Boundary Dispute":
            # Route belongs to the boundary_dispute blueprint
            return redirect("/complainant/boundary_dispute/new_boundary_dispute_form")
        elif complaint_type == "Pathway Dispute":
            return redirect("/complainant/complaints/pathway_dispute.html")
        elif complaint_type == "Unauthorized Occupation":
            return redirect("/complainant/complaints/unauthorized_occupation.html")
        elif complaint_type == "Illegal Construction":
            return redirect("/complainant/complaints/illegal_construction.html")
        else:
            return redirect("/complainant/home/dashboard.html")
    else:
        # No registration, redirect to not_registered.html
        return redirect("/complainant/not_registered")


