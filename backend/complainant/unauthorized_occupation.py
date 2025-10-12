
import os
import time
from flask import Blueprint, session, render_template, jsonify, request
from werkzeug.utils import secure_filename
from backend.database.models import (
    Registration,
    Complaint,
    UnauthorizedOccupation,
    Area,
    RegistrationHOAMember,
    RegistrationFamOfMember,
    Beneficiary
)
from backend.database.db import db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "..", "frontend", "complainant", "complaints"))

unauthorized_occupation_bp = Blueprint(
    "unauthorized_occupation",
    __name__,
    url_prefix="/complainant/unauthorized_occupation"
)

@unauthorized_occupation_bp.route('/new_unauthorized_occupation_form')
def new_unauthorized_occupation_form():
    user_id = session.get('user_id')
    if not user_id:
        return
    registration = Registration.query.filter_by(user_id=user_id).first()
    if not registration:
        return
    session['complaint_id'] = f"{user_id}-{int(time.time())}"
    session['registration_id'] = registration.registration_id
    return render_template('unauthorized_occupation.html')

@unauthorized_occupation_bp.route('/submit_unauthorized_occupation', methods=['POST'])
def submit_unauthorized_occupation():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'message': 'Not logged in'})

        registration_id = request.form.get('registration_id') or session.get('registration_id')
        registration = Registration.query.get(registration_id)
        if not registration:
            return jsonify({'success': False, 'message': 'Registration not found'})

        # Helper functions
        def clean_field(val):
            return val.strip() if val else None

        def parse_json(val):
            import json
            if not val:
                return None
            try:
                return json.loads(val)
            except Exception:
                return None

        # Build complainant name and address
        middle_name = clean_field(registration.middle_name)
        suffix = clean_field(registration.suffix)
        name_parts = [registration.first_name, middle_name, registration.last_name, suffix]
        complainant_name = " ".join([p for p in name_parts if p])
        address = registration.current_address or ""

        # Create Complaint record
        complaint = Complaint(
            registration_id=registration.registration_id,
            type_of_complaint="Unauthorized Occupation",
            complainant_name=complainant_name,
            area_id=getattr(registration, 'hoa', None) or 0,
            address=address,
            status="Valid",
            complaint_stage="Pending"
        )
        db.session.add(complaint)
        db.session.flush()  # get complaint_id

        # Create UnauthorizedOccupation record
        unauthorized = UnauthorizedOccupation(
            complaint_id=complaint.complaint_id,
            block_lot=parse_json(request.form.get('block_lot')),
            q1=clean_field(request.form.get('legal_connection')),
            q2=parse_json(request.form.get('involved_persons')),
            q3=request.form.get('noticed_date'),
            q4=parse_json(request.form.get('activities')),
            q5=clean_field(request.form.get('occupant_claim')),
            q5a=parse_json(request.form.get('occupant_documents')),
            q6=clean_field(request.form.get('approach')),
            q6a=parse_json(request.form.get('approach_details')),
            q7=parse_json(request.form.get('boundary_reported_to')),
            q8=clean_field(request.form.get('result')),
            description=request.form.get('description'),
            signature=request.form.get('signature')
        )
        db.session.add(unauthorized)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Unauthorized Occupation complaint submitted.'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@unauthorized_occupation_bp.route('/get_unauthorized_occupation_session_data')
def get_unauthorized_occupation_session_data():
    registration_id = session.get("registration_id")
    complaint_id = session.get("complaint_id")
    if not registration_id:
        return jsonify({'success': False, 'message': 'No registration in session'})
    reg = Registration.query.get(registration_id)
    if not reg:
        return jsonify({'success': False, 'message': 'Registration not found'})
    def safe(val):
        return val if val else ''
    name_parts = [safe(reg.first_name), safe(reg.middle_name), safe(reg.last_name), safe(reg.suffix)]
    full_name = " ".join([p for p in name_parts if p])


    # --- Resolve area_name for HOA/Area field ---
    hoa_value = getattr(reg, "hoa", "") or ""
    area_name = hoa_value
    if hoa_value:
        # Try as area_id (int)
        try:
            area_id = int(hoa_value)
            area = Area.query.filter_by(area_id=area_id).first()
            if area:
                area_name = area.area_name
        except Exception:
            # Try as area_name directly
            area = Area.query.filter_by(area_name=hoa_value).first()
            if area:
                area_name = area.area_name


    # --- Supporting documents logic (match pathway_dispute/boundary_dispute) ---
    supporting_documents = None
    parent_info = None
    relationship = None
    if reg.category == "hoa_member":
        hoa_member = RegistrationHOAMember.query.filter_by(registration_id=reg.registration_id).first()
        if hoa_member and hoa_member.supporting_documents:
            supporting_documents = hoa_member.supporting_documents
    elif reg.category == "family_of_member":
        fam = RegistrationFamOfMember.query.filter_by(registration_id=reg.registration_id).first()
        if fam:
            # Find parent registration (the HOA member this family belongs to)
            parent_reg = None
            if fam.beneficiary_id:
                ben = Beneficiary.query.get(fam.beneficiary_id)
                if ben:
                    parent_reg = Registration.query.filter_by(beneficiary_id=ben.beneficiary_id, category="hoa_member").first()
            if parent_reg:
                hoa_member = RegistrationHOAMember.query.filter_by(registration_id=parent_reg.registration_id).first()
                parent_info = {
                    "full_name": " ".join([str(parent_reg.first_name or ""), str(parent_reg.middle_name or ""), str(parent_reg.last_name or ""), str(parent_reg.suffix or "")]).strip(),
                    "date_of_birth": parent_reg.date_of_birth.isoformat() if parent_reg.date_of_birth else "",
                    "sex": parent_reg.sex,
                    "citizenship": parent_reg.citizenship,
                    "age": parent_reg.age,
                    "current_address": parent_reg.current_address,
                    "year_of_residence": parent_reg.year_of_residence,
                    "phone_number": parent_reg.phone_number,
                    "civil_status": parent_reg.civil_status,
                    "hoa": area_name if hasattr(parent_reg, 'hoa') else "",
                    "blk_num": getattr(parent_reg, "block_no", "") or "",
                    "lot_num": getattr(parent_reg, "lot_no", "") or "",
                    "lot_size": getattr(parent_reg, "lot_size", "") or "",
                    "recipient_of_other_housing": parent_reg.recipient_of_other_housing,
                    "supporting_documents": hoa_member.supporting_documents if hoa_member and hoa_member.supporting_documents else None
                }
                relationship = fam.relationship if hasattr(fam, 'relationship') else None
                if hoa_member and hoa_member.supporting_documents:
                    supporting_documents = hoa_member.supporting_documents


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
        "hoa": area_name,
        "blk_num": getattr(reg, "block_no", "") or "",
        "lot_num": getattr(reg, "lot_no", "") or "",
        "lot_size": getattr(reg, "lot_size", "") or "",
        "supporting_documents": supporting_documents,
    }
    if reg.category == "family_of_member":
        data["parent_info"] = parent_info
        data["relationship"] = relationship
    return jsonify(data)

