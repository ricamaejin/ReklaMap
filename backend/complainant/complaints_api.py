from flask import Blueprint, jsonify, session
from backend.database.models import Complaint, Registration, LotDispute, BoundaryDispute, Area, PathwayDispute, UnauthorizedOccupation
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
            # helper to extract a usable string from stored question value
            def _first(val):
                try:
                    if val is None:
                        return ""
                    if isinstance(val, list):
                        return val[0] if val else ""
                    if isinstance(val, str):
                        try:
                            parsed = json.loads(val)
                            if isinstance(parsed, list):
                                return parsed[0] if parsed else ""
                            if isinstance(parsed, str):
                                return parsed
                            return str(parsed)
                        except Exception:
                            return val
                    return str(val)
                except Exception:
                    return ""

            pathway_q1 = ""
            pathway_q2 = ""

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
                    person_role = relationship_value if relationship_value and relationship_value.strip() else "N/A"
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
            elif c.type_of_complaint == "Boundary Dispute":
                # Populate opposing parties from BoundaryDispute.q12 (persons) and q13 (relationships)
                try:
                    bound = BoundaryDispute.query.filter_by(complaint_id=c.complaint_id).first()
                except Exception:
                    bound = None
                opposing_parties = []
                if bound and bound.q12:
                    # parse q12 (could be JSON string or list)
                    try:
                        q12_data = bound.q12
                        if isinstance(q12_data, str):
                            try:
                                q12_data = json.loads(q12_data)
                            except Exception:
                                # treat as comma separated names
                                q12_data = [s.strip() for s in str(q12_data).split(',') if s.strip()]
                        if not isinstance(q12_data, list):
                            q12_data = [q12_data]
                    except Exception:
                        q12_data = []

                    # parse q13 (relationships)
                    q13_data = []
                    if bound.q13:
                        try:
                            q13_data = bound.q13
                            if isinstance(q13_data, str):
                                try:
                                    q13_data = json.loads(q13_data)
                                except Exception:
                                    q13_data = [s.strip() for s in str(q13_data).split(',') if s.strip()]
                            if not isinstance(q13_data, list):
                                q13_data = [q13_data]
                        except Exception:
                            q13_data = []

                    # build opposing parties list
                    for idx, entry in enumerate(q12_data):
                        name = None
                        block = None
                        lot = None
                        relationship = None
                        # entry can be dict, list, or string
                        if isinstance(entry, dict):
                            # try various key names
                            name = entry.get('name') or entry.get('Name') or entry.get('first_name') or None
                            if not name:
                                # maybe object has first/last
                                fn = entry.get('first_name') or entry.get('first') or ''
                                ln = entry.get('last_name') or entry.get('last') or ''
                                if fn or ln:
                                    name = (fn + ' ' + ln).strip()
                            block = entry.get('block') or entry.get('blk') or entry.get('blk_num') or entry.get('Block')
                            lot = entry.get('lot') or entry.get('lt') or entry.get('lot_num') or entry.get('Lot')
                            relationship = entry.get('relationship') or entry.get('rel') or None
                        elif isinstance(entry, list):
                            # common shape: [name, relationship, block, lot] or [name, block, lot]
                            if len(entry) >= 1:
                                name = entry[0]
                            if len(entry) >= 2:
                                # ambiguous; if numeric maybe block
                                if isinstance(entry[1], str) and not entry[1].isdigit():
                                    relationship = entry[1]
                                else:
                                    block = entry[1]
                            if len(entry) >= 3:
                                lot = entry[2]
                        else:
                            name = str(entry)

                        # fallback to q13_data if relationship not present
                        if not relationship and idx < len(q13_data):
                            relationship = q13_data[idx]

                        # normalize
                        if name:
                            opposing_parties.append({
                                'name': name,
                                'relationship': relationship or '',
                                'block': block,
                                'lot': lot
                            })
                # attach opposing_parties to this complaint's person structure
                if opposing_parties:
                    # prefer setting person_name to first opposing party's name for older UI compatibility
                    person_name = opposing_parties[0].get('name') or person_name
                else:
                    opposing_parties = []
            elif c.type_of_complaint == "Unauthorized Occupation" or (c.type_of_complaint and 'unauthorized' in c.type_of_complaint.lower()):
                # Parse involved persons from UnauthorizedOccupation.q2 (could be list, json string, etc.)
                try:
                    un = UnauthorizedOccupation.query.filter_by(complaint_id=c.complaint_id).first()
                except Exception:
                    un = None
                opposing_parties = []
                if un and getattr(un, 'q2', None):
                    try:
                        q2_data = un.q2
                        if isinstance(q2_data, str):
                            try:
                                q2_data = json.loads(q2_data)
                            except Exception:
                                q2_data = [s.strip() for s in str(q2_data).split(',') if s.strip()]
                        if not isinstance(q2_data, list):
                            q2_data = [q2_data]
                    except Exception:
                        q2_data = []

                    for entry in q2_data:
                        name = None
                        # entry can be dict or string
                        if isinstance(entry, dict):
                            name = entry.get('name') or entry.get('full_name') or entry.get('person') or None
                        else:
                            name = str(entry)
                        if name:
                            opposing_parties.append({'name': name, 'relationship': '', 'block': None, 'lot': None})
                # set default person_name to first opposing if missing
                if opposing_parties and not person_name:
                    person_name = opposing_parties[0].get('name')
            # Ensure complainant block/lot fall back to registration values when missing
            if reg:
                try:
                    if not person_block:
                        person_block = getattr(reg, 'block_no', None)
                except Exception:
                    person_block = None
                try:
                    if not person_lot:
                        person_lot = getattr(reg, 'lot_no', None)
                except Exception:
                    person_lot = None
            # PathwayDispute parsing should be independent of reg presence
            if c.type_of_complaint == "Pathway Dispute" or (c.type_of_complaint and 'pathway' in c.type_of_complaint.lower()):
                # Pull q1 (pathway type) and q2 (encroachment) from PathwayDispute model
                try:
                    pd = PathwayDispute.query.filter_by(complaint_id=c.complaint_id).first()
                except Exception:
                    pd = None
                if pd:
                    pathway_q1 = _first(getattr(pd, 'q1', None))
                    pathway_q2 = _first(getattr(pd, 'q2', None))
                # expose on top-level for frontend convenience
                # We'll attach these after building complainant/person

            # Compute complainant display values from registration
            complainant_name = ""
            complainant_type = "Non-HOA Member"
            hoa_or_area = ""
            if reg:
                complainant_name = f"{reg.first_name} {reg.last_name}"
                cat = (reg.category or "").lower()
                if cat == "hoa_member":
                    complainant_type = "HOA Member"
                elif "family" in cat:
                    complainant_type = "Family of Beneficiary"
                else:
                    complainant_type = "Non-HOA Member"

                # Try to resolve HOA/area name (reg.hoa may be an id or a string)
                if reg.hoa:
                    try:
                        aid = int(reg.hoa)
                        area = Area.query.get(aid)
                        hoa_or_area = area.area_name if area else str(reg.hoa)
                    except Exception:
                        hoa_or_area = str(reg.hoa)
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

            # created time parts for frontend display
            created_date = c.date_received.strftime("%B %d, %Y") if c.date_received else ""
            created_time = c.date_received.strftime("%H:%M") if c.date_received else ""

            result.append({
                "complaint_id": c.complaint_id,
                "type": c.type_of_complaint,
                "status": c.status,
                "created_at": created_date,
                "created_time": created_time,
                "created_at_ts": int(c.date_received.timestamp() * 1000) if c.date_received else 0,
                "description": description,
                "latest_action": latest_action,
                "action_datetime": latest_action_time,
                "complaint_stage": complaint_stage,
                "complainant": {
                    "name": complainant_name,
                    "type": complainant_type,
                    "hoa": hoa_or_area,
                    "block": person_block,
                    "lot": person_lot
                },
                "person": {
                    "name": person_name,
                    "role": person_role or ""
                },
                "opposing_parties": opposing_parties if 'opposing_parties' in locals() else [],
                "q1": pathway_q1 if 'pathway_q1' in locals() else "",
                "q2": pathway_q2 if 'pathway_q2' in locals() else ""
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
        elif complaint.type_of_complaint == "Boundary Dispute":
            try:
                bound = BoundaryDispute.query.filter_by(complaint_id=complaint.complaint_id).first()
            except Exception:
                bound = None
            opposing_parties = []
            if bound and bound.q12:
                try:
                    q12_data = bound.q12
                    if isinstance(q12_data, str):
                        try:
                            q12_data = json.loads(q12_data)
                        except Exception:
                            q12_data = [s.strip() for s in str(q12_data).split(',') if s.strip()]
                    if not isinstance(q12_data, list):
                        q12_data = [q12_data]
                except Exception:
                    q12_data = []

                q13_data = []
                if bound.q13:
                    try:
                        q13_data = bound.q13
                        if isinstance(q13_data, str):
                            try:
                                q13_data = json.loads(q13_data)
                            except Exception:
                                q13_data = [s.strip() for s in str(q13_data).split(',') if s.strip()]
                        if not isinstance(q13_data, list):
                            q13_data = [q13_data]
                    except Exception:
                        q13_data = []

                for idx, entry in enumerate(q12_data):
                    name = None
                    block = None
                    lot = None
                    relationship = None
                    if isinstance(entry, dict):
                        name = entry.get('name') or entry.get('Name') or None
                        block = entry.get('block') or entry.get('blk') or entry.get('blk_num')
                        lot = entry.get('lot') or entry.get('lt') or entry.get('lot_num')
                        relationship = entry.get('relationship') or entry.get('rel') or None
                    elif isinstance(entry, list):
                        if len(entry) >= 1:
                            name = entry[0]
                        if len(entry) >= 2:
                            if isinstance(entry[1], str) and not entry[1].isdigit():
                                relationship = entry[1]
                            else:
                                block = entry[1]
                        if len(entry) >= 3:
                            lot = entry[2]
                    else:
                        name = str(entry)

                    if not relationship and idx < len(q13_data):
                        relationship = q13_data[idx]

                    if name:
                        opposing_parties.append({
                            'name': name,
                            'relationship': relationship or '',
                            'block': block,
                            'lot': lot
                        })
            # set default person name to first opposing if missing
            if opposing_parties and not person_name:
                person_name = opposing_parties[0].get('name')
        elif complaint.type_of_complaint == "Unauthorized Occupation" or (complaint.type_of_complaint and 'unauthorized' in complaint.type_of_complaint.lower()):
            try:
                un = UnauthorizedOccupation.query.filter_by(complaint_id=complaint.complaint_id).first()
            except Exception:
                un = None
            opposing_parties = []
            if un and getattr(un, 'q2', None):
                try:
                    q2_data = un.q2
                    if isinstance(q2_data, str):
                        try:
                            q2_data = json.loads(q2_data)
                        except Exception:
                            q2_data = [s.strip() for s in str(q2_data).split(',') if s.strip()]
                    if not isinstance(q2_data, list):
                        q2_data = [q2_data]
                except Exception:
                    q2_data = []

                for entry in q2_data:
                    name = None
                    if isinstance(entry, dict):
                        name = entry.get('name') or entry.get('full_name') or entry.get('person') or None
                    else:
                        name = str(entry)
                    if name:
                        opposing_parties.append({'name': name, 'relationship': '', 'block': None, 'lot': None})
            if opposing_parties and not person_name:
                person_name = opposing_parties[0].get('name')
        else:
            person_role = "Complainant"

        # Ensure complainant block/lot fall back to registration values when missing (details endpoint)
        try:
            if reg:
                if not person_block:
                    person_block = getattr(reg, 'block_no', None)
        except Exception:
            person_block = person_block
        try:
            if reg:
                if not person_lot:
                    person_lot = getattr(reg, 'lot_no', None)
        except Exception:
            person_lot = person_lot

        # Pathway Dispute: pull q1/q2 for details view
        pathway_q1 = ""
        pathway_q2 = ""
        def _first_local(val):
            try:
                if val is None:
                    return ""
                if isinstance(val, list):
                    return val[0] if val else ""
                if isinstance(val, str):
                    try:
                        parsed = json.loads(val)
                        if isinstance(parsed, list):
                            return parsed[0] if parsed else ""
                        if isinstance(parsed, str):
                            return parsed
                        return str(parsed)
                    except Exception:
                        return val
                return str(val)
            except Exception:
                return ""

        if complaint.type_of_complaint == "Pathway Dispute" or (complaint.type_of_complaint and 'pathway' in complaint.type_of_complaint.lower()):
            try:
                pd = PathwayDispute.query.filter_by(complaint_id=complaint.complaint_id).first()
            except Exception:
                pd = None
            if pd:
                pathway_q1 = _first_local(getattr(pd, 'q1', None))
                pathway_q2 = _first_local(getattr(pd, 'q2', None))

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

        created_date = complaint.date_received.strftime("%B %d, %Y") if complaint.date_received else ""
        created_time = complaint.date_received.strftime("%H:%M") if complaint.date_received else ""

        result = {
            "complaint_id": complaint.complaint_id,
            "type": complaint.type_of_complaint,
            "status": complaint.status,
            "created_at": created_date,
            "created_time": created_time,
            "created_at_ts": int(complaint.date_received.timestamp() * 1000) if complaint.date_received else 0,
            "description": description,
            "latest_action": latest_action,
            "action_datetime": latest_action_time,
            "complaint_stage": complaint_stage,
            "signature": signature,
            "complainant": {
                "name": (reg.first_name + ' ' + reg.last_name) if reg else "",
                "type": ("HOA Member" if (reg and (reg.category or '').lower()=='hoa_member') else ("Family of Beneficiary" if (reg and 'family' in (reg.category or '').lower()) else "Non-HOA Member")),
                "hoa": (Area.query.get(int(reg.hoa)).area_name if reg and reg.hoa and str(reg.hoa).isdigit() and Area.query.get(int(reg.hoa)) else (reg.hoa if reg and reg.hoa else "")),
                "block": person_block,
                "lot": person_lot
            },
            "person": {
                "name": person_name,
                "role": person_role or ""
            }
        }
        # Attach pathway answers for details response
        if pathway_q1:
            result['q1'] = pathway_q1
        if pathway_q2:
            result['q2'] = pathway_q2
        # include opposing_parties when available (boundary dispute or unauthorized occupation)
        if 'opposing_parties' in locals():
            result['opposing_parties'] = opposing_parties
        # expose q2 for unauthorized occupation details (involved persons)
        try:
            if complaint.type_of_complaint and 'unauthorized' in complaint.type_of_complaint.lower() and un and getattr(un, 'q2', None):
                result['q2'] = un.q2
        except Exception:
            pass

        return jsonify({"success": True, "complaint": result})
    except Exception as e:
        return jsonify({"success": False, "message": f"Server error: {e}"}), 500