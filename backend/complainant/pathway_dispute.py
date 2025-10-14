import os
import time
import json
from flask import Blueprint, session, render_template, jsonify, request
from werkzeug.utils import secure_filename
from backend.database.models import Registration, Complaint, PathwayDispute
from backend.database.db import db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "..", "frontend", "complainant", "complaints"))
UPLOAD_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "uploads", "signatures"))
os.makedirs(UPLOAD_DIR, exist_ok=True)

pathway_dispute_bp = Blueprint(
	"pathway_dispute",
	__name__,
	url_prefix="/complainant/pathway_dispute"
)


# --- New form route ---
@pathway_dispute_bp.route('/new_pathway_dispute_form')
def new_pathway_dispute_form():
	user_id = session.get('user_id')
	if not user_id:
		return "Not logged in", 401
	registration = Registration.query.filter_by(user_id=user_id).first()
	if not registration:
		return "No registration found for user", 400
	session['complaint_id'] = f"{user_id}-{int(time.time())}"
	session['registration_id'] = registration.registration_id
	return render_template('pathway_dispute.html')

@pathway_dispute_bp.route('/get_pathway_session_data')
def get_pathway_session_data():
    registration_id = session.get("registration_id")
    complaint_id = session.get("complaint_id")

    if not registration_id:
        return jsonify({"error": "No registration_id in session"}), 400

    reg = Registration.query.get(registration_id)
    if not reg:
        return jsonify({"error": "No registration found for registration_id"}), 404

    def safe(val):
        if not val:
            return ""
        val_str = str(val).strip()
        if val_str.lower() in {"na", "n/a", "none"}:
            return ""
        return val_str

    # Build full name
    name_parts = [safe(reg.first_name), safe(reg.middle_name), safe(reg.last_name), safe(reg.suffix)]
    full_name = " ".join([p for p in name_parts if p])

    # Resolve HOA/area name (for beneficiary or block/lot or hoa field)
    hoa_value = ""
    from backend.database.models import Area, Block, Beneficiary
    # Try by beneficiary_id
    if getattr(reg, "beneficiary_id", None):
        beneficiary = Beneficiary.query.get(reg.beneficiary_id)
        if beneficiary and getattr(beneficiary, "area_id", None):
            area = Area.query.get(beneficiary.area_id)
            if area:
                hoa_value = area.area_name
    # Try by block/lot
    if not hoa_value:
        try:
            block_no = getattr(reg, "block_no", None)
            lot_no = getattr(reg, "lot_no", None)
            if block_no and lot_no:
                bn = int(block_no)
                ln = int(lot_no)
                blk = Block.query.filter_by(block_no=bn).first()
                if blk:
                    beneficiary = Beneficiary.query.filter_by(block_id=blk.block_id, lot_no=ln).first()
                    if beneficiary:
                        area = Area.query.filter_by(area_id=beneficiary.area_id).first()
                        if area:
                            hoa_value = area.area_name
        except Exception:
            pass
    # Try by reg.hoa (if it's an area_id or area_code)
    if not hoa_value:
        hoa_field = getattr(reg, "hoa", None)
        if hoa_field:
            # Try as area_id
            area = None
            try:
                area = Area.query.get(int(hoa_field))
            except Exception:
                pass
            if not area:
                # Try as area_code
                area = Area.query.filter_by(area_code=hoa_field).first()
            if area:
                hoa_value = area.area_name

    # Supporting documents
    supporting_documents = []
    if reg.category in ("hoa_member", "family_of_member"):
        try:
            docs = getattr(reg, "supporting_documents", None)
            if docs:
                import json as _json
                if isinstance(docs, str):
                    supporting_documents = _json.loads(docs)
                elif isinstance(docs, list):
                    supporting_documents = docs
        except Exception:
            supporting_documents = []

    # Build main data dict
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
        "recipient_of_other_housing": getattr(reg, "recipient_of_other_housing", "") or "",
        "hoa": hoa_value,
        "blk_num": getattr(reg, "block_no", "") or "",
        "lot_num": getattr(reg, "lot_no", "") or "",
        "lot_size": getattr(reg, "lot_size", "") or "",
        "supporting_documents": supporting_documents if supporting_documents else [],
    }

    # For non_member, fetch connections from RegistrationNonMember
    if reg.category == "non_member":
        from backend.database.models import RegistrationNonMember
        reg_non_member = RegistrationNonMember.query.filter_by(registration_id=reg.registration_id).first()
        connections_val = ""
        if reg_non_member and reg_non_member.connections:
            # connections is JSON, but could be a string or list or dict
            conn = reg_non_member.connections
            # Checkbox label mapping (should match nonmemreg.py)
            checkbox_labels = [
                "I live on the lot but I am not the official beneficiary",
                "I live near the lot and I am affected by the issue",
                "I am claiming ownership of the lot",
                "I am related to the person currently occupying the lot",
                "I was previously assigned to this lot but was replaced or removed"
            ]
            display_labels = []
            if isinstance(conn, dict):
                for idx, label in enumerate(checkbox_labels, start=1):
                    key = f"connection_{idx}"
                    if conn.get(key):
                        display_labels.append(label)
                # Handle 'other' freeform text
                other = conn.get("connection_other")
                if other:
                    display_labels.append(other)
            elif isinstance(conn, list):
                display_labels = [str(x) for x in conn if x]
            elif isinstance(conn, str):
                display_labels = [conn]
            else:
                display_labels = [str(conn)]
            connections_val = ", ".join(display_labels)
            data["connections"] = connections_val

    # If family_of_member, add parent_info and relationship
    if reg.category == "family_of_member":
        relationship = ""
        from backend.database.models import RegistrationFamOfMember

        # fetch by registration_id (more reliable than name match)
        fam_link = RegistrationFamOfMember.query.filter_by(registration_id=reg.registration_id).first()
        if fam_link:
            relationship = fam_link.relationship or ""
        data["relationship"] = relationship

        parent_info = None
        # First try to build parent_info from the family link itself (works even if parent never registered)
        if fam_link:
            sd = getattr(fam_link, "supporting_documents", {}) or {}
            hoa_raw = sd.get("hoa") or None
            # Robust HOA resolution: try id, code, name
            parent_hoa_value = ""
            from backend.database.models import Area, Beneficiary
            if hoa_raw:
                try:
                    candidate = int(hoa_raw)
                    a = Area.query.get(candidate)
                    if a:
                        parent_hoa_value = a.area_name
                except Exception:
                    # try by area_code or exact name
                    a = Area.query.filter((Area.area_code == str(hoa_raw)) | (Area.area_name == str(hoa_raw))).first()
                    if a:
                        parent_hoa_value = a.area_name

            # If no explicit HOA in supporting_documents, try linked beneficiary
            if not parent_hoa_value and getattr(fam_link, 'beneficiary_id', None):
                try:
                    ben = Beneficiary.query.get(fam_link.beneficiary_id)
                    if ben and getattr(ben, 'area_id', None):
                        a = Area.query.get(ben.area_id)
                        if a:
                            parent_hoa_value = a.area_name
                except Exception:
                    pass

            parts = [str(getattr(fam_link, 'first_name', '') or '').strip(), str(getattr(fam_link, 'middle_name', '') or '').strip(), str(getattr(fam_link, 'last_name', '') or '').strip(), str(getattr(fam_link, 'suffix', '') or '').strip()]
            parent_full_name = " ".join([p for p in parts if p])
            parent_info = {
                "full_name": parent_full_name,
                "date_of_birth": getattr(fam_link, 'date_of_birth', None).isoformat() if getattr(fam_link, 'date_of_birth', None) else "",
                "sex": getattr(fam_link, 'sex', None),
                "citizenship": getattr(fam_link, 'citizenship', None),
                "age": getattr(fam_link, 'age', None),
                "phone_number": getattr(fam_link, 'phone_number', None),
                "year_of_residence": getattr(fam_link, 'year_of_residence', None),
                "current_address": getattr(fam_link, 'current_address', None) or sd.get('current_address') or "",
                "blk_num": sd.get('block_assignment') or getattr(fam_link, 'block_no', '') or "",
                "lot_num": sd.get('lot_assignment') or getattr(fam_link, 'lot_no', '') or "",
                "lot_size": sd.get('lot_size') or getattr(fam_link, 'lot_size', '') or "",
                "civil_status": sd.get('civil_status') or getattr(fam_link, 'civil_status', None),
                "recipient_of_other_housing": sd.get('recipient_of_other_housing') or getattr(fam_link, 'recipient_of_other_housing', None),
                "hoa": parent_hoa_value,
                "supporting_documents": sd if sd else None,
            }

        # If we didn't get useful parent_info from the fam_link, try to locate a parent Registration (hoa_member) and use that
        if not parent_info and getattr(reg, "beneficiary_id", None):
            parent = Registration.query.filter_by(beneficiary_id=reg.beneficiary_id, category="hoa_member").first()
            if parent:
                parent_name_parts = [safe(parent.first_name), safe(parent.middle_name), safe(parent.last_name), safe(parent.suffix)]
                parent_full_name = " ".join([p for p in parent_name_parts if p])
                parent_docs = []
                from backend.database.models import RegistrationHOAMember, Area, Beneficiary
                hoa_member = RegistrationHOAMember.query.filter_by(registration_id=parent.registration_id).first()
                if hoa_member and hoa_member.supporting_documents:
                    try:
                        import json as _json
                        if isinstance(hoa_member.supporting_documents, str):
                            parent_docs = _json.loads(hoa_member.supporting_documents)
                        elif isinstance(hoa_member.supporting_documents, list):
                            parent_docs = hoa_member.supporting_documents
                    except Exception:
                        parent_docs = []
                if not parent_docs and getattr(parent, "supporting_documents", None):
                    try:
                        import json as _json
                        if isinstance(parent.supporting_documents, str):
                            parent_docs = _json.loads(parent.supporting_documents)
                        elif isinstance(parent.supporting_documents, list):
                            parent_docs = parent.supporting_documents
                    except Exception:
                        parent_docs = []

                # Resolve parent's HOA area_name
                parent_hoa_value = ""
                if getattr(parent, "beneficiary_id", None):
                    beneficiary = Beneficiary.query.get(parent.beneficiary_id)
                    if beneficiary and getattr(beneficiary, "area_id", None):
                        area = Area.query.get(beneficiary.area_id)
                        if area:
                            parent_hoa_value = area.area_name
                if not parent_hoa_value:
                    try:
                        hoa_field = getattr(parent, "hoa", None)
                        if hoa_field:
                            try:
                                a = Area.query.get(int(hoa_field))
                                if a:
                                    parent_hoa_value = a.area_name
                            except Exception:
                                a = Area.query.filter((Area.area_code == hoa_field) | (Area.area_name == hoa_field)).first()
                                if a:
                                    parent_hoa_value = a.area_name
                    except Exception:
                        pass

                parent_info = {
                    "full_name": parent_full_name,
                    "date_of_birth": parent.date_of_birth.isoformat() if parent.date_of_birth else "",
                    "sex": parent.sex,
                    "citizenship": parent.citizenship,
                    "age": parent.age,
                    "phone_number": parent.phone_number,
                    "year_of_residence": parent.year_of_residence,
                    "current_address": parent.current_address or "",
                    "blk_num": getattr(parent, "block_no", "") or "",
                    "lot_num": getattr(parent, "lot_no", "") or "",
                    "lot_size": getattr(parent, "lot_size", "") or "",
                    "civil_status": parent.civil_status,
                    "recipient_of_other_housing": parent.recipient_of_other_housing,
                    "hoa": parent_hoa_value,
                    "supporting_documents": parent_docs if parent_docs else [],
                }
        data["parent_info"] = parent_info

    return jsonify(data)

