from flask import Blueprint, jsonify, session
from backend.database.models import Complaint, Registration, LotDispute
from backend.database.db import db
from sqlalchemy import text
import json

complaints_bp = Blueprint("complaints_bp", __name__, url_prefix="/complainant/complaints")

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
                    # Extract name from q7 (could be JSON array or string)
                    if lotd.q7:
                        try:
                            if isinstance(lotd.q7, str):
                                # Try to parse as JSON first
                                try:
                                    q7_data = json.loads(lotd.q7)
                                    if isinstance(q7_data, list) and q7_data:
                                        person_name = q7_data[0]
                                    elif isinstance(q7_data, str):
                                        person_name = q7_data
                                except json.JSONDecodeError:
                                    # If not JSON, use as string
                                    person_name = lotd.q7
                            elif isinstance(lotd.q7, list) and lotd.q7:
                                person_name = lotd.q7[0]
                            else:
                                person_name = str(lotd.q7) if lotd.q7 else person_name
                        except Exception:
                            person_name = str(lotd.q7) if lotd.q7 else person_name
                    
                    # Extract relationship from q8 (could be JSON array or string)
                    relationship_value = "N/A"
                    if lotd.q8:
                        try:
                            if isinstance(lotd.q8, str):
                                # Try to parse as JSON first
                                try:
                                    q8_data = json.loads(lotd.q8)
                                    if isinstance(q8_data, list) and q8_data:
                                        relationship_value = q8_data[0]
                                    elif isinstance(q8_data, str):
                                        relationship_value = q8_data
                                except json.JSONDecodeError:
                                    # If not JSON, use as string
                                    relationship_value = lotd.q8
                            elif isinstance(lotd.q8, list) and lotd.q8:
                                relationship_value = lotd.q8[0]
                            else:
                                relationship_value = str(lotd.q8) if lotd.q8 else "N/A"
                        except Exception:
                            relationship_value = str(lotd.q8) if lotd.q8 else "N/A"
                    
                    # Format the role with proper relationship value
                    person_role = f"Relationship: {relationship_value}" if relationship_value and relationship_value.strip() else "Relationship: N/A"
                    description = lotd.q4 or description
                    
                    # Extract block from block_lot JSON (first number is the block)
                    if lotd.block_lot:
                        try:
                            if isinstance(lotd.block_lot, str):
                                # Try to parse as JSON first
                                try:
                                    block_lot_data = json.loads(lotd.block_lot)
                                except json.JSONDecodeError:
                                    block_lot_data = None
                            else:
                                block_lot_data = lotd.block_lot
                            
                            # Extract block and lot from parsed data
                            if isinstance(block_lot_data, list) and block_lot_data:
                                # Handle array of objects: [{"block": "1", "lot": "2"}] or array of arrays: [["1", "2"]]
                                first_entry = block_lot_data[0]
                                if isinstance(first_entry, dict):
                                    person_block = first_entry.get("block") or first_entry.get("blk") or first_entry.get("blk_num")
                                    person_lot = first_entry.get("lot") or first_entry.get("lt") or first_entry.get("lot_num")
                                elif isinstance(first_entry, list) and len(first_entry) >= 2:
                                    person_block = first_entry[0]  # First element is block
                                    person_lot = first_entry[1]    # Second element is lot
                                elif isinstance(first_entry, str):
                                    person_block = first_entry
                            elif isinstance(block_lot_data, dict):
                                # Handle single object: {"block": "1", "lot": "2"}
                                person_block = block_lot_data.get("block") or block_lot_data.get("blk") or block_lot_data.get("blk_num")
                                person_lot = block_lot_data.get("lot") or block_lot_data.get("lt") or block_lot_data.get("lot_num")
                        except Exception as e:
                            print(f"Error parsing block_lot for complaint {c.complaint_id}: {e}")
                            
                # Fallback: Use registration block if block_lot parsing failed
                if not person_block and reg:
                    person_block = reg.block_no
                if not person_lot and reg:
                    person_lot = reg.lot_no
            else:
                person_role = "Complainant"

            # Fetch latest action from timeline
            latest_action = None
            latest_action_time = None
            try:
                row = db.session.execute(
                    text("""
                        SELECT type_of_action, action_datetime
                        FROM complaint_history
                        WHERE complaint_id = :cid
                        ORDER BY action_datetime DESC
                        LIMIT 1
                    """),
                    {"cid": c.complaint_id}
                ).fetchone()
                if row:
                    latest_action = row.type_of_action
                    latest_action_time = row.action_datetime.isoformat() if row.action_datetime else None
            except Exception:
                pass

            # Fetch complaint_stage from DB (model may not expose column)
            complaint_stage = None
            try:
                stage_row = db.session.execute(
                    text("SELECT complaint_stage FROM complaints WHERE complaint_id = :cid"),
                    {"cid": c.complaint_id}
                ).fetchone()
                if stage_row:
                    # tuple or Row object
                    complaint_stage = getattr(stage_row, "complaint_stage", None) or (stage_row[0] if len(stage_row) else None)
            except Exception:
                complaint_stage = None

            result.append({
                "complaint_id": c.complaint_id,
                "type": c.type_of_complaint,
                "status": c.status,
                "created_at": c.date_received.strftime("%B %d, %Y") if c.date_received else "",
                "created_at_ts": int(c.date_received.timestamp() * 1000) if c.date_received else 0,
                "description": description,
                "latest_action": latest_action,
                "action_datetime": latest_action_time,
                "complaint_stage": complaint_stage,
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
                # Extract name from q7 (could be JSON array or string)
                if lotd.q7:
                    try:
                        if isinstance(lotd.q7, str):
                            # Try to parse as JSON first
                            try:
                                q7_data = json.loads(lotd.q7)
                                if isinstance(q7_data, list) and q7_data:
                                    person_name = q7_data[0]
                                elif isinstance(q7_data, str):
                                    person_name = q7_data
                            except json.JSONDecodeError:
                                # If not JSON, use as string
                                person_name = lotd.q7
                        elif isinstance(lotd.q7, list) and lotd.q7:
                            person_name = lotd.q7[0]
                        else:
                            person_name = str(lotd.q7) if lotd.q7 else person_name
                    except Exception:
                        person_name = str(lotd.q7) if lotd.q7 else person_name
                
                # Extract relationship from q8 (could be JSON array or string)
                relationship_value = "N/A"
                if lotd.q8:
                    try:
                        if isinstance(lotd.q8, str):
                            # Try to parse as JSON first
                            try:
                                q8_data = json.loads(lotd.q8)
                                if isinstance(q8_data, list) and q8_data:
                                    relationship_value = q8_data[0]
                                elif isinstance(q8_data, str):
                                    relationship_value = q8_data
                            except json.JSONDecodeError:
                                # If not JSON, use as string
                                relationship_value = lotd.q8
                        elif isinstance(lotd.q8, list) and lotd.q8:
                            relationship_value = lotd.q8[0]
                        else:
                            relationship_value = str(lotd.q8) if lotd.q8 else "N/A"
                    except Exception:
                        relationship_value = str(lotd.q8) if lotd.q8 else "N/A"
                
                # Format the role with proper relationship value
                person_role = f"Relationship: {relationship_value}" if relationship_value and relationship_value.strip() else "Relationship: N/A"
                description = lotd.q4 or description
                
                # Extract block from block_lot JSON (first number is the block)
                if lotd.block_lot:
                    try:
                        if isinstance(lotd.block_lot, str):
                            # Try to parse as JSON first
                            try:
                                block_lot_data = json.loads(lotd.block_lot)
                            except json.JSONDecodeError:
                                block_lot_data = None
                        else:
                            block_lot_data = lotd.block_lot
                        
                        # Extract block and lot from parsed data
                        if isinstance(block_lot_data, list) and block_lot_data:
                            # Handle array of objects: [{"block": "1", "lot": "2"}] or array of arrays: [["1", "2"]]
                            first_entry = block_lot_data[0]
                            if isinstance(first_entry, dict):
                                person_block = first_entry.get("block") or first_entry.get("blk") or first_entry.get("blk_num")
                                person_lot = first_entry.get("lot") or first_entry.get("lt") or first_entry.get("lot_num")
                            elif isinstance(first_entry, list) and len(first_entry) >= 2:
                                person_block = first_entry[0]  # First element is block
                                person_lot = first_entry[1]    # Second element is lot
                            elif isinstance(first_entry, str):
                                person_block = first_entry
                        elif isinstance(block_lot_data, dict):
                            # Handle single object: {"block": "1", "lot": "2"}
                            person_block = block_lot_data.get("block") or block_lot_data.get("blk") or block_lot_data.get("blk_num")
                            person_lot = block_lot_data.get("lot") or block_lot_data.get("lt") or block_lot_data.get("lot_num")
                    except Exception as e:
                        print(f"Error parsing block_lot for complaint {complaint.complaint_id}: {e}")
                        
            # Fallback: Use registration block if block_lot parsing failed
            if not person_block and reg:
                person_block = reg.block_no
            if not person_lot and reg:
                person_lot = reg.lot_no
        else:
            person_role = "Complainant"

        # Fetch latest action and complaint_stage
        latest_action = None
        latest_action_time = None
        try:
            row = db.session.execute(
                text("""
                    SELECT type_of_action, action_datetime
                    FROM complaint_history
                    WHERE complaint_id = :cid
                    ORDER BY action_datetime DESC
                    LIMIT 1
                """),
                {"cid": complaint.complaint_id}
            ).fetchone()
            if row:
                latest_action = row.type_of_action
                latest_action_time = row.action_datetime.isoformat() if row.action_datetime else None
        except Exception:
            pass

        complaint_stage = None
        try:
            stage_row = db.session.execute(
                text("SELECT complaint_stage FROM complaints WHERE complaint_id = :cid"),
                {"cid": complaint.complaint_id}
            ).fetchone()
            if stage_row:
                complaint_stage = getattr(stage_row, "complaint_stage", None) or (stage_row[0] if len(stage_row) else None)
        except Exception:
            pass

        result = {
            "complaint_id": complaint.complaint_id,
            "type": complaint.type_of_complaint,
            "status": complaint.status,
            "created_at": complaint.date_received.strftime("%B %d, %Y") if complaint.date_received else "",
            "created_at_ts": int(complaint.date_received.timestamp() * 1000) if complaint.date_received else 0,
            "description": description,
            "latest_action": latest_action,
            "action_datetime": latest_action_time,
            "complaint_stage": complaint_stage,
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