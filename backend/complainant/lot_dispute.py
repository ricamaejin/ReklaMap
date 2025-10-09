import os, json, time
from datetime import datetime
from flask import Blueprint, session, send_from_directory, jsonify, request
from werkzeug.utils import secure_filename
from backend.database.models import Registration, Complaint, LotDispute, Beneficiary, Block, Area, RegistrationFamOfMember, GeneratedLots
from backend.database.db import db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "..", "frontend", "complainant", "complaints"))
UPLOAD_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "uploads", "signatures"))
os.makedirs(UPLOAD_DIR, exist_ok=True)

lot_dispute_bp = Blueprint(
    "lot_dispute",
    __name__,
    url_prefix="/complainant/lot_dispute"
)

def get_area_name(area_id):
    """Get area name from area_id"""
    if not area_id:
        return ""
    try:
        area = Area.query.get(int(area_id))
        return area.area_name if area else str(area_id)
    except (ValueError, TypeError):
        return str(area_id)

@lot_dispute_bp.route('/new_lot_dispute_form')
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

@lot_dispute_bp.route('/get_lot_session_data')
def get_lot_session_data():
    """Provide registration and derived details for rendering category-specific header."""
    registration_id = session.get('registration_id')
    complaint_id = session.get('complaint_id')
    if not registration_id:
        return jsonify({"error": "No registration found in session"}), 400
    reg = Registration.query.get(registration_id)
    if not reg:
        return jsonify({"error": "Registration not found"}), 404

    def safe(val):
        if not val:
            return ""
        val_str = str(val).strip()
        if val_str.lower() in {"na", "n/a", "none"}:
            return ""
        return val_str

    name_parts = [safe(reg.first_name), safe(reg.middle_name), safe(reg.last_name), safe(reg.suffix)]
    full_name = " ".join([p for p in name_parts if p])

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
        # Always include resolved HOA name if available
        "hoa": get_area_name(reg.hoa) if reg.hoa else "",
    }

    if reg.category in ["hoa_member", "family_of_member"]:
        data.update({
            "blk_num": reg.block_no,
            "lot_num": reg.lot_no,
            "lot_size": reg.lot_size,
        })

    if reg.category == "family_of_member":
        fam = RegistrationFamOfMember.query.filter_by(registration_id=reg.registration_id).first()
        if fam:
            parent_name_parts = [safe(fam.first_name), safe(fam.middle_name), safe(fam.last_name), safe(fam.suffix)]
            parent_full_name = " ".join([p for p in parent_name_parts if p])
            data["relationship"] = fam.relationship
            data["parent_info"] = {
                "full_name": parent_full_name,
                "date_of_birth": fam.date_of_birth.isoformat() if fam.date_of_birth else "",
                "sex": fam.sex,
                "citizenship": fam.citizenship,
                "age": fam.age,
                "phone_number": fam.phone_number,
                "year_of_residence": fam.year_of_residence,
            }

    return jsonify(data)

@lot_dispute_bp.route('/validate_pairs', methods=['POST'])
def validate_pairs():
    """Validate provided Block/Lot pairs against the user's HOA area.
    Expects JSON body: { "pairs": [{"block": "..", "lot": ".."}, ...] }
    """
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "message": "User not logged in"}), 401
        registration_id = session.get('registration_id')
        reg = Registration.query.get(registration_id) if registration_id else None
        if not reg:
            return jsonify({"success": False, "message": "Registration not found"}), 400

        # Resolve area_id as in submit
        area_id = None
        if getattr(reg, 'hoa', None):
            try:
                area_id_candidate = int(reg.hoa)
                if Area.query.get(area_id_candidate):
                    area_id = area_id_candidate
            except Exception:
                area_id = None
        if area_id is None and reg.block_no and reg.lot_no:
            try:
                bn = int(reg.block_no)
            except Exception:
                bn = reg.block_no
            try:
                ln = int(reg.lot_no)
            except Exception:
                ln = reg.lot_no
            beneficiary = Beneficiary.query.filter_by(block_id=bn, lot_no=ln).first()
            if not beneficiary:
                blk = Block.query.filter_by(block_no=bn).first()
                if blk:
                    beneficiary = Beneficiary.query.filter_by(block_id=blk.block_id, lot_no=ln).first()
            if beneficiary:
                area_id = beneficiary.area_id

        if area_id is None:
            return jsonify({"success": False, "message": "Area assignment not found from your registration."}), 400

        payload = request.get_json(silent=True) or {}
        pairs = payload.get('pairs')
        if not isinstance(pairs, list):
            return jsonify({"success": False, "message": "Invalid payload."}), 400

        found_invalid = False
        for idx, item in enumerate(pairs, start=1):
            b_str = str(item.get("block", "")).strip()
            l_str = str(item.get("lot", "")).strip()
            if not b_str or not l_str:
                found_invalid = True
                break
            try:
                b_no = int(b_str)
            except Exception:
                found_invalid = True
                break
            try:
                l_no = int(l_str)
            except Exception:
                found_invalid = True
                break
            blk = Block.query.filter_by(area_id=area_id, block_no=b_no).first()
            if not blk:
                found_invalid = True
                break
            ben = Beneficiary.query.filter_by(block_id=blk.block_id, lot_no=l_no).first()
            if not ben:
                gen = GeneratedLots.query.filter_by(block_id=blk.block_id, lot_no=l_no).first()
                if not gen:
                    found_invalid = True
                    break
        if found_invalid:
            return jsonify({"success": False, "message": "Block or lot could not be found for your HOA.", "mismatches": ["Block or lot could not be found for your HOA."]}), 400
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": f"Server error: {e}"}), 500

