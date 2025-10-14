import os, json, time
from flask import Blueprint, session, render_template, jsonify, request
from werkzeug.utils import secure_filename
from backend.database.models import Registration, Complaint, BoundaryDispute, Beneficiary, Block
from backend.database.db import db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "..", "frontend", "complainant", "complaints"))

boundary_dispute_bp = Blueprint(
    "boundary_dispute",
    __name__,
    url_prefix="/complainant/boundary_dispute"
)

@boundary_dispute_bp.route('/new_boundary_dispute_form')
def new_boundary_dispute_form():
    user_id = session.get('user_id')
    if not user_id:
        return "Not logged in", 401
    registration = Registration.query.filter_by(user_id=user_id).first()
    if not registration:
        return "No registration found for user", 400
    session['complaint_id'] = f"{user_id}-{int(time.time())}"
    session['registration_id'] = registration.registration_id
    return render_template('boundary_dispute.html')

@boundary_dispute_bp.route('/submit_boundary_dispute', methods=['POST'])
def submit_boundary_dispute():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "message": "User not logged in"}), 401

        registration_id = request.form.get('registration_id') or session.get('registration_id')
        registration = Registration.query.get(registration_id)
        if not registration:
            return jsonify({"success": False, "message": "Parent registration not found"}), 400

        # Helper functions
        def clean_field(val):
            if not val:
                return None
            val_str = str(val).strip()
            if val_str.lower() in {"na", "n/a", "none", ""}:
                return None
            return val_str

        def clean_enum(val, allowed):
            return val if val in allowed else None

        def parse_date(val):
            from datetime import datetime
            if not val:
                return None
            try:
                return datetime.strptime(val, "%Y-%m-%d").date()
            except ValueError:
                return None

        # Build complainant name and address
        middle_name = clean_field(registration.middle_name)
        suffix = clean_field(registration.suffix)
        name_parts = [registration.first_name, middle_name, registration.last_name, suffix]
        complainant_name = " ".join([p for p in name_parts if p])
        address = registration.current_address or ""





        # --- Use area/HOA from registration as reference for Q12 validation only ---
        # Resolve area_id from registration.hoa (can be area_id or area_name)
        area_id = None
        hoa_val = registration.hoa
        try:
            area_id = int(hoa_val)
        except Exception:
            from backend.database.models import Area
            area_obj = Area.query.filter_by(area_name=hoa_val).first()
            if area_obj:
                area_id = area_obj.area_id
        if area_id is None:
            return jsonify({
                "success": False,
                "message": "Cannot submit complaint: Area assignment not found for your HOA/area. Please contact admin.",
                "mismatches": ["Area Assignment"]
            }), 400

        # Create Complaint
        new_complaint = Complaint(
            registration_id=registration.registration_id,
            type_of_complaint="Boundary Dispute",
            status="Valid",
            complainant_name=complainant_name,
            area_id=area_id,
            address=address
        )
        db.session.add(new_complaint)
        db.session.flush()  # Assigns complaint_id without committing

        # --- Robust cross-check for Q12 (persons involved) ---
        # Q12: list of {name, block, lot} (excluding complainant)
        import json as _json
        # q12 can come as JSON string array OR as bracketed fields q12[0][name], q12[0][block], q12[0][lot]
        q12_raw = request.form.getlist("q12")
        q12_list = []
        if len(q12_raw) == 1 and isinstance(q12_raw[0], str) and q12_raw[0].strip().startswith("["):
            try:
                q12_list = _json.loads(q12_raw[0])
            except Exception:
                q12_list = []
        else:
            # Build from bracketed fields
            # Collect all keys like q12[<idx>][name|block|lot]
            import re
            pattern = re.compile(r"^q12\[(\d+)\]\[(name|block|lot)\]$")
            q12_map = {}
            for key in request.form.keys():
                m = pattern.match(key)
                if not m:
                    continue
                idx, field = m.group(1), m.group(2)
                q12_map.setdefault(idx, {})[field] = request.form.get(key)
            # Convert to ordered list by idx
            for idx in sorted(q12_map.keys(), key=lambda x: int(x)):
                q12_list.append(q12_map[idx])

        area_id = new_complaint.area_id
        from backend.database.models import Beneficiary, Block
        failed_entries = []
        def normalize_mi(val):
            if not val: return None
            return str(val).replace('.', '').strip().upper()[:1] or None

        for entry in q12_list:
            name = (entry.get("name") or "").strip()
            block = entry.get("block")
            lot = entry.get("lot")
            if not (name and block and lot):
                failed_entries.append({"entry": entry, "reason": ["Missing required fields"]})
                continue
            # Parse name: try to split into first and last name (ignore middle names/initials)
            name_parts = [p for p in name.split() if p]
            if len(name_parts) < 2:
                failed_entries.append({"entry": entry, "reason": ["Name must include at least first and last name"]})
                continue
            # Use only first and last name for matching, ignore middle names/initials
            first = name_parts[0].strip().upper()
            last = name_parts[-1].strip().upper()
            try:
                block_no = int(str(block).strip())
                lot_no = int(str(lot).strip())
            except Exception:
                failed_entries.append({"entry": entry, "reason": ["Block/Lot must be numbers"]})
                continue
            blk = Block.query.filter_by(area_id=area_id, block_no=block_no).first()
            if not blk:
                failed_entries.append({"entry": entry, "reason": ["Block Assignment"]})
                continue
            # Find beneficiary by block, lot, area
            ben = Beneficiary.query.filter(
                Beneficiary.area_id == area_id,
                Beneficiary.block_id == blk.block_id,
                Beneficiary.lot_no == lot_no
            ).first()
            if not ben:
                failed_entries.append({"entry": entry, "reason": ["No matching beneficiary for block/lot in your HOA"]})
                continue
            # Compare first and last name (case-insensitive, ignore extra spaces, allow partial match)
            ben_first = (ben.first_name or '').strip().upper()
            ben_last = (ben.last_name or '').strip().upper()
            mismatch = []
            # Allow partial match: form name must be contained in beneficiary name or vice versa
            if first not in ben_first and ben_first not in first:
                mismatch.append("First Name")
            if last not in ben_last and ben_last not in last:
                mismatch.append("Last Name")
            # Block Assignment (should always match, but double-check)
            try:
                benef_block_no = ben.block.block_no if ben.block else None
            except Exception:
                benef_block_no = None
            if benef_block_no != block_no:
                mismatch.append("Block Assignment")
            # Lot Assignment
            if str(ben.lot_no) != str(lot_no):
                mismatch.append("Lot Assignment")
            # HOA
            if str(ben.area_id) != str(area_id):
                mismatch.append("HOA")
            if mismatch:
                failed_entries.append({"entry": entry, "reason": mismatch})

        if failed_entries:
            # Compose error message listing failed entries and reasons
            msg = "The following person(s) have mismatches: "
            msg += "; ".join([
                f"{e['entry'].get('name','?')} (Block {e['entry'].get('block','?')}, Lot {e['entry'].get('lot','?')}): " + ", ".join(e['reason']) for e in failed_entries
            ])
            return jsonify({"success": False, "message": msg, "field": "q12"}), 400

        # Map HTML form fields to BoundaryDispute columns (ensure correct mapping and types)
        # Q1: nature_of_issue (checkboxes, string[])
        q1 = request.form.getlist("nature_of_issue")
        if not q1 or (len(q1) == 1 and not q1[0]):
            q1 = []
        # Q2: conflict (radio, string)
        q2 = clean_field(request.form.get("conflict"))
        # Q3: structure_status (radio, string)
        q3 = clean_field(request.form.get("structure_status"))

        # Q4: notice (radio, Yes/No)
        q4 = clean_enum((request.form.get("notice") or "").strip().capitalize(), ["Yes", "No"])
        # Q5: confronted (radio, Yes/No)
        q5 = clean_enum((request.form.get("confronted") or "").strip().capitalize(), ["Yes", "No"])
        # Q5_1: reasonDateInput (date)
        q5_1 = parse_date(request.form.get("reasonDateInput"))
        # Q6: dispute_effects (checkboxes, string[])
        q6 = request.form.getlist("dispute_effects")
        if not q6 or (len(q6) == 1 and not q6[0]):
            q6 = []
        # Q7: boundary_reported_to[] (checkboxes, string[])
        q7 = request.form.getlist("boundary_reported_to[]")
        if not q7 or (len(q7) == 1 and not q7[0]):
            q7 = []
        # Q8: site_inspection (radio, string)
        # Normalize some similar values for site_inspection
        si = clean_field(request.form.get("site_inspection"))
        q8 = si
        # Q9: site_result[] (checkboxes, string[])
        q9 = request.form.getlist("site_result[]")
        if not q9 or (len(q9) == 1 and not q9[0]):
            q9 = []
        # Q10: have_docs (radio, Yes/No)
        q10 = clean_enum(request.form.get("have_docs"), ["Yes", "No"])
        # Q10_1: boundary_docs[] (checkboxes, string[])
        q10_1 = request.form.getlist("boundary_docs[]")
        if not q10_1 or (len(q10_1) == 1 and not q10_1[0]):
            q10_1 = []
        # Q11: reason (radio, Yes/No/Not sure)
        q11 = clean_enum((request.form.get("reason") or "").strip().capitalize(), ["Yes", "No", "Not sure"])
        # Q12: q12 (persons involved, JSON array)
        # Already validated and parsed as q12_list above
        q12 = q12_list
        # Q13: boundary_relationship (text[])
        q13 = request.form.getlist("boundary_relationship")
        if not q13 or (len(q13) == 1 and not q13[0]):
            q13 = []
        # Q14: boundary_reside (radio, Yes/No/Not sure)
        q14 = clean_enum((request.form.get("boundary_reside") or "").strip().capitalize(), ["Yes", "No", "Not sure"])
        # Q15: claimDocs (radio, Yes/No)
        q15 = clean_enum(request.form.get("claimDocs"), ["Yes", "No"])
        # Q15_1: docs (checkboxes, string[])
        q15_1 = request.form.getlist("docs")
        if not q15_1 or (len(q15_1) == 1 and not q15_1[0]):
            q15_1 = []
        # Description: textarea
        description = clean_field(request.form.get("description"))
        # Signature upload: accept file and save to uploads/signatures
        signature_path = None
        try:
            file = request.files.get("signature_path")
            if file and getattr(file, 'filename', ''):
                filename = secure_filename(file.filename)
                # Use backend/uploads/signatures as in complainant.routes
                upload_dir = os.path.join(BASE_DIR, "..", "uploads", "signatures")
                upload_dir = os.path.normpath(upload_dir)
                os.makedirs(upload_dir, exist_ok=True)
                save_path = os.path.join(upload_dir, filename)
                # Avoid overwriting: if exists, add a timestamp prefix
                if os.path.exists(save_path):
                    name, ext = os.path.splitext(filename)
                    filename = f"{int(time.time())}_{name}{ext}"
                    save_path = os.path.join(upload_dir, filename)
                file.save(save_path)
                # Store just the filename; serving route will use known dir
                signature_path = filename
            else:
                # Fallback to text path if provided
                signature_path = clean_field(request.form.get("signature_path"))
        except Exception:
            signature_path = clean_field(request.form.get("signature_path"))


        # Handle block_lot for non-members (from static fields: block_no[] and lot_no[])
        block_lot = None
        if registration.category == 'non_member':
            block_nos = request.form.getlist('block_no[]')
            lot_nos = request.form.getlist('lot_no[]')
            block_lot = []
            for b, l in zip(block_nos, lot_nos):
                b = (b or '').strip()
                l = (l or '').strip()
                if b or l:
                    block_lot.append({'block': b, 'lot': l})
            if not block_lot:
                block_lot = None

        boundary_entry = BoundaryDispute(
            complaint_id=new_complaint.complaint_id,
            block_lot=json.dumps(block_lot) if block_lot is not None else None,
            q1=json.dumps(q1),
            q2=q2,
            q3=q3,
            q4=q4,
            q5=q5,
            q5_1=q5_1,
            q6=json.dumps(q6),
            q7=json.dumps(q7),
            q8=q8,
            q9=json.dumps(q9),
            q10=q10,
            q10_1=json.dumps(q10_1),
            q11=q11,
            q12=json.dumps(q12),
            q13=json.dumps(q13),
            q14=q14,
            q15=q15,
            q15_1=json.dumps(q15_1),
            description=description,
            signature_path=signature_path
        )

        db.session.add(boundary_entry)
        
        # Create initial timeline entry for "Submitted" status with actual submission time
        from backend.database.models import ComplaintHistory
        import json as timeline_json
        
        submitted_timeline = ComplaintHistory(
            complaint_id=new_complaint.complaint_id,
            type_of_action='Submitted',
            assigned_to='',
            details=timeline_json.dumps({'description': 'Submitted a Valid Complaint'}),
            action_datetime=new_complaint.date_received  # Use actual submission time from complaints table
        )
        db.session.add(submitted_timeline)
        
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Boundary dispute submitted successfully!",
            "complaint_id": new_complaint.complaint_id
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Server error: {e}"}), 500

