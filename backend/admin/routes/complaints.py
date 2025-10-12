import os
import json
from flask import Blueprint, send_file, request, jsonify, session, render_template
from ...database.db import db
from ...database.models import (
    Complaint,
    ComplaintHistory,
    Admin,
    Area,
    Beneficiary,
    Registration,
    LotDispute,
    BoundaryDispute,
    PathwayDispute,
    UnauthorizedOccupation,
    RegistrationFamOfMember,
    RegistrationHOAMember,
    RegistrationNonMember,
)
from sqlalchemy import text, func
from datetime import datetime

complaints_bp = Blueprint("complaints", __name__, url_prefix="/admin/complaints")

frontend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../frontend"))


def _safe_from_json_list(val):
    try:
        if isinstance(val, list):
            return val
        if isinstance(val, str):
            s = val.strip()
            if not s:
                return []
            if s.startswith('['):
                return json.loads(s)
            if ',' in s:
                return [p.strip() for p in s.split(',') if p.strip()]
            return [s]
    except Exception:
        return []
    return []

def _get_area_name(area_id):
    if not area_id:
        return ""
    try:
        area = Area.query.get(int(area_id))
        return area.area_name if area else str(area_id)
    except Exception:
        return str(area_id)

def _is_truthy(val):
    return val in (True, 1, '1', 'true', 'True', 'yes', 'on', 'Y', 'y')

def _normalize_list(val):
    try:
        if isinstance(val, list):
            return [x for x in val if x is not None]
        if isinstance(val, str):
            s = val.strip()
            if not s:
                return []
            if s.startswith('['):
                parsed = json.loads(s)
                return parsed if isinstance(parsed, list) else [s]
            if ',' in s:
                return [p.strip() for p in s.split(',') if p.strip()]
            return [s]
        return []
    except Exception:
        return []

def _to_lower_set(items):
    try:
        return {str(x).strip().lower() for x in (items or []) if str(x).strip()}
    except Exception:
        return set()