def get_form_structure():
    # Return a list of dicts describing the form fields (for dynamic rendering)
    return [
        {"type": "radio", "name": "legal_connection", "label": "1. What is your legal connection to this property?", "options": [
            ("beneficiary", "I am an awarded beneficiary."),
            ("heir", "I am an heir/successor-in-interest of the deceased registered owner."),
            ("purchaser", "I am the purchaser/buyer with a signed Deed of Sale or Contract to Sell."),
            ("lessee", "I am a lessee/tenant with a valid and current lease agreement."),
            ("hoa_officer", "I am a public Officer reporting on a common area"),
            ("representative", "I am an authorized representative of the owner/beneficiary")
        ]},
        {"type": "multiple_text", "name": "involved_persons", "label": "2. Who is currently occupying the lot?"},
        {"type": "date", "name": "noticed_date", "label": "3. When did you first notice the unauthorized occupation?"},
        {"type": "checkbox", "name": "activities", "label": "4. What activities are being done on the property?", "options": [
            ("living", "Living/residing on the lot"),
            ("built_structure", "Built a structure (house, shack, etc.)"),
            ("fenced", "Fenced or enclosed the area"),
            ("storing", "Storing personal belongings"),
            ("utilities", "Connected utilities (water, electricity)"),
            ("renting", "Renting it out to someone else")
        ]},
        {"type": "radio", "name": "occupant_claim", "label": "5. Have they claimed legal rights over the lot?", "options": [
            ("docs", "Yes, they presented documents"),
            ("verbal", "Yes, a verbal claim only (no documents)."),
            ("none", "No, they haven't made any claim."),
            ("unknown", "I don't know / I haven't asked.")
        ]},
        {"type": "checkbox", "name": "occupant_documents", "label": "Which documents do they have?", "options": [
            ("title", "Title"),
            ("contract_to_sell", "Contract to Sell"),
            ("certificate_full_payment", "Certificate of Full Payment"),
            ("qualification_stub", "Pre-qualification Stub"),
            ("contract_agreement", "Contract/Agreement"),
            ("deed_of_sale", "Deed of Sale")
        ]},
        {"type": "radio", "name": "approach", "label": "6. Have you tried to resolve this directly with the occupant?", "options": [
            ("yes", "Yes, I have spoken with them"),
            ("no", "No")
        ]},
        {"type": "checkbox", "name": "approach_details", "label": "What was their response?", "options": [
            ("no_docs", "They admitted they have no documents"),
            ("refused_leave", "They refused to leave the lot"),
            ("claim_owner", "They claim they are the real owner"),
            ("ignored", "They ignored me"),
            ("hostile", "They became hostile or aggressive")
        ]},
        {"type": "checkbox", "name": "boundary_reported_to", "label": "7. Have you reported this boundary issue to any office or authority?", "options": [
            ("Barangay", "Barangay"),
            ("HOA", "HOA"),
            ("NGC", "NGC"),
            ("USAD - PHASELAD", "USAD - PHASELAD"),
            ("none", "None")
        ]},
        {"type": "radio", "name": "result", "label": "8. What was the result of that report?", "options": [
            ("asked_to_leave", "The occupant was formally asked to leave"),
            ("provide_docs", "I was asked to provide more documents"),
            ("investigation", "Still under investigation"),
            ("pending", "The issue is still pending or unresolved."),
            ("no_action", "No action was taken by the authority."),
            ("no_valid_claim", "I was told I have no valid claim")
        ]},
        {"type": "textarea", "name": "description", "label": "Please describe what happened briefly, including how you found out about the issue."},
        {"type": "file", "name": "signature", "label": "Signature"}
    ]