@boundary_dispute_bp.route('/get_boundary_session_data')
def get_boundary_session_data():
    registration_id = session.get("registration_id")
    complaint_id = session.get("complaint_id")
    if not registration_id:
        return
    reg = Registration.query.get(registration_id)
    if not reg:
        return

    def safe(val):
        if not val:
            return ""
        val_str = str(val).strip()
        if val_str.lower() in {"na", "n/a", "none"}:
            return ""
        return val_str

    name_parts = [safe(reg.first_name), safe(reg.middle_name), safe(reg.last_name), safe(reg.suffix)]
    full_name = " ".join([p for p in name_parts if p])

    # Default HOA value is the registration.hoa field (may be an ID or name)
    hoa_value = getattr(reg, "hoa", "") or ""
    # For non_member, hoa_member, and family_of_member, try to resolve area name from block/beneficiary
    def resolve_area_name(block_no, lot_no):
        try:
            if block_no and lot_no:
                bn = int(block_no)
                ln = int(lot_no)
                blk = Block.query.filter_by(block_no=bn).first()
                if blk:
                    beneficiary = Beneficiary.query.filter_by(block_id=blk.block_id, lot_no=ln).first()
                    if beneficiary:
                        from backend.database.models import Area
                        area = Area.query.filter_by(area_id=beneficiary.area_id).first()
                        if area:
                            return area.area_name
        except Exception:
            pass
        return ""

    # Helper: resolve hoa value (id or name) to the canonical area_name when possible
    def resolve_hoa_name(hoa_val):
        if not hoa_val:
            return ""
        try:
            aid = int(hoa_val)
            from backend.database.models import Area
            area = Area.query.get(aid)
            if area:
                return area.area_name
        except Exception:
            pass
        try:
            from backend.database.models import Area
            a = Area.query.filter_by(area_name=str(hoa_val)).first()
            if a:
                return a.area_name
        except Exception:
            pass
        return str(hoa_val)

    if reg.category == "non_member":
        area_name = resolve_area_name(getattr(reg, "block_no", None), getattr(reg, "lot_no", None))
        if area_name:
            hoa_value = area_name
        else:
            # Fallback: try to resolve area name from hoa_value if it's an ID
            try:
                from backend.database.models import Area
                hoa_id = int(hoa_value)
                area = Area.query.filter_by(area_id=hoa_id).first()
                if area:
                    hoa_value = area.area_name
            except Exception:
                pass
    elif reg.category in ("hoa_member", "family_of_member"):
        area_name = resolve_area_name(getattr(reg, "block_no", None), getattr(reg, "lot_no", None))
        if area_name:
            hoa_value = area_name
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
        "hoa": hoa_value,
        "blk_num": getattr(reg, "block_no", "") or "",
        "lot_num": getattr(reg, "lot_no", "") or "",
        "lot_size": getattr(reg, "lot_size", "") or "",
        "supporting_documents": None,
    }

    if reg.category == "hoa_member":
        from backend.database.models import RegistrationHOAMember
        hoa_member = RegistrationHOAMember.query.filter_by(registration_id=reg.registration_id).first()
        if hoa_member and hoa_member.supporting_documents:
            data["supporting_documents"] = hoa_member.supporting_documents
    elif reg.category == "non_member":
        from backend.database.models import RegistrationNonMember
        non_member = RegistrationNonMember.query.filter_by(registration_id=reg.registration_id).first()
        if non_member and non_member.connections:
            connections_val = ""
            if isinstance(non_member.connections, dict):
                checkbox_labels = [
                    "I live on the lot but I am not the official beneficiary",
                    "I live near the lot and I am affected by the issue",
                    "I am claiming ownership of the lot",
                    "I am related to the person currently occupying the lot",
                    "I was previously assigned to this lot but was replaced or removed"
                ]
                display_labels = []
                for idx, label in enumerate(checkbox_labels, start=1):
                    key = f"connection_{idx}"
                    if non_member.connections.get(key):
                        display_labels.append(label)
                other = non_member.connections.get("connection_other")
                if other:
                    display_labels.append(other)
                connections_val = ", ".join(display_labels)
            elif isinstance(non_member.connections, list):
                connections_val = ", ".join([str(x) for x in non_member.connections if x])
            elif isinstance(non_member.connections, str):
                connections_val = non_member.connections
            else:
                connections_val = str(non_member.connections)
            data["connections"] = connections_val
    elif reg.category == "family_of_member":
        from backend.database.models import RegistrationFamOfMember, RegistrationHOAMember
        fam = RegistrationFamOfMember.query.filter_by(registration_id=reg.registration_id).first()
        if fam:
            data["relationship"] = getattr(fam, "relationship", "")
            # First build parent_info from the family record where available
            sd = getattr(fam, 'supporting_documents', {}) or {}
            parts = [str(getattr(fam, 'last_name', '') or '').strip(), str(getattr(fam, 'first_name', '') or '').strip(), str(getattr(fam, 'middle_name', '') or '').strip(), str(getattr(fam, 'suffix', '') or '').strip()]
            parent_full_name = " ".join([p for p in parts if p])
            parent_info = {
                "full_name": parent_full_name,
                "date_of_birth": getattr(fam, 'date_of_birth', None).isoformat() if getattr(fam, 'date_of_birth', None) else "",
                "sex": getattr(fam, 'sex', None),
                "citizenship": getattr(fam, 'citizenship', None),
                "age": getattr(fam, 'age', None),
                "phone_number": getattr(fam, 'phone_number', None),
                "year_of_residence": getattr(fam, 'year_of_residence', None),
                "hoa": sd.get('hoa') or getattr(fam, 'hoa', '') or "",
                "current_address": getattr(fam, 'current_address', None) or sd.get('current_address') or "",
                "blk_num": sd.get('block_assignment') or getattr(fam, 'block_no', '') or "",
                "lot_num": sd.get('lot_assignment') or getattr(fam, 'lot_no', '') or "",
                "lot_size": sd.get('lot_size') or getattr(fam, 'lot_size', '') or "",
                "civil_status": sd.get('civil_status') or getattr(fam, 'civil_status', None),
                "recipient_of_other_housing": sd.get('recipient_of_other_housing') or getattr(fam, 'recipient_of_other_housing', None),
                "supporting_documents": sd if sd else None,
            }
            # If the family record references a beneficiary_id, try to locate the registered HOA parent and enrich
            try:
                if getattr(fam, 'beneficiary_id', None):
                    parent_reg = Registration.query.filter_by(beneficiary_id=fam.beneficiary_id, category='hoa_member').first()
                    if parent_reg:
                        parent_name_parts = [safe(parent_reg.first_name), safe(parent_reg.middle_name), safe(parent_reg.last_name), safe(parent_reg.suffix)]
                        parent_full_name = " ".join([p for p in parent_name_parts if p])
                        parent_info.update({
                            "full_name": parent_full_name,
                            "date_of_birth": parent_reg.date_of_birth.isoformat() if parent_reg.date_of_birth else parent_info.get('date_of_birth',''),
                            "sex": parent_reg.sex or parent_info.get('sex'),
                            "citizenship": parent_reg.citizenship or parent_info.get('citizenship'),
                            "age": parent_reg.age or parent_info.get('age'),
                            "phone_number": parent_reg.phone_number or parent_info.get('phone_number'),
                            "year_of_residence": parent_reg.year_of_residence or parent_info.get('year_of_residence'),
                            "current_address": parent_reg.current_address or parent_info.get('current_address'),
                            "blk_num": getattr(parent_reg, 'block_no', '') or parent_info.get('blk_num',''),
                            "lot_num": getattr(parent_reg, 'lot_no', '') or parent_info.get('lot_num',''),
                            "lot_size": getattr(parent_reg, 'lot_size', '') or parent_info.get('lot_size',''),
                        })
                        hoa_member = RegistrationHOAMember.query.filter_by(registration_id=parent_reg.registration_id).first()
                        if hoa_member and hoa_member.supporting_documents:
                            parent_info['supporting_documents'] = hoa_member.supporting_documents
            except Exception:
                pass
            data["parent_info"] = parent_info
        else:
            # fallback: just use family member's own info (should not happen in normal flow)
            parent_name_parts = [safe(fam.first_name), safe(fam.middle_name), safe(fam.last_name), safe(fam.suffix)]
            parent_full_name = " ".join([p for p in parent_name_parts if p])
            data["parent_info"] = {
                "full_name": parent_full_name,
                "date_of_birth": fam.date_of_birth.isoformat() if fam.date_of_birth else "",
                "sex": fam.sex,
                "citizenship": fam.citizenship,
                "age": fam.age,
                "phone_number": fam.phone_number,
                "year_of_residence": fam.year_of_residence,
                "hoa": "",
                "current_address": fam.current_address or "",
                "blk_num": "",
                "lot_num": "",
                "lot_size": "",
                "civil_status": "",
                "recipient_of_other_housing": "",
                "supporting_documents": fam.supporting_documents if hasattr(fam, "supporting_documents") else None,
            }

    # Ensure returned hoa is an area name when possible
    try:
        if data.get('hoa'):
            data['hoa'] = resolve_hoa_name(data['hoa'])
    except Exception:
        pass

    # Normalize parent_info.hoa to area name if present
    try:
        if data.get('parent_info') and isinstance(data['parent_info'], dict):
            p_h = data['parent_info'].get('hoa')
            if p_h:
                data['parent_info']['hoa'] = resolve_hoa_name(p_h)
    except Exception:
        pass

    return jsonify(data)

