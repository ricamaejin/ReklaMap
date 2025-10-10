
import os, json, time
from flask import Blueprint, session, render_template, jsonify, request
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

        # Determine area_id
        area_id = None
        try:
            if registration.block_no and registration.lot_no:
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
                blk = Block.query.filter_by(block_no=bn).first()
                if blk:
                    beneficiary = Beneficiary.query.filter_by(block_id=blk.block_id, lot_no=ln).first()
                    if beneficiary:
                        area_id = beneficiary.area_id
        except Exception:
            area_id = None

        if area_id is None:
            return jsonify({
                "success": False,
                "message": "Cannot submit complaint: Area assignment not found for your block and lot. Please contact admin.",
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

        # Create BoundaryDispute entry
        boundary_entry = BoundaryDispute(
            complaint_id=new_complaint.complaint_id,
            q1=json.dumps(request.form.getlist("q1")),
            q2=clean_field(request.form.get("q2")),
            q3=clean_field(request.form.get("q3")),
            q4=clean_enum(request.form.get("q4"), ["Yes", "No"]),
            q5=clean_enum(request.form.get("q5"), ["Yes", "No"]),
            q5_1=parse_date(request.form.get("q5_1")),
            q6=json.dumps(request.form.getlist("q6")),
            q7=json.dumps(request.form.getlist("q7")),
            q8=clean_field(request.form.get("q8")),
            q9=json.dumps(request.form.getlist("q9")),
            q10=clean_enum(request.form.get("q10"), ["Yes", "No"]),
            q10_1=json.dumps(request.form.getlist("q10_1")),
            q11=clean_enum(request.form.get("q11"), ["Yes", "No", "Not sure"]),
            q12=json.dumps(request.form.getlist("q12")),
            q13=json.dumps(request.form.getlist("q13")),
            q14=clean_enum(request.form.get("q14"), ["Yes", "No", "Not sure"]),
            q15=clean_enum(request.form.get("q15"), ["Yes", "No"]),
            q15_1=json.dumps(request.form.getlist("q15_1")),
            description=clean_field(request.form.get("description")),
            signature_path=clean_field(request.form.get("signature_path"))
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
        if non_member and hasattr(non_member, "connections") and isinstance(non_member.connections, dict):
            data["connections"] = non_member.connections
    elif reg.category == "family_of_member":
        from backend.database.models import RegistrationFamOfMember, RegistrationHOAMember
        fam = RegistrationFamOfMember.query.filter_by(registration_id=reg.registration_id).first()
        if fam:
            data["relationship"] = getattr(fam, "relationship", "")
            # Find parent registration (the HOA member this family belongs to)
            parent_reg = None
            if fam.beneficiary_id:
                # Try to find Registration with matching beneficiary_id and category 'hoa_member'
                parent_reg = Registration.query.filter_by(beneficiary_id=fam.beneficiary_id, category="hoa_member").first()
            if parent_reg:
                parent_name_parts = [safe(parent_reg.first_name), safe(parent_reg.middle_name), safe(parent_reg.last_name), safe(parent_reg.suffix)]
                parent_full_name = " ".join([p for p in parent_name_parts if p])
                parent_info = {
                    "full_name": parent_full_name,
                    "date_of_birth": parent_reg.date_of_birth.isoformat() if parent_reg.date_of_birth else "",
                    "sex": parent_reg.sex,
                    "citizenship": parent_reg.citizenship,
                    "age": parent_reg.age,
                    "phone_number": parent_reg.phone_number,
                    "year_of_residence": parent_reg.year_of_residence,
                    "hoa": getattr(parent_reg, "hoa", "") or "",
                    "current_address": parent_reg.current_address or "",
                    "blk_num": getattr(parent_reg, "block_no", "") or "",
                    "lot_num": getattr(parent_reg, "lot_no", "") or "",
                    "lot_size": getattr(parent_reg, "lot_size", "") or "",
                    "civil_status": parent_reg.civil_status,
                    "recipient_of_other_housing": parent_reg.recipient_of_other_housing,
                    "supporting_documents": None,
                }
                # Get supporting documents for parent HOA member
                hoa_member = RegistrationHOAMember.query.filter_by(registration_id=parent_reg.registration_id).first()
                if hoa_member and hoa_member.supporting_documents:
                    parent_info["supporting_documents"] = hoa_member.supporting_documents
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

    return jsonify(data)