@lot_dispute_bp.route('/submit_lot_dispute', methods=['POST'])
def submit_lot_dispute():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "message": "User not logged in"}), 401
        registration_id = request.form.get('registration_id') or session.get('registration_id')
        registration = Registration.query.get(registration_id)
        if not registration:
            return jsonify({"success": False, "message": "Parent registration not found"}), 400
        # Build required Complaint fields
        def clean_field(val):
            if not val:
                return None
            val_str = str(val).strip()
            if val_str.lower() in {"na", "n/a", "none", ""}:
                return None
            return val_str

        middle_name = clean_field(registration.middle_name)
        suffix = clean_field(registration.suffix)
        name_parts = [registration.first_name, middle_name, registration.last_name, suffix]
        complainant_name = " ".join([p for p in name_parts if p])
        address = registration.current_address or ""

        # Determine area via registration.hoa (preferred) or beneficiary using stored block/lot
        area_id = None
        # Prefer area from registration.hoa if present (stored as area_id)
        if getattr(registration, 'hoa', None):
            try:
                area_id_candidate = int(registration.hoa)
                if Area.query.get(area_id_candidate):
                    area_id = area_id_candidate
            except Exception:
                area_id = None
        try:
            if area_id is None and registration.block_no and registration.lot_no:
                bn = registration.block_no
                ln = registration.lot_no
                try:
                    bn = int(bn)
                except Exception:
                    pass
                try:
                    ln = int(ln)
                except Exception:
                    pass
                beneficiary = Beneficiary.query.filter_by(block_id=bn, lot_no=ln).first()
                if not beneficiary:
                    # Fallback: registration may store block_no instead of block_id
                    blk = Block.query.filter_by(block_no=bn).first()
                    if blk:
                        beneficiary = Beneficiary.query.filter_by(block_id=blk.block_id, lot_no=ln).first()
                if beneficiary:
                    area_id = beneficiary.area_id
        except Exception:
            area_id = None

        if area_id is None:
            # No area found; cannot proceed
            return jsonify({
                "success": False,
                "message": "Cannot submit complaint: Area assignment not found from your registration.",
                "mismatches": ["Area Assignment"]
            }), 400

        # Capture free-text description from form
        description = request.form.get("description")

        new_complaint = Complaint(
            registration_id=registration.registration_id,
            type_of_complaint="Lot Dispute",
            status="Valid",
            complainant_name=complainant_name,
            area_id=area_id,
            address=address,
            description=description
        )
        db.session.add(new_complaint)
        db.session.flush()
        q1 = request.form.get("possession")
        # Optional block/lot pairs (non-members). Expect JSON string from frontend.
        block_lot_raw = request.form.get("block_lot")
        block_lot = None
        if block_lot_raw:
            try:
                parsed = json.loads(block_lot_raw)
                # Basic shape validation: list of {block, lot}
                if isinstance(parsed, list):
                    block_lot = [
                        {
                            "block": str(item.get("block", "")).strip(),
                            "lot": str(item.get("lot", "")).strip(),
                        }
                        for item in parsed if isinstance(item, dict)
                    ]
                else:
                    block_lot = None
            except Exception:
                block_lot = None

        # Server-side cross-check: ensure each provided Block/Lot exists within this HOA area
        # Applies primarily to non-members, but safe to run for any provided pairs.
        if block_lot:
            found_invalid = False
            for idx, item in enumerate(block_lot, start=1):
                b_str = (item.get("block") or "").strip()
                l_str = (item.get("lot") or "").strip()
                if not b_str or not l_str:
                    found_invalid = True
                    break
                try:
                    b_no = int(b_str)
                except Exception:
                    found_invalid = True
                    break
                try:
                    l_no = int(l_str)
                except Exception:
                    found_invalid = True
                    break
                blk = Block.query.filter_by(area_id=area_id, block_no=b_no).first()
                if not blk:
                    found_invalid = True
                    break
                ben = Beneficiary.query.filter_by(block_id=blk.block_id, lot_no=l_no).first()
                if not ben:
                    gen = GeneratedLots.query.filter_by(block_id=blk.block_id, lot_no=l_no).first()
                    if not gen:
                        found_invalid = True
                        break
            if found_invalid:
                db.session.rollback()
                return jsonify({
                    "success": False,
                    "message": "Block or lot could not be found for your HOA.",
                    "mismatches": ["Block or lot could not be found for your HOA."]
                }), 400
        q2 = request.form.get("conflict")
        # Parse date to Python date if provided
        q3_raw = request.form.get("dispute_start_date")
        q3 = None
        if q3_raw:
            try:
                q3 = datetime.strptime(q3_raw, "%Y-%m-%d").date()
            except Exception:
                q3 = None
        q4 = request.form.get("reason")
        q5 = json.loads(request.form.get("reported_to") or "[]")
        q6 = request.form.get("result")
        
        # Handle multiple opposing names
        opposing_names = []
        for key in request.form:
            if key == 'opposing_name[]':
                opposing_names.extend(request.form.getlist(key))
        q7 = json.dumps([name.strip() for name in opposing_names if name.strip()])
        
        # Handle multiple relationships
        relationships = []
        for key in request.form:
            if key == 'relationship_with_person[]':
                relationships.extend(request.form.getlist(key))
        q8 = json.dumps([rel.strip() for rel in relationships if rel.strip()])
        
        # Handle q9 - Legal documents claim with conditional document types
        legal_docs_claim = request.form.get("claimDocs")
        q9_data = {"claim": legal_docs_claim}
        
        # If they claim to have documents, collect the document types
        if legal_docs_claim == "Yes":
            docs_checked = []
            for key in request.form:
                if key == "docs":  # Handle multiple values for checkboxes
                    docs_checked.extend(request.form.getlist(key))
            if docs_checked:
                q9_data["documents"] = docs_checked
        
        q9 = json.dumps(q9_data)
        
        # Handle q10 - "Do they reside on the disputed lot?"
        reside_answer = request.form.get("reside")
        q10 = json.dumps({"reside": reside_answer}) if reside_answer else None
        lot_dispute_entry = LotDispute(
            complaint_id=new_complaint.complaint_id,
            q1=q1,
            block_lot=block_lot,
            q2=q2,
            q3=q3,
            q4=q4,
            q5=json.dumps(q5),
            q6=q6,
            q7=q7,
            q8=q8,
            q9=q9,
            q10=q10,
            description=description
        )
        db.session.add(lot_dispute_entry)
        
        # Optional signature upload: save to shared signatures folder and attach to registration
        try:
            file = request.files.get('signature')
            if file and getattr(file, 'filename', ''):
                fname = secure_filename(file.filename)
                # prefix to reduce collision risk
                safe_name = f"{int(time.time())}_{fname}"
                dest = os.path.join(UPLOAD_DIR, safe_name)
                file.save(dest)
                # store only the filename; previews use a route that resolves the path
                registration.signature_path = safe_name
                # also keep a copy reference on lot_dispute
                lot_dispute_entry.signature = safe_name
        except Exception:
            # Do not fail submission if signature save fails
            pass

        db.session.commit()
        return jsonify({
            "success": True,
            "message": "Lot dispute submitted successfully!",
            "complaint_id": new_complaint.complaint_id
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Server error: {e}"}), 500

@lot_dispute_bp.route('/areas')
def list_areas():
    try:
        areas = Area.query.order_by(Area.area_name.asc()).all()
        return jsonify({
            "success": True,
            "areas": [{"area_id": a.area_id, "area_name": a.area_name} for a in areas]
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"Server error: {e}"}), 500

def get_form_structure(type_of_complaint: str):
    """Form structure used by previews (valid/invalid) for Lot Dispute.
    Mirrors the complainant form so answers can be displayed like Overlapping.
    """
    if type_of_complaint != "Lot Dispute":
        return []
    return [
        {
            "type": "radio",
            "name": "q1",
            "label": "1. How did you come into possession of the lot?",
            "options": [
                ("Official assignment by NGCHDP/NHA", "I was officially assigned the lot by NGCHDP/NHA"),
                ("Passed on by a family member", "The lot was passed on to me by a family member"),
                ("Purchased from another occupant", "I purchased the lot from another occupant"),
                ("Living since project started", "I have been living here since the NCC project started"),
                ("Relocated after demolition/displacement", "I relocated here after demolition/displacement elsewhere"),
                ("Verbal promise by former officer/neighbor", "I was verbally promised the lot by a former officer or neighbor"),
                ("Other", "Other"),
            ],
        },
        {
            "type": "radio",
            "name": "q2",
            "label": "2. What is the nature of the ownership conflict?",
            "options": [
                ("Contract duplication for same lot", "Someone else has a contract for the same lot"),
                ("Another is claiming my assigned lot", "Someone else is claiming my assigned lot"),
                ("Assigned a different lot than told", "I was assigned a different lot than what I was told"),
                ("Lot not reflected in masterlist", "My lot is not reflected in the masterlist"),
                ("Name removed or replaced in beneficiary list", "My name was removed or replaced in the beneficiary list"),
                ("Lot illegally sold or reassigned", "Lot was illegally sold or reassigned to someone else"),
                ("Family member/relative claiming the lot I occupy", "A family member/relative is claiming the lot I currently occupy"),
                ("Assigned lot details incorrect in records", "My assigned lot details (e.g., lot no., area) are incorrect in the records"),
            ],
        },
        {
            "type": "date",
            "name": "q3",
            "label": "3. When did the dispute start?",
        },
        {
            "type": "radio",
            "name": "q4",
            "label": "4. What led you to raise this complaint?",
            "options": [
                ("Asked to vacate the lot I occupy", "I was asked to vacate the lot I’ve been occupying"),
                ("Denied access to lot I believe was assigned", "I was denied access to a lot I believe was assigned to me"),
                ("Notice received that someone else is rightful owner", "I received notice that someone else is the rightful owner"),
                ("Attempted to build and was stopped", "I attempted to build on the lot and was stopped"),
                ("Another person listed in official records for my lot", "I discovered another person listed in official records for my lot"),
                ("Other", "Other"),
            ],
        },
        {
            "type": "checkbox",
            "name": "q5",
            "label": "5. Have you reported this to any authority?",
            "options": [
                ("Barangay", "Barangay"),
                ("HOA", "HOA"),
                ("NGC", "NGC"),
                ("None", "None"),
            ],
        },
        {
            "type": "radio",
            "name": "q6",
            "label": "6. What was the result of that report?",
            "options": [
                ("Other party asked to vacate", "The other party was asked to vacate"),
                ("Agency asked for more documentation", "The agency asked for more documentation"),
                ("No action taken", "No action was taken"),
                ("Still under investigation", "Still under investigation"),
                ("Told I have no valid claim", "I was told I have no valid claim"),
                ("Other", "Other"),
            ],
        },
        {
            "type": "multiple_text",
            "name": "q7",
            "label": "7. Name of opposing claimant?",
            "description": "Multiple names can be added for each person involved"
        },
        {
            "type": "multiple_text", 
            "name": "q8",
            "label": "8. Relationship with person involved?",
            "description": "Multiple relationships can be added corresponding to each person"
        },
        {
            "type": "radio",
            "name": "q9",
            "label": "9. Do they claim to have legal documents?",
            "options": [
                ("Yes", "Yes"),
                ("No", "No"),
                ("Not Sure", "Not sure"),
            ],
            "conditional": {
                "show_when": "Yes",
                "additional_fields": [
                    {
                        "type": "checkbox",
                        "name": "docs",
                        "label": "What documents do they have?",
                        "options": [
                            ("Certificate of Lot Award (CLA)", "Certificate of Lot Award (CLA)"),
                            ("Notice of Award", "Notice of Award"),
                            ("Deed of Assignment / Transfer", "Deed of Assignment / Transfer"),
                            ("Certification from NGC/NHA/Barangay", "Certification from NGC/NHA/Barangay"),
                            ("Other supporting paper", "Other supporting paper (e.g., tax receipt, ID copy, etc.)"),
                        ]
                    }
                ]
            }
        },
        {
            "type": "radio",
            "name": "q10",
            "label": "10. Do they reside on the disputed lot?",
            "options": [
                ("Yes", "Yes"),
                ("No", "No"),
                ("Not Sure", "Not sure"),
            ],
        },
        {
            "type": "textarea",
            "name": "description",
            "label": "Please describe what happened briefly, including how you found out about the issue.",
        },
        {
            "type": "signature",
            "name": "signature",
            "label": "Signature",
        },
    ]
