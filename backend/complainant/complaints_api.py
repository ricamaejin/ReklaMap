from flask import Blueprint, jsonify, session
from backend.database.models import Complaint, Overlapping, Registration
import json

complaints_bp = Blueprint("complaints_bp", __name__, url_prefix="/complainant/complaints")

# ---------------------------
# Get all complaints for logged-in user
# ---------------------------
@complaints_bp.route("/submitted", methods=["GET"])
def get_submitted_complaints():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "message": "User not logged in"}), 401

    # 1. Get all registration IDs for this user
    registrations = Registration.query.filter_by(user_id=user_id).all()
    registration_ids = [r.registration_id for r in registrations]

    if not registration_ids:
        return jsonify({"success": True, "complaints": []})  # no registrations found

    # 2. Fetch complaints linked to these registrations
    complaints = Complaint.query.filter(
        Complaint.registration_id.in_(registration_ids)
    ).order_by(Complaint.date_received.desc()).all()

    result = []
    for c in complaints:
        o = c.overlapping  # Overlapping row (one-to-one)

        # Extract block & lot from q1
        block, lot = None, None
        try:
            q1_data = json.loads(o.q1) if o and o.q1 else []
            if isinstance(q1_data, list) and len(q1_data) > 0:
                block = q1_data[0].get("block")
                lot = q1_data[0].get("lot")
        except Exception:
            pass

        result.append({
            "complaint_id": c.complaint_id,
            "type": c.type_of_complaint,
            "status": c.status,
            "created_at": c.date_received.strftime("%B %d, %Y") if c.date_received else "",
            "description": o.description if o else c.description,
            "person": {
                "name": o.q8 if o else "Unknown",
                "block": block,
                "lot": lot,
                "role": "HOA Member"
            }
        })

    return jsonify({"success": True, "complaints": result})


# ---------------------------
# Get details of a single complaint
# ---------------------------
@complaints_bp.route("/details/<int:complaint_id>", methods=["GET"])
def get_complaint_details(complaint_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "message": "User not logged in"}), 401

    complaint = Complaint.query.get_or_404(complaint_id)

    # Ensure the complaint belongs to the logged-in user
    if complaint.registration.user_id != user_id:
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    o = complaint.overlapping

    # Extract block & lot from q1
    block, lot = None, None
    try:
        q1_data = json.loads(o.q1) if o and o.q1 else []
        if isinstance(q1_data, list) and len(q1_data) > 0:
            block = q1_data[0].get("block")
            lot = q1_data[0].get("lot")
    except Exception:
        pass

    result = {
        "complaint_id": complaint.complaint_id,
        "type": complaint.type_of_complaint,
        "status": complaint.status,
        "created_at": complaint.date_received.strftime("%B %d, %Y") if complaint.date_received else "",
        "description": o.description if o else complaint.description,
        "signature": o.signature if o else None,
        "person": {
            "name": o.q8 if o else "Unknown",
            "block": block,
            "lot": lot,
            "role": "HOA Member"
        }
    }

    return jsonify({"success": True, "complaint": result})
