import os, json, time
from flask import Blueprint, session, render_template, jsonify, request
from backend.database.models import Registration, Complaint, BoundaryDispute
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
        new_complaint = Complaint(
            registration_id=registration.registration_id,
            type_of_complaint="Boundary Dispute",
            status="Valid"
        )
        db.session.add(new_complaint)
        db.session.flush()
        q1 = request.form.get("possession")
        q2 = request.form.get("conflict")
        q3 = request.form.get("reason")
        q4 = request.form.get("q4")
        q5 = request.form.get("q5")
        q6 = request.form.getlist("q6")
        q7 = request.form.get("reason")
        q7_1 = request.form.get("reasonDateInput")
        q8 = request.form.get("q8")
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
