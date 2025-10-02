import os, json, time
from flask import Blueprint, session, send_from_directory, jsonify, request
from backend.database.models import Registration, Complaint, LotDispute
from backend.database.db import db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "..", "frontend", "complainant", "complaints"))

lot_dispute_bp = Blueprint(
    "lot_dispute",
    __name__,
    url_prefix="/complainant/lot_dispute"
)

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
        new_complaint = Complaint(
            registration_id=registration.registration_id,
            type_of_complaint="Lot Dispute",
            status="Valid"
        )
        db.session.add(new_complaint)
        db.session.flush()
        q1 = request.form.get("possession")
        q2 = request.form.get("conflict")
        q3 = request.form.get("dispute_start_date")
        q4 = request.form.get("reason")
        q5 = json.loads(request.form.get("reported_to") or "[]")
        q6 = request.form.get("result")
        q7 = request.form.get("opposing_name")
        q8 = request.form.get("relationship_with_person")
        q9 = request.form.get("legal_docs")
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
