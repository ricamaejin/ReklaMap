from flask import Blueprint, request, jsonify, session, render_template, send_from_directory, current_app, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from backend.database.models import User, Overlapping, Registration, Complaint, LotDispute, BoundaryDispute
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
    registration_id = session.get("registration_id")
    complaint_id = session.get("complaint_id")

    if not registration_id:
        return jsonify({"error": "No registration found in session"}), 400

    reg = Registration.query.get(registration_id)
    if not reg:
        return jsonify({"error": "Registration not found"}), 404

    def safe(val):
        """Turn None, 'NA', 'N/A', 'None' into empty string."""
        if not val:
            return ""
        val_str = str(val).strip()
        if val_str.lower() in {"na", "n/a", "none"}:
            return ""
        return val_str

    name_parts = [safe(reg.first_name), safe(reg.middle_name), safe(reg.last_name), safe(reg.suffix)]
    full_name = " ".join([part for part in name_parts if part])
    return jsonify({
        "complaint_id": complaint_id,
        "registration_id": reg.registration_id,
        "full_name": full_name,
        "date_of_birth": reg.date_of_birth.isoformat() if reg.date_of_birth else "",
        "sex": reg.sex,
        "civil_status": reg.civil_status,
        "citizenship": reg.citizenship,
        "cur_add": reg.current_address,
        "hoa": reg.hoa,   # if HOA is a relationship, you can use reg.hoa.name
        "blk_num": reg.block_no,
        "lot_num": reg.lot_no,
        "lot_size": reg.lot_size,
        "phone_number": reg.phone_number,
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

        # Validate q8 (name) and q1 (block/lot) against Beneficiary table
        from backend.database.models import Beneficiary
        complaint_status = "Invalid"
        beneficiary_match = None
        if q8:
            # Try to match full name (first, last, middle, suffix)
            name_parts = q8.strip().split()
            # Build query for best match
            query = Beneficiary.query
            if len(name_parts) == 1:
                query = query.filter((Beneficiary.first_name == name_parts[0]) | (Beneficiary.last_name == name_parts[0]))
            elif len(name_parts) >= 2:
                query = query.filter(Beneficiary.first_name == name_parts[0], Beneficiary.last_name == name_parts[-1])
            # Optionally match middle_initial and suffix if provided
            if len(name_parts) == 3:
                query = query.filter(Beneficiary.middle_initial == name_parts[1])
            if len(name_parts) == 4:
                query = query.filter(Beneficiary.middle_initial == name_parts[1], Beneficiary.suffix == name_parts[2])
            beneficiary_match = query.first()

        block_lot_valid = False
        if beneficiary_match and isinstance(q1, list) and len(q1) > 0:
            block = q1[0].get("block")
            lot = q1[0].get("lot")
            if block is not None and lot is not None:
                # block_id in Beneficiary is int, q1 may be str
                try:
                    block = int(block)
                    lot = int(lot)
                except Exception:
                    pass
                if beneficiary_match.block_id == block and beneficiary_match.lot_no == lot:
                    block_lot_valid = True

        if beneficiary_match and block_lot_valid:
            complaint_status = "Valid"

        # Compose complainant_name from registration
        # Clean up middle_name and suffix: treat NA/N/A/None/empty as None
        def clean_field(val):
            if not val:
                return None
            val_str = str(val).strip().lower()
            if val_str in {"na", "n/a", "none", ""}:
                return None
            return val

        middle_name = clean_field(registration.middle_name)
        suffix = clean_field(registration.suffix)
        name_parts = [registration.first_name, middle_name, registration.last_name, suffix]
        complainant_name = " ".join([part for part in name_parts if part])
        # Get area_id from Beneficiary using registration block_no and lot_no
        area_id = None
        from backend.database.models import Beneficiary
        if registration.block_no and registration.lot_no:
            beneficiary = Beneficiary.query.filter_by(block_id=registration.block_no, lot_no=registration.lot_no).first()
            if beneficiary:
                area_id = beneficiary.area_id
        address = registration.current_address

        # Create Complaint entry
        new_complaint = Complaint(
            registration_id=registration.registration_id,
            type_of_complaint="Overlapping",
            status=complaint_status,
            complainant_name=complainant_name,
            area_id=area_id,
            address=address
        )
        db.session.add(new_complaint)
        db.session.flush()

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
            "message": f"Overlap complaint submitted successfully! Status: {complaint_status}",
            "complaint_id": new_complaint.complaint_id,
            "status": complaint_status
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Server error: {e}"}), 500

# -----------------------------
# Dynamic form structure for preview
# -----------------------------
def get_form_structure(type_of_complaint):
    """
    Returns a list of field definitions for the given complaint type.
    Each field is a dict: {type, name, label, options, ...}
    Extend this for each complaint type as needed.
    """
    if type_of_complaint == "Overlapping":
        return [
            {"type": "block_lot_pairs", "name": "q1", "label": "1. What are the specific block and lot numbers involved in the overlap?"},
            {"type": "radio", "name": "q2", "label": "2. What is the current status of the lot?", "options": [
                ("residing", "I am currently residing or building on the lot"),
                ("built_by_other", "Someone else has built or is using part of the same lot"),
                ("no_one_using", "No one is using the lot, but another person also claims it"),
                ("multiple_structures", "There are multiple structures claiming the same lot area")
            ]},
            {"type": "radio", "name": "q3", "label": "3. How long have you been assigned to or occupying this lot?", "options": [
                ("<1_year", "Less than 1 year"),
                ("1-3_years", "1–3 years"),
                ("3-5_years", "3–5 years"),
                (">5_years", "More than 5 years")
            ]},
            {"type": "checkbox", "name": "q4", "label": "4. What shows that your lot is overlapping with another claim?", "options": [
                ("survey", "Official subdivision or site survey shows overlapping lot boundaries"),
                ("lot_in_docs", "My lot number or coordinates appear in someone else’s documents"),
                ("structure_on_space", "There is another structure on my assigned space"),
                ("markers", "Markers or fences show mismatched or shared boundary lines"),
                ("advice", "HOA, NGC, or an LGU unit advised me that my lot is overlapping")
            ]},
            {"type": "checkbox", "name": "q5", "label": "5. How did you discover the overlap?", "options": [
                ("informed_by_officer", "I was informed by an NHA, NGC, or barangay officer"),
                ("saw_structure", "I saw a structure already built partially or fully on my lot"),
                ("verbal_warning", "I received a verbal warning or notice from another claimant"),
                ("compared_docs", "I compared documents and noticed the same block/lot number"),
                ("advised_survey", "I was advised during a survey, inspection, or mapping activity")
            ]},
            {"type": "radio", "name": "q6", "label": "6. When did the construction begin?", "options": [
                ("<3m", "Less than 3 months"),
                ("3-6m", "3–6 months"),
                ("6-12m", "6–12 months"),
                (">1y", "Over a year"),
                ("not_sure", "Not sure")
            ]},
            {"type": "radio", "name": "q7", "label": "7. Who else is involved in this overlap?", "options": [
                ("official_beneficiary", "An officially listed beneficiary with their own documents"),
                ("relative_of_beneficiary", "A relative of the listed beneficiary (not on paper)"),
                ("private_claimant", "A private claimant not from the community"),
                ("prev_occupant", "A structure built by a previous occupant"),
                ("unknown", "I do not know who the other claimant is")
            ]},
            {"type": "text", "name": "q8", "label": "8. What is the name of the involved person?"},
            {"type": "checkbox", "name": "q9", "label": "9. What do you know about the other party’s claim?", "options": [
                ("different_doc", "They showed a different assignment document"),
                ("refused_to_vacate", "They refused to vacate or adjust"),
                ("structure_covers", "Their structure covers part of my lot"),
                ("no_docs_seen", "I have not seen any documents from their side")
            ]},
            {"type": "radio", "name": "q10", "label": "10. Have you reported this to any office or authority?", "options": [
                ("barangay", "Yes – Barangay"),
                ("hoa", "Yes – HOA"),
                ("ngc", "Yes – NGC"),
                ("no_first_time", "No – This is the first time")
            ]},
            {"type": "radio", "name": "q11", "label": "11. Was a site inspection or verification done?", "options": [
                ("barangay", "Yes – by Barangay"),
                ("hoa", "Yes – by HOA"),
                ("ngc", "Yes – by NGC"),
                ("no", "No"),
                ("not_sure", "Not sure")
            ]},
            {"type": "radio", "name": "q12", "label": "12. What was the result of the report or inspection?", "options": [
                ("other_vacate", "The other party was advised to vacate"),
                ("gather_docs", "I was advised to gather more documents"),
                ("no_action", "No action was taken"),
                ("under_investigation", "The issue is still under investigation"),
                ("overlapping_assign", "I was told the lot has overlapping assignments")
            ]},
            {"type": "radio", "name": "q13", "label": "13. What has the overlap issue caused or affected?", "options": [
                ("cannot_build", "I cannot build or renovate due to the boundary issue"),
                ("conflict_with_family", "I am in conflict with another family over the lot"),
                ("threats_or_eviction", "I received threats or was told to leave"),
                ("lost_use", "I lost use of part/all of the land I was assigned"),
                ("public_path", "A public path or neighbor's property is also affected")
            ]},
            {"type": "textarea", "name": "description", "label": "Please describe what happened briefly:"},
            {"type": "signature", "name": "signature", "label": "Signature"}
        ]
    # Add more complaint types here as needed
    return []


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

# -----------------------------
# LOT DISPUTE FORM ROUTE
# -----------------------------

@complainant_bp.route('/new_lot_dispute_form')
def new_lot_dispute_form():
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
    return send_from_directory(html_dir, 'lot_dispute.html')

# -----------------------------
# Submit lot dispute complaint
# -----------------------------

@complainant_bp.route('/submit_lot_dispute', methods=['POST'])
def submit_lot_dispute():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "message": "User not logged in"}), 401

        registration_id = request.form.get('registration_id') or session.get('registration_id')
        registration = Registration.query.get(registration_id)
        if not registration:
            return jsonify({"success": False, "message": "Parent registration not found"}), 400

        # Create a new complaint entry
        new_complaint = Complaint(
            registration_id=registration.registration_id,
            type_of_complaint="Lot Dispute",
            status="Valid"
        )
        db.session.add(new_complaint)
        db.session.flush()  # flush to get complaint_id

        # Parse form fields
        q1 = request.form.get("possession")
        q2 = request.form.get("conflict")
        q3 = request.form.get("dispute_start_date")
        q4 = request.form.get("reason")
        q5 = json.loads(request.form.get("reported_to") or "[]")  # checkboxes
        q6 = request.form.get("result")
        q7 = request.form.get("opposing_name")
        q8 = request.form.get("relationship_with_person")
        q9 = request.form.get("legal_docs")  # yes/no/not sure

        # Save lot dispute
        lot_dispute_entry = LotDispute(
            complaint_id=new_complaint.complaint_id,
            q1=q1,
            q2=q2,
            q3=q3,
            q4=q4,
            q5=json.dumps(q5),
            q6=q6,
            q7=q7,
            q8=q8,
            q9=q9
        )

        db.session.add(lot_dispute_entry)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Lot dispute submitted successfully!",
            "complaint_id": new_complaint.complaint_id
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Server error: {e}"}), 500

