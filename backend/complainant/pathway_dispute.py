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

# --- Get session data for prefill ---
@pathway_dispute_bp.route('/get_pathway_session_data')
def get_pathway_session_data():
    registration_id = session.get("registration_id")
    complaint_id = session.get("complaint_id")
    if not registration_id:
        return jsonify({"error": "No registration_id in session"}), 400
    reg = Registration.query.get(registration_id)
    if not reg:
        return jsonify({"error": "No registration found for registration_id"}), 404

    # Build full_name (same as lot_dispute)
    middle_name = reg.middle_name or ""
    suffix = reg.suffix or ""
    name_parts = [reg.first_name, middle_name, reg.last_name, suffix]
    full_name = " ".join([p for p in name_parts if p])

    # Area name lookup (same as lot_dispute)
    hoa_value = ""
    reg_area_id = getattr(reg, "area_id", None)  # safely get area_id
    if reg_area_id:
        from backend.database.models import Area
        area = Area.query.filter_by(area_id=reg_area_id).first()
        if area and getattr(area, "area_name", None):
            hoa_value = str(area.area_name)
        else:
            hoa_value = str(reg_area_id)

    # DEBUG: print values to console
    print("registration area_id:", reg_area_id)
    print("hoa_value resolved as:", hoa_value)


    # Supporting documents (for hoa_member/family_of_member)
    supporting_documents = []
    if reg.category in ("hoa_member", "family_of_member"):
        try:
            docs = getattr(reg, "supporting_documents", None)
            if docs:
                if isinstance(docs, str):
                    import json as _json
                    supporting_documents = _json.loads(docs)
                elif isinstance(docs, list):
                    supporting_documents = docs
        except Exception:
            supporting_documents = []

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

		# Create Complaint
		new_complaint = Complaint(
			registration_id=registration.registration_id,
			type_of_complaint="Pathway Dispute",
			status="Valid",
			complainant_name=complainant_name,
			area_id=None,  # Set if you have area logic
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

		# Map HTML form fields to PathwayDispute columns
		q1 = request.form.get("possession")
		q2 = request.form.get("nature")
		q3 = request.form.get("conflict")
		q4 = request.form.get("obstruction_present")
		q5 = request.form.getlist("site_effects[]")
		q6 = request.form.get("residents_concerned")
		q7 = request.form.get("party_informed")
		q8 = request.form.getlist("boundary_reported_to[]")
		q9 = request.form.getlist("site_result[]")
		q10 = request.form.get("site_inspection")
		q11 = request.form.getlist("site_docs[]")
		q12 = request.form.get("ongoing_development")
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
