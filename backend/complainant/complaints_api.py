from flask import Blueprint, jsonify, session
from backend.database.models import Complaint, Overlapping, Registration, LotDispute
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
            person_name = "Unknown"
            person_block = None
            person_lot = None
            person_role = None
            description = c.description

            # Prefer complaint.registration when available; fallback safe
            reg = getattr(c, "registration", None)
            if not reg:
                try:
                    reg = Registration.query.get(c.registration_id)
                except Exception:
                    reg = None

            if c.type_of_complaint == "Lot Dispute":
                # Populate from LotDispute: q7 = opposing claimant name, q8 = relationship
                try:
                    lotd = LotDispute.query.filter_by(complaint_id=c.complaint_id).first()
                except Exception:
                    lotd = None
                if lotd:
                    person_name = lotd.q7 or person_name
                    # Relationship shown instead of HOA role; ensure safe fallback
                    person_role = f"Relationship: {lotd.q8}" if (lotd.q8 and str(lotd.q8).strip()) else "Relationship: N/A"
                    description = lotd.q4 or description
                # Block should be same as complainant's block (lot dispute context)
                if reg:
                    person_block = reg.block_no
                    person_lot = reg.lot_no
            else:
                # Overlapping and other types: fallback to overlapping logic
                o = c.overlapping
                try:
                    pairs = extract_pairs(o)
                    b, l = _first_block_lot(pairs)
                    person_block, person_lot = b, l
                except Exception:
                    person_block, person_lot = None, None
                if o and hasattr(o, 'q8'):
                    person_name = o.q8 or person_name
                # Default role
                person_role = "HOA Member"

            result.append({
                "complaint_id": c.complaint_id,
                "type": c.type_of_complaint,
                "status": c.status,
                "created_at": c.date_received.strftime("%B %d, %Y") if c.date_received else "",
                "created_at_ts": int(c.date_received.timestamp() * 1000) if c.date_received else 0,
                "description": description,
                "person": {
                    "name": person_name,
                    "block": person_block,
                    "lot": person_lot,
                    "role": person_role or ""
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

        # Build person/details depending on complaint type
        person_name = "Unknown"
        person_block = None
        person_lot = None
        person_role = None
        description = complaint.description
        signature = None

        reg = getattr(complaint, "registration", None)
        if not reg:
            try:
                reg = Registration.query.get(complaint.registration_id)
            except Exception:
                reg = None

        if complaint.type_of_complaint == "Lot Dispute":
            try:
                lotd = LotDispute.query.filter_by(complaint_id=complaint.complaint_id).first()
            except Exception:
                lotd = None
            if lotd:
                person_name = lotd.q7 or person_name
                person_role = f"Relationship: {lotd.q8}" if (lotd.q8 and str(lotd.q8).strip()) else "Relationship: N/A"
                description = lotd.q4 or description
            if reg:
                person_block = reg.block_no
                person_lot = reg.lot_no
        else:
            o = complaint.overlapping
            try:
                pairs = _parse_pairs_field(getattr(o, "q2", None)) if o else []
                if not pairs and o:
                    pairs = _parse_pairs_field(getattr(o, "q1", None))
                person_block, person_lot = _first_block_lot(pairs)
            except Exception:
                person_block, person_lot = None, None
            if o and hasattr(o, 'q8'):
                person_name = o.q8 or person_name
            description = (o.description if o else description)
            signature = (o.signature if o else None)
            person_role = "HOA Member"

        result = {
            "complaint_id": complaint.complaint_id,
            "type": complaint.type_of_complaint,
            "status": complaint.status,
            "created_at": complaint.date_received.strftime("%B %d, %Y") if complaint.date_received else "",
            "created_at_ts": int(complaint.date_received.timestamp() * 1000) if complaint.date_received else 0,
            "description": description,
            "signature": signature,
            "person": {
                "name": person_name,
                "block": person_block,
                "lot": person_lot,
                "role": person_role or ""
            }
        }

        return jsonify({"success": True, "complaint": result})
    except Exception as e:
        return jsonify({"success": False, "message": f"Server error: {e}"}), 500
