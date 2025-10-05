from flask import Blueprint, jsonify, session
from backend.database.models import Complaint, Overlapping, Registration
import json

complaints_bp = Blueprint("complaints_bp", __name__, url_prefix="/complainant/complaints")


# ---------------------------------
# Helpers: tolerant JSON and pairs
# ---------------------------------
def _parse_pairs_field(value):
    """Safely parse a pairs field that may be:
    - a Python list/dict (already deserialized)
    - a JSON string (list or dict)
    - bytes
    - an empty/whitespace/NA string
    Returns a list (possibly empty). If a dict is provided, wrap in a list.
    """
    try:
        if value is None:
            return []
        # Already a collection
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        if isinstance(value, dict):
            return [value]
        # Bytes-like
        if isinstance(value, (bytes, bytearray)):
            try:
                value = value.decode(errors="ignore")
            except Exception:
                return []
        # String handling
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return []
            if s.lower() in {"n/a", "na", "none", "null"}:
                return []
            # Only attempt JSON if it appears JSON-like
            if s[0] in "[{":
                try:
                    return json.loads(s)
                except Exception:
                    # Best-effort: normalize single quotes to double quotes
                    try:
                        return json.loads(s.replace("'", '"'))
                    except Exception:
                        return []
            return []
        # Unknown type
        return []
    except Exception:
        return []


def _first_block_lot(pairs):
    """Extract the first (block, lot) from a list of pairs where each item may be:
    - dict with keys like block/lot (with a few common aliases)
    - list/tuple like [block, lot]
    Returns (block, lot) or (None, None).
    """
    if not isinstance(pairs, list) or not pairs:
        return (None, None)
    first = pairs[0]
    if isinstance(first, dict):
        block = first.get("block") or first.get("blk") or first.get("blk_num") or first.get("block_no")
        lot = first.get("lot") or first.get("lt") or first.get("lot_num") or first.get("lot_no")
        return (block, lot)
    if isinstance(first, (list, tuple)) and len(first) >= 2:
        return (first[0], first[1])
    return (None, None)

# ---------------------------
# Get all complaints for logged-in user
# ---------------------------
@complaints_bp.route("/submitted", methods=["GET"])
def get_submitted_complaints():
    try:
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

        def extract_pairs(o):
            if not o:
                return []
            # Prefer new q2 JSON (pairs), then legacy q1 JSON (pairs)
            pairs = _parse_pairs_field(getattr(o, "q2", None))
            if not pairs:
                pairs = _parse_pairs_field(getattr(o, "q1", None))
            return pairs if isinstance(pairs, list) else []

        result = []
        for c in complaints:
            o = c.overlapping  # Overlapping row (one-to-one)
            block, lot = None, None
            try:
                pairs = extract_pairs(o)
                block, lot = _first_block_lot(pairs)
            except Exception:
                block, lot = None, None

            result.append({
                "complaint_id": c.complaint_id,
                "type": c.type_of_complaint,
                "status": c.status,
                "created_at": c.date_received.strftime("%B %d, %Y") if c.date_received else "",
                "description": o.description if o else c.description,
                "person": {
                    "name": (o.q8 if o and hasattr(o, 'q8') else "Unknown"),
                    "block": block,
                    "lot": lot,
                    "role": "HOA Member"
                }
            })

        return jsonify({"success": True, "complaints": result})
    except Exception as e:
        return jsonify({"success": False, "message": f"Server error: {e}"}), 500


# ---------------------------
# Get details of a single complaint
# ---------------------------
@complaints_bp.route("/details/<int:complaint_id>", methods=["GET"])
def get_complaint_details(complaint_id):
    try:
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"success": False, "message": "User not logged in"}), 401

        complaint = Complaint.query.get_or_404(complaint_id)

        # Ensure the complaint belongs to the logged-in user
        if complaint.registration.user_id != user_id:
            return jsonify({"success": False, "message": "Unauthorized"}), 403

        o = complaint.overlapping

        # Extract block & lot: prefer new q2 JSON pairs, fallback to legacy q1 JSON
        block, lot = None, None
        try:
            pairs = _parse_pairs_field(getattr(o, "q2", None)) if o else []
            if not pairs and o:
                pairs = _parse_pairs_field(getattr(o, "q1", None))
            block, lot = _first_block_lot(pairs)
        except Exception:
            block, lot = None, None

        result = {
            "complaint_id": complaint.complaint_id,
            "type": complaint.type_of_complaint,
            "status": complaint.status,
            "created_at": complaint.date_received.strftime("%B %d, %Y") if complaint.date_received else "",
            "description": o.description if o else complaint.description,
            "signature": o.signature if o else None,
            "person": {
                "name": (o.q8 if o and hasattr(o, 'q8') else "Unknown"),
                "block": block,
                "lot": lot,
                "role": "HOA Member"
            }
        }

        return jsonify({"success": True, "complaint": result})
    except Exception as e:
        return jsonify({"success": False, "message": f"Server error: {e}"}), 500
