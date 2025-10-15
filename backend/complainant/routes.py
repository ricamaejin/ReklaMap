from flask import Blueprint, request, jsonify, session, render_template, send_from_directory, current_app, abort, redirect
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from backend.database.models import User, Registration, Complaint, LotDispute, BoundaryDispute, RegistrationFamOfMember, RegistrationHOAMember, RegistrationNonMember
from backend.database.db import db
from backend.complainant.lot_dispute import get_form_structure as get_lot_form_structure
from backend.complainant.boundary_dispute import get_form_structure as get_boundary_form_structure
from backend.complainant.redirects import complaint_redirect_path
from backend.database.models import BoundaryDispute, PathwayDispute
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
    # Try both possible upload locations for signatures
    import os
    # 1. backend/uploads/signatures
    main_upload_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "uploads", "signatures"))
    # 2. backend/complainant/uploads/signatures (legacy or alternate)
    complainant_upload_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "uploads", "signatures"))
    for dir_path in [main_upload_dir, complainant_upload_dir]:
        file_path = os.path.join(dir_path, filename)
        if os.path.isfile(file_path):
            return send_from_directory(dir_path, filename)
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


@complainant_bp.route("/has-active-complaint", methods=["GET"])
def has_active_complaint():
    """Return whether the logged-in user's registration has any complaint
    with complaint_stage in ('Pending','Ongoing').
    """
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"success": True, "has_active": False})

    # Find registration for this user
    reg = Registration.query.filter_by(user_id=user_id).first()
    if not reg:
        return jsonify({"success": True, "has_active": False})

    # Query complaints linked to this registration
    active = Complaint.query.filter(
        Complaint.registration_id == reg.registration_id,
        Complaint.complaint_stage.in_(["Pending", "Ongoing"])  # pending or ongoing
    ).first() is not None

    return jsonify({"success": True, "has_active": bool(active)})

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

    # Attach supporting documents (if any) to the registration object
    try:
        hoa_member = RegistrationHOAMember.query.filter_by(registration_id=registration.registration_id).first()
        if hoa_member and getattr(hoa_member, 'supporting_documents', None):
            setattr(registration, 'supporting_documents', hoa_member.supporting_documents)
        else:
            if not hasattr(registration, 'supporting_documents'):
                setattr(registration, 'supporting_documents', None)
    except Exception:
        if not hasattr(registration, 'supporting_documents'):
            setattr(registration, 'supporting_documents', None)

    # Initialize
    answers = {}
    lot_dispute = None
    boundary_dispute = None
    pathway_dispute = None
    form_structure = []

    # Helper functions
    import json
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

    def _parse_json_list(val):
        try:
            if isinstance(val, list):
                return val
            if isinstance(val, str):
                s = val.strip()
                if not s:
                    return []
                return json.loads(s)
        except Exception as e:
            print('[DEBUG] _parse_json_list error:', e, 'val:', val)
        return []

    def _parse_str(val):
        if val is None:
            return ''
        if isinstance(val, str):
            return val
        try:
            return str(val)
        except Exception:
            return ''

    def _parse_date(val):
        if not val:
            return ''
        try:
            return val.strftime('%Y-%m-%d')
        except Exception:
            return str(val)

    print('[DEBUG] complaint.type_of_complaint:', complaint.type_of_complaint)

    # -----------------------------
    # Lot Dispute
    # -----------------------------
    if complaint.type_of_complaint == "Lot Dispute":
        form_structure = get_lot_form_structure("Lot Dispute")
        lot_dispute = LotDispute.query.filter_by(complaint_id=complaint_id).first()
        if lot_dispute:
            q2_list = _parse_list(getattr(lot_dispute, 'q2', None))
            q4_list = _parse_list(getattr(lot_dispute, 'q4', None))
            q5_list = _parse_list(getattr(lot_dispute, 'q5', None))
            q6_list = _parse_list(getattr(lot_dispute, 'q6', None))
            q7_list = _parse_list(getattr(lot_dispute, 'q7', None))
            q8_list = _parse_list(getattr(lot_dispute, 'q8', None))
            # q9
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
            # q10
            q10_raw = getattr(lot_dispute, 'q10', None)
            q10_data = {}
            try:
                if isinstance(q10_raw, dict):
                    q10_data = q10_raw
                elif isinstance(q10_raw, str) and q10_raw.strip():
                    q10_data = json.loads(q10_raw)
            except Exception:
                q10_data = {}

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

    # -----------------------------
    # Boundary Dispute
    # -----------------------------
    elif complaint.type_of_complaint == "Boundary Dispute":
        boundary_dispute = BoundaryDispute.query.filter_by(complaint_id=complaint_id).first()
        form_structure = get_boundary_form_structure("Boundary Dispute")
        bd = boundary_dispute
        if bd:
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

            _safe = lambda v: v or ''
            q12_val = []
            try:
                raw = getattr(bd, 'q12', None)
                if isinstance(raw, list):
                    q12_val = raw
                elif isinstance(raw, str) and raw.strip():
                    q12_val = json.loads(raw)
            except Exception:
                q12_val = []

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

    # -----------------------------
    # Pathway Dispute
    # -----------------------------
    elif complaint.type_of_complaint == "Pathway Dispute":
        from backend.complainant.pathway_dispute import get_form_structure as get_pathway_form_structure
        from backend.database.models import PathwayDispute
        form_structure = get_pathway_form_structure("Pathway Dispute")
        pathway_dispute = PathwayDispute.query.filter_by(complaint_id=complaint_id).first()
        if pathway_dispute:
            q12_val = getattr(pathway_dispute, 'q12', None)
            answers = {
                'q1': getattr(pathway_dispute, 'q1', None) or '',
                'q2': getattr(pathway_dispute, 'q2', None) or '',
                'q3': getattr(pathway_dispute, 'q3', None) or '',
                'q4': getattr(pathway_dispute, 'q4', None) or '',
                'q5': _parse_json_list(getattr(pathway_dispute, 'q5', None)),
                'q6': getattr(pathway_dispute, 'q6', None) or '',
                'q7': getattr(pathway_dispute, 'q7', None) or '',
                'q8': _parse_json_list(getattr(pathway_dispute, 'q8', None)),
                'q9': _parse_json_list(getattr(pathway_dispute, 'q9', None)),
                'q10': getattr(pathway_dispute, 'q10', None) or '',
                'q11': _parse_json_list(getattr(pathway_dispute, 'q11', None)),
                'q12': _parse_str(q12_val),
                'description': getattr(pathway_dispute, 'description', None) or getattr(complaint, 'description', '') or '',
                'signature': getattr(pathway_dispute, 'signature', None) or getattr(registration, 'signature_path', '') or '',
            }
        else:
            answers = {}
            print("[DEBUG] No PathwayDispute record found for complaint_id", complaint_id)

    # -----------------------------
    # Unauthorized Occupation
    # -----------------------------
    elif complaint.type_of_complaint == "Unauthorized Occupation":
        from backend.complainant.unauthorized_occupation import get_form_structure as get_unauth_form_structure
        from backend.database.models import UnauthorizedOccupation

        form_structure = get_unauth_form_structure()
        unauthorized_occupation = UnauthorizedOccupation.query.filter_by(complaint_id=complaint_id).first()

        if unauthorized_occupation:
            q6a_val = getattr(unauthorized_occupation, 'q6a', None)
            q8_val = getattr(unauthorized_occupation, 'q8', None)

            answers = {
                'block_lot': _parse_json_list(getattr(unauthorized_occupation, 'block_lot', None)),
                'q1': getattr(unauthorized_occupation, 'q1', None) or '',
                'q2': _parse_json_list(getattr(unauthorized_occupation, 'q2', None)),
                'q3': _parse_date(getattr(unauthorized_occupation, 'q3', None)),
                'q4': _parse_json_list(getattr(unauthorized_occupation, 'q4', None)),
                'q5': getattr(unauthorized_occupation, 'q5', None) or '',
                'q5a': _parse_json_list(getattr(unauthorized_occupation, 'q5a', None)),
                'q6': getattr(unauthorized_occupation, 'q6', None) or '',
                'q6a': q6a_val or '',
                'q7': _parse_json_list(getattr(unauthorized_occupation, 'q7', None)),
                'q8': q8_val or '',
                'description': getattr(unauthorized_occupation, 'description', None) or getattr(complaint, 'description', '') or '',
                'signature': getattr(unauthorized_occupation, 'signature', None) or getattr(registration, 'signature_path', '') or '',
            }
            print("[DEBUG] Unauthorized Occupation Preview Answers:")
            for k, v in answers.items():
                print(f"  {k}: {v} (type: {type(v)})")
        else:
            answers = {}
            print("[DEBUG] No UnauthorizedOccupation record found for complaint_id", complaint_id)

    # -----------------------------
    # Fallback if complaint type unknown
    # -----------------------------
    else:
        form_structure = []

    # -----------------------------
    # Family of member info
    # -----------------------------
    parent_info = None
    relationship = None
    try:
        if registration.category == "family_of_member":
            fam = RegistrationFamOfMember.query.filter_by(registration_id=registration.registration_id).first()
            if fam:
                relationship = fam.relationship
                _safe = lambda v: str(v).strip() if v else ""
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

    # Non-member connections aggregation for display
    non_member_connections = None
    non_member_connections_list = None
    try:
        cat = (registration.category or '').strip().lower()
        if cat == 'non_member':
            reg_non_member = RegistrationNonMember.query.filter_by(registration_id=registration.registration_id).first()
            labels = [
                "I live on the lot but I am not the official beneficiary",
                "I live near the lot and I am affected by the issue",
                "I am claiming ownership of the lot",
                "I am related to the person currently occupying the lot",
                "I was previously assigned to this lot but was replaced or removed",
            ]
            display = []
            conn = getattr(reg_non_member, 'connections', None) if reg_non_member else None
            if isinstance(conn, dict):
                for idx, label in enumerate(labels, start=1):
                    v = conn.get(f'connection_{idx}')
                    if v in (True, 1, '1', 'true', 'True', 'yes', 'on'):
                        display.append(label)
                other = conn.get('connection_other')
                if other:
                    other_s = str(other).strip()
                    if other_s:
                        display.append(other_s)
            elif isinstance(conn, list):
                display = [str(x).strip() for x in conn if str(x).strip()]
            elif isinstance(conn, str):
                s = conn.strip()
                if s:
                    # If it's a JSON array string, parse it
                    if s.startswith('[') and s.endswith(']'):
                        try:
                            arr = json.loads(s)
                            if isinstance(arr, list):
                                display = [str(x).strip() for x in arr if str(x).strip()]
                            else:
                                display = [s]
                        except Exception:
                            # Fallback: split by comma
                            display = [p.strip() for p in s.split(',') if p.strip()]
                    else:
                        # Try comma-separated string
                        if ',' in s:
                            display = [p.strip() for p in s.split(',') if p.strip()]
                        else:
                            display = [s]
            elif conn is not None:
                s = str(conn).strip()
                if s:
                    display = [s]

            non_member_connections_list = display
            non_member_connections = ", ".join(display) if display else ""
    except Exception as e:
        print('[WARN] Failed to compute non_member connections:', e)
        non_member_connections = None
        non_member_connections_list = None

    # Render 'valid' details only when complaint.status == 'Valid' and complaint_stage is not a final non-actionable stage.
    # Treat 'Out of Jurisdiction' and 'Unresolved' complaint_stage as cases that should show the invalid/details popup.
    non_actionable_stages = ("Out of Jurisdiction", "Unresolved")
    if getattr(complaint, 'status', '') == "Valid" and (getattr(complaint, 'complaint_stage', None) not in non_actionable_stages):
        template_name = "complaint_details_valid.html"
    else:
        template_name = "complaint_details_invalid.html"
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
        pathway_dispute=pathway_dispute,
        non_member_connections=non_member_connections,
        non_member_connections_list=non_member_connections_list,
    )