@complainant_bp.route('/new_boundary_dispute_form')
def new_boundary_dispute_form():
    user_id = session.get('user_id')
    if not user_id:
        return "Not logged in", 401

    registration = Registration.query.filter_by(user_id=user_id).first()
    if not registration:
        return "No registration found for user", 400

    session['complaint_id'] = f"{user_id}-{int(time.time())}"
    session['registration_id'] = registration.registration_id

    return render_template('boundary_dispute.html')  # ← uses TEMPLATE_DIR set in blueprint

@complainant_bp.route('/submit_boundary_dispute', methods=['POST'])
def submit_boundary_dispute():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "message": "User not logged in"}), 401

        registration_id = request.form.get('registration_id') or session.get('registration_id')
        registration = Registration.query.get(registration_id)
        if not registration:
            return jsonify({"success": False, "message": "Parent registration not found"}), 400

        # Create a new Complaint entry
        new_complaint = Complaint(
            registration_id=registration.registration_id,
            type_of_complaint="Boundary Dispute",
            status="Valid"
        )
        db.session.add(new_complaint)
        db.session.flush()  # to get complaint_id

        # Parse form fields
        q1 = request.form.get("possession")  # radio buttons
        q2 = request.form.get("conflict")    # radio buttons
        q3 = request.form.get("reason")      # radio buttons for construction status
        q4 = request.form.get("q4")          # Yes/No prior notice
        q5 = request.form.get("q5")          # Yes/No discussed with other party
        q6 = request.form.getlist("q6")      # checkboxes
        q7 = request.form.get("reason")      # Yes/No Q7
        q7_1 = request.form.get("reasonDateInput")  # date if Yes
        q8 = request.form.get("q8")          # Yes/No/Not Sure for ongoing development

        # Save BoundaryDispute entry
        boundary_entry = BoundaryDispute(
            complaint_id=new_complaint.complaint_id,
            q1=q1,
            q2=q2,
            q3=q3,
            q4=q4,
            q5=q5,
            q6=json.dumps(q6),
            q7=q7,
            q7_1=q7_1 if q7_1 else None,
            q8=q8
        )

        db.session.add(boundary_entry)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Boundary dispute submitted successfully!",
            "complaint_id": new_complaint.complaint_id
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Server error: {e}"}), 500
