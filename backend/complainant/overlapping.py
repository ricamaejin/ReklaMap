import os
import time
import json
from flask import Blueprint, session, send_from_directory, jsonify, request, abort
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
    
    # Base registration data
    data = {
        "complaint_id": complaint_id,
        "registration_id": reg.registration_id,
        "category": reg.category,
        "full_name": full_name,
        "date_of_birth": reg.date_of_birth.isoformat() if reg.date_of_birth else "",
        "sex": reg.sex,
        "civil_status": reg.civil_status,
        "citizenship": reg.citizenship,
        "age": reg.age,
        "cur_add": reg.current_address,
        "phone_number": reg.phone_number,
        "year_of_residence": reg.year_of_residence,
        "recipient_of_other_housing": reg.recipient_of_other_housing,
        # Expose HOA (Area) for all categories when available
        "hoa": get_area_name(reg.hoa) if reg.hoa else "",
    }
    
    # Add lot information only for HOA members and family members
    if reg.category in ["hoa_member", "family_of_member"]:
        data.update({
            "blk_num": reg.block_no,
            "lot_num": reg.lot_no,
            "lot_size": reg.lot_size,
        })
    
    # For family members, add parent info and relationship
    if reg.category == "family_of_member":
        from backend.database.models import RegistrationFamOfMember
        fam_member = RegistrationFamOfMember.query.filter_by(registration_id=reg.registration_id).first()
        if fam_member:
            data["relationship"] = fam_member.relationship
            
            # Parent info from fam_member table
            parent_name_parts = [safe(fam_member.first_name), safe(fam_member.middle_name), safe(fam_member.last_name), safe(fam_member.suffix)]
            parent_full_name = " ".join([part for part in parent_name_parts if part])
            
            data["parent_info"] = {
                "full_name": parent_full_name,
                "date_of_birth": fam_member.date_of_birth.isoformat() if fam_member.date_of_birth else "",
                "sex": fam_member.sex,
                "citizenship": fam_member.citizenship,
                "age": fam_member.age,
                "phone_number": fam_member.phone_number,
                "year_of_residence": fam_member.year_of_residence,
            }
    
    return jsonify(data)