@complaints_bp.route('/api/complaint_form_preview/<int:complaint_id>', methods=['GET'])
def complaint_form_preview(complaint_id):
    """Return rendered HTML for the left-side complaint form preview for admin view.
    This mirrors complainant preview but is delivered as a server-rendered partial for injection.
    """
    try:
        complaint = Complaint.query.get_or_404(complaint_id)
        registration = Registration.query.get(complaint.registration_id)
        if not registration:
            return jsonify({'success': False, 'message': 'Registration not found'}), 404

        # Attach supporting documents convenience attribute (as done for complainant preview)
        try:
            hoa_member = RegistrationHOAMember.query.filter_by(registration_id=registration.registration_id).first()
            if hoa_member and getattr(hoa_member, 'supporting_documents', None):
                setattr(registration, 'supporting_documents', hoa_member.supporting_documents)
            else:
                if not hasattr(registration, 'supporting_documents'):
                    setattr(registration, 'supporting_documents', None)
        except Exception:
            if not hasattr(registration, 'supporting_documents'):
                setattr(registration, 'supporting_documents', None)

        # Build form_structure and answers depending on complaint type
        answers = {}
        form_structure = []
        lot_dispute = None
        boundary_dispute = None
        pathway_dispute = None
        unauthorized_occupation = None

        if complaint.type_of_complaint == 'Lot Dispute':
            # Import here to avoid circular import
            from backend.complainant.lot_dispute import get_form_structure as get_lot_form_structure
            form_structure = get_lot_form_structure('Lot Dispute')
            lot = LotDispute.query.filter_by(complaint_id=complaint_id).first()
            lot_dispute = lot
            if lot:
                # Normalize fields as in complainant preview
                q2_list = _safe_from_json_list(getattr(lot, 'q2', None))
                q4_list = _safe_from_json_list(getattr(lot, 'q4', None))
                q5_list = _safe_from_json_list(getattr(lot, 'q5', None))
                q6_list = _safe_from_json_list(getattr(lot, 'q6', None))
                q7_list = _safe_from_json_list(getattr(lot, 'q7', None))
                q8_list = _safe_from_json_list(getattr(lot, 'q8', None))

                q9_raw = getattr(lot, 'q9', None)
                q9_data = { 'claim': '', 'documents': [] }
                try:
                    if isinstance(q9_raw, dict):
                        q9_data = { 'claim': q9_raw.get('claim', ''), 'documents': q9_raw.get('documents', []) }
                    elif isinstance(q9_raw, str) and q9_raw.strip():
                        parsed = json.loads(q9_raw)
                        if isinstance(parsed, dict):
                            q9_data = { 'claim': parsed.get('claim', ''), 'documents': parsed.get('documents', []) }
                except Exception:
                    pass

                q10_raw = getattr(lot, 'q10', None)
                q10_data = {}
                try:
                    if isinstance(q10_raw, dict):
                        q10_data = q10_raw
                    elif isinstance(q10_raw, str) and q10_raw.strip():
                        q10_data = json.loads(q10_raw)
                except Exception:
                    q10_data = {}

                q3_val = lot.q3.strftime('%Y-%m-%d') if getattr(lot, 'q3', None) else ''

                answers = {
                    'q1': getattr(lot, 'q1', '') or '',
                    'q2': q2_list,
                    'q3': q3_val,
                    'q4': q4_list,
                    'q5': q5_list,
                    'q6': q6_list,
                    'q7': q7_list,
                    'q8': q8_list,
                    'q9': q9_data,
                    'q10': q10_data,
                    'description': getattr(lot, 'description', None) or getattr(complaint, 'description', '') or '',
                    'signature': getattr(lot, 'signature', None) or getattr(registration, 'signature_path', '') or '',
                }
        elif complaint.type_of_complaint == 'Boundary Dispute':
            bd = BoundaryDispute.query.filter_by(complaint_id=complaint_id).first()
            boundary_dispute = bd
            if bd:
                # Import here to avoid circular import
                try:
                    from backend.complainant.boundary_dispute import get_form_structure as get_boundary_form_structure
                    form_structure = get_boundary_form_structure('Boundary Dispute')
                except Exception:
                    form_structure = []

                def _json_list(v):
                    try:
                        if isinstance(v, list):
                            return v
                        if isinstance(v, str) and v.strip():
                            s = v.strip()
                            if s.startswith('['):
                                return json.loads(s)
                            if ',' in s:
                                return [p.strip() for p in s.split(',') if p.strip()]
                        return []
                    except Exception:
                        return []

                def _safe(v):
                    return v or ''

                q12_val = []
                try:
                    raw = getattr(bd, 'q12', None)
                    if isinstance(raw, list):
                        q12_val = raw
                    elif isinstance(raw, str) and raw.strip():
                        q12_val = json.loads(raw)
                except Exception:
                    q12_val = []

                answers = {
                    'q1': _json_list(getattr(bd, 'q1', None)),
                    'q2': _safe(getattr(bd, 'q2', None)),
                    'q3': _safe(getattr(bd, 'q3', None)),
                    'q4': _safe(getattr(bd, 'q4', None)),
                    'q5': _safe(getattr(bd, 'q5', None)),
                    'q5_1': getattr(bd, 'q5_1', None).strftime('%Y-%m-%d') if getattr(bd, 'q5_1', None) else '',
                    'q6': _json_list(getattr(bd, 'q6', None)),
                    'q7': _json_list(getattr(bd, 'q7', None)),
                    'q8': _safe(getattr(bd, 'q8', None)),
                    'q9': _json_list(getattr(bd, 'q9', None)),
                    'q10': _safe(getattr(bd, 'q10', None)),
                    'q10_1': _json_list(getattr(bd, 'q10_1', None)),
                    'q11': _safe(getattr(bd, 'q11', None)),
                    'q12': q12_val,
                    'q13': _json_list(getattr(bd, 'q13', None)),
                    'q14': _safe(getattr(bd, 'q14', None)),
                    'q15': _safe(getattr(bd, 'q15', None)),
                    'q15_1': _json_list(getattr(bd, 'q15_1', None)),
                    'description': _safe(getattr(bd, 'description', None)),
                    'signature_path': _safe(getattr(bd, 'signature_path', None)),
                }
        elif complaint.type_of_complaint == 'Pathway Dispute':
            # Dedicated block mirroring complainant preview
            pathway = PathwayDispute.query.filter_by(complaint_id=complaint_id).first()
            pathway_dispute = pathway
            if pathway:
                try:
                    from backend.complainant.pathway_dispute import get_form_structure as get_pathway_form_structure
                    form_structure = get_pathway_form_structure('Pathway Dispute')
                except Exception:
                    form_structure = []

                def _parse_json_list(val):
                    try:
                        if isinstance(val, list):
                            return val
                        if isinstance(val, str):
                            s = val.strip()
                            if not s:
                                return []
                            return json.loads(s)
                    except Exception:
                        pass
                    return []

                def _parse_str(val):
                    if val is None:
                        return ''
                    if isinstance(val, str):
                        return val
                    try:
                        return str(val)
                    except Exception:
                        return ''

                q12_val = getattr(pathway, 'q12', None)
                answers = {
                    'q1': getattr(pathway, 'q1', None) or '',
                    'q2': getattr(pathway, 'q2', None) or '',
                    'q3': getattr(pathway, 'q3', None) or '',
                    'q4': getattr(pathway, 'q4', None) or '',
                    'q5': _parse_json_list(getattr(pathway, 'q5', None)),
                    'q6': getattr(pathway, 'q6', None) or '',
                    'q7': getattr(pathway, 'q7', None) or '',
                    'q8': _parse_json_list(getattr(pathway, 'q8', None)),
                    'q9': _parse_json_list(getattr(pathway, 'q9', None)),
                    'q10': getattr(pathway, 'q10', None) or '',
                    'q11': _parse_json_list(getattr(pathway, 'q11', None)),
                    'q12': _parse_str(q12_val),
                    'description': getattr(pathway, 'description', None) or getattr(complaint, 'description', '') or '',
                    'signature': getattr(pathway, 'signature', None) or getattr(registration, 'signature_path', '') or '',
                }
        elif complaint.type_of_complaint == 'Unauthorized Occupation':
            # Build answers based on UnauthorizedOccupation model and its form structure
            unauthorized = UnauthorizedOccupation.query.filter_by(complaint_id=complaint_id).first()
            unauthorized_occupation = unauthorized
            try:
                from backend.complainant.unauthorized_occupation import get_form_structure as get_unauth_form_structure
                form_structure = get_unauth_form_structure()
            except Exception:
                form_structure = []

            if unauthorized:
                def _parse_list(val):
                    try:
                        if isinstance(val, list):
                            return val
                        if isinstance(val, str):
                            s = val.strip()
                            if not s:
                                return []
                            return json.loads(s)
                    except Exception:
                        pass
                    return []

                def _parse_date(val):
                    try:
                        if hasattr(val, 'strftime'):
                            return val.strftime('%Y-%m-%d')
                        if isinstance(val, str):
                            return val
                    except Exception:
                        pass
                    return ''

                # Map DB fields to generic names expected by form_structure template
                answers = {
                    'legal_connection': getattr(unauthorized, 'q1', None) or '',
                    'involved_persons': _parse_list(getattr(unauthorized, 'q2', None)),
                    'noticed_date': _parse_date(getattr(unauthorized, 'q3', None)),
                    'activities': _parse_list(getattr(unauthorized, 'q4', None)),
                    'occupant_claim': getattr(unauthorized, 'q5', None) or '',
                    'occupant_documents': _parse_list(getattr(unauthorized, 'q5a', None)),
                    'approach': getattr(unauthorized, 'q6', None) or '',
                    'approach_details': _parse_list(getattr(unauthorized, 'q6a', None)),
                    'boundary_reported_to': _parse_list(getattr(unauthorized, 'q7', None)),
                    'result': getattr(unauthorized, 'q8', None) or '',
                    'description': getattr(unauthorized, 'description', None) or getattr(complaint, 'description', '') or '',
                    'signature': getattr(unauthorized, 'signature', None) or getattr(registration, 'signature_path', '') or '',
                }

        # Parent info for family_of_member
        parent_info = None
        relationship = None
        try:
            if registration.category == 'family_of_member':
                fam = RegistrationFamOfMember.query.filter_by(registration_id=registration.registration_id).first()
                if fam:
                    relationship = fam.relationship
                    def _sv(v):
                        return str(v).strip() if v else ''
                    parts = [_sv(fam.first_name), _sv(fam.middle_name), _sv(fam.last_name), _sv(fam.suffix)]
                    sd = getattr(fam, 'supporting_documents', {}) or {}
                    hoa_raw = sd.get('hoa')
                    parent_info = {
                        'full_name': ' '.join([p for p in parts if p]),
                        'first_name': fam.first_name,
                        'middle_name': fam.middle_name,
                        'last_name': fam.last_name,
                        'suffix': fam.suffix,
                        'date_of_birth': fam.date_of_birth,
                        'sex': fam.sex,
                        'citizenship': fam.citizenship,
                        'age': fam.age,
                        'phone_number': fam.phone_number,
                        'year_of_residence': fam.year_of_residence,
                        'supporting_documents': getattr(fam, 'supporting_documents', None),
                        'hoa': _get_area_name(hoa_raw) if hoa_raw else '',
                        'block_no': sd.get('block_assignment') or '',
                        'lot_no': sd.get('lot_assignment') or '',
                        'lot_size': sd.get('lot_size') or '',
                        'civil_status': sd.get('civil_status') or '',
                        'recipient_of_other_housing': sd.get('recipient_of_other_housing') or '',
                        'current_address': sd.get('current_address') or '',
                    }
        except Exception:
            pass

        # Non-member connections (for non_member registrations)
        non_member_connections = None
        non_member_connections_list = None
        try:
            if registration and (registration.category or '').strip().lower() == 'non_member':
                reg_non_member = RegistrationNonMember.query.filter_by(registration_id=registration.registration_id).first()
                connections_val = ""
                if reg_non_member and getattr(reg_non_member, 'connections', None):
                    conn = reg_non_member.connections
                    checkbox_labels = [
                        "I live on the lot but I am not the official beneficiary",
                        "I live near the lot and I am affected by the issue",
                        "I am claiming ownership of the lot",
                        "I am related to the person currently occupying the lot",
                        "I was previously assigned to this lot but was replaced or removed"
                    ]
                    display_labels = []
                    if isinstance(conn, dict):
                        for idx, label in enumerate(checkbox_labels, start=1):
                            key = f"connection_{idx}"
                            val = conn.get(key)
                            if val in (True, 1, '1', 'true', 'True', 'yes', 'on'):
                                display_labels.append(label)
                        other = conn.get("connection_other")
                        if other:
                            display_labels.append(other)
                    elif isinstance(conn, list):
                        display_labels = [str(x) for x in conn if x]
                    elif isinstance(conn, str):
                        s = conn.strip()
                        if s:
                            if s.startswith('[') and s.endswith(']'):
                                try:
                                    arr = json.loads(s)
                                    if isinstance(arr, list):
                                        display_labels = [str(x).strip() for x in arr if str(x).strip()]
                                    else:
                                        display_labels = [s]
                                except Exception:
                                    display_labels = [p.strip() for p in s.split(',') if p.strip()]
                            else:
                                display_labels = [p.strip() for p in s.split(',') if p.strip()] if ',' in s else [s]
                    else:
                        display_labels = [str(conn)]
                    connections_val = ", ".join(display_labels)
                    non_member_connections_list = display_labels
                non_member_connections = connections_val
        except Exception:
            non_member_connections = None
            non_member_connections_list = None

        # Render the same structure as complainant side but as a partial for admin
        html = render_template(
            'admin/complaints/_complaint_form_preview.html',
            complaint=complaint,
            registration=registration,
            form_structure=form_structure,
            answers=answers,
            get_area_name=_get_area_name,
            lot_dispute=lot_dispute,
            boundary_dispute=boundary_dispute,
            pathway_dispute=pathway_dispute,
            unauthorized_occupation=unauthorized_occupation,
            parent_info=parent_info,
            relationship=relationship,
            non_member_connections=non_member_connections,
            non_member_connections_list=non_member_connections_list,
        )
        return html
    except Exception as e:
        print(f"Error generating form preview: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# Recommendation endpoint removed per request

# Staff Inspection Data Endpoint - loads inspection assignment details for staff modal
@complaints_bp.route('/api/staff_inspection_data/<int:complaint_id>', methods=['GET'])
def get_staff_inspection_data(complaint_id):
    """Get inspection assignment data for staff modal - deadline, location, scope from admin assignment"""
    try:
        # Query complaint_history for the most recent Inspection assignment
        inspection_query = text("""
            SELECT ch.details, ch.assigned_to, ch.action_datetime
            FROM complaint_history ch
            WHERE ch.complaint_id = :complaint_id 
            AND ch.type_of_action = 'Inspection'
            ORDER BY ch.action_datetime DESC
            LIMIT 1
        """)
        
        result = db.session.execute(inspection_query, {'complaint_id': complaint_id})
        inspection_row = result.fetchone()
        
        if not inspection_row:
            return jsonify({
                'success': False,
                'error': 'No inspection assignment found for this complaint'
            }), 404
        
        # Parse details JSON to extract inspection data
        inspection_details = {}
        if inspection_row.details:
            try:
                if isinstance(inspection_row.details, str):
                    inspection_details = json.loads(inspection_row.details)
                else:
                    inspection_details = inspection_row.details
            except (json.JSONDecodeError, TypeError):
                inspection_details = {}
        
        # Extract inspection assignment data
        staff_data = {
            'deadline': inspection_details.get('deadline', 'No deadline set'),
            'location': inspection_details.get('location', 'No location specified'),
            'scope': inspection_details.get('scope', []),
            'inspector': inspection_row.assigned_to or 'Not assigned',
            'assigned_date': inspection_row.action_datetime.strftime('%Y-%m-%d') if inspection_row.action_datetime else None
        }
        
        return jsonify({
            'success': True,
            'data': staff_data,
            **staff_data  # Flatten for easier access in frontend
        })
        
    except Exception as e:
        print(f"Error loading staff inspection data: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Staff Invitation Data Endpoint - loads invitation assignment details for staff modal
@complaints_bp.route('/api/staff_invitation_data/<int:complaint_id>', methods=['GET'])
def get_staff_invitation_data(complaint_id):
    """Get invitation assignment data for staff modal - individuals, date, time, venue, agenda from admin assignment"""
    try:
        # Query complaint_history for the most recent Invitation assignment
        invitation_query = text("""
            SELECT ch.details, ch.assigned_to, ch.action_datetime
            FROM complaint_history ch
            WHERE ch.complaint_id = :complaint_id 
            AND ch.type_of_action = 'Invitation'
            ORDER BY ch.action_datetime DESC
            LIMIT 1
        """)
        
        result = db.session.execute(invitation_query, {'complaint_id': complaint_id})
        invitation_row = result.fetchone()
        
        if not invitation_row:
            return jsonify({
                'success': False,
                'error': 'No invitation assignment found for this complaint'
            }), 404
        
        # Parse details JSON to extract invitation data
        invitation_details = {}
        if invitation_row.details:
            try:
                if isinstance(invitation_row.details, str):
                    invitation_details = json.loads(invitation_row.details)
                else:
                    invitation_details = invitation_row.details
            except (json.JSONDecodeError, TypeError):
                invitation_details = {}
        
        # Extract invitation assignment data using admin action field names
        to_field = invitation_details.get('to', 'No recipients specified')
        individuals_list = [name.strip() for name in to_field.split(',')] if to_field != 'No recipients specified' else ['No recipients specified']
        
        staff_data = {
            'individuals': individuals_list,  # Convert comma-separated 'to' field to list
            'meeting_date': invitation_details.get('meeting_date', 'No date set'),
            'meeting_time': invitation_details.get('meeting_time', 'No time set'),
            'venue': invitation_details.get('location', 'No venue specified'),  # Admin uses 'location' field
            'agenda': invitation_details.get('agenda', 'No agenda specified'),
            'assistant': invitation_row.assigned_to or 'Not assigned',
            'assigned_date': invitation_row.action_datetime.strftime('%Y-%m-%d') if invitation_row.action_datetime else None
        }
        
        return jsonify({
            'success': True,
            'data': staff_data,
            **staff_data  # Flatten for easier access in frontend
        })
        
    except Exception as e:
        print(f"Error loading staff invitation data: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Action Details Endpoint - fetch specific action details that admin inputted
@complaints_bp.route('/api/action_details/<int:complaint_id>/<string:action_type>', methods=['GET'])
def get_action_details(complaint_id, action_type):
    """Get action details that admin inputted when creating the action (e.g., Invitation details)"""
    try:
        # Query complaint_history for the most recent action of the specified type
        action_query = text("""
            SELECT ch.details, ch.assigned_to, ch.action_datetime, ch.description
            FROM complaint_history ch
            WHERE ch.complaint_id = :complaint_id 
            AND ch.type_of_action = :action_type
            ORDER BY ch.action_datetime DESC
            LIMIT 1
        """)
        
        result = db.session.execute(action_query, {
            'complaint_id': complaint_id, 
            'action_type': action_type
        })
        action_row = result.fetchone()
        
        if not action_row:
            return jsonify({
                'success': False,
                'error': f'No {action_type} action found for this complaint'
            }), 404
        
        # Parse details JSON to extract action data
        action_details = {}
        if action_row.details:
            try:
                if isinstance(action_row.details, str):
                    action_details = json.loads(action_row.details)
                else:
                    action_details = action_row.details
            except (json.JSONDecodeError, TypeError):
                action_details = {}
        
        return jsonify({
            'success': True,
            'action_details': {
                'details': action_details,
                'assigned_to': action_row.assigned_to,
                'action_datetime': action_row.action_datetime.isoformat() if action_row.action_datetime else None,
                'description': action_row.description
            }
        })
        
    except Exception as e:
        print(f"Error loading action details: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Staff Complete Task Endpoint - handles when staff clicks "Update" button
@complaints_bp.route('/api/staff_complete_task', methods=['POST'])
def staff_complete_task():
    """Handle staff task completion - updates timeline status to 'Task Completed'"""
    try:
        data = request.get_json()
        complaint_id = data.get('complaint_id')
        description = data.get('description', '')
        files = data.get('files', [])
        staff_account_type = data.get('staff_account_type', 2)  # admin.account == 2
        
        if not complaint_id:
            return jsonify({'success': False, 'error': 'Complaint ID is required'}), 400
        
        # Determine completion status based on task type
        request_data = data  # Use the request data to determine task type
        task_type = request_data.get('task_type', 'inspection')  # Default to inspection
        
        if task_type == 'invitation':
            completion_status = 'Sent Invitation'
            task_description = 'invitation'
        elif task_type == 'assessment':
            completion_status = 'Assessment'
            task_description = 'assessment'
        else:
            completion_status = 'Inspection done'
            task_description = 'inspection'
        
        # Create detailed completion record with task findings
        completion_details = {
            f'{task_description}_findings': description,
            'attached_files': files,
            'completed_by_staff': True,
            'staff_account_type': staff_account_type,
            'completion_datetime': datetime.now().isoformat(),
            'task_type': task_type
        }
        
        # Get staff name from session using correct session key
        staff_name = session.get('admin_name')
        
        if not staff_name:
            # Try to get staff name from latest assignment in complaint_history
            staff_query = text("""
                SELECT assigned_to FROM complaint_history 
                WHERE complaint_id = :complaint_id 
                AND type_of_action IN ('Inspection', 'Send Invitation')
                ORDER BY action_datetime DESC LIMIT 1
            """)
            staff_result = db.session.execute(staff_query, {'complaint_id': complaint_id})
            staff_row = staff_result.fetchone()
            staff_name = staff_row.assigned_to if staff_row else 'Staff Member'
        
        # Use database NOW() function to get current local time (same as other endpoints)
        # This avoids timezone conversion issues that were causing 8-hour offset
        # The database will handle the timestamp in the correct local timezone
        
        # Debug logging before insertion
        print(f"STAFF COMPLETION DEBUG:")
        print(f"  Complaint ID: {complaint_id}")
        print(f"  Completion Status: {completion_status}")
        print(f"  Staff Name: {staff_name}")
        print(f"  Using NOW() for timestamp to match other endpoints")
        
        # Use raw SQL to insert into complaint_history with proper field names
        # Store all data including task findings in details column as JSON
        # Use NOW() function like other endpoints to get correct local database time
        insert_query = text("""
            INSERT INTO complaint_history (complaint_id, type_of_action, assigned_to, details, action_datetime)
            VALUES (:complaint_id, :completion_status, :staff_name, :details, NOW())
        """)
        
        db.session.execute(insert_query, {
            'complaint_id': complaint_id,
            'completion_status': completion_status,
            'staff_name': staff_name,
            'details': json.dumps(completion_details)
        })
        
        print(f"  Successfully inserted completion record using NOW() timestamp")
        
        # Update complaint stage based on completion type
        # Keep complaint status as 'Ongoing' for all task types - staff completion only affects timeline
        # The complaint_stage should remain 'Ongoing' until admin explicitly resolves it
        new_stage = 'Ongoing'
        
        update_complaint_query = text("""
            UPDATE complaints 
            SET complaint_stage = :stage
            WHERE complaint_id = :complaint_id
        """)
        
        db.session.execute(update_complaint_query, {
            'complaint_id': complaint_id,
            'stage': new_stage
        })
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'{task_description.title()} completed successfully',
            'complaint_id': complaint_id,
            'status': completion_status
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error completing staff task: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@complaints_bp.route('/api/timeline_entry/<int:history_id>', methods=['GET'])
def get_timeline_entry(history_id):
    """Get detailed timeline entry for preview modal"""
    try:
        # Query the specific timeline entry
        query = text("""
            SELECT 
                ch.history_id,
                ch.complaint_id,
                ch.type_of_action,
                ch.assigned_to,
                ch.action_datetime,
                ch.details
            FROM complaint_history ch
            WHERE ch.history_id = :history_id
        """)
        
        result = db.session.execute(query, {'history_id': history_id})
        entry = result.fetchone()
        
        if not entry:
            return jsonify({
                'success': False,
                'error': 'Timeline entry not found'
            }), 404
        
        # Convert to dictionary
        entry_data = {
            'history_id': entry.history_id,
            'complaint_id': entry.complaint_id,
            'type_of_action': entry.type_of_action,
            'assigned_to': entry.assigned_to,
            'action_datetime': entry.action_datetime.isoformat() if entry.action_datetime else '',
            'details': entry.details,
            'description': ''
        }
        
        # Parse details to extract description if available
        if entry.details:
            try:
                import json
                details_dict = json.loads(entry.details) if isinstance(entry.details, str) else entry.details
                entry_data['description'] = details_dict.get('description', '')
            except (json.JSONDecodeError, TypeError):
                pass
        
        return jsonify({
            'success': True,
            'entry': entry_data
        })
        
    except Exception as e:
        print(f"Error fetching timeline entry {history_id}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def format_complainant_name(first_name, middle_name, last_name, suffix):
    """Format complainant name as 'FirstName M. LastName, Suffix'"""
    name_parts = []
    
    if first_name:
        name_parts.append(first_name.strip())
    
    if middle_name:
        middle_initial = middle_name.strip()[:1] + "." if middle_name.strip() else ""
        if middle_initial:
            name_parts.append(middle_initial)
    
    if last_name:
        name_parts.append(last_name.strip())
    
    formatted_name = " ".join(name_parts)
    
    if suffix and suffix.strip():
        formatted_name += f", {suffix.strip()}"
    
    return formatted_name

def format_address(area_name, lot_no, block_no):
    """Format address as 'Lot X, Block Y, Area Name'"""
    address_parts = []
    
    if lot_no:
        address_parts.append(f"Lot {lot_no}")
    
    if block_no:
        address_parts.append(f"Block {block_no}")
    
    if area_name:
        address_parts.append(area_name)
    
    return ", ".join(address_parts)

@complaints_bp.route('/api/report_summary', methods=['GET'])
def api_report_summary():
    """Return monthly (or date-range) report stats and a narrative summary for the admin report.

    Query params:
      - year: int (required if month provided)
      - month: int (1-12) optional; if omitted, computes for whole year
      - start: ISO date (YYYY-MM-DD) optional; overrides month/year if provided
      - end: ISO date (YYYY-MM-DD) optional; overrides month/year if provided
    """
    try:
        # Determine date range
        year = request.args.get('year', type=int)
        month = request.args.get('month', type=int)
        start_param = request.args.get('start')
        end_param = request.args.get('end')

        if start_param and end_param:
            start_dt = datetime.strptime(start_param, '%Y-%m-%d')
            end_dt = datetime.strptime(end_param, '%Y-%m-%d')
            # include full end day
            end_dt = datetime(end_dt.year, end_dt.month, end_dt.day, 23, 59, 59)
        elif year and month:
            from calendar import monthrange
            start_dt = datetime(year, month, 1, 0, 0, 0)
            last_day = monthrange(year, month)[1]
            end_dt = datetime(year, month, last_day, 23, 59, 59)
        elif year:
            start_dt = datetime(year, 1, 1, 0, 0, 0)
            end_dt = datetime(year, 12, 31, 23, 59, 59)
        else:
            # default to current month
            now = datetime.now()
            from calendar import monthrange
            start_dt = datetime(now.year, now.month, 1, 0, 0, 0)
            last_day = monthrange(now.year, now.month)[1]
            end_dt = datetime(now.year, now.month, last_day, 23, 59, 59)

        # 1) Complaints received in period
        complaints_query = text(
            """
            SELECT 
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'Valid' THEN 1 ELSE 0 END) AS valid,
                SUM(CASE WHEN status = 'Invalid' THEN 1 ELSE 0 END) AS invalid
            FROM complaints
            WHERE date_received BETWEEN :start_dt AND :end_dt
            """
        )
        comp_row = db.session.execute(complaints_query, { 'start_dt': start_dt, 'end_dt': end_dt }).fetchone()
        complaints_received = int(comp_row.total or 0)
        complaints_valid = int(comp_row.valid or 0)
        complaints_invalid = int(comp_row.invalid or 0)

        # 2) Actions in complaint_history in period, grouped by type
        actions_query = text(
            """
            SELECT type_of_action, details
            FROM complaint_history
            WHERE action_datetime BETWEEN :start_dt AND :end_dt
            """
        )
        action_rows = db.session.execute(actions_query, { 'start_dt': start_dt, 'end_dt': end_dt }).fetchall()

        action_counts = {}
        individuals_summoned = 0
        inspections_required = 0
        cases_settled = 0

        for row in action_rows:
            atype = (row.type_of_action or '').strip()
            action_counts[atype] = action_counts.get(atype, 0) + 1

            # invitations: count individuals from details['to']
            if atype in ('Invitation', 'Send Invitation', 'Sent Invitation', 'Accepted Invitation'):
                try:
                    details = row.details
                    if isinstance(details, str):
                        details = json.loads(details)
                    if isinstance(details, dict):
                        to_field = details.get('to')
                        if isinstance(to_field, str):
                            people = [p.strip() for p in to_field.split(',') if p.strip()]
                            individuals_summoned += len(people)
                        elif isinstance(to_field, list):
                            individuals_summoned += len([p for p in to_field if str(p).strip()])
                except Exception:
                    pass

            # inspections assigned or done
            if atype in ('Inspection', 'Inspection done'):
                inspections_required += 1

            # resolved
            if atype == 'Resolved':
                cases_settled += 1

        # Mediation/hearing: treat 'Mediation' actions as hearings
        mediations = action_counts.get('Mediation', 0)

        # 3) Build narrative
        # Basic total activities: count of complaint_history rows in period
        total_activities = len(action_rows)

        # Month/Year label
        period_label = (
            f"{start_dt.strftime('%B %Y')}" if (start_dt.month == end_dt.month and start_dt.year == end_dt.year)
            else f"{start_dt.strftime('%b %d, %Y')} - {end_dt.strftime('%b %d, %Y')}"
        )

        narrative = (
            f"The Accomplishment Report for {period_label} provides a detailed overview of activities and achievements in governance, community service, and housing. "
            f"A total of {total_activities} actions were recorded in the period, reflecting sustained engagement across complaints handling and field operations. "
            f"A total of {complaints_received} complaints were received, of which {complaints_valid} were validated and {complaints_invalid} were marked invalid. "
            f"Mediation and hearings: {mediations} mediation-related actions were conducted. "
            f"Invitations issued summoned approximately {individuals_summoned} individual(s) to hearings and meetings. "
            f"Inspections: {inspections_required} inspection-related actions were recorded for site validation and boundary identification. "
            f"Resolved cases: {cases_settled} complaint(s) reached a resolution during this period."
        )

        return jsonify({
            'success': True,
            'period': {
                'start': start_dt.isoformat(),
                'end': end_dt.isoformat(),
                'label': period_label,
            },
            'counts': {
                'total_activities': total_activities,
                'complaints_received': complaints_received,
                'complaints_valid': complaints_valid,
                'complaints_invalid': complaints_invalid,
                'mediations': mediations,
                'individuals_summoned': individuals_summoned,
                'inspections': inspections_required,
                'resolved': cases_settled,
                'by_action': action_counts,
            },
            'narrative': narrative,
        })
    except Exception as e:
        print(f"Error in report summary: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

def get_complaint_data_with_proper_areas(status_filter=None, stage_filter=None, assigned_filter=None):
    """NEW: Get complaint data with proper area joins - DEBUGGING VERSION"""
    try:
        # Enhanced query that gets both latest action details AND invitation details for meeting info
        query = """
        SELECT 
            c.complaint_id,
            c.type_of_complaint,
            c.priority_level,
            c.status,
            c.complaint_stage,
            c.date_received,
            c.description,
            c.complainant_name,
            c.address,
            c.area_id,
            COALESCE(r.lot_no, 0) as lot_no,
            COALESCE(r.block_no, 0) as block_no,
            COALESCE(a.area_name, 'N/A') as area_name,
            ch_latest.assigned_to,
            ch_latest.action_datetime,
            ch_latest.type_of_action as latest_action,
            ch_latest.details,
            ch_invitation.details as invitation_details,
            ch_inspection.details as inspection_details        FROM complaints c
        LEFT JOIN registration r ON c.registration_id = r.registration_id
        LEFT JOIN areas a ON c.area_id = a.area_id
        LEFT JOIN (
            SELECT 
                ch1.complaint_id,
                ch1.assigned_to,
                ch1.action_datetime,
                ch1.type_of_action,
                ch1.details,
                ROW_NUMBER() OVER (PARTITION BY ch1.complaint_id ORDER BY ch1.action_datetime DESC) as rn
            FROM complaint_history ch1
        ) ch_latest ON c.complaint_id = ch_latest.complaint_id AND ch_latest.rn = 1
        LEFT JOIN (
            SELECT 
                ch2.complaint_id,
                ch2.details,
                ROW_NUMBER() OVER (PARTITION BY ch2.complaint_id ORDER BY ch2.action_datetime DESC) as rn
            FROM complaint_history ch2
            WHERE ch2.type_of_action = 'Invitation'
        ) ch_invitation ON c.complaint_id = ch_invitation.complaint_id AND ch_invitation.rn = 1
        LEFT JOIN (
            SELECT 
                chi.complaint_id,
                chi.details,
                ROW_NUMBER() OVER (PARTITION BY chi.complaint_id ORDER BY chi.action_datetime DESC) as rn
            FROM complaint_history chi
            WHERE chi.type_of_action = 'Inspection'
        ) ch_inspection ON c.complaint_id = ch_inspection.complaint_id AND ch_inspection.rn = 1
        """
        
        params = {}
        where_clauses = []
        
        if status_filter:
            if status_filter == 'valid':
                where_clauses.append("c.status = 'Valid'")
            elif status_filter == 'invalid':
                where_clauses.append("(c.status = 'Invalid' OR c.complaint_stage = 'Out of Jurisdiction')")
        
        if stage_filter:
            if stage_filter == 'Pending':
                # For pending complaints, ensure no actions have been taken yet
                where_clauses.append("c.complaint_stage = :stage AND c.status = 'Valid' AND ch_latest.complaint_id IS NULL")
            else:
                where_clauses.append("c.complaint_stage = :stage AND c.status = 'Valid'")
            params['stage'] = stage_filter
        
        if assigned_filter:
            where_clauses.append("ch_latest.assigned_to = :assigned_to")
            params['assigned_to'] = assigned_filter
        
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        
        query += " ORDER BY c.date_received DESC"
        
        print(f"[DEBUG NEW] Executing query: {query}")
        print(f"[DEBUG NEW] With params: {params}")
        result = db.session.execute(text(query), params)
        complaints = result.fetchall()
        print(f"[DEBUG NEW] Raw query returned {len(complaints)} rows")
        
        # Debug first few complaints to see area data
        for i, complaint in enumerate(complaints[:3]):
            print(f"[DEBUG NEW] Complaint {i+1}: complaint_id={complaint.complaint_id}, area_id={complaint.area_id}, area_name='{complaint.area_name}'")
        
        # Format the data
        formatted_complaints = []
        for complaint in complaints:
            # Use address directly from complaints table if available, otherwise format from components
            if complaint.address:
                formatted_address = complaint.address
            else:
                formatted_address = format_address(
                    complaint.area_name,
                    complaint.lot_no,
                    complaint.block_no
                )
            
            # For invalid complaints, set assigned_to and action_datetime to None for N/A display
            if complaint.status == 'Invalid':
                assigned_to = None
                action_datetime = None
                latest_action = 'Invalid'
            else:
                assigned_to = complaint.assigned_to
                action_datetime = complaint.action_datetime
                latest_action = complaint.latest_action or 'Pending'
            
            # Parse details JSON to extract admin-set deadlines and meeting info
            details = {}
            if complaint.details:
                try:
                    if isinstance(complaint.details, str):
                        details = json.loads(complaint.details)
                    else:
                        details = complaint.details
                except (json.JSONDecodeError, TypeError):
                    details = {}
            
            # Parse invitation details to get meeting date/time for "Accepted Invitation" cases
            invitation_details = {}
            if hasattr(complaint, 'invitation_details') and complaint.invitation_details:
                try:
                    if isinstance(complaint.invitation_details, str):
                        invitation_details = json.loads(complaint.invitation_details)
                    else:
                        invitation_details = complaint.invitation_details
                except (json.JSONDecodeError, TypeError):
                    invitation_details = {}
            
            # For "Accepted Invitation", prefer meeting details from invitation_details
            meeting_date = invitation_details.get('meeting_date') or details.get('meeting_date')
            meeting_time = invitation_details.get('meeting_time') or details.get('meeting_time')

            # Extract explicit inspection deadline from the latest Inspection action (if present)
            inspection_details = {}
            if hasattr(complaint, 'inspection_details') and complaint.inspection_details:
                try:
                    if isinstance(complaint.inspection_details, str):
                        inspection_details = json.loads(complaint.inspection_details)
                    else:
                        inspection_details = complaint.inspection_details
                except (json.JSONDecodeError, TypeError):
                    inspection_details = {}
            explicit_deadline = inspection_details.get('deadline') or details.get('deadline')
            
            formatted_complaints.append({
                'complaint_id': complaint.complaint_id,
                'type_of_complaint': complaint.type_of_complaint,
                'complainant_name': complaint.complainant_name or 'N/A',
                'address': formatted_address,
                'area_name': complaint.area_name or 'N/A',  # ADD THIS LINE - Include area_name in JSON response
                'priority_level': complaint.priority_level or 'Minor',
                'status': complaint.status,
                'complaint_stage': complaint.complaint_stage,
                'date_received': complaint.date_received.isoformat() if complaint.date_received else '',
                'description': complaint.description or '',
                'assigned_to': assigned_to,
                'action_datetime': action_datetime.isoformat() if action_datetime else None,
                'latest_action': latest_action,
                'action_needed': latest_action,  # For backward compatibility
                # Admin-set deadline information
                'deadline': explicit_deadline,
                'meeting_date': meeting_date,
                'meeting_time': meeting_time
            })
        
        return formatted_complaints
        
    except Exception as e:
        print(f"Error getting complaint data: {e}")
        return []

def get_complaint_data(status_filter=None, stage_filter=None, assigned_filter=None):
    """Get complaint data with proper joins and formatting including complaint_history"""
    try:
        # Enhanced query that gets both latest action details AND invitation details for meeting info
        query = """
        SELECT 
            c.complaint_id,
            c.type_of_complaint,
            c.priority_level,
            c.status,
            c.complaint_stage,
            c.date_received,
            c.description,
            c.complainant_name,
            c.address,
            COALESCE(r.lot_no, 0) as lot_no,
            COALESCE(r.block_no, 0) as block_no,
            COALESCE(a.area_name, 'N/A') as area_name,
            ch_latest.assigned_to,
            ch_latest.action_datetime,
            ch_latest.type_of_action as latest_action,
            ch_latest.details,
            ch_invitation.details as invitation_details
        FROM complaints c
        LEFT JOIN registration r ON c.registration_id = r.registration_id
        LEFT JOIN areas a ON c.area_id = a.area_id
        LEFT JOIN (
            SELECT 
                ch1.complaint_id,
                ch1.assigned_to,
                ch1.action_datetime,
                ch1.type_of_action,
                ch1.details,
                ROW_NUMBER() OVER (PARTITION BY ch1.complaint_id ORDER BY ch1.action_datetime DESC) as rn
            FROM complaint_history ch1
        ) ch_latest ON c.complaint_id = ch_latest.complaint_id AND ch_latest.rn = 1
        LEFT JOIN (
            SELECT 
                ch2.complaint_id,
                ch2.details,
                ROW_NUMBER() OVER (PARTITION BY ch2.complaint_id ORDER BY ch2.action_datetime DESC) as rn
            FROM complaint_history ch2
            WHERE ch2.type_of_action = 'Invitation'
        ) ch_invitation ON c.complaint_id = ch_invitation.complaint_id AND ch_invitation.rn = 1
        """
        
        params = {}
        where_clauses = []
        
        if status_filter:
            if status_filter == 'valid':
                where_clauses.append("c.status = 'Valid'")
            elif status_filter == 'invalid':
                where_clauses.append("(c.status = 'Invalid' OR c.complaint_stage = 'Out of Jurisdiction')")
        
        if stage_filter:
            if stage_filter in ['Pending', 'Ongoing', 'Resolved']:
                where_clauses.append("c.complaint_stage = :stage AND c.status = 'Valid'")
                params['stage'] = stage_filter
        
        if assigned_filter:
            where_clauses.append("ch_latest.assigned_to = :assigned_to")
            params['assigned_to'] = assigned_filter
        
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        
        query += " ORDER BY c.date_received DESC"
        
        print(f"[DEBUG] Executing query: {query}")
        print(f"[DEBUG] With params: {params}")
        result = db.session.execute(text(query), params)
        complaints = result.fetchall()
        print(f"[DEBUG] Raw query returned {len(complaints)} rows")
        
        # Format the data
        formatted_complaints = []
        for complaint in complaints:
            # Use address directly from complaints table if available, otherwise format from components
            if complaint.address:
                formatted_address = complaint.address
            else:
                formatted_address = format_address(
                    complaint.area_name,
                    complaint.lot_no,
                    complaint.block_no
                )
            
            # For invalid complaints, set assigned_to and action_datetime to None for N/A display
            if complaint.status == 'Invalid':
                assigned_to = None
                action_datetime = None
                latest_action = 'Invalid'
            else:
                assigned_to = complaint.assigned_to
                action_datetime = complaint.action_datetime
                latest_action = complaint.latest_action or 'Pending'
            
            # Parse details JSON to extract admin-set deadlines and meeting info
            details = {}
            if complaint.details:
                try:
                    if isinstance(complaint.details, str):
                        details = json.loads(complaint.details)
                    else:
                        details = complaint.details
                except (json.JSONDecodeError, TypeError):
                    details = {}
            
            # Parse invitation details to get meeting date/time for "Accepted Invitation" cases
            invitation_details = {}
            if hasattr(complaint, 'invitation_details') and complaint.invitation_details:
                try:
                    if isinstance(complaint.invitation_details, str):
                        invitation_details = json.loads(complaint.invitation_details)
                    else:
                        invitation_details = complaint.invitation_details
                except (json.JSONDecodeError, TypeError):
                    invitation_details = {}
            
            # For "Accepted Invitation", prefer meeting details from invitation_details
            meeting_date = invitation_details.get('meeting_date') or details.get('meeting_date')
            meeting_time = invitation_details.get('meeting_time') or details.get('meeting_time')
            
            formatted_complaints.append({
                'complaint_id': complaint.complaint_id,
                'type_of_complaint': complaint.type_of_complaint,
                'complainant_name': complaint.complainant_name or 'N/A',
                'address': formatted_address,
                'area_name': complaint.area_name or 'N/A',  # ADD THIS LINE - Include area_name in JSON response
                'priority_level': complaint.priority_level or 'Minor',
                'status': complaint.status,
                'complaint_stage': complaint.complaint_stage,
                'date_received': complaint.date_received.isoformat() if complaint.date_received else '',
                'description': complaint.description or '',
                'assigned_to': assigned_to,
                'action_datetime': action_datetime.isoformat() if action_datetime else None,
                'latest_action': latest_action,
                'action_needed': latest_action,  # For backward compatibility
                # Admin-set deadline information
                'deadline': details.get('deadline'),
                'meeting_date': meeting_date,
                'meeting_time': meeting_time
            })
        
        return formatted_complaints
        
    except Exception as e:
        print(f"Error getting complaint data: {e}")
        return []

# HTML Routes
@complaints_bp.route("/")
def complaints():
    return send_file(os.path.join(frontend_path, "admin", "complaints", "all.html"))

@complaints_bp.route("/all.html")
def complaints_all():
    return send_file(os.path.join(frontend_path, "admin", "complaints", "all.html"))

@complaints_bp.route("/pending.html")
def complaints_pending():
    return send_file(os.path.join(frontend_path, "admin", "complaints", "pending.html"))

@complaints_bp.route("/ongoing.html")
def complaints_ongoing():
    return send_file(os.path.join(frontend_path, "admin", "complaints", "ongoing.html"))

@complaints_bp.route("/resolved.html")
def complaints_resolved():
    return send_file(os.path.join(frontend_path, "admin", "complaints", "resolved.html"))

@complaints_bp.route("/invalid.html")
def complaints_invalid():
    return send_file(os.path.join(frontend_path, "admin", "complaints", "invalid.html"))

@complaints_bp.route("/complaint_details_valid.html")
def complaint_details_valid():
    return send_file(os.path.join(frontend_path, "admin", "complaints", "complaint_details_valid.html"))

@complaints_bp.route("/complaint_details_invalid.html")
def complaint_details_invalid():
    return send_file(os.path.join(frontend_path, "admin", "complaints", "complaint_details_invalid.html"))

@complaints_bp.route("/unresolved.html")
def complaints_unresolved():
    return send_file(os.path.join(frontend_path, "admin", "complaints", "unresolved.html"))

# Staff complaint detail pages
@complaints_bp.route("/staff/complaints/complaint_inspector_valid.html")
def staff_complaint_inspector_valid():
    return send_file(os.path.join(frontend_path, "admin", "staff", "complaints", "complaint_inspector_valid.html"))

@complaints_bp.route("/staff/complaints/complaint_assistant_valid.html")
def staff_complaint_assistant_valid():
    return send_file(os.path.join(frontend_path, "admin", "staff", "complaints", "complaint_assistant_valid.html"))

# API Routes for Admin
@complaints_bp.route('/api/all', methods=['GET'])
def get_all_complaints():
    """Get all valid complaints for admin"""
    try:
        # Check if user is admin - TEMPORARILY DISABLED FOR TESTING
        # if session.get('account') != 1:
        #     return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        print("[DEBUG] Getting all complaints...")
        
        # FIXED QUERY - Using proper complaint_history joins to get assigned_to, latest_action, and deadline
        complaints_query = """
        SELECT 
            c.complaint_id,
            c.type_of_complaint,
            c.priority_level,
            c.status,
            c.complaint_stage,
            c.date_received,
            c.description,
            c.complainant_name,
            c.address,
            COALESCE(a.area_name, 'N/A') as area_name,
            ch_latest.assigned_to,
            ch_latest.action_datetime,
            ch_latest.type_of_action as latest_action,
            ch_latest.details as ch_latest_details
        FROM complaints c
        LEFT JOIN areas a ON c.area_id = a.area_id
        LEFT JOIN (
            SELECT 
                ch1.complaint_id,
                ch1.assigned_to,
                ch1.action_datetime,
                ch1.type_of_action,
                ch1.details,
                ROW_NUMBER() OVER (PARTITION BY ch1.complaint_id ORDER BY ch1.action_datetime DESC) as rn
            FROM complaint_history ch1
            WHERE ch1.type_of_action != 'Submitted'
        ) ch_latest ON c.complaint_id = ch_latest.complaint_id AND ch_latest.rn = 1
        ORDER BY c.date_received DESC
        """
        
        result = db.session.execute(text(complaints_query))
        complaints_data = result.fetchall()
        print(f"[DEBUG] Found {len(complaints_data)} complaints in database")
        
        # Format the data with proper complaint_history information
        formatted_complaints = []
        for complaint in complaints_data:
            # For invalid complaints, set assigned_to and action_datetime to None for N/A display
            if complaint.status == 'Invalid':
                assigned_to = None
                action_datetime = None
                latest_action = 'Invalid'
                deadline = None
            else:
                assigned_to = complaint.assigned_to
                action_datetime = complaint.action_datetime
                # Use latest_action from complaint_history, or fallback to complaint_stage
                latest_action = complaint.latest_action or complaint.complaint_stage or 'Pending'
                
                # Extract deadline from complaint_history details if available
                deadline = None
                if complaint.ch_latest_details:
                    try:
                        if isinstance(complaint.ch_latest_details, str):
                            details = json.loads(complaint.ch_latest_details)
                        else:
                            details = complaint.ch_latest_details
                        
                        # Try to get deadline from nested details first, then fallback to root level
                        if 'details' in details and isinstance(details['details'], dict):
                            deadline = details['details'].get('deadline')
                        if not deadline:
                            deadline = details.get('deadline')
                    except (json.JSONDecodeError, TypeError):
                        deadline = None
            
            formatted_complaints.append({
                'complaint_id': complaint.complaint_id,
                'type_of_complaint': complaint.type_of_complaint,
                'complainant_name': complaint.complainant_name or 'N/A',
                'address': complaint.address or 'N/A',
                'area_name': complaint.area_name or 'N/A',
                'priority_level': complaint.priority_level or 'Minor',
                'status': complaint.status,
                'complaint_stage': complaint.complaint_stage,
                'date_received': complaint.date_received.isoformat() if complaint.date_received else '',
                'description': complaint.description or '',
                'assigned_to': assigned_to,
                'action_datetime': action_datetime.isoformat() if action_datetime else None,
                'latest_action': latest_action,
                'action_needed': latest_action,  # For backward compatibility
                'deadline': deadline
            })
        
        print(f"[DEBUG] Returning {len(formatted_complaints)} formatted complaints")
        
        response = jsonify(formatted_complaints)
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    
    except Exception as e:
        print(f"[DEBUG] Exception in get_all_complaints: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

@complaints_bp.route('/api/pending', methods=['GET'])
def get_pending_complaints():
    """Get pending complaints for admin"""
    try:
        # Check if user is admin - TEMPORARILY DISABLED FOR TESTING
        # if session.get('account') != 1:
        #     return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        complaints = get_complaint_data_with_proper_areas(stage_filter='Pending')
        
        response = jsonify(complaints)
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@complaints_bp.route('/api/ongoing', methods=['GET'])
def get_ongoing_complaints():
    """Get ongoing complaints for admin"""
    try:
        # Check if user is admin - TEMPORARILY DISABLED FOR TESTING
        # if session.get('account') != 1:
        #     return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        print("[DEBUG] Getting ongoing complaints...")
        
        # Use the same query as /api/all but filter for Ongoing stage
        complaints_query = """
        SELECT 
            c.complaint_id,
            c.type_of_complaint,
            c.priority_level,
            c.status,
            c.complaint_stage,
            c.date_received,
            c.description,
            c.complainant_name,
            c.address,
            COALESCE(a.area_name, 'N/A') as area_name,
            ch_latest.assigned_to,
            ch_latest.action_datetime,
            ch_latest.type_of_action as latest_action,
            ch_latest.details as ch_latest_details
        FROM complaints c
        LEFT JOIN areas a ON c.area_id = a.area_id
        LEFT JOIN (
            SELECT 
                ch1.complaint_id,
                ch1.assigned_to,
                ch1.action_datetime,
                ch1.type_of_action,
                ch1.details,
                ROW_NUMBER() OVER (PARTITION BY ch1.complaint_id ORDER BY ch1.action_datetime DESC) as rn
            FROM complaint_history ch1
        ) ch_latest ON c.complaint_id = ch_latest.complaint_id AND ch_latest.rn = 1
        WHERE c.status = 'Valid' AND c.complaint_stage = 'Ongoing'
        ORDER BY c.date_received DESC
        """
        
        result = db.session.execute(text(complaints_query))
        complaints = result.fetchall()
        
        formatted_complaints = []
        for complaint in complaints:
            # Default values
            assigned_to = 'N/A'
            action_datetime = None
            latest_action = complaint.complaint_stage or 'Pending'
            
            # Use data from complaint_history if available
            if hasattr(complaint, 'assigned_to') and complaint.assigned_to:
                assigned_to = complaint.assigned_to
                action_datetime = complaint.action_datetime
                # Use latest_action from complaint_history, or fallback to complaint_stage
                latest_action = complaint.latest_action or complaint.complaint_stage or 'Pending'
                
                # Extract deadline, meeting_date, and meeting_time from complaint_history details if available
                deadline = None
                meeting_date = None
                meeting_time = None
                if complaint.ch_latest_details:
                    try:
                        if isinstance(complaint.ch_latest_details, str):
                            details = json.loads(complaint.ch_latest_details)
                        else:
                            details = complaint.ch_latest_details
                        
                        print(f"[ONGOING] 📊 Processing complaint {complaint.complaint_id} details: {details}")
                        
                        # Try to get deadline from nested details first, then fallback to root level
                        if 'details' in details and isinstance(details['details'], dict):
                            deadline = details['details'].get('deadline')
                            meeting_date = details['details'].get('meeting_date')
                            meeting_time = details['details'].get('meeting_time')
                        if not deadline:
                            deadline = details.get('deadline')
                        if not meeting_date:
                            meeting_date = details.get('meeting_date')
                        if not meeting_time:
                            meeting_time = details.get('meeting_time')
                            
                        print(f"[ONGOING] 📊 Extracted data for complaint {complaint.complaint_id}:")
                        print(f"[ONGOING] 📊   - deadline: {deadline}")
                        print(f"[ONGOING] 📊   - meeting_date: {meeting_date}")
                        print(f"[ONGOING] 📊   - meeting_time: {meeting_time}")
                        print(f"[ONGOING] 📊   - latest_action: {latest_action}")
                            
                    except (json.JSONDecodeError, TypeError) as e:
                        print(f"[ONGOING] ❌ Error parsing details for complaint {complaint.complaint_id}: {e}")
                        deadline = None
                        meeting_date = None
                        meeting_time = None
            
            formatted_complaints.append({
                'complaint_id': complaint.complaint_id,
                'type_of_complaint': complaint.type_of_complaint,
                'complainant_name': complaint.complainant_name or 'N/A',
                'address': complaint.address or 'N/A',
                'area_name': complaint.area_name or 'N/A',
                'priority_level': complaint.priority_level or 'Minor',
                'status': complaint.status,
                'complaint_stage': complaint.complaint_stage,
                'date_received': complaint.date_received.isoformat() if complaint.date_received else '',
                'description': complaint.description or '',
                'assigned_to': assigned_to,
                'action_datetime': action_datetime.isoformat() if action_datetime else None,
                'latest_action': latest_action,
                'action_needed': latest_action,  # For backward compatibility
                'deadline': deadline,
                'meeting_date': meeting_date,
                'meeting_time': meeting_time
            })
        
        print(f"[DEBUG] Returning {len(formatted_complaints)} ongoing complaints")
        
        response = jsonify(formatted_complaints)
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    
    except Exception as e:
        print(f"[ERROR] Error in get_ongoing_complaints: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@complaints_bp.route('/api/resolved', methods=['GET'])
def get_resolved_complaints():
    """Get resolved complaints for admin"""
    try:
        # Check if user is admin - TEMPORARILY DISABLED FOR TESTING
        # if session.get('account') != 1:
        #     return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        complaints = get_complaint_data_with_proper_areas(stage_filter='Resolved')
        
        response = jsonify(complaints)
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@complaints_bp.route('/api/invalid', methods=['GET'])
def get_invalid_complaints():
    """Get invalid complaints for admin"""
    try:
        # Check if user is admin - TEMPORARILY DISABLED FOR TESTING
        # if session.get('account') != 1:
        #     return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        complaints = get_complaint_data_with_proper_areas(status_filter='invalid')
        
        response = jsonify({'success': True, 'complaints': complaints})
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@complaints_bp.route('/api/unresolved', methods=['GET'])
def get_unresolved_complaints():
    """Get unresolved complaints for admin - complaints that didn't complete the full sequence"""
    try:
        # Check if user is admin - TEMPORARILY DISABLED FOR TESTING
        # if session.get('account') != 1:
        #     return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        # Get complaints that went from Inspection directly to Assessment (skipping Invitation and Mediation)
        query = """
        SELECT 
            c.complaint_id,
            c.type_of_complaint,
            c.priority_level,
            c.status,
            c.complaint_stage,
            c.date_received,
            c.description,
            c.complainant_name,
            c.address,
            COALESCE(r.lot_no, 0) as lot_no,
            COALESCE(r.block_no, 0) as block_no,
            COALESCE(a.area_name, 'N/A') as area_name,
            ch_latest.assigned_to,
            ch_latest.action_datetime,
            ch_latest.type_of_action as latest_action
        FROM complaints c
        LEFT JOIN registration r ON c.registration_id = r.registration_id
        LEFT JOIN areas a ON c.area_id = a.area_id
        LEFT JOIN (
            SELECT 
                ch1.complaint_id,
                ch1.assigned_to,
                ch1.action_datetime,
                ch1.type_of_action,
                ROW_NUMBER() OVER (PARTITION BY ch1.complaint_id ORDER BY ch1.action_datetime DESC) as rn
            FROM complaint_history ch1
        ) ch_latest ON c.complaint_id = ch_latest.complaint_id AND ch_latest.rn = 1
        WHERE (
            (c.status = 'Valid' 
            AND c.complaint_id IN (
                -- Get complaints that have both Inspection and Assessment
                SELECT complaint_id FROM complaint_history WHERE type_of_action = 'Inspection'
                INTERSECT
                SELECT complaint_id FROM complaint_history WHERE type_of_action = 'Assessment'
            )
            AND c.complaint_id NOT IN (
                -- Exclude complaints that have Invitation or Mediation
                SELECT complaint_id FROM complaint_history WHERE type_of_action IN ('Invitation', 'Mediation')
            ))
            OR c.complaint_stage = 'Unresolved'
        )
        ORDER BY c.date_received DESC
        """
        
        result = db.session.execute(text(query))
        complaints_data = result.fetchall()
        
        formatted_complaints = []
        for complaint in complaints_data:
            # Use address directly from complaints table if available, otherwise format from components
            if complaint.address:
                formatted_address = complaint.address
            else:
                formatted_address = format_address(
                    complaint.area_name,
                    complaint.lot_no,
                    complaint.block_no
                )
            
            formatted_complaints.append({
                'complaint_id': complaint.complaint_id,
                'type_of_complaint': complaint.type_of_complaint,
                'complainant_name': complaint.complainant_name or 'N/A',
                'address': formatted_address,
                'area_name': complaint.area_name or 'N/A',  # ADD THIS LINE - Include area_name in JSON response
                'priority_level': complaint.priority_level or 'Minor',
                'status': complaint.status,
                'complaint_stage': complaint.complaint_stage,
                'date_received': complaint.date_received.isoformat() if complaint.date_received else '',
                'description': complaint.description or '',
                'assigned_to': complaint.assigned_to,
                'action_datetime': complaint.action_datetime.isoformat() if complaint.action_datetime else None,
                'latest_action': complaint.latest_action or 'Pending',
                'action_needed': complaint.latest_action or 'Unresolved'
            })
        
        response = jsonify(formatted_complaints)
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@complaints_bp.route('/api/debug/complaints', methods=['GET'])
def debug_complaints():
    """Debug endpoint to check complaint data in database"""
    try:
        # Simple query to count complaints
        count_query = "SELECT COUNT(*) as total FROM complaints"
        count_result = db.session.execute(text(count_query))
        total_complaints = count_result.fetchone().total
        
        # Get sample complaint data
        sample_query = "SELECT complaint_id, type_of_complaint, status, complaint_stage, complainant_name FROM complaints LIMIT 5"
        sample_result = db.session.execute(text(sample_query))
        sample_complaints = sample_result.fetchall()
        
        # Check areas table
        areas_query = "SELECT COUNT(*) as total FROM areas"
        areas_result = db.session.execute(text(areas_query))
        total_areas = areas_result.fetchone().total
        
        return jsonify({
            'success': True,
            'total_complaints': total_complaints,
            'total_areas': total_areas,
            'sample_complaints': [
                {
                    'complaint_id': c.complaint_id,
                    'type_of_complaint': c.type_of_complaint,
                    'status': c.status,
                    'complaint_stage': c.complaint_stage,
                    'complainant_name': c.complainant_name
                } for c in sample_complaints
            ]
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@complaints_bp.route('/api/test/timeline/<int:complaint_id>', methods=['GET'])
def test_timeline_debug(complaint_id):
    """Debug timeline functionality to see what's happening"""
    try:
        print(f"[TIMELINE DEBUG] Testing timeline for complaint {complaint_id}")
        
        # Test if complaint exists
        complaint_query = "SELECT complaint_id, complainant_name, status FROM complaints WHERE complaint_id = :id"
        complaint_result = db.session.execute(text(complaint_query), {'id': complaint_id})
        complaint = complaint_result.fetchone()
        
        if not complaint:
            return jsonify({
                'success': False,
                'error': f'Complaint {complaint_id} not found'
            })
        
        # Test if timeline entries exist with detailed debug info
        timeline_query = """
        SELECT history_id, type_of_action, assigned_to, action_datetime, details
        FROM complaint_history 
        WHERE complaint_id = :id
        ORDER BY action_datetime DESC
        """
        timeline_result = db.session.execute(text(timeline_query), {'id': complaint_id})
        timeline_entries = timeline_result.fetchall()
        
        # Debug the details column specifically
        detailed_entries = []
        for t in timeline_entries:
            entry_debug = {
                'history_id': t.history_id,
                'type_of_action': t.type_of_action,
                'assigned_to': t.assigned_to,
                'action_datetime': t.action_datetime.isoformat() if t.action_datetime else None,
                'details_raw': str(t.details) if t.details else None,
                'details_type': str(type(t.details)),
                'details_length': len(str(t.details)) if t.details else 0
            }
            
            # Try to parse details to see what's causing the issue
            if t.details:
                try:
                    import json
                    if isinstance(t.details, str):
                        parsed = json.loads(t.details)
                        entry_debug['details_parsed'] = parsed
                        entry_debug['details_parsed_type'] = str(type(parsed))
                    else:
                        entry_debug['details_parsed'] = t.details
                        entry_debug['details_parsed_type'] = str(type(t.details))
                except Exception as parse_error:
                    entry_debug['details_parse_error'] = str(parse_error)
            
            detailed_entries.append(entry_debug)
        
        return jsonify({
            'success': True,
            'complaint': {
                'complaint_id': complaint.complaint_id,
                'complainant_name': complaint.complainant_name,
                'status': complaint.status
            },
            'timeline_entries_count': len(timeline_entries),
            'timeline_entries': detailed_entries
        })
        
    except Exception as e:
        print(f"[TIMELINE DEBUG] Exception: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@complaints_bp.route('/api/assigned', methods=['GET'])
def get_assigned_complaints():
    """Get assigned complaints for admin - used for inbox functionality"""
    try:
        # Check if user is admin - TEMPORARILY DISABLED FOR TESTING
        # if session.get('account') != 1:
        #     return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        print("[DEBUG] Getting assigned complaints...")
        
        # Use the same query as /api/all but filter for assigned complaints
        complaints_query = """
        SELECT 
            c.complaint_id,
            c.type_of_complaint,
            c.priority_level,
            c.status,
            c.complaint_stage,
            c.date_received,
            c.description,
            c.complainant_name,
            c.address,
            COALESCE(a.area_name, 'N/A') as area_name,
            ch_latest.assigned_to,
            ch_latest.action_datetime,
            ch_latest.type_of_action as latest_action,
            ch_latest.details as ch_latest_details
        FROM complaints c
        LEFT JOIN areas a ON c.area_id = a.area_id
        LEFT JOIN (
            SELECT 
                ch1.complaint_id,
                ch1.assigned_to,
                ch1.action_datetime,
                ch1.type_of_action,
                ch1.details,
                ROW_NUMBER() OVER (PARTITION BY ch1.complaint_id ORDER BY ch1.action_datetime DESC) as rn
            FROM complaint_history ch1
        ) ch_latest ON c.complaint_id = ch_latest.complaint_id AND ch_latest.rn = 1
        WHERE c.status = 'Valid' 
        AND c.complaint_stage IN ('Pending', 'Ongoing')
        AND ch_latest.assigned_to IS NOT NULL
        ORDER BY c.date_received DESC
        """
        
        result = db.session.execute(text(complaints_query))
        complaints = result.fetchall()
        
        formatted_complaints = []
        for complaint in complaints:
            # Extract deadline from complaint_history details if available
            deadline = None
            if complaint.ch_latest_details:
                try:
                    if isinstance(complaint.ch_latest_details, str):
                        details = json.loads(complaint.ch_latest_details)
                    else:
                        details = complaint.ch_latest_details
                    
                    # Try to get deadline from nested details first, then fallback to root level
                    if 'details' in details and isinstance(details['details'], dict):
                        deadline = details['details'].get('deadline')
                    if not deadline:
                        deadline = details.get('deadline')
                except (json.JSONDecodeError, TypeError):
                    deadline = None
            
            formatted_complaints.append({
                'complaint_id': complaint.complaint_id,
                'type_of_complaint': complaint.type_of_complaint,
                'complainant_name': complaint.complainant_name or 'N/A',
                'address': complaint.address or 'N/A',
                'area_name': complaint.area_name or 'N/A',
                'priority_level': complaint.priority_level or 'Minor',
                'status': complaint.status,
                'complaint_stage': complaint.complaint_stage,
                'date_received': complaint.date_received.isoformat() if complaint.date_received else '',
                'description': complaint.description or '',
                'assigned_to': complaint.assigned_to,
                'action_datetime': complaint.action_datetime.isoformat() if complaint.action_datetime else None,
                'latest_action': complaint.latest_action or complaint.complaint_stage or 'Pending',
                'action_needed': complaint.latest_action or complaint.complaint_stage or 'Pending',
                'deadline': deadline
            })
        
        print(f"[DEBUG] Returning {len(formatted_complaints)} assigned complaints")
        
        response = jsonify(formatted_complaints)
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    
    except Exception as e:
        print(f"[ERROR] Error in get_assigned_complaints: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@complaints_bp.route('/api/<int:complaint_id>/action', methods=['POST'])
def handle_complaint_action(complaint_id):
    """Handle admin actions on complaints"""
    try:
        # Check if user is admin
        if session.get('account_type') != 1:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        data = request.get_json()
        action_type = data.get('action_type')
        assigned_to = data.get('assigned_to')
        description = data.get('description', '')
        
        if not action_type:
            return jsonify({'success': False, 'message': 'Missing action type'}), 400
        
        # Insert into complaint_history with correct column names
        action_details = {
            'description': description,
            'created_by': session.get('name', 'Admin'),
            'action_datetime': datetime.now().isoformat()
        }
        
        insert_query = """
        INSERT INTO complaint_history (complaint_id, assigned_to, type_of_action, details, action_datetime)
        VALUES (:complaint_id, :assigned_to, :type_of_action, :details, NOW())
        """
        
        db.session.execute(text(insert_query), {
            'complaint_id': complaint_id,
            'assigned_to': assigned_to,
            'type_of_action': action_type,
            'details': json.dumps(action_details)
        })
        
        # Update complaint stage based on action
        new_stage = None
        if 'assign' in action_type.lower() or assigned_to:
            new_stage = 'Ongoing'
        elif 'resolved' in action_type.lower():
            new_stage = 'Resolved'
        elif action_type.lower() == 'out of jurisdiction':
            new_stage = 'Out of Jurisdiction'
            # Also update status to Invalid when marked as Out of Jurisdiction
            update_status_query = "UPDATE complaints SET status = 'Invalid' WHERE complaint_id = :complaint_id"
            db.session.execute(text(update_status_query), {'complaint_id': complaint_id})
        # Note: Assessment actions no longer automatically mark complaint as Resolved
        # Only the admin "Resolved" button should move complaints to resolved status
        
        if new_stage:
            update_query = "UPDATE complaints SET complaint_stage = :stage WHERE complaint_id = :complaint_id"
            db.session.execute(text(update_query), {'stage': new_stage, 'complaint_id': complaint_id})
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Action recorded successfully',
            'new_stage': new_stage
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@complaints_bp.route('/api/<int:complaint_id>/resolve', methods=['POST'])
def resolve_complaint(complaint_id):
    """Mark a complaint as resolved"""
    try:
        # Check if user is admin
        if session.get('account_type') != 1:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        admin_name = session.get('admin_name')
        
        # Update complaint stage to resolved
        update_query = "UPDATE complaints SET complaint_stage = 'Resolved' WHERE complaint_id = :complaint_id"
        db.session.execute(text(update_query), {'complaint_id': complaint_id})
        
        # Insert history record with correct column names
        resolution_details = {
            'description': f'Complaint marked as resolved by {admin_name}',
            'created_by': admin_name,
            'resolution_datetime': datetime.now().isoformat()
        }
        
        insert_query = """
        INSERT INTO complaint_history (complaint_id, type_of_action, assigned_to, details, action_datetime)
        VALUES (:complaint_id, 'Resolved', :assigned_to, :details, NOW())
        """
        
        db.session.execute(text(insert_query), {
            'complaint_id': complaint_id,
            'assigned_to': admin_name,
            'details': json.dumps(resolution_details)
        })
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Complaint resolved successfully'
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@complaints_bp.route('/api/<int:complaint_id>/unresolve', methods=['POST'])
def unresolve_complaint(complaint_id):
    """Mark a complaint as unresolved"""
    try:
        # Check if user is admin
        if session.get('account_type') != 1:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        admin_name = session.get('admin_name')
        
        # Update complaint stage to unresolved
        update_query = "UPDATE complaints SET complaint_stage = 'Unresolved' WHERE complaint_id = :complaint_id"
        db.session.execute(text(update_query), {'complaint_id': complaint_id})
        
        # Insert history record with correct column names
        unresolve_details = {
            'description': f'Complaint marked as unresolved by {admin_name}',
            'created_by': admin_name,
            'unresolve_datetime': datetime.now().isoformat()
        }
        
        insert_query = """
        INSERT INTO complaint_history (complaint_id, type_of_action, assigned_to, details, action_datetime)
        VALUES (:complaint_id, 'Unresolved', :assigned_to, :details, NOW())
        """
        
        db.session.execute(text(insert_query), {
            'complaint_id': complaint_id,
            'assigned_to': admin_name,
            'details': json.dumps(unresolve_details)
        })
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Complaint marked as unresolved successfully'
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@complaints_bp.route('/api/stats', methods=['GET'])
def get_admin_complaint_stats():
    """Get complaint statistics for admin"""
    try:
        # TEMPORARILY DISABLED FOR TESTING
        # if session.get('account') != 1:
        #     return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        print("[DEBUG] Getting complaint stats...")
        stats_query = """
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN complaint_stage = 'Pending' AND status = 'Valid' THEN 1 ELSE 0 END) as pending,
            SUM(CASE WHEN complaint_stage = 'Ongoing' AND status = 'Valid' THEN 1 ELSE 0 END) as ongoing,
            SUM(CASE WHEN complaint_stage = 'Resolved' AND status = 'Valid' THEN 1 ELSE 0 END) as resolved,
            SUM(CASE WHEN status = 'Invalid' THEN 1 ELSE 0 END) as unresolved,
            SUM(CASE WHEN status = 'Valid' THEN 1 ELSE 0 END) as valid,
            SUM(CASE WHEN status = 'Invalid' THEN 1 ELSE 0 END) as invalid
        FROM complaints
        """
        
        result = db.session.execute(text(stats_query))
        stats = result.fetchone()
        print(f"[DEBUG] Stats result: total={stats.total}, pending={stats.pending}, ongoing={stats.ongoing}, resolved={stats.resolved}, unresolved={stats.unresolved}")
        
        response = jsonify({
            'total': stats.total or 0,
            'pending': stats.pending or 0,
            'ongoing': stats.ongoing or 0,
            'resolved': stats.resolved or 0,
            'unresolved': stats.unresolved or 0,
            'valid': stats.valid or 0,
            'invalid': stats.invalid or 0
        })
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@complaints_bp.route("/api/complaint/<int:complaint_id>")
def api_complaint_details(complaint_id):
    """Get detailed complaint information"""
    try:
        # Check if user is admin or staff
        if session.get('account_type') not in [1, 2]:
            return jsonify({'error': 'Unauthorized'}), 403
            
        query = """
        SELECT 
            c.*,
            r.first_name,
            r.middle_name,
            r.last_name,
            r.suffix,
            r.lot_no,
            b.block_no,
            a.area_name,
            ch.assigned_to,
            ch.type_of_action,
            ch.details as action_description,
            ch.action_datetime as action_date,
            ch.assigned_to as created_by
        FROM complaints c
        LEFT JOIN registration r ON c.complainant_name = CONCAT(r.first_name, ' ', IFNULL(CONCAT(LEFT(r.middle_name, 1), '. '), ''), r.last_name, IFNULL(CONCAT(', ', r.suffix), ''))
        LEFT JOIN areas a ON r.area_id = a.area_id  
        LEFT JOIN blocks b ON r.block_id = b.block_id
        LEFT JOIN complaint_history ch ON c.complaint_id = ch.complaint_id
        WHERE c.complaint_id = :complaint_id
        ORDER BY ch.action_datetime DESC
        """
        
        result = db.session.execute(text(query), {'complaint_id': complaint_id})
        complaint_data = result.fetchall()
        
        if not complaint_data:
            return jsonify({'error': 'Complaint not found'}), 404
        
        # Get the first row for basic complaint info
        complaint = complaint_data[0]
        
        formatted_name = format_complainant_name(
            complaint.first_name,
            complaint.middle_name, 
            complaint.last_name,
            complaint.suffix
        )
        
        formatted_address = format_address(
            complaint.area_name,
            complaint.lot_no,
            complaint.block_no
        )
        
        # Get all actions/history
        actions = []
        for row in complaint_data:
            if row.action_type:
                actions.append({
                    'action_type': row.action_type,
                    'description': row.action_description,
                    'assigned_to': row.assigned_to,
                    'date_created': row.action_date.strftime('%Y-%m-%d %H:%M:%S') if row.action_date else '',
                    'created_by': row.created_by
                })
        
        result_data = {
            'complaint_id': complaint.complaint_id,
            'type_of_complaint': complaint.type_of_complaint,
            'complainant_name': formatted_name,
            'address': formatted_address,
            'priority_level': complaint.priority_level,
            'status': complaint.status,
            'complaint_stage': complaint.complaint_stage,
            'date_received': complaint.date_received.strftime('%Y-%m-%d %H:%M:%S') if complaint.date_received else '',
            'description': complaint.description,
            'actions': actions
        }
        
        response = jsonify(result_data)
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
        
    except Exception as e:
        print(f"Error getting complaint details: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@complaints_bp.route("/api/debug/areas")
def api_debug_areas():
    """Debug endpoint to check area data"""
    try:
        # Check complaints table area_id values
        complaints_query = """
        SELECT complaint_id, area_id, complainant_name 
        FROM complaints 
        ORDER BY complaint_id 
        LIMIT 10
        """
        
        areas_query = """
        SELECT area_id, area_name 
        FROM areas 
        ORDER BY area_id
        """
        
        join_query = """
        SELECT c.complaint_id, c.area_id as complaint_area_id, a.area_id as areas_area_id, a.area_name
        FROM complaints c
        LEFT JOIN areas a ON c.area_id = a.area_id
        ORDER BY c.complaint_id
        LIMIT 10
        """
        
        complaints_result = db.session.execute(text(complaints_query)).fetchall()
        areas_result = db.session.execute(text(areas_query)).fetchall()
        join_result = db.session.execute(text(join_query)).fetchall()
        
        return jsonify({
            'complaints_data': [
                {'complaint_id': row.complaint_id, 'area_id': row.area_id, 'complainant_name': row.complainant_name}
                for row in complaints_result
            ],
            'areas_data': [
                {'area_id': row.area_id, 'area_name': row.area_name}
                for row in areas_result
            ],
            'join_result': [
                {
                    'complaint_id': row.complaint_id, 
                    'complaint_area_id': row.complaint_area_id,
                    'areas_area_id': row.areas_area_id,
                    'area_name': row.area_name
                }
                for row in join_result
            ],
            'summary': {
                'total_complaints': len(complaints_result),
                'total_areas': len(areas_result),
                'successful_joins': len([r for r in join_result if r.area_name is not None]),
                'null_area_ids_in_complaints': len([r for r in complaints_result if r.area_id is None]),
                'null_area_names_in_areas': len([r for r in areas_result if r.area_name is None])
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@complaints_bp.route("/api/staff")
def api_get_staff():
    """Get list of staff members for assignment"""
    try:
        # Debug: print session contents and cookies to help trace 403 issues
        try:
            print('[DEBUG] session keys:', dict(session))
            acct = session.get('account_type')
            print('[DEBUG] session.account_type =', acct, 'type=', type(acct))
            print('[DEBUG] request.cookies =', dict(request.cookies))
        except Exception as _:
            print('[DEBUG] could not stringify session or cookies')

        # Allow admin (1) and staff (2) to access this endpoint.
        # Normalize session account to int when possible to avoid '"1"' vs 1 mismatches.
        acct = session.get('account_type')
        try:
            acct_int = int(acct) if acct is not None else None
        except Exception:
            acct_int = None
        if acct_int not in (1, 2):
            print(f"[DEBUG] Unauthorized access to /api/staff, acct_int={acct_int}")
            return jsonify({'error': 'Unauthorized'}), 403
            
        staff_query = """
        SELECT admin_id, name, employee_id 
        FROM admin 
        WHERE account = 2
        ORDER BY name
        """
        
        result = db.session.execute(text(staff_query))
        staff = result.fetchall()
        
        staff_list = []
        for member in staff:
            staff_list.append({
                'admin_id': member.admin_id,
                'name': member.name,
                'employee_id': member.employee_id
            })
        
        return jsonify(staff_list)
        
    except Exception as e:
        print(f"Error getting staff: {e}")
        return jsonify({'error': 'Internal server error'}), 500
    

@complaints_bp.route("/api/action", methods=['POST'])
def api_add_action():
    try:
        # Skip session authentication for now to avoid 500 errors
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No JSON data received'}), 400

        complaint_id = data.get('complaint_id')
        action_type = data.get('action_type')
        assigned_to = data.get('assigned_to')
        description = data.get('description', '')

        if not complaint_id or not action_type:
            return jsonify({'error': 'Missing required fields: complaint_id and action_type'}), 400

        # Log the received data for debugging
        print(f"Received action data: complaint_id={complaint_id}, action_type={action_type}, assigned_to={assigned_to}")
        print(f"Full payload: {data}")

        # Insert into complaint_history using actual database structure (details JSON field)
        import json
        from datetime import datetime, timedelta
        
        # Get account type for restrictions (temporarily use 1 for admin, 2 for staff)
        account_type = session.get('account_type', 1)  # Default to admin if not set
        
        # #restrict actions
        # if account_type == 1 and action_type not in ["Assessment", "Mediation"]:
        #     return jsonify({'error': 'Admins can only add Assessment or Mediation'}), 403
        # if account_type == 2 and action_type not in ["Inspection", "Invitation"]:
        #     return jsonify({'error': 'Staff can only add Inspection or Invitation'}), 403

        # If frontend provided a nested `details` object, prefer it. Otherwise fall back to flattened keys.
        incoming_details = None
        if isinstance(data.get('details'), dict):
            incoming_details = data.get('details')

        # #build details JSON depending on action type - preserve frontend detail building
        details = {}
        if action_type == "Mediation":
            details = {
                "advisors": data.get("advisors", []),
                "agenda": data.get("agenda"),
                "summary": data.get("summary"),
                "files": data.get("files", []),  # [{filename, type}]
                "assigned_personnel": data.get("assigned_personnel") or data.get('med_assigned_personnel'),
                "parties_involved": data.get("parties_involved", [])
            }
            if (not assigned_to or assigned_to == "System") and details.get('assigned_personnel'):
                assigned_to = details.get('assigned_personnel')
        elif action_type == "Assessment":
            details = {
                "notes": data.get("notes")
            }
        elif action_type == "Inspection":
            details = {
                "deadline": data.get("deadline"),
                "inspector": data.get("inspector"),
                "location": data.get("location"),
                "scope": data.get("scope", []),  
            }
        elif action_type == "Invitation":
            # If frontend passed nested details, use it. Otherwise use flattened keys.
            if incoming_details is not None:
                details = {
                    "to": incoming_details.get("to"),
                    "meeting_date": incoming_details.get("meeting_date"),
                    "meeting_time": incoming_details.get("meeting_time"),
                    "location": incoming_details.get("location"),
                    "agenda": incoming_details.get("agenda")
                }
            else:
                details = {
                    "to": data.get("to"),
                    "meeting_date": data.get("meeting_date"),
                    "meeting_time": data.get("meeting_time"),
                    "location": data.get("location"),
                    "agenda": data.get("agenda")
                }
        elif action_type == "Out of Jurisdiction":
            details = {
                "jurisdiction": data.get("details", {}).get("jurisdiction", ""),
                "notes": data.get("details", {}).get("notes", "")
            }
        
        # Use admin-defined deadline from frontend, with fallback defaults only when not provided
        deadline = details.get('deadline') or data.get('deadline')
        if not deadline:
            action_date = datetime.now()
            if action_type.lower() == 'inspection':
                deadline = (action_date + timedelta(days=3)).strftime('%Y-%m-%d')
            elif action_type.lower() == 'invitation':
                deadline = (action_date + timedelta(days=1)).strftime('%Y-%m-%d')
            elif action_type.lower() == 'mediation':
                deadline = (action_date + timedelta(days=1)).strftime('%Y-%m-%d')
            elif action_type.lower() == 'assessment':
                deadline = (action_date + timedelta(days=1)).strftime('%Y-%m-%d')
        
        print(f"Admin-defined deadline for {action_type}: {deadline}")
        
        # Add deadline to details while preserving all action-specific details
        details['deadline'] = deadline
        
        # Also preserve any additional fields from frontend that weren't captured above
        # Do NOT copy the top-level 'details' key back into details (would create nested duplication)
        excluded = {'complaint_id', 'action_type', 'assigned_to', 'action_datetime', 'description', 'details'}
        for key, value in data.items():
            if key in excluded:
                continue
            # don't overwrite existing meaningful detail keys with None/empty from flattened payload
            if key in details and details.get(key) is not None:
                continue
            if key not in details:
                details[key] = value
        
        details_json = json.dumps(details)
        
        # Insert into complaint_history
        insert_query = """
        INSERT INTO complaint_history 
            (complaint_id, assigned_to, type_of_action, action_datetime, details)
        VALUES (:complaint_id, :assigned_to, :action_type, :action_datetime, :details)
        """

        db.session.execute(text(insert_query), {
            'complaint_id': complaint_id,
            'assigned_to': assigned_to,
            'action_type': action_type,
            'action_datetime': datetime.now(),
            'details': details_json
        })
        
        # Ensure proper ordering by adding a small delay for timeline consistency
        import time
        time.sleep(0.001)  # 1ms delay to ensure distinct timestamps

        # Update complaint stage based on action type
        if action_type.lower() == 'out of jurisdiction':
            update_query = """
            UPDATE complaints
            SET complaint_stage = 'Out of Jurisdiction'
            WHERE complaint_id = :complaint_id
            """
        else:
            update_query = """
            UPDATE complaints
            SET complaint_stage = 'Ongoing'
            WHERE complaint_id = :complaint_id
            """
        db.session.execute(text(update_query), {'complaint_id': complaint_id})

        db.session.commit()
        print(f"Successfully saved action: {action_type} for complaint {complaint_id}")
        return jsonify({'success': True, 'message': f'{action_type} action added successfully'})

    except Exception as e:
        # Rollback any pending transaction so the DB session stays clean
        try:
            db.session.rollback()
        except Exception:
            pass
        print(f"Error saving action: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@complaints_bp.route("/api/resolve", methods=['POST'])
def api_resolve_complaint():
    """Resolve a complaint"""
    try:
        # Check if user is admin
        if session.get('account_type') != 1:
            return jsonify({'error': 'Unauthorized'}), 403
            
        data = request.get_json()
        complaint_id = data.get('complaint_id')
        
        if not complaint_id:
            return jsonify({'error': 'Missing complaint_id'}), 400
        
        # Update complaint stage to Resolved
        update_query = "UPDATE complaints SET complaint_stage = 'Resolved' WHERE complaint_id = :complaint_id"
        db.session.execute(text(update_query), {'complaint_id': complaint_id})
        
        # Add resolution action to history
        insert_query = """
        INSERT INTO complaint_history (complaint_id, type_of_action, assigned_to, details, action_datetime)
        VALUES (:complaint_id, 'Resolved', :assigned_to, :details, NOW())
        """
        
        resolution_details = {
            'description': 'Complaint has been resolved',
            'created_by': session.get('admin_name', 'Admin')
        }
        
        db.session.execute(text(insert_query), {
            'complaint_id': complaint_id,
            'assigned_to': session.get('admin_name', 'Admin'),
            'details': json.dumps(resolution_details)
        })
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Complaint resolved successfully'})
        
    except Exception as e:
        print(f"Error resolving complaint: {e}")
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500

@complaints_bp.route("/api/action_autofill/<int:complaint_id>")
def api_action_autofill(complaint_id):
    """
    Returns data to autofill forms for different action types
    - Invitation: 'to', 'agenda', 'location'
    - Inspection: 'location', 'assigned_personnel', 'block_no', 'lot_no'
    """
    import json

    def safe_parse_name_field(value):
        """Handle names that might be JSON arrays, dicts, or quoted strings with escapes."""
        if not value:
            return ""
        try:
            s = str(value).strip()
            if s.startswith('"') and s.endswith('"'):
                s = s[1:-1]
            s = s.replace('\\"', '"').replace("\\'", "'")
            parsed = json.loads(s)
            # If it's a list, prefer extracting 'name' from dict items, otherwise use string items
            if isinstance(parsed, list):
                names = []
                for item in parsed:
                    if isinstance(item, dict):
                        # Prefer explicit 'name' key
                        if item.get('name'):
                            names.append(str(item.get('name')).strip())
                        else:
                            # Try common name-like keys if present
                            possible = []
                            for k in ('full_name', 'fullname', 'first_name', 'first', 'last_name', 'last'):
                                if item.get(k):
                                    possible.append(str(item.get(k)).strip())
                            if possible:
                                names.append(' '.join(possible))
                    elif isinstance(item, str):
                        if item.strip():
                            names.append(item.strip())
                return ", ".join(names)
            elif isinstance(parsed, dict):
                # Prefer 'name' key in dicts
                if parsed.get('name'):
                    return str(parsed.get('name')).strip()
                # Otherwise join likely name-like fields
                possible = []
                for k in ('full_name', 'fullname', 'first_name', 'first', 'last_name', 'last'):
                    if parsed.get(k):
                        possible.append(str(parsed.get(k)).strip())
                if possible:
                    return ' '.join(possible)
                # Fallback: join all string values (less ideal, but better than raw dict)
                return ", ".join(str(v).strip() for v in parsed.values() if isinstance(v, (str, int, float)) and str(v).strip())
            elif isinstance(parsed, str):
                return parsed.strip()
            return str(parsed)
        except Exception:
            # Final fallback: remove brackets/quotes and attempt to extract quoted substrings
            try:
                cleaned = str(value).replace('[', '').replace(']', '').replace('"', '').strip()
                # If there are multiple quoted names separated by commas, return them cleaned
                return cleaned
            except Exception:
                return str(value).strip()

    try:
        # --- Base complaint info
        complaint = db.session.execute(
            text("""
                SELECT c.complaint_id,
                       c.type_of_complaint,
                       r.first_name,
                       r.middle_name,
                       r.last_name,
                       r.suffix,
                       r.lot_no,
                       r.block_no,
                       a.area_name
                FROM complaints c
                LEFT JOIN registration r ON c.registration_id = r.registration_id
                LEFT JOIN areas a ON c.area_id = a.area_id
                WHERE c.complaint_id = :id
            """),
            {"id": complaint_id}
        ).fetchone()

        if not complaint:
            return jsonify({"error": "Complaint not found"}), 404

        complaint_type = (complaint.type_of_complaint or "").lower().replace(" ", "_")
        complainant_name = f"{complaint.first_name} {complaint.middle_name or ''} {complaint.last_name} {complaint.suffix or ''}".strip()

        autofill_data = {
            "agenda": complaint.type_of_complaint,
            "location": "2nd FLR. USAD-PHASELAD OFFICE, BAYANIHAN BUILDING BARANGAY MAIN",
            "to": complainant_name
        }

        # === LOT DISPUTE ===
        if complaint_type == "lot_dispute":
            lot_dispute = db.session.execute(
                text("SELECT q7 FROM lot_dispute WHERE complaint_id=:id"),
                {"id": complaint_id}
            ).fetchone()
            if lot_dispute:
                other_party = safe_parse_name_field(getattr(lot_dispute, "q7", ""))
                autofill_data["to"] = f"{complainant_name}{', ' + other_party if other_party else ''}"
                autofill_data["inspection_assigned_personnel"] = "Alberto Nonato Jr."

        # === BOUNDARY DISPUTE ===
        elif complaint_type == "boundary_dispute":
            boundary = db.session.execute(
                text("SELECT q12 FROM boundary_dispute WHERE complaint_id=:id"),
                {"id": complaint_id}
            ).fetchone()
            if boundary and getattr(boundary, "q12", None):
                raw = getattr(boundary, "q12")
                try:
                    # Try to parse as JSON if it's a string, otherwise treat as already-parsed
                    q12_list = json.loads(raw) if isinstance(raw, str) else raw
                    if isinstance(q12_list, list):
                        # Accept list items that are dicts with a 'name' key or simple strings
                        names = []
                        for p in q12_list:
                            if isinstance(p, dict) and p.get("name"):
                                names.append(p.get("name"))
                            elif isinstance(p, str) and p.strip():
                                names.append(p.strip())
                        other_parties = ", ".join(names)
                        autofill_data["to"] = f"{complainant_name}{', ' + other_parties if other_parties else ''}"
                    else:
                        # Fallback: try to clean/parse non-JSON strings
                        other_party = safe_parse_name_field(raw)
                        if other_party:
                            autofill_data["to"] = f"{complainant_name}{', ' + other_party if other_party else ''}"
                except Exception:
                    # Final fallback to tolerant parser for odd formats
                    other_party = safe_parse_name_field(raw)
                    if other_party:
                        autofill_data["to"] = f"{complainant_name}{', ' + other_party if other_party else ''}"
                autofill_data["inspection_assigned_personnel"] = "Alberto Nonato Jr."

        # === UNAUTHORIZED OCCUPATION ===
        elif complaint_type == "unauthorized_occupation":
            unauthorized = db.session.execute(
                text("SELECT q2 FROM unauthorized_occupation WHERE complaint_id=:id"),
                {"id": complaint_id}
            ).fetchone()
            if unauthorized and getattr(unauthorized, "q2", None):
                raw = getattr(unauthorized, "q2")
                try:
                    q2_list = json.loads(raw) if isinstance(raw, str) else raw
                    if isinstance(q2_list, list):
                        names = [p.get("name") if isinstance(p, dict) else str(p) for p in q2_list if p]
                        other_parties = ", ".join(names)
                        autofill_data["to"] = f"{complainant_name}{', ' + other_parties if other_parties else ''}"
                except Exception:
                    other_party = safe_parse_name_field(raw)
                    autofill_data["to"] = f"{complainant_name}{', ' + other_party if other_party else ''}"
                autofill_data["inspection_assigned_personnel"] = "Alberto Nonato Jr."

        # === GENERAL FALLBACK: location prettifier ===
        if "inspection_location_pretty" not in autofill_data:
            location_parts = []
            if complaint.area_name:
                location_parts.append(complaint.area_name)
            if complaint.block_no:
                location_parts.append(f"Block {complaint.block_no}")
            if complaint.lot_no:
                location_parts.append(f"Lot {complaint.lot_no}")
            autofill_data["inspection_location_pretty"] = ", ".join(location_parts) or "Barangay Main Office"

        autofill_data.setdefault("inspection_assigned_personnel", "Alberto Nonato Jr.")

        return jsonify(autofill_data)

    except Exception as e:
        print("Autofill error:", str(e))
        return jsonify({"error": str(e)}), 500



def safe_parse_name_field(value):
    """
    Safely parse fields that may be JSON arrays or quoted strings, e.g.
    '["Jaime Aglugub", "Rafael Perez"]' → 'Jaime Aglugub, Rafael Perez'
    """
    if not value:
        return ""
    try:
        s = value.strip()
        # Remove extra quotes if double-encoded
        if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
            s = s[1:-1]
        # Try to parse as JSON
        parsed = json.loads(s)
        if isinstance(parsed, list):
            return ", ".join(str(v).strip() for v in parsed if v)
        elif isinstance(parsed, dict):
            # Just return all dict values joined, if accidentally stored that way
            return ", ".join(str(v).strip() for v in parsed.values() if v)
        else:
            return str(parsed)
    except Exception:
        # If it's not valid JSON, just return it cleaned up
        return str(value).strip()


# Staff API Routes
@complaints_bp.route('/staff/api/stats', methods=['GET'])
def get_staff_stats():
    """Get statistics for staff member"""
    try:
        # Get current staff name from session or use test name for debugging
        staff_name = session.get('name')
        if not staff_name:
            # TEMPORARY: Use test staff name for debugging area_name issue
            staff_name = "Test Staff"
            print(f"[DEBUG] Using test staff name for debugging: {staff_name}")
        
        # Count assigned complaints (currently assigned and not completed)
        assigned_query = """
        SELECT COUNT(DISTINCT c.complaint_id) as count
        FROM complaints c
        LEFT JOIN (
            SELECT 
                ch1.complaint_id,
                ch1.assigned_to,
                ch1.type_of_action,
                ROW_NUMBER() OVER (PARTITION BY ch1.complaint_id ORDER BY ch1.action_datetime DESC) as rn
            FROM complaint_history ch1
        ) ch_latest ON c.complaint_id = ch_latest.complaint_id AND ch_latest.rn = 1
        WHERE ch_latest.assigned_to = :staff_name 
        AND c.status = 'Valid'
        AND c.complaint_stage != 'Resolved'
        AND ch_latest.type_of_action NOT IN ('Inspection done', 'Sent Invitation')
        AND NOT EXISTS (
            SELECT 1 FROM complaint_history ch_completed 
            WHERE ch_completed.complaint_id = c.complaint_id 
            AND (ch_completed.assigned_to = :staff_name OR ch_completed.assigned_to = 'Staff Member')
            AND ch_completed.type_of_action IN ('Inspection done', 'Sent Invitation')
        )
        """
        
        # Count resolved complaints (where staff completed tasks)
        resolved_query = """
        SELECT COUNT(DISTINCT c.complaint_id) as count
        FROM complaints c
        JOIN complaint_history ch ON c.complaint_id = ch.complaint_id
        WHERE (ch.assigned_to = :staff_name OR ch.assigned_to = 'Staff Member')
        AND ch.type_of_action IN ('Inspection done', 'Sent Invitation')
        AND c.status = 'Valid'
        """
        
        assigned_result = db.session.execute(text(assigned_query), {'staff_name': staff_name}).fetchone()
        resolved_result = db.session.execute(text(resolved_query), {'staff_name': staff_name}).fetchone()
        
        return jsonify({
            'success': True,
            'total_assigned': assigned_result.count if assigned_result else 0,
            'resolved': resolved_result.count if resolved_result else 0
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@complaints_bp.route('/staff/api/complaints/assigned', methods=['GET'])
def get_staff_assigned_complaints():
    """Get complaints assigned to the current staff member"""
    try:
        # Get current staff name from session - try multiple session keys for compatibility
        staff_name = session.get('name') or session.get('admin_name')
        print(f"[STAFF ASSIGNED] Session staff name: '{staff_name}'")
        print(f"[STAFF ASSIGNED] Session keys available: {list(session.keys())}")
        
        if not staff_name:
            # TEMPORARY: Use test staff name for debugging area_name issue
            staff_name = "Test Staff"
            print(f"[DEBUG] Using test staff name for debugging: {staff_name}")
        
        # Check what names exist in complaint_history for debugging
        debug_names_query = """
        SELECT DISTINCT assigned_to, COUNT(*) as count
        FROM complaint_history 
        WHERE assigned_to IS NOT NULL AND assigned_to != ''
        GROUP BY assigned_to
        ORDER BY count DESC
        """
        debug_names_result = db.session.execute(text(debug_names_query))
        debug_names = debug_names_result.fetchall()
        print(f"[DEBUG] Available staff names in database: {[f'{row.assigned_to} ({row.count})' for row in debug_names]}")
        
        # Try to find exact or similar match for the staff name
        if staff_name != "Test Staff":
            similar_names = [name.assigned_to for name in debug_names if staff_name.lower() in name.assigned_to.lower() or name.assigned_to.lower() in staff_name.lower()]
            if similar_names:
                print(f"[DEBUG] Similar names found: {similar_names}")
                if staff_name not in [name.assigned_to for name in debug_names]:
                    staff_name = similar_names[0]  # Use the first similar match
                    print(f"[DEBUG] Using similar name match: {staff_name}")
        
        # Simple test query first - get all complaints with areas for this staff member
        test_query = """
        SELECT DISTINCT
            c.complaint_id,
            c.area_id,
            a.area_name,
            c.complainant_name,
            ch.assigned_to
        FROM complaints c
        LEFT JOIN areas a ON c.area_id = a.area_id
        LEFT JOIN complaint_history ch ON c.complaint_id = ch.complaint_id
        WHERE ch.assigned_to = :staff_name
        AND c.status = 'Valid'
        LIMIT 10
        """
        
        # Run test query first
        test_result = db.session.execute(text(test_query), {'staff_name': staff_name})
        test_data = test_result.fetchall()
        
        # If no test data, return empty with debug info
        if not test_data:
            return jsonify({
                'success': True, 
                'complaints': [], 
                'debug': f'No assignments found for staff: {staff_name}',
                'test_data': []
            })
        
        # Main query with proper area join - exclude completed tasks
        query = """
        SELECT DISTINCT
            c.complaint_id,
            c.type_of_complaint,
            c.priority_level,
            c.status,
            c.complaint_stage,
            c.date_received,
            c.description,
            c.complainant_name,
            c.address,
            c.area_id,
            COALESCE(r.lot_no, 0) as lot_no,
            COALESCE(r.block_no, 0) as block_no,
            COALESCE(a.area_name, 'No Area Assigned') as area_name,
            ch_latest.assigned_to,
            ch_latest.action_datetime,
            ch_latest.type_of_action as latest_action
        FROM complaints c
        LEFT JOIN registration r ON c.registration_id = r.registration_id
        LEFT JOIN areas a ON c.area_id = a.area_id
        LEFT JOIN (
            SELECT 
                ch1.complaint_id,
                ch1.assigned_to,
                ch1.action_datetime,
                ch1.type_of_action,
                ROW_NUMBER() OVER (PARTITION BY ch1.complaint_id ORDER BY ch1.action_datetime DESC) as rn
            FROM complaint_history ch1
        ) ch_latest ON c.complaint_id = ch_latest.complaint_id AND ch_latest.rn = 1
        WHERE ch_latest.assigned_to = :staff_name 
        AND c.status = 'Valid'
        AND c.complaint_stage != 'Resolved'
        AND ch_latest.type_of_action NOT IN ('Inspection done', 'Sent Invitation')
        AND NOT EXISTS (
            SELECT 1 FROM complaint_history ch_completed 
            WHERE ch_completed.complaint_id = c.complaint_id 
            AND ch_completed.assigned_to = :staff_name
            AND ch_completed.type_of_action IN ('Inspection done', 'Sent Invitation')
        )
        ORDER BY c.date_received DESC
        """
        
        result = db.session.execute(text(query), {'staff_name': staff_name})
        complaints = result.fetchall()
        
        formatted_complaints = []
        for complaint in complaints:
            # Use address directly from complaints table if available, otherwise format from components
            if complaint.address:
                formatted_address = complaint.address
            else:
                formatted_address = format_address(
                    complaint.area_name,
                    complaint.lot_no,
                    complaint.block_no
                )
            
            # Debug area_name issue
            area_display = complaint.area_name
            if not area_display or area_display == 'N/A':
                area_display = f"area_id:{complaint.area_id}" if hasattr(complaint, 'area_id') else 'No Area Data'
            
            # Extract deadline, meeting_date, and meeting_time from complaint_history details JSON
            deadline = None
            meeting_date = None
            meeting_time = None
            print(f"[STAFF ASSIGNED] 🔍 Extracting deadline for complaint {complaint.complaint_id}")
            try:
                # First try to get deadline from Inspection action (for inspection tasks)
                deadline_query = """
                SELECT details, type_of_action, action_datetime
                FROM complaint_history 
                WHERE complaint_id = :complaint_id 
                AND type_of_action IN ('Inspection', 'Invitation')
                AND details IS NOT NULL 
                ORDER BY action_datetime DESC 
                LIMIT 1
                """
                deadline_result = db.session.execute(text(deadline_query), {'complaint_id': complaint.complaint_id})
                deadline_row = deadline_result.fetchone()
                print(f"[STAFF ASSIGNED] 🔍 Query result for complaint {complaint.complaint_id}: found_row={deadline_row is not None}")
                
                # Special debugging for complaint 272
                if complaint.complaint_id == 272:
                    print(f"[STAFF ASSIGNED] 🎯 COMPLAINT 272 BACKEND DEBUG:")
                    print(f"[STAFF ASSIGNED] 🎯 Running query: {deadline_query}")
                    print(f"[STAFF ASSIGNED] 🎯 Query params: complaint_id={complaint.complaint_id}")
                    
                    # Check ALL complaint_history records for this complaint
                    all_history_query = """
                    SELECT complaint_id, type_of_action, details, action_datetime
                    FROM complaint_history 
                    WHERE complaint_id = :complaint_id 
                    ORDER BY action_datetime DESC
                    """
                    all_history_result = db.session.execute(text(all_history_query), {'complaint_id': complaint.complaint_id})
                    all_history_rows = all_history_result.fetchall()
                    print(f"[STAFF ASSIGNED] 🎯 ALL history records for complaint 272: {len(all_history_rows)} records found")
                    
                    for i, hist_row in enumerate(all_history_rows):
                        print(f"[STAFF ASSIGNED] 🎯   Record {i+1}: type={hist_row.type_of_action}, datetime={hist_row.action_datetime}, has_details={hist_row.details is not None}")
                        if hist_row.details:
                            print(f"[STAFF ASSIGNED] 🎯   Details: {hist_row.details}")
                
                if deadline_row and deadline_row.details:
                    print(f"[STAFF ASSIGNED] 🔍 Raw details for complaint {complaint.complaint_id}: {deadline_row.details}")
                    print(f"[STAFF ASSIGNED] 🔍 Details type: {type(deadline_row.details)}")
                    print(f"[STAFF ASSIGNED] 🔍 Action type: {deadline_row.type_of_action}")
                    
                    # Special debugging for complaint 272
                    if complaint.complaint_id == 272:
                        print(f"[STAFF ASSIGNED] 🎯 COMPLAINT 272 - Found details!")
                        print(f"[STAFF ASSIGNED] 🎯   - Action type: {deadline_row.type_of_action}")
                        print(f"[STAFF ASSIGNED] 🎯   - Raw details: {deadline_row.details}")
                        print(f"[STAFF ASSIGNED] 🎯   - Details length: {len(str(deadline_row.details)) if deadline_row.details else 0}")
                    
                    try:
                        # Handle both string and dict details
                        if isinstance(deadline_row.details, str):
                            details_data = json.loads(deadline_row.details)
                        else:
                            details_data = deadline_row.details
                            
                        print(f"[STAFF ASSIGNED] 🔍 Parsed details data: {details_data}")
                        print(f"[STAFF ASSIGNED] 🔍 Parsed details type: {type(details_data)}")
                        
                        # Special debugging for complaint 272
                        if complaint.complaint_id == 272:
                            print(f"[STAFF ASSIGNED] 🎯 COMPLAINT 272 - Parsed details successfully!")
                            print(f"[STAFF ASSIGNED] 🎯   - Details keys: {list(details_data.keys()) if isinstance(details_data, dict) else 'Not a dict'}")
                            print(f"[STAFF ASSIGNED] 🎯   - Looking for 'deadline' key...")
                        
                        # Try to get deadline from nested details first, then fallback to root level
                        if isinstance(details_data, dict):
                            if 'details' in details_data and isinstance(details_data['details'], dict):
                                nested_details = details_data['details']
                                if 'deadline' in nested_details:
                                    deadline = nested_details['deadline']
                                    print(f"[STAFF ASSIGNED] ✅ Found deadline in nested details: {deadline}")
                                if 'meeting_date' in nested_details:
                                    meeting_date = nested_details['meeting_date']
                                    print(f"[STAFF ASSIGNED] ✅ Found meeting_date in nested details: {meeting_date}")
                                if 'meeting_time' in nested_details:
                                    meeting_time = nested_details['meeting_time']
                                    print(f"[STAFF ASSIGNED] ✅ Found meeting_time in nested details: {meeting_time}")
                            
                            # Fallback to root level - CHECK HERE FOR COMPLAINT 272
                            if not deadline and 'deadline' in details_data:
                                deadline = details_data['deadline']
                                print(f"[STAFF ASSIGNED] ✅ Found deadline in root: {deadline}")
                                
                                # Special success for complaint 272
                                if complaint.complaint_id == 272:
                                    print(f"[STAFF ASSIGNED] 🎯 COMPLAINT 272 SUCCESS! Found deadline: {deadline}")
                                    
                            if not meeting_date and 'meeting_date' in details_data:
                                meeting_date = details_data['meeting_date']
                                print(f"[STAFF ASSIGNED] ✅ Found meeting_date in root: {meeting_date}")
                            if not meeting_time and 'meeting_time' in details_data:
                                meeting_time = details_data['meeting_time']
                                print(f"[STAFF ASSIGNED] ✅ Found meeting_time in root: {meeting_time}")
                                
                            if not deadline and not meeting_date and not meeting_time:
                                print(f"[STAFF ASSIGNED] ❌ No deadline or meeting fields found in details")
                                
                                # Special failure for complaint 272
                                if complaint.complaint_id == 272:
                                    print(f"[STAFF ASSIGNED] 🎯 COMPLAINT 272 FAILURE - No deadline found in details!")
                                    print(f"[STAFF ASSIGNED] 🎯   - Available keys in details: {list(details_data.keys())}")
                                    print(f"[STAFF ASSIGNED] 🎯   - Full details object: {details_data}")
                        else:
                            print(f"[STAFF ASSIGNED] ❌ Details data is not a dictionary: {type(details_data)}")
                    except json.JSONDecodeError as e:
                        print(f"[STAFF ASSIGNED] ❌ Error parsing deadline JSON for complaint {complaint.complaint_id}: {e}")
                        
                        # Special error for complaint 272
                        if complaint.complaint_id == 272:
                            print(f"[STAFF ASSIGNED] 🎯 COMPLAINT 272 JSON ERROR!")
                            print(f"[STAFF ASSIGNED] 🎯   - Raw details that failed to parse: {deadline_row.details}")
                            print(f"[STAFF ASSIGNED] 🎯   - Error: {e}")
                else:
                    print(f"[STAFF ASSIGNED] ❌ No details found for complaint {complaint.complaint_id}")
                    
                    # Special check for complaint 272
                    if complaint.complaint_id == 272:
                        print(f"[STAFF ASSIGNED] 🎯 COMPLAINT 272 - NO DETAILS FOUND!")
                        print(f"[STAFF ASSIGNED] 🎯   - deadline_row: {deadline_row}")
                        print(f"[STAFF ASSIGNED] 🎯   - deadline_row.details: {deadline_row.details if deadline_row else 'No row'}")
            except Exception as e:
                print(f"[STAFF ASSIGNED] ❌ Error extracting deadline for complaint {complaint.complaint_id}: {e}")
            
            print(f"[STAFF ASSIGNED] 🎯 Final extracted data for complaint {complaint.complaint_id}:")
            print(f"[STAFF ASSIGNED] 🎯   - deadline: {deadline}")
            print(f"[STAFF ASSIGNED] 🎯   - meeting_date: {meeting_date}")
            print(f"[STAFF ASSIGNED] 🎯   - meeting_time: {meeting_time}")
            
            formatted_complaints.append({
                'complaint_id': complaint.complaint_id,
                'type_of_complaint': complaint.type_of_complaint,
                'complainant': complaint.complainant_name or 'N/A',
                'area_name': area_display,
                'address': formatted_address,
                'priority_level': complaint.priority_level or 'Minor',
                'status': complaint.status,
                'complaint_stage': complaint.complaint_stage,
                'date_received': complaint.date_received.isoformat() if complaint.date_received else '',
                'assigned_to': complaint.assigned_to,
                'action_datetime': complaint.action_datetime.isoformat() if complaint.action_datetime else None,
                'action_needed': complaint.latest_action or 'Pending',
                'deadline': deadline,  # Add deadline field from complaint_history details
                'meeting_date': meeting_date,  # Add meeting_date from complaint_history details
                'meeting_time': meeting_time,  # Add meeting_time from complaint_history details
                # Debug info
                'debug_area_id': complaint.area_id,
                'debug_raw_area_name': complaint.area_name
            })
        
        return jsonify({
            'success': True, 
            'complaints': formatted_complaints,
            'debug_test_data': [{
                'complaint_id': row.complaint_id,
                'area_id': row.area_id,
                'area_name': row.area_name,
                'complainant': row.complainant_name,
                'assigned_to': row.assigned_to
            } for row in test_data]
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@complaints_bp.route('/staff/api/debug', methods=['GET'])
def debug_staff_data():
    """Debug endpoint to check data relationships"""
    try:
        staff_name = session.get('name') or session.get('admin_name')
        debug_info = {
            'session_name': staff_name,
            'session_all': dict(session),
        }
        
        if staff_name:
            # Check if staff exists in admin table
            admin_check = db.session.execute(
                text("SELECT name, account FROM admin WHERE name = :name"), 
                {'name': staff_name}
            ).fetchone()
            debug_info['admin_found'] = admin_check._asdict() if admin_check else None
            
            # Check areas table
            areas_check = db.session.execute(
                text("SELECT area_id, area_name FROM areas LIMIT 5")
            ).fetchall()
            debug_info['areas_sample'] = [row._asdict() for row in areas_check]
            
            # Check complaints with area_id
            complaints_check = db.session.execute(
                text("SELECT complaint_id, area_id, complainant_name FROM complaints WHERE area_id IS NOT NULL LIMIT 5")
            ).fetchall()
            debug_info['complaints_with_area'] = [row._asdict() for row in complaints_check]
            
            # Check complaint_history for this staff
            history_check = db.session.execute(
                text("SELECT complaint_id, assigned_to, type_of_action FROM complaint_history WHERE assigned_to = :name LIMIT 5"),
                {'name': staff_name}
            ).fetchall()
            debug_info['complaint_history'] = [row._asdict() for row in history_check]
            
            # Test the exact query from assigned complaints
            test_query = """
            SELECT DISTINCT
                c.complaint_id,
                c.area_id,
                COALESCE(a.area_name, 'N/A') as area_name,
                c.complainant_name,
                ch_latest.assigned_to
            FROM complaints c
            LEFT JOIN areas a ON c.area_id = a.area_id
            JOIN admin staff_admin ON staff_admin.name = :staff_name AND staff_admin.account = 2
            LEFT JOIN (
                SELECT 
                    ch1.complaint_id,
                    ch1.assigned_to,
                    ROW_NUMBER() OVER (PARTITION BY ch1.complaint_id ORDER BY ch1.action_datetime DESC) as rn
                FROM complaint_history ch1
            ) ch_latest ON c.complaint_id = ch_latest.complaint_id AND ch_latest.rn = 1
            WHERE ch_latest.assigned_to = :staff_name 
            AND c.status = 'Valid'
            AND c.complaint_stage != 'Resolved'
            LIMIT 5
            """
            
            test_result = db.session.execute(text(test_query), {'staff_name': staff_name}).fetchall()
            debug_info['test_query_result'] = [row._asdict() for row in test_result]
        
        return jsonify({'success': True, 'debug': debug_info})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@complaints_bp.route('/staff/api/complaints/resolved', methods=['GET'])
def get_staff_resolved_complaints():
    """Get complaints where staff members have been assigned tasks - visible regardless of admin resolution"""
    try:
        # Get current staff name from session - try multiple session keys for compatibility
        staff_name = session.get('name') or session.get('admin_name')
        
        # For debugging/demo purposes, if no session, use known staff names
        if not staff_name:
            # Check what staff assignments exist and use one of them
            staff_check_query = """
            SELECT DISTINCT assigned_to, COUNT(*) as task_count
            FROM complaint_history 
            WHERE assigned_to IS NOT NULL AND assigned_to != ''
            GROUP BY assigned_to
            ORDER BY task_count DESC
            """
            staff_result = db.session.execute(text(staff_check_query))
            staff_list = staff_result.fetchall()
            
            if staff_list:
                # Use the staff member with the most assignments for demo
                staff_name = staff_list[0].assigned_to
            else:
                return jsonify({'success': True, 'complaints': [], 'debug': 'No staff assignments found in database'})
        
        # Query to get all complaints where this staff member was assigned tasks
        # This should show their work regardless of whether admin marked complaint as resolved
        query = """
        SELECT DISTINCT
            c.complaint_id,
            c.type_of_complaint,
            c.priority_level,
            c.status,
            c.complaint_stage,
            c.date_received,
            c.description,
            c.complainant_name,
            c.address,
            COALESCE(r.lot_no, 0) as lot_no,
            COALESCE(r.block_no, 0) as block_no,
            COALESCE(a.area_name, 'N/A') as area_name,
            ch.action_datetime as task_date,
            ch.type_of_action
        FROM complaint_history ch
        JOIN complaints c ON ch.complaint_id = c.complaint_id
        LEFT JOIN registration r ON c.registration_id = r.registration_id
        LEFT JOIN areas a ON c.area_id = a.area_id
        WHERE ch.assigned_to = :staff_name
        AND ch.assigned_to IS NOT NULL 
        AND ch.assigned_to != ''
        ORDER BY ch.action_datetime DESC
        """
        
        result = db.session.execute(text(query), {'staff_name': staff_name})
        complaints = result.fetchall()
        
        formatted_complaints = []
        for complaint in complaints:
            # Use address directly from complaints table if available, otherwise format from components
            if complaint.address:
                formatted_address = complaint.address
            else:
                formatted_address = format_address(
                    complaint.area_name,
                    complaint.lot_no,
                    complaint.block_no
                )
            
            # Show what task was assigned to this staff member
            task_description = f"{complaint.type_of_action} assigned to {staff_name}"
            if complaint.complaint_stage == 'Resolved':
                task_description += " (Complaint later resolved by admin)"
            elif complaint.complaint_stage == 'Out of Jurisdiction':
                task_description += " (Complaint marked out of jurisdiction)"
            
            formatted_complaints.append({
                'complaint_id': complaint.complaint_id,
                'type_of_complaint': complaint.type_of_complaint,
                'complainant': complaint.complainant_name or 'N/A',
                'area_name': complaint.area_name,
                'address': formatted_address,
                'priority_level': complaint.priority_level or 'Minor',
                'status': complaint.status,
                'complaint_stage': complaint.complaint_stage,  
                'date_received': complaint.date_received.isoformat() if complaint.date_received else '',
                'action_datetime': complaint.task_date.isoformat() if complaint.task_date else None,
                'resolution_action': task_description,
                'action_needed': complaint.type_of_action or 'Task Assigned'
            })
        
        return jsonify({
            'success': True, 
            'complaints': formatted_complaints, 
            'debug_staff_name': staff_name, 
            'total_tasks': len(formatted_complaints),
            'query_result_count': len(complaints)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e), 'error_type': type(e).__name__}), 500

@complaints_bp.route('/staff/api/debug/assignments', methods=['GET'])
def debug_staff_assignments():
    """Debug endpoint to see what staff assignments exist"""
    try:
        # Simple query to see all staff assignments
        query = """
        SELECT 
            assigned_to, 
            type_of_action, 
            complaint_id, 
            action_datetime
        FROM complaint_history 
        WHERE assigned_to IS NOT NULL AND assigned_to != ''
        ORDER BY action_datetime DESC
        LIMIT 10
        """
        result = db.session.execute(text(query))
        assignments = result.fetchall()
        
        formatted_assignments = []
        for assignment in assignments:
            formatted_assignments.append({
                'assigned_to': assignment.assigned_to,
                'type_of_action': assignment.type_of_action,
                'complaint_id': assignment.complaint_id,
                'action_datetime': assignment.action_datetime.isoformat() if assignment.action_datetime else None
            })
        
        return jsonify({
            'success': True,
            'assignments': formatted_assignments,
            'total': len(formatted_assignments)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@complaints_bp.route('/api/complainant_timeline/<int:complaint_id>', methods=['GET'])
def get_complainant_timeline(complaint_id):
    """Get timeline data for complainant view - filtered to show only specific statuses"""
    try:
        # Query complaint_history for this specific complaint
        timeline_query = text("""
            SELECT 
                ch.type_of_action,
                ch.assigned_to,
                ch.action_datetime,
                ch.details
            FROM complaint_history ch
            WHERE ch.complaint_id = :complaint_id
            ORDER BY ch.action_datetime DESC
        """)
        
        timeline_result = db.session.execute(timeline_query, {'complaint_id': complaint_id})
        timeline_entries = timeline_result.fetchall()
        
        # Filter timeline entries for complainant view - only show specific statuses
        complainant_allowed_statuses = [
            'Submitted a valid complaint',
            'Inspection done', 
            'Sent Invitation',
            'Accepted Invitation',
            'Assessment',
            'Resolved'
        ]
        
        filtered_timeline = []
        for entry in timeline_entries:
            action_type = entry.type_of_action
            
            # Map action types to complainant-friendly status names
            mapped_status = None
            if 'inspection' in action_type.lower() and 'done' in action_type.lower():
                mapped_status = 'Inspection done'
            elif 'sent invitation' in action_type.lower() or 'invitation' in action_type.lower():
                mapped_status = 'Sent Invitation'
            elif 'accept' in action_type.lower() and 'invitation' in action_type.lower():
                mapped_status = 'Accepted Invitation'
            elif action_type == 'Assessment':
                mapped_status = 'Resolved'  # Assessment completion shows as "Resolved" to complainant
            elif 'resolved' in action_type.lower():
                mapped_status = 'Resolved'
            
            # Only include if it's an allowed status for complainant
            if mapped_status and mapped_status in complainant_allowed_statuses:
                # Parse details if it exists
                details_data = {}
                if entry.details:
                    try:
                        details_data = json.loads(entry.details)
                    except:
                        details_data = {}
                
                filtered_timeline.append({
                    'status': mapped_status,
                    'assigned_to': entry.assigned_to,
                    'action_datetime': entry.action_datetime.strftime('%Y-%m-%d') if entry.action_datetime else '',
                    'description': get_default_complainant_message(mapped_status, entry.assigned_to),
                    'details': details_data
                })
        
        return jsonify({'success': True, 'timeline': filtered_timeline})
        
    except Exception as e:
        print(f"Error getting complainant timeline: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

def get_default_complainant_message(status, assigned_to):
    """Generate default messages for complainant timeline"""
    messages = {
        'Submitted a valid complaint': 'Your complaint has been submitted and is under review.',
        'Inspection done': f'Site inspection completed by {assigned_to or "staff"}.',
        'Sent Invitation': f'Invitation sent to parties by {assigned_to or "staff"}.',
        'Accepted Invitation': 'Invitation accepted by all parties.',
        'Resolved': 'Your complaint has been resolved.'
    }
    return messages.get(status, f'{status} - Processing your complaint.')

def update_assessment_complaints_to_resolved():
    """Update complaints that have Assessment as latest action but are still marked as Ongoing"""
    try:
        # Find complaints with Assessment as latest action but still marked as Ongoing
        update_query = text("""
            UPDATE complaints c
            SET complaint_stage = 'Resolved'
            WHERE c.complaint_stage = 'Ongoing'
            AND EXISTS (
                SELECT 1 FROM complaint_history ch
                WHERE ch.complaint_id = c.complaint_id
                AND ch.type_of_action = 'Assessment'
                AND ch.action_datetime = (
                    SELECT MAX(ch2.action_datetime)
                    FROM complaint_history ch2
                    WHERE ch2.complaint_id = c.complaint_id
                )
            )
        """)
        
        result = db.session.execute(update_query)
        db.session.commit()
        
        if result.rowcount > 0:
            print(f"Updated {result.rowcount} complaints from Ongoing to Resolved due to Assessment completion")
            
    except Exception as e:
        print(f"Error updating Assessment complaints to Resolved: {e}")
        db.session.rollback()

@complaints_bp.route('/api/fix_assessment_status', methods=['POST'])
def fix_assessment_status():
    """Manual endpoint to fix Assessment complaint statuses"""
    try:
        update_assessment_complaints_to_resolved()
        return jsonify({'success': True, 'message': 'Assessment complaint statuses updated'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@complaints_bp.route('/api/complaint_details/<int:complaint_id>', methods=['GET'])
def get_complaint_details(complaint_id):
    """Get complaint details including area information for map display"""
    try:
        # Query complaint with area details
        query = text("""
            SELECT 
                c.complaint_id,
                c.complainant_name,
                c.type_of_complaint,
                c.date_received,
                c.status,
                c.complaint_stage,
                a.area_id,
                a.area_code,
                a.area_name
            FROM complaints c
            LEFT JOIN areas a ON c.area_id = a.area_id
            WHERE c.complaint_id = :complaint_id
        """)
        
        result = db.session.execute(query, {'complaint_id': complaint_id})
        complaint = result.fetchone()
        
        if not complaint:
            return jsonify({'success': False, 'message': 'Complaint not found'}), 404
        
        complaint_data = {
            'complaint_id': complaint.complaint_id,
            'complainant_name': complaint.complainant_name,
            'type_of_complaint': complaint.type_of_complaint,
            'date_received': complaint.date_received.isoformat() if complaint.date_received else '',
            'status': complaint.status,
            'complaint_stage': complaint.complaint_stage,
            'area_id': complaint.area_id,
            'area_code': complaint.area_code,
            'area_name': complaint.area_name
        }
        
        return jsonify({'success': True, 'complaint': complaint_data})
        
    except Exception as e:
        print(f"Error getting complaint details: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