def get_form_structure(type_of_complaint: str):
    if type_of_complaint != "Boundary Dispute":
        return []

    return [
        {
            "type": "checkbox",
            "name": "q1",
            "label": "1. What is the nature of the boundary issue? <i style='font-size: 14px; font-weight: normal; color: grey;'>(Check all that apply)</i>",
            "options": [
                ("Neighbor structure extends beyond line", "A neighbor’s house or structure extends beyond their boundary line"),
                ("Fence overlaps into my property", "A fence or wall installed by the neighbor overlaps into my property"),
                ("Construction within my claimed boundary", "Construction is ongoing within my claimed boundary"),
                ("Shared boundary demolished", "Shared boundary structure (wall/fence) was demolished without consent"),
                ("Boundary markers moved", "Boundary markers (mohon) were moved or removed"),
                ("Neighbor expanded structure beyond assigned area", "The neighbor expanded their structure beyond their assigned area"),
                ("Encroachment affects utilities", "Encroachment is affecting access to utilities (e.g., water, drainage, electricity)"),
            ],
        },
        {
            "type": "radio",
            "name": "q2",
            "label": "2. How long has this encroachment existed?",
            "options": [
                ("Less than 1 month", "Less than 1 month"),
                ("1-6 months", "1-6 months"),
                ("More than 6 months", "More than 6 months"),
                ("Not sure", "Not sure"),
            ],
        },
        {
            "type": "radio",
            "name": "q3",
            "label": "3. Has the encroaching structure already been built or is it under construction?",
            "options": [
                ("Fully constructed", "Fully constructed"),
                ("Partially constructed", "Partially constructed"),
                ("Ongoing construction", "Ongoing construction"),
                ("Structure was removed but boundary still contested", "Structure was removed but boundary still contested"),
            ],
        },
        {
            "type": "radio",
            "name": "q4",
            "label": "4. Were you given any prior notice before the structure crossed into your property?",
            "options": [("Yes", "Yes"), ("No", "No")],
        },
        {
            "type": "radio",
            "name": "q5",
            "label": "5. Have you discussed or confronted the other party about the boundary issue?",
            "options": [("Yes", "Yes"), ("No", "No")],
            "conditional": {
                "trigger_value": "Yes",
                "additional_fields": [
                    {"type": "date", "name": "q5_1", "label": "Date Reported"},
                ],
            },
        },
        {
            "type": "checkbox",
            "name": "q6",
            "label": "6. Has the dispute led to any of the following? <i style='font-size: 14px; font-weight: normal; color: grey;'>(Check all that apply)</i>",
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
            "name": "q7",
            "label": "7. Have you reported this boundary issue to any office or authority? <i style='font-size: 14px; font-weight: normal; color: grey;'>(Check all that apply)</i>",
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
            "name": "q8",
            "label": "8. Was there any site inspection or verification conducted?",
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
            "name": "q9",
            "label": "9. What was the result of the report or inspection? <i style='font-size: 14px; font-weight: normal; color: grey;'>(Check all that apply)</i>",
            "options": [
                ("Advised to adjust or vacate", "The other party was advised to adjust or vacate"),
                ("Asked to provide more documents", "I was advised to provide more documents"),
                ("Still under investigation", "The issue is still under investigation"),
                ("No valid claim", "I was told I have no valid claim"),
                ("No action taken", "No action was taken"),
                ("Not applicable", "Not applicable / No inspection yet"),
            ],
        },
        {
            "type": "radio",
            "name": "q10",
            "label": "10. Do you have any documents or proof showing your boundary or property line?",
            "options": [("Yes", "Yes"), ("No", "No")],
            "conditional": {
                "trigger_value": "Yes",
                "additional_fields": [
                    {
                        "type": "checkbox",
                        "name": "q10_1",
                        "label": "Please specify documents <i style='font-size: 14px; font-weight: normal; color: grey;'>(Check all that apply)</i>",
                        "options": [
                            ("Subdivision or site survey map", "Subdivision or site survey map"),
                            ("Certificate of Lot Award (CLA)", "Title"),
                            ("Approved fence or building plan", "Building permit"),
                            ("Barangay certification or inspection report", "Barangay certification or inspection report"),
                            ("Photographs showing boundary markers or encroachment", "Photographs showing boundary markers or encroachment"),
                        ],
                    },
                ],
            },
        },
        {
            "type": "radio",
            "name": "q11",
            "label": "11. Is there an ongoing development or government housing project in the area?",
            "options": [("Yes", "Yes"), ("No", "No"), ("Not sure", "Not sure")],
        },
        {
            "type": "table",
            "name": "q12",
            "label": "12. Who are the persons and specific block and lot numbers involved in the boundary dispute? (Excluding yours)",
            "columns": ["Name", "Block", "Lot"],
        },
        {
            "type": "multiple_text",
            "name": "q13",
            "label": "13. Relationship with the person involved",
        },
        {
            "type": "radio",
            "name": "q14",
            "label": "14. Do they reside on or near the disputed boundary?",
            "options": [("Yes", "Yes"), ("No", "No"), ("Not sure", "Not sure")],
        },
        {
            "type": "radio",
            "name": "q15",
            "label": "15. Do they claim to have legal or assignment documents?",
            "options": [("Yes", "Yes"), ("No", "No")],
            "conditional": {
                "trigger_value": "Yes",
                "additional_fields": [
                    {
                        "type": "checkbox",
                        "name": "q15_1",
                        "label": "What documents do they have?",
                        "options": [
                            ("Title", "Title"),
                            ("Contract to Sell", "Contract to Sell"),
                            ("Certificate of Full Payment", "Certificate of Full Payment"),
                            ("Pre-qualification Stub", "Pre-qualification Stub"),
                            ("Contract/Agreement", "Contract/Agreement"),
                            ("Deed of Sale", "Deed of Sale"),
                        ],
                    },
                ],
            },
        },
        {
            "type": "textarea",
            "name": "description",
            "label": "Please describe what happened briefly, including how you found out about the issue.",
        },
    ]