@overlapping_bp.route("/api/complaint_form/<int:complaint_id>")
def api_complaint_form_details(complaint_id):
    """Get detailed complaint form information for admin preview"""
    try:
        # Get complaint and registration details
        complaint = Complaint.query.get(complaint_id)
        if not complaint:
            return jsonify({'error': 'Complaint not found'}), 404
            
        if complaint.type_of_complaint != "Overlapping":
            return jsonify({'error': 'This endpoint only supports Overlapping complaints'}), 400
            
        registration = Registration.query.get(complaint.registration_id)
        if not registration:
            return jsonify({'error': 'Registration not found'}), 404
        
        def safe(val):
            if not val:
                return ""
            val_str = str(val).strip()
            if val_str.lower() in {"na", "n/a", "none"}:
                return ""
            return val_str
        
        # Build complainant name
        name_parts = [safe(registration.first_name), safe(registration.middle_name), safe(registration.last_name), safe(registration.suffix)]
        full_name = " ".join([part for part in name_parts if part])
        
        # Base registration data
        data = {
            "complaint_id": complaint.complaint_id,
            "type_of_complaint": complaint.type_of_complaint,
            "status": complaint.status,
            "complaint_stage": complaint.complaint_stage,
            "date_received": complaint.date_received.strftime('%Y-%m-%d %H:%M:%S') if complaint.date_received else '',
            "registration_id": registration.registration_id,
            "category": registration.category,
            "full_name": full_name,
            "date_of_birth": registration.date_of_birth.isoformat() if registration.date_of_birth else "",
            "sex": registration.sex,
            "civil_status": registration.civil_status,
            "citizenship": registration.citizenship,
            "age": registration.age,
            "cur_add": registration.current_address,
            "phone_number": registration.phone_number,
            "year_of_residence": registration.year_of_residence,
            "recipient_of_other_housing": registration.recipient_of_other_housing,
        }
        
        # Add lot information only for HOA members and family members
        if registration.category in ["hoa_member", "family_of_member"]:
            data.update({
                "hoa": get_area_name(registration.hoa) if registration.hoa else "",
                "blk_num": registration.block_no,
                "lot_num": registration.lot_no,
                "lot_size": registration.lot_size,
            })
        
        # For family members, add parent info and relationship
        if registration.category == "family_of_member":
            from backend.database.models import RegistrationFamOfMember
            fam_member = RegistrationFamOfMember.query.filter_by(registration_id=registration.registration_id).first()
            if fam_member:
                data["relationship"] = fam_member.relationship
                
                # Parent info from fam_member table
                parent_name_parts = [safe(fam_member.first_name), safe(fam_member.middle_name), safe(fam_member.last_name), safe(fam_member.suffix)]
                parent_full_name = " ".join([part for part in parent_name_parts if part])
                
                data["parent_info"] = {
                    "full_name": parent_full_name,
                    "date_of_birth": fam_member.date_of_birth.isoformat() if fam_member.date_of_birth else "",
                    "sex": fam_member.sex,
                    "citizenship": fam_member.citizenship,
                    "age": fam_member.age,
                    "phone_number": fam_member.phone_number,
                    "year_of_residence": fam_member.year_of_residence,
                }
        
        # Get specific complaint form data
        overlap_data = Overlapping.query.filter_by(complaint_id=complaint_id).first()
        if overlap_data:
            # q1 stored as CSV -> list, q2 stored as JSON string -> list of pairs
            q1_list = []
            if overlap_data.q1:
                q1_list = [s.strip() for s in str(overlap_data.q1).split(',') if s.strip()]
            try:
                q2_pairs = json.loads(overlap_data.q2 or "[]")
            except Exception:
                q2_pairs = []
            data["form_data"] = {
                "q1": q1_list,
                "q2": q2_pairs,
                "q3": overlap_data.q3,
                "q4": json.loads(overlap_data.q4 or "[]"),
                "q5": json.loads(overlap_data.q5 or "[]"),
                "q6": overlap_data.q6,
                "q7": overlap_data.q7,
                "q8": overlap_data.q8,
                "q9": json.loads(overlap_data.q9 or "[]"),
                "q10": overlap_data.q10,
                "q11": overlap_data.q11,
                "q12": overlap_data.q12,
                "q13": overlap_data.q13,
                "description": overlap_data.description,
                "signature": overlap_data.signature
            }
        
        return jsonify(data)
        
    except Exception as e:
        print(f"Error getting complaint form details: {e}")
        return jsonify({'error': 'Internal server error'}), 500

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

        # Accept new form input but store to legacy schema
        # New inputs: current_status CSV, q2 block/lot pairs JSON
        current_status_csv = request.form.get("current_status") or ""
        # Pairs can come under 'q2' (preferred) or 'q1' (fallback from older/newer clients)
        try:
            q2_pairs = json.loads(request.form.get("q2") or request.form.get("q1") or "[]")
        except Exception:
            q2_pairs = []
        q4 = json.loads(request.form.get("evidence") or "[]")
        q5 = json.loads(request.form.get("discover") or "[]")
        q9 = json.loads(request.form.get("other_claim") or "[]")
        # Keep variable names used in validation logic
        q2 = current_status_csv
        q3 = request.form.get("occupancy_duration")
        q6 = request.form.get("construction_timeframe")
        q7 = request.form.get("who_else")
        q8 = request.form.get("involved_person_name")
        # Also capture the Q9 Yes/No radio for robustness in previews
        approach = request.form.get("approach")
        # New: involved persons array for validation
        involved_persons_raw = request.form.get("involved_persons")
        try:
            involved_persons = json.loads(involved_persons_raw) if involved_persons_raw else []
            if not isinstance(involved_persons, list):
                involved_persons = []
        except Exception:
            involved_persons = []
        q10 = request.form.get("reported_to")
        q11 = request.form.get("inspection")
        q12 = request.form.get("report_result")
        q13 = request.form.get("impact")
        description = request.form.get("description")
        from backend.database.models import Beneficiary
        complaint_status = "Invalid"
        mismatches = []

        # Helper to find first beneficiary by a rough full name match
        def find_beneficiary_by_name(name: str):
            parts = name.strip().split()
            q = Beneficiary.query
            if len(parts) == 1:
                q = q.filter((Beneficiary.first_name == parts[0]) | (Beneficiary.last_name == parts[0]))
            elif len(parts) >= 2:
                q = q.filter(Beneficiary.first_name == parts[0], Beneficiary.last_name == parts[-1])
                if len(parts) >= 3:
                    q = q.filter(Beneficiary.middle_initial == parts[1])
            return q.first()

        # Normalize pairs and persons
        pairs = q2_pairs if isinstance(q2_pairs, list) else []
        persons = involved_persons
        if not persons and q8:
            # fallback to single field split by comma
            persons = [p.strip() for p in q8.split(',') if p.strip()]

        # If user selected 'Yes' for approach but didn't tick any details, add a sentinel
        try:
            if (approach or "").lower() == "yes" and isinstance(q9, list) and len(q9) == 0:
                q9 = ["__yes_no_details__"]
        except Exception:
            pass

        # Matching logic:
        # - If there are N pairs and N persons, enforce 1-to-1 positional matching
        # - If there is 1 pair and multiple persons, at least one person must match that pair
        # - If multiple pairs and fewer persons, require that each pair has some matching person (best-effort across people)
        def bl_equal(b1, l1, b2, l2):
            try:
                return int(b1) == int(b2) and int(l1) == int(l2)
            except Exception:
                return str(b1) == str(b2) and str(l1) == str(l2)

        if pairs:
            # Build beneficiary info for persons once
            person_bens = []
            for pname in persons:
                ben = find_beneficiary_by_name(pname)
                if ben:
                    person_bens.append({
                        'name': pname,
                        # Use block_no from related Block, not block_id
                        'block_no': (ben.block.block_no if hasattr(ben, 'block') and ben.block else None),
                        'lot_no': ben.lot_no
                    })

            if len(pairs) == len(persons) and persons:
                # positional match
                for idx, pair in enumerate(pairs):
                    b = pair.get('block')
                    l = pair.get('lot')
                    if idx >= len(person_bens) or not bl_equal(b, l, person_bens[idx]['block_no'], person_bens[idx]['lot_no']):
                        mismatches.append(f"Pair {idx+1}: Block/Lot does not match person '{persons[idx]}'")
            elif len(pairs) == 1 and persons:
                # at least one person matches
                p = pairs[0]
                b, l = p.get('block'), p.get('lot')
                any_match = any(bl_equal(b, l, pb['block_no'], pb['lot_no']) for pb in person_bens)
                if not any_match:
                    mismatches.append("At least one involved person must match the provided block/lot")
            else:
                # multiple pairs, fewer or more persons -> each pair must have some matching person
                for idx, pair in enumerate(pairs):
                    b, l = pair.get('block'), pair.get('lot')
                    has_match = any(bl_equal(b, l, pb['block_no'], pb['lot_no']) for pb in person_bens)
                    if not has_match:
                        mismatches.append(f"Pair {idx+1}: No involved person matches block/lot")
        else:
            mismatches.append("Block Assignment or Lot Assignment")

        # Also require at least one recognizable person if any persons are provided
        if involved_persons_raw and not persons:
            mismatches.append("Involved person(s) format invalid")
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
        # Prefer explicit registration.hoa (Area) when available; it's stored as Area.area_id in Registration
        try:
            if registration.hoa is not None and str(registration.hoa).strip() != "":
                area_id = int(str(registration.hoa))
        except Exception:
            area_id = None
        if registration.block_no:
            # Fallback: resolve via Blocks by block_no
            if area_id is None:
                try:
                    from backend.database.models import Block
                    blk_no = int(registration.block_no) if registration.block_no is not None else None
                    if blk_no is not None:
                        # If registration.hoa is present, narrow by area; else take the first match
                        q = Block.query.filter_by(block_no=blk_no)
                        if registration.hoa:
                            try:
                                q = q.filter_by(area_id=int(str(registration.hoa)))
                            except Exception:
                                pass
                        block_row = q.first()
                        if block_row:
                            area_id = block_row.area_id
                except Exception:
                    area_id = None

        # Block complaint if area_id is missing
        if area_id is None:
            return jsonify({
                "success": False,
                "message": "Cannot submit complaint: Area assignment not found for your block and lot. Please contact admin.",
                "mismatches": ["Area Assignment"]
            }), 400
        # Decide validity based on mismatches regardless of category
        if mismatches:
            return jsonify({
                "success": False,
                "message": "Mismatch found in the following field(s): " + ", ".join(mismatches) + ". Please correct them before submitting again.",
                "mismatches": mismatches
            }), 400
        else:
            complaint_status = "Valid"
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
            # New schema: q1 CSV current_status, q2 JSON pairs, q6 string
            q1=current_status_csv,
            q2=q2_pairs,
            q3=q3,
            q4=q4,
            q5=q5,
            q6=q6,
            q7=q7,
            q8=q8,
            q9=q9,
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
            {"type": "checkbox", "name": "q1", "label": "1. What is the current status of your assigned lot?", "options": [
                ("survey_overlap", "Official subdivision or site survey shows overlapping boundaries"),
                ("coords_in_docs", "My assigned lot number/coordinates also appear in someone else’s documents"),
                ("residing", "I am currently residing or building on the lot"),
                ("vacant_overlap_records", "The lot is vacant, but subdivision/records show overlapping assignments"),
                ("built_by_other", "Someone else has built or is using part of the same lot"),
                ("other_has_docs", "Another person has documents showing the same lot as mine"),
                ("unsure_told_overlap", "I am unsure of the current usage, but I was told there is an overlap")
            ]},
            {"type": "block_lot_pairs", "name": "q2", "label": "2. What are the specific block and lot numbers involved in the overlap? (Excluding yours)"},
            {"type": "radio", "name": "q3", "label": "3. How long have you been assigned to or occupying this lot?", "options": [
                ("<6m", "Less than 6 months"),
                ("6m-1y", "6 months-1 year"),
                ("1-3y", "1–3 years"),
                ("3-5y", "3–5 years"),
                (">5y", "More than 5 years")
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
            {"type": "radio", "name": "q6", "label": "6. When did the overlapping begin?", "options": [
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
            {"type": "radio", "name": "q9_approach", "label": "9. Is there someone who claims that your lot is overlapping with theirs?", "options": [
                ("yes", "Yes"),
                ("no", "No")
            ]},
            {"type": "checkbox", "name": "q9", "label": "What information or evidence do they have about the overlapping?", "options": [
                ("same_lot_number", "Their documents show the same lot number as mine"),
                ("different_doc", "I saw documents but they did not match mine"),
                ("no_docs_seen", "I have not seen any documents from their side"),
                ("structure_covers", "Their structure covers part of my lot"),
                ("not_sure", "I am not sure / No information")
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
                ("overlapping_assign", "I was told the lot has overlapping assignments"),
                ("not_applicable", "Not applicable / No report filed")
            ]},
            {"type": "radio", "name": "q13", "label": "13. What has the overlap issue caused or affected?", "options": [
                ("cannot_build", "I cannot build or renovate due to the boundary issue"),
                ("conflict_with_family", "I am in conflict with another family over the lot"),
                ("threats_or_eviction", "I received threats or was told to leave"),
                ("lost_use", "I lost use of part/all of the land I was assigned"),
                ("public_path", "A public path or neighbor's property is also affected"),
                ("none", "None of the above")
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
