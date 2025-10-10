from flask import Blueprint, request, jsonify, session, render_template, send_from_directory, current_app, abort, redirect
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from backend.database.models import User, Registration, Complaint, LotDispute, BoundaryDispute, RegistrationFamOfMember, RegistrationHOAMember
from backend.database.db import db
from backend.complainant.lot_dispute import get_form_structure as get_lot_form_structure
from backend.complainant.boundary_dispute import get_form_structure as get_boundary_form_structure
from backend.complainant.redirects import complaint_redirect_path
from backend.database.models import BoundaryDispute
import os, json, time

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
# Serve uploaded signature files (for previews)
# -----------------------------
@complainant_bp.route("/signatures/<path:filename>")
def uploaded_signature(filename):
    try:
        # Limit to the known upload directory
        return send_from_directory(UPLOAD_DIR, filename)
    except Exception:
        abort(404)

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
            
            sd = getattr(fam_member, 'supporting_documents', {}) or {}
            # Extract mapped values from supporting_docs JSON
            hoa_raw = sd.get('hoa')
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
                    "current_address": fam_member.current_address or (sd.get('current_address') if sd else "") or "",
                # Pull HOA/lot/civil/recipient/current address from family member JSON
                "hoa": get_area_name(hoa_raw) if hoa_raw else "",
                "block_no": sd.get('block_assignment') or "",
                "lot_no": sd.get('lot_assignment') or "",
                "lot_size": sd.get('lot_size') or "",
                "civil_status": sd.get('civil_status') or "",
                "recipient_of_other_housing": sd.get('recipient_of_other_housing') or "",
                "current_address": sd.get('current_address') or "",
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
# Start complaint: resolve destination form
# Used by dashboard modal to jump to the correct form page
# -----------------------------
@complainant_bp.route("/start-complaint", methods=["POST"])
def start_complaint():
    try:
        user_id = session.get("user_id")
        # Always reply JSON so the frontend never tries to parse HTML
        if not user_id:
            return jsonify({
                "success": False,
                "error": "Not logged in",
                "redirect": "/complainant/complainant_login.html",
            }), 200

        payload = request.get_json(silent=True) or request.form
        complaint_type = payload.get("type") if payload else None

        registration = Registration.query.filter_by(user_id=user_id).first()
        has_registration = bool(registration)

        # Persist the selection in session for later flows
        session["type_of_complaint"] = complaint_type

        # Compute where to send the user (registered users go straight to form, otherwise to not_registered)
        dest = complaint_redirect_path(complaint_type, has_registration)

        # For form routes that need session context, we set what we can here; the specific form route may refine it
        if registration:
            session["registration_id"] = registration.registration_id

        return jsonify({
            "success": True,
            "redirect": dest,
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"Server error: {e}"}), 200

# -----------------------------
# JSON: Complaint details (for timeline)
# Matches frontend fetch: /complainant/complaints/details/<id>
# -----------------------------
@complainant_bp.route("/complaints/details/<int:complaint_id>")
def complaint_details_json(complaint_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "error": "Not logged in"}), 401

    complaint = Complaint.query.get_or_404(complaint_id)
    registration = Registration.query.get(complaint.registration_id)
    if not registration or registration.user_id != user_id:
        return jsonify({"success": False, "error": "Forbidden"}), 403

    return jsonify({
        "success": True,
        "complaint": {
            "complaint_id": complaint.complaint_id,
            "status": complaint.status,
            "created_at": complaint.date_received.isoformat() if getattr(complaint, "date_received", None) else None,
            "type_of_complaint": complaint.type_of_complaint,
            "rejection_reason": getattr(complaint, "rejection_reason", None)
        }
    })


# -----------------------------
# View complaint details
# -----------------------------