# --- Submit pathway dispute ---

@pathway_dispute_bp.route('/submit_pathway_dispute', methods=['POST'])
def submit_pathway_dispute():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "message": "User not logged in"}), 401

        registration_id = request.form.get('registration_id') or session.get('registration_id')
        registration = Registration.query.get(registration_id)
        if not registration:
            return jsonify({"success": False, "message": "Parent registration not found"}), 400

        # Build complainant name and address
        middle_name = registration.middle_name or ""
        suffix = registration.suffix or ""
        name_parts = [registration.first_name, middle_name, registration.last_name, suffix]
        complainant_name = " ".join([p for p in name_parts if p])
        address = registration.current_address or ""


        # --- Resolve area_id (match logic from get_pathway_session_data) ---
        from backend.database.models import Area, Block, Beneficiary
        area_id = None
        # Try by beneficiary_id
        if getattr(registration, "beneficiary_id", None):
            beneficiary = Beneficiary.query.get(registration.beneficiary_id)
            if beneficiary and getattr(beneficiary, "area_id", None):
                area_id = beneficiary.area_id
        # Try by block/lot
        if area_id is None:
            try:
                block_no = getattr(registration, "block_no", None)
                lot_no = getattr(registration, "lot_no", None)
                if block_no and lot_no:
                    bn = int(block_no)
                    ln = int(lot_no)
                    blk = Block.query.filter_by(block_no=bn).first()
                    if blk:
                        beneficiary = Beneficiary.query.filter_by(block_id=blk.block_id, lot_no=ln).first()
                        if beneficiary:
                            area_id = beneficiary.area_id
            except Exception:
                pass
        # Try by reg.hoa (if it's an area_id or area_code)
        if area_id is None:
            hoa_field = getattr(registration, "hoa", None)
            if hoa_field:
                area = None
                try:
                    area = Area.query.get(int(hoa_field))
                except Exception:
                    pass
                if not area:
                    area = Area.query.filter_by(area_code=hoa_field).first()
                if area:
                    area_id = area.area_id
        if area_id is None:
            return jsonify({
                "success": False,
                "message": "Cannot submit complaint: Area assignment not found for your HOA/area. Please contact admin.",
                "mismatches": ["Area Assignment"]
            }), 400

        # Create Complaint
        new_complaint = Complaint(
            registration_id=registration.registration_id,
            type_of_complaint="Pathway Dispute",
            status="Valid",
            complainant_name=complainant_name,
            area_id=area_id,
            address=address
        )
        db.session.add(new_complaint)
        db.session.flush()  # Assigns complaint_id without committing


        # Handle block_lot for non-members (if present)
        block_lot = None
        if registration.category == 'non_member':
            block_nos = request.form.getlist('block_no[]')
            lot_nos = request.form.getlist('lot_no[]')
            block_lot = []
            for b, l in zip(block_nos, lot_nos):
                if b.strip() or l.strip():
                    block_lot.append({"block": b.strip(), "lot": l.strip()})
            if not block_lot:
                block_lot = None


        # Map HTML form fields to PathwayDispute columns (support both legacy names and q1..q12)
        def pick_one(*keys):
            for k in keys:
                # Always try getlist first (for checkboxes, or if only one value, returns single-item list)
                vals = request.form.getlist(k)
                if vals and (len(vals) > 1 or (len(vals) == 1 and vals[0] != '')):
                    return vals
                v = request.form.get(k)
                if v:
                    return v
            return None

        def ensure_str(val):
            if isinstance(val, list):
                return val[0] if val else None
            return val

        # Radios (single answer, always string)
        q1 = ensure_str(pick_one("q1", "possession"))
        q2 = ensure_str(pick_one("q2", "nature"))
        q3 = ensure_str(pick_one("q3", "conflict"))
        q4 = ensure_str(pick_one("q4", "obstruction_present"))
        q6 = ensure_str(pick_one("q6", "residents_concerned"))
        q7 = ensure_str(pick_one("q7", "party_informed"))
        q10 = ensure_str(pick_one("q10", "site_inspection"))
        q12 = ensure_str(pick_one("q12", "ongoing_development"))
        # Checkboxes (multi-answer, always list)
        q5 = pick_one("q5", "site_effects[]") or []
        q8 = pick_one("q8", "boundary_reported_to[]") or []
        q9 = pick_one("q9", "site_result[]") or []
        q11 = pick_one("q11", "site_docs[]") or []
        description = request.form.get("description")

        # Signature upload
        signature_path = None
        try:
            file = request.files.get("signature_path")
            if file and getattr(file, 'filename', ''):
                filename = secure_filename(file.filename)
                save_path = os.path.join(UPLOAD_DIR, filename)
                file.save(save_path)
                signature_path = filename
            else:
                signature_path = request.form.get("signature_path")
        except Exception:
            signature_path = request.form.get("signature_path")

        pathway_entry = PathwayDispute(
            complaint_id=new_complaint.complaint_id,
            block_lot=json.dumps(block_lot) if block_lot is not None else None,
            q1=q1,
            q2=q2,
            q3=q3,
            q4=q4,
            q5=json.dumps(q5) if q5 else None,
            q6=q6,
            q7=q7,
            q8=json.dumps(q8) if q8 else None,
            q9=json.dumps(q9) if q9 else None,
            q10=q10,
            q11=json.dumps(q11) if q11 else None,
            q12=q12,
            description=description,
            signature=signature_path
        )

        db.session.add(pathway_entry)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Pathway dispute submitted successfully!",
            "complaint_id": new_complaint.complaint_id
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Server error: {e}"}), 500



