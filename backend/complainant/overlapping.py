import os
import time
import json
from flask import Blueprint, session, send_from_directory, jsonify, request
from werkzeug.utils import secure_filename
from backend.database.models import Registration, Complaint, Overlapping
from backend.database.db import db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "..", "frontend", "complainant", "complaints"))
UPLOAD_DIR = os.path.normpath(os.path.join(BASE_DIR, "uploads", "signatures"))
os.makedirs(UPLOAD_DIR, exist_ok=True)

overlapping_bp = Blueprint(
    "overlapping",
    __name__,
    url_prefix="/complainant/overlapping"
)

@overlapping_bp.route('/new_overlap_form')
def new_overlap_form():
    user_id = session.get('user_id')
    print(f"[DEBUG] new_overlap_form: session user_id={user_id}")
    if not user_id:
        print("[DEBUG] Not logged in")
        return jsonify({"error": "Not logged in"}), 401
    registration = Registration.query.filter_by(user_id=user_id).first()
    print(f"[DEBUG] Registration found: {registration}")
    if not registration:
        print("[DEBUG] No registration found for user")
        return jsonify({"error": "No registration found for user"}), 400
    complaint_id = f"{user_id}-{int(time.time())}"
    session['complaint_id'] = complaint_id
    session['registration_id'] = registration.registration_id
    print(f"[DEBUG] Set session complaint_id={complaint_id}, registration_id={registration.registration_id}")
    html_dir = TEMPLATE_DIR
    return send_from_directory(html_dir, 'overlapping.html')

@overlapping_bp.route('/get_overlap_session_data')
def get_overlap_session_data():
    registration_id = session.get("registration_id")
    complaint_id = session.get("complaint_id")
    print(f"[DEBUG] get_overlap_session_data: session registration_id={registration_id}, complaint_id={complaint_id}")
    if not registration_id:
        print("[DEBUG] No registration_id in session")
        return jsonify({"error": "No registration found in session"}), 400
    reg = Registration.query.get(registration_id)
    print(f"[DEBUG] Registration query result: {reg}")
    if not reg:
        print("[DEBUG] Registration not found for id")
        return jsonify({"error": "Registration not found"}), 404
    def safe(val):
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
        "hoa": reg.hoa,
        "blk_num": reg.block_no,
        "lot_num": reg.lot_no,
        "lot_size": reg.lot_size,
        "phone_number": reg.phone_number,
    })

@overlapping_bp.route("/submit_overlap", methods=["POST"])
def submit_overlap():
    try:
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"success": False, "message": "User not logged in"}), 401
        registration_id = request.form.get("registration_id")
        registration = Registration.query.get(registration_id)
        if not registration:
            return jsonify({"success": False, "message": "Parent registration does not exist"}), 400
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
        from backend.database.models import Beneficiary
        complaint_status = "Invalid"
        beneficiary_match = None
        mismatches = []
        if q8:
            name_parts = q8.strip().split()
            query = Beneficiary.query
            if len(name_parts) == 1:
                query = query.filter((Beneficiary.first_name == name_parts[0]) | (Beneficiary.last_name == name_parts[0]))
            elif len(name_parts) >= 2:
                query = query.filter(Beneficiary.first_name == name_parts[0], Beneficiary.last_name == name_parts[-1])
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
                try:
                    block = int(block)
                    lot = int(lot)
                except Exception:
                    pass
                if beneficiary_match.block_id == block and beneficiary_match.lot_no == lot:
                    block_lot_valid = True
                else:
                    mismatches.append("Block Assignment or Lot Assignment")
            else:
                mismatches.append("Block Assignment or Lot Assignment")
        else:
            mismatches.append("Beneficiary Name")
        if beneficiary_match and block_lot_valid:
            complaint_status = "Valid"
            mismatches = []
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
        area_id = None
        address = registration.current_address
        if registration.block_no and registration.lot_no:
            beneficiary = Beneficiary.query.filter_by(block_id=registration.block_no, lot_no=registration.lot_no).first()
            if beneficiary:
                area_id = beneficiary.area_id
            if beneficiary_match and block_lot_valid:
                complaint_status = "Valid"
                mismatches = []

            # If there are mismatches, do not save complaint, return error
            if complaint_status == "Invalid" and mismatches:
                return jsonify({
                    "success": False,
                    "message": "Mismatch found in the following field(s): " + ", ".join(mismatches) + ". Please correct them before submitting again.",
                    "mismatches": mismatches
                }), 400

        # Block complaint if area_id is missing
        if area_id is None:
            return jsonify({
                "success": False,
                "message": "Cannot submit complaint: Area assignment not found for your block and lot. Please contact admin.",
                "mismatches": ["Area Assignment"]
            }), 400
        # Prevent duplicate complaints for the same registration unless previous complaint is invalid or resolved
        existing_complaint = Complaint.query.filter_by(
            registration_id=registration.registration_id,
            type_of_complaint="Overlapping"
        ).order_by(Complaint.complaint_id.desc()).first()
        if existing_complaint and existing_complaint.status not in ["Invalid", "Resolved"]:
            return jsonify({
                "success": False,
                "message": "A complaint for this registration already exists.",
                "status": existing_complaint.status,
                "complaint_id": existing_complaint.complaint_id
            }), 400

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
        signature_file = request.files.get("signature")
        signature_filename = None
        if signature_file:
            signature_filename = secure_filename(signature_file.filename)
            save_path = os.path.join(UPLOAD_DIR, signature_filename)
            signature_file.save(save_path)
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
            "status": complaint_status,
            "mismatches": mismatches
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Server error: {e}"}), 500

def get_form_structure(type_of_complaint):
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
    return []

# -----------------------------
# Serve uploaded signatures
# -----------------------------
@overlapping_bp.route("/uploads/signatures/<filename>")
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