@complainant_bp.route("/complaint/<int:complaint_id>")
def view_complaint(complaint_id):
    print('[DEBUG] view_complaint called for complaint_id:', complaint_id)
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/complainant/complainant_login.html")

    complaint = Complaint.query.get_or_404(complaint_id)
    registration = Registration.query.get(complaint.registration_id)
    if not registration or registration.user_id != user_id:
        return abort(403)

    # Attach supporting documents (if any) to the registration object for template access
    try:
        hoa_member = RegistrationHOAMember.query.filter_by(registration_id=registration.registration_id).first()
        if hoa_member and getattr(hoa_member, 'supporting_documents', None):
            # Dynamically attach to the model instance for template convenience
            setattr(registration, 'supporting_documents', hoa_member.supporting_documents)
        else:
            # Ensure attribute exists to simplify template conditionals
            if not hasattr(registration, 'supporting_documents'):
                setattr(registration, 'supporting_documents', None)
    except Exception:
        # On any lookup error, keep a safe default
        if not hasattr(registration, 'supporting_documents'):
            setattr(registration, 'supporting_documents', None)

    # Build answers from the correct complaint table
    answers = {}
    lot_dispute = None
    boundary_dispute = None

    def _parse_list(val):
        try:
            if isinstance(val, list):
                return val
            if isinstance(val, str):
                s = val.strip()
                if not s:
                    return []
                if s.startswith('['):
                    return json.loads(s)
                if ',' in s:
                    return [p.strip() for p in s.split(',') if p.strip()]
                return [s]
        except Exception:
            pass
        return []

    print('[DEBUG] complaint.type_of_complaint:', complaint.type_of_complaint)
    if complaint.type_of_complaint == "Lot Dispute":
        form_structure = get_lot_form_structure("Lot Dispute")
        # Load user's saved answers
        lot_dispute = LotDispute.query.filter_by(complaint_id=complaint_id).first()
        if lot_dispute:
            # q2, q4–q8 can be JSON strings or CSV; normalize to lists
            q2_list = _parse_list(getattr(lot_dispute, 'q2', None))
            q4_list = _parse_list(getattr(lot_dispute, 'q4', None))
            q5_list = _parse_list(getattr(lot_dispute, 'q5', None))
            q6_list = _parse_list(getattr(lot_dispute, 'q6', None))
            q7_list = _parse_list(getattr(lot_dispute, 'q7', None))
            q8_list = _parse_list(getattr(lot_dispute, 'q8', None))

            # q9 may be a json string {claim, documents}
            q9_raw = getattr(lot_dispute, 'q9', None)
            q9_data = {"claim": "", "documents": []}
            try:
                if isinstance(q9_raw, dict):
                    q9_data = {"claim": q9_raw.get("claim", ""), "documents": q9_raw.get("documents", [])}
                elif isinstance(q9_raw, str) and q9_raw.strip():
                    parsed = json.loads(q9_raw)
                    if isinstance(parsed, dict):
                        q9_data = {"claim": parsed.get("claim", ""), "documents": parsed.get("documents", [])}
            except Exception:
                pass

            # q10 may be a json string {reside: Yes/No/Not Sure}
            q10_raw = getattr(lot_dispute, 'q10', None)
            q10_data = {}
            try:
                if isinstance(q10_raw, dict):
                    q10_data = q10_raw
                elif isinstance(q10_raw, str) and q10_raw.strip():
                    q10_data = json.loads(q10_raw)
            except Exception:
                q10_data = {}

            # q3 is a date
            q3_val = lot_dispute.q3.strftime("%Y-%m-%d") if getattr(lot_dispute, 'q3', None) else ""

            answers = {
                "q1": getattr(lot_dispute, 'q1', '') or '',
                "q2": q2_list,
                "q3": q3_val,
                "q4": q4_list,
                "q5": q5_list,
                "q6": q6_list,
                "q7": q7_list,
                "q8": q8_list,
                "q9": q9_data,
                "q10": q10_data,
                "description": getattr(lot_dispute, 'description', None) or getattr(complaint, 'description', '') or '',
                "signature": getattr(lot_dispute, 'signature', None) or getattr(registration, 'signature_path', '') or '',
            }

            print("\n[DEBUG] --- Final Data Before Render ---")
            print("[DEBUG] Complaint Type:", complaint.type_of_complaint)
            print("[DEBUG] form_structure length:", len(form_structure))
            print("[DEBUG] form_structure fields:")
            for f in form_structure:
                print("   ", f.get("name"), "-", f.get("type"))

            print("[DEBUG] answers keys:", list(answers.keys()))
            for k, v in answers.items():
                print(f"   {k}: {v}")
            print("[DEBUG] -----------------------------------\n")
    elif complaint.type_of_complaint == "Boundary Dispute":
        # Build answers from BoundaryDispute
        bd = BoundaryDispute.query.filter_by(complaint_id=complaint_id).first()
        print('[DEBUG] BoundaryDispute record found:', bool(bd))
        boundary_dispute = bd
        form_structure = get_boundary_form_structure("Boundary Dispute")
        if bd:
            print('[DEBUG] Building answers dict for Boundary Dispute')
            def _json_list(v):
                try:
                    if isinstance(v, list):
                        return v
                    if isinstance(v, str) and v.strip():
                        s = v.strip()
                        if s.startswith('['):
                            return json.loads(s)
                        if ',' in s:
                            return [p.strip() for p in s.split(',') if p.strip()]
                    return []
                except Exception:
                    return []
            def _safe(v):
                return v or ''
            # q12 is a list of dicts
            q12_val = []
            try:
                raw = getattr(bd, 'q12', None)
                if isinstance(raw, list):
                    q12_val = raw
                elif isinstance(raw, str) and raw.strip():
                    q12_val = json.loads(raw)
            except Exception:
                q12_val = []

            # Collect all other fields
            answers = {
                'q1': _json_list(getattr(bd, 'q1', None)),
                'q2': _safe(getattr(bd, 'q2', None)),
                'q3': _safe(getattr(bd, 'q3', None)),
                'q4': _safe(getattr(bd, 'q4', None)),
                'q5': _safe(getattr(bd, 'q5', None)),
                'q5_1': getattr(bd, 'q5_1', None).strftime('%Y-%m-%d') if getattr(bd, 'q5_1', None) else '',
                'q6': _json_list(getattr(bd, 'q6', None)),
                'q7': _json_list(getattr(bd, 'q7', None)),
                'q8': _safe(getattr(bd, 'q8', None)),
                'q9': _json_list(getattr(bd, 'q9', None)),
                'q10': _safe(getattr(bd, 'q10', None)),
                'q10_1': _json_list(getattr(bd, 'q10_1', None)),
                'q11': _safe(getattr(bd, 'q11', None)),
                'q12': q12_val,
                'q13': _json_list(getattr(bd, 'q13', None)),
                'q14': _safe(getattr(bd, 'q14', None)),
                'q15': _safe(getattr(bd, 'q15', None)),
                'q15_1': _json_list(getattr(bd, 'q15_1', None)),
                'description': _safe(getattr(bd, 'description', None)),
                'signature_path': _safe(getattr(bd, 'signature_path', None)),
            }
            print("[DEBUG] Complaint Preview Answers:")
            for k, v in answers.items():
                print(f"  {k}: {v} (type: {type(v)})")
    else:
        form_structure = []

    # For family_of_member, include parent details and relationship for header section
    parent_info = None
    relationship = None
    try:
        if registration.category == "family_of_member":
            fam = RegistrationFamOfMember.query.filter_by(registration_id=registration.registration_id).first()
            if fam:
                relationship = fam.relationship
                def _safe(v):
                    return str(v).strip() if v else ""
                parts = [_safe(fam.first_name), _safe(fam.middle_name), _safe(fam.last_name), _safe(fam.suffix)]
                sd = getattr(fam, 'supporting_documents', {}) or {}
                hoa_raw = sd.get('hoa')
                parent_info = {
                    "full_name": " ".join([p for p in parts if p]),
                    "first_name": fam.first_name,
                    "middle_name": fam.middle_name,
                    "last_name": fam.last_name,
                    "suffix": fam.suffix,
                    "date_of_birth": fam.date_of_birth,
                    "sex": fam.sex,
                    "citizenship": fam.citizenship,
                    "age": fam.age,
                    "phone_number": fam.phone_number,
                    "year_of_residence": fam.year_of_residence,
                    "supporting_documents": getattr(fam, 'supporting_documents', None),
                    # Additional mapped fields for templates
                    "hoa": get_area_name(hoa_raw) if hoa_raw else "",
                    "block_no": sd.get('block_assignment') or "",
                    "lot_no": sd.get('lot_assignment') or "",
                    "lot_size": sd.get('lot_size') or "",
                    "civil_status": sd.get('civil_status') or "",
                    "recipient_of_other_housing": sd.get('recipient_of_other_housing') or "",
                    "current_address": sd.get('current_address') or "",
                }
    except Exception:
        pass

    template_name = "complaint_details_valid.html" if complaint.status == "Valid" else "complaint_details_invalid.html"
    return render_template(
        template_name,
        complaint=complaint,
        registration=registration,
        form_structure=form_structure,
        answers=answers,
        get_area_name=get_area_name,
        lot_dispute=lot_dispute,
        boundary_dispute=boundary_dispute,
        parent_info=parent_info,
        relationship=relationship,
    )