def get_form_structure(type_of_complaint: str):
    if type_of_complaint != "Pathway Dispute":
        return []

    return [
        {
            "type": "radio",
            "name": "q1",
            "label": "1. What type of pathway is being encroached upon?",
            "options": [
                ("Public sidewalk (pedestrian path)", "Public sidewalk (pedestrian path)"),
                ("Common path/alley used by residents", "Common path/alley used by residents"),
                ("Government-declared easement or right-of-way", "Government-declared easement or right-of-way"),
                ("Path used for access to utilities (water lines, drainage, etc.)", "Path used for access to utilities (water lines, drainage, etc.)"),
            ],
        },
        {
            "type": "radio",
            "name": "q2",
            "label": "2. What is the nature of the encroachment?",
            "options": [
                ("Permanent structure", "A permanent structure (e.g., house extension, wall) was built on the path"),
                ("Fence or gate", "A fence or gate blocks pedestrian access"),
                ("Store or business", "A store or business has occupied the pathway"),
                ("Temporary blockage", "Temporary materials (e.g., chairs, tables, stalls) regularly block the path"),
                ("Parked vehicle", "Vehicle/s parked long-term on the path or right-of-way"),
                ("Debris or materials", "Construction debris or materials are placed on the path"),
            ],
        },
        {
            "type": "radio",
            "name": "q3",
            "label": "3. How long has the pathway been obstructed or encroached?",
            "options": [
                ("Less than 1 month", "Less than 1 month"),
                ("1-6 months", "1-6 months"),
                ("More than 6 months", "More than 6 months"),
                ("Not sure", "Not sure"),
            ],
        },
        {
            "type": "radio",
            "name": "q4",
            "label": "4. Is the obstruction still present at the time of filing this complaint?",
            "options": [
                ("Yes – fully blocked", "Yes – fully blocked"),
                ("Yes – partially blocked", "Yes – partially blocked"),
                ("No – removed but may return", "No – it was removed but may return"),
                ("No", "No"),
                ("Not sure", "Not sure"),
            ],
        },
        {
            "type": "checkbox",
            "name": "q5",
            "label": "5. How has this encroachment affected your access or mobility? <i style='font-size: 14px; font-weight: normal; color: grey;'>(Check all that apply)</i>",
            "options": [
                ("Cannot pass", "I can no longer pass through the area"),
                ("Unsafe or narrow", "The path has become unsafe or too narrow"),
                ("Children or elderly affected", "Children, elderly, or PWDs cannot safely use the path"),
                ("Forced to walk on road", "The obstruction forces people to walk on the road"),
                ("Emergency affected", "Emergency vehicles or services are affected"),
            ],
        },
        {
            "type": "radio",
            "name": "q6",
            "label": "6. Have other residents or the barangay raised similar concerns?",
            "options": [
                ("Yes", "Yes"),
                ("No", "No"),
                ("Not sure", "Not sure"),
            ],
        },
        {
            "type": "radio",
            "name": "q7",
            "label": "7. Has the encroaching party been informed or warned by anyone?",
            "options": [
                ("Yes – by me", "Yes – by me"),
                ("Yes – by barangay officials", "Yes – by barangay officials"),
                ("No", "No"),
                ("Not sure", "Not sure"),
            ],
        },
        {
            "type": "checkbox",
            "name": "q8",
            "label": "8. Has the dispute led to any of the following? <i style='font-size: 14px; font-weight: normal; color: grey;'>(Check all that apply)</i>",
            "options": [
                ("Threats or harassment", "Threats or harassment"),
                ("Physical altercation", "Physical altercation"),
                ("Demolition or forced entry", "Demolition or forced entry"),
                ("Property damage", "Property damage"),
                ("None", "None"),
            ],
        },
        {
            "type": "checkbox",
            "name": "q9",
            "label": "9. Have you reported this pathway issue to any office or authority? <i style='font-size: 14px; font-weight: normal; color: grey;'>(Check all that apply)</i>",
            "options": [
                ("Barangay", "Barangay"),
                ("HOA", "HOA"),
                ("NGC", "NGC"),
                ("USAD - PHASELAD", "USAD - PHASELAD"),
                ("None", "None"),
            ],
        },
        {
            "type": "radio",
            "name": "q10",
            "label": "10. Was there any site inspection or verification conducted?",
            "options": [
                ("Yes - Barangay", "Yes – by Barangay"),
                ("Yes - HOA", "Yes – by HOA"),
                ("Yes - NGC", "Yes – by NGC"),
                ("Yes - USAD - PHASELAD", "Yes – by USAD - PHASELAD"),
                ("No", "No"),
                ("Not sure", "Not sure"),
            ],
        },
        {
            "type": "checkbox",
            "name": "q11",
            "label": "11. What was the result of the report or inspection? <i style='font-size: 14px; font-weight: normal; color: grey;'>(Check all that apply)</i>",
            "options": [
                ("Advised to adjust or vacate", "The other party was advised to adjust or vacate"),
                ("Asked to provide more documents", "I was advised to provide more documents"),
                ("Still under investigation", "The issue is still under investigation"),
                ("No action taken", "No action was taken"),
                ("Not applicable", "Not applicable / No inspection yet"),
            ],
        },
        {
            "type": "radio",
            "name": "q12",
            "label": "12. Is there an ongoing development or government housing project in the area?",
            "options": [
                ("Yes", "Yes"),
                ("No", "No"),
                ("Not sure", "Not sure"),
            ],
        },
        {
            "type": "textarea",
            "name": "description",
            "label": "Please describe what happened briefly, including how you found out about the issue.",
        },
    ]