import os
import json
from flask import Blueprint, send_file, request, jsonify, session
from ...database.db import db
from ...database.models import Complaint, ComplaintHistory, Admin, Area, Beneficiary
from sqlalchemy import text, func
from datetime import datetime

complaints_bp = Blueprint("complaints", __name__, url_prefix="/admin/complaints")

frontend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../frontend"))

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

def get_complaint_data_with_proper_areas(status_filter=None, stage_filter=None, assigned_filter=None):
    """NEW: Get complaint data with proper area joins - DEBUGGING VERSION"""
    try:
        # Simple query that DEFINITELY joins complaints.area_id = areas.area_id
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
        """
        
        params = {}
        where_clauses = []
        
        if status_filter:
            if status_filter == 'valid':
                where_clauses.append("c.status = 'Valid'")
            elif status_filter == 'invalid':
                where_clauses.append("c.status = 'Invalid'")
        
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
            
            formatted_complaints.append({
                'complaint_id': complaint.complaint_id,
                'type_of_complaint': complaint.type_of_complaint,
                'complainant_name': complaint.complainant_name or 'N/A',
                'address': formatted_address,
                'area_name': complaint.area_name or 'N/A',  # ADD THIS LINE - Include area_name in JSON response
                'priority_level': complaint.priority_level or 'Minor',
                'status': complaint.status,
                'complaint_stage': complaint.complaint_stage,
                'date_received': complaint.date_received.strftime('%Y-%m-%d') if complaint.date_received else '',
                'description': complaint.description or '',
                'assigned_to': assigned_to,
                'action_datetime': action_datetime.isoformat() if action_datetime else None,
                'latest_action': latest_action,
                'action_needed': latest_action  # For backward compatibility
            })
        
        return formatted_complaints
        
    except Exception as e:
        print(f"Error getting complaint data: {e}")
        return []

def get_complaint_data(status_filter=None, stage_filter=None, assigned_filter=None):
    """Get complaint data with proper joins and formatting including complaint_history"""
    try:
        # Use complainant_name directly from complaints table and get latest complaint_history data
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
        """
        
        params = {}
        where_clauses = []
        
        if status_filter:
            if status_filter == 'valid':
                where_clauses.append("c.status = 'Valid'")
            elif status_filter == 'invalid':
                where_clauses.append("c.status = 'Invalid'")
        
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
            
        formatted_complaints.append({
            'complaint_id': complaint.complaint_id,
            'type_of_complaint': complaint.type_of_complaint,
            'complainant_name': complaint.complainant_name or 'N/A',
            'address': formatted_address,
            'area_name': complaint.area_name or 'N/A',  # ADD THIS LINE - Include area_name in JSON response
            'priority_level': complaint.priority_level or 'Minor',
            'status': complaint.status,
            'complaint_stage': complaint.complaint_stage,
            'date_received': complaint.date_received.strftime('%Y-%m-%d') if complaint.date_received else '',
            'description': complaint.description or '',
            'assigned_to': assigned_to,
            'action_datetime': action_datetime.isoformat() if action_datetime else None,
            'latest_action': latest_action,
            'action_needed': latest_action  # For backward compatibility
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

@complaints_bp.route("/timeline_test.html")
def timeline_test():
    return send_file(os.path.join(frontend_path, "timeline_test.html"))

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
        complaints = get_complaint_data_with_proper_areas()  # USING NEW DEBUG FUNCTION
        print(f"[DEBUG] Found {len(complaints)} complaints")
        
        response = jsonify(complaints)
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    
    except Exception as e:
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
        
        complaints = get_complaint_data_with_proper_areas(stage_filter='Ongoing')
        
        response = jsonify(complaints)
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    
    except Exception as e:
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
        WHERE c.status = 'Valid' 
        AND c.complaint_id IN (
            -- Get complaints that have both Inspection and Assessment
            SELECT complaint_id FROM complaint_history WHERE type_of_action = 'Inspection'
            INTERSECT
            SELECT complaint_id FROM complaint_history WHERE type_of_action = 'Assessment'
        )
        AND c.complaint_id NOT IN (
            -- Exclude complaints that have Invitation or Mediation
            SELECT complaint_id FROM complaint_history WHERE type_of_action IN ('Invitation', 'Mediation')
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
                'date_received': complaint.date_received.strftime('%Y-%m-%d') if complaint.date_received else '',
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
            details = {
                "to": data.get("to"),
                "meeting_date": data.get("meeting_date"),
                "meeting_time": data.get("meeting_time"),
                "location": data.get("location"),
                "agenda": data.get("agenda")
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
        for key, value in data.items():
            if key not in {'complaint_id', 'action_type', 'assigned_to', 'action_datetime', 'description'} and key not in details:
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

        # Update complaint stage
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
    try:
        # Get complaint info
        # Join using the complaint.registration_id and complaint.area_id which match the
        # database models (Registration.registration_id and Areas.area_id). Previous
        # joins attempted to use r.area_id/r.block_id which don't exist on the
        # registration table in this schema and caused OperationalError (unknown column).
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

        complaint_type = complaint.type_of_complaint.lower().replace(" ", "_")
        autofill_data = {
            "agenda": complaint.type_of_complaint,
            "location": "2nd FLR. USAD-PHASELAD OFFICE, BARANGAY MAIN"  # default location for invitation
        }

        # Default 'to' is complainant name
        complainant_name = f"{complaint.first_name} {complaint.middle_name or ''} {complaint.last_name} {complaint.suffix or ''}".strip()
        autofill_data["to"] = complainant_name

        # Additional tables based on complaint type
        if complaint_type == "overlapping":
            overlapping = db.session.execute(
                text("SELECT q1, q8 FROM overlapping WHERE complaint_id=:id"), {"id": complaint_id}
            ).fetchone()
            if overlapping:
                # overlapping.q1 often contains a JSON-encoded block/lot structure.
                # Do NOT append that JSON blob to the 'to' field (which should be names).
                # Keep 'to' as complainant and the other party (q8) only.
                other_party = overlapping.q8 if hasattr(overlapping, 'q8') and overlapping.q8 else ''
                autofill_data["to"] = f"{complainant_name}{', ' + other_party if other_party else ''}"

                # Try to parse overlapping.q1 into structured data on the server so the
                # frontend doesn't have to guess encoding/escaping rules.
                parsed_q1 = None
                try:
                    raw = overlapping.q1
                    if isinstance(raw, str):
                        # Remove surrounding quotes if accidentally double-encoded
                        s = raw.strip()
                        if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
                            s = s[1:-1]
                        parsed_q1 = json.loads(s)
                    else:
                        parsed_q1 = raw
                except Exception:
                    parsed_q1 = None

                # Build a human-friendly inspection location.
                inspection_block = None
                inspection_lot = None
                if parsed_q1:
                    # parsed_q1 may be a list of objects or a single object
                    if isinstance(parsed_q1, list) and len(parsed_q1) > 0 and isinstance(parsed_q1[0], dict):
                        inspection_block = parsed_q1[0].get('block')
                        inspection_lot = parsed_q1[0].get('lot')
                    elif isinstance(parsed_q1, dict):
                        inspection_block = parsed_q1.get('block')
                        inspection_lot = parsed_q1.get('lot')

                # If parsing did not yield block/lot, fall back to complaint's block/lot
                inspection_block = inspection_block or complaint.block_no
                inspection_lot = inspection_lot or complaint.lot_no

                # HOA / area name
                inspection_hoa = complaint.area_name or ''

                # Human-friendly string
                inspection_pretty_parts = []
                if inspection_hoa:
                    inspection_pretty_parts.append(inspection_hoa)
                if inspection_block:
                    inspection_pretty_parts.append(f"Block {inspection_block}")
                if inspection_lot:
                    inspection_pretty_parts.append(f"Lot {inspection_lot}")
                inspection_pretty = ", ".join(inspection_pretty_parts)

                # Return structured and pretty values
                autofill_data["inspection_location_raw"] = overlapping.q1
                autofill_data["inspection_location_parsed"] = {
                    'block': inspection_block,
                    'lot': inspection_lot,
                    'hoa': inspection_hoa,
                    'raw_parsed': parsed_q1
                }
                autofill_data["inspection_location_pretty"] = inspection_pretty
                # This person is the suggested inspector for inspections only.
                autofill_data["inspection_assigned_personnel"] = "Alberto Nonato Jr."
                autofill_data["block_no"] = complaint.block_no
                autofill_data["lot_no"] = complaint.lot_no

        elif complaint_type == "lot_dispute":
            lot_dispute = db.session.execute(
                text("SELECT q7 FROM lot_dispute WHERE complaint_id=:id"), {"id": complaint_id}
            ).fetchone()
            if lot_dispute:
                autofill_data["to"] = f"{complainant_name}, {lot_dispute.q7}"

        elif complaint_type == "unauthorized_occupation":
            unauthorized = db.session.execute(
                text("SELECT q2 FROM unauthorized_occupation WHERE complaint_id=:id"), {"id": complaint_id}
            ).fetchone()
            if unauthorized:
                autofill_data["to"] = f"{complainant_name}, {unauthorized.q2}"

        # Pathway Dispute and Boundary Dispute use only complainant name, already set

        return jsonify(autofill_data)

    except Exception as e:
        print("Error fetching autofill data:", e)
        return jsonify({"error": str(e)}), 500

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
        # Get current staff name from session or use test name for debugging
        staff_name = session.get('name')
        if not staff_name:
            # TEMPORARY: Use test staff name for debugging area_name issue
            staff_name = "Test Staff"
            print(f"[DEBUG] Using test staff name for debugging: {staff_name}")
        
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
            
            formatted_complaints.append({
                'complaint_id': complaint.complaint_id,
                'type_of_complaint': complaint.type_of_complaint,
                'complainant': complaint.complainant_name or 'N/A',
                'area_name': area_display,
                'address': formatted_address,
                'priority_level': complaint.priority_level or 'Minor',
                'status': complaint.status,
                'complaint_stage': complaint.complaint_stage,
                'date_received': complaint.date_received.strftime('%Y-%m-%d') if complaint.date_received else '',
                'assigned_to': complaint.assigned_to,
                'action_datetime': complaint.action_datetime.isoformat() if complaint.action_datetime else None,
                'action_needed': complaint.latest_action or 'Pending',
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
        staff_name = session.get('name')
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
    """Get complaints resolved by the current staff member"""
    try:
        # Get current staff name from session
        staff_name = session.get('name')
        print(f"[STAFF RESOLVED] Session staff name: {staff_name}")
        
        # For debugging - also try to get any staff completions
        debug_query = """
        SELECT DISTINCT assigned_to, type_of_action, complaint_id
        FROM complaint_history 
        WHERE type_of_action IN ('Inspection done', 'Sent Invitation')
        ORDER BY action_datetime DESC LIMIT 10
        """
        debug_result = db.session.execute(text(debug_query))
        debug_completions = debug_result.fetchall()
        print(f"[STAFF RESOLVED] Recent completions: {[dict(row._mapping) for row in debug_completions]}")
        
        if not staff_name:
            # Try to use any staff name that has completed tasks for debugging
            if debug_completions:
                staff_name = debug_completions[0].assigned_to
                print(f"[STAFF RESOLVED] Using fallback staff name: {staff_name}")
            else:
                return jsonify({'success': False, 'message': 'Staff name not found in session and no completed tasks found'}), 401
        
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
            ch_completed.action_datetime as completion_date,
            CONCAT(ch_completed.type_of_action, ' completed by ', ch_completed.assigned_to) as resolution_action
        FROM complaints c
        LEFT JOIN registration r ON c.registration_id = r.registration_id
        LEFT JOIN areas a ON c.area_id = a.area_id
        JOIN complaint_history ch_completed ON c.complaint_id = ch_completed.complaint_id
        WHERE (ch_completed.assigned_to = :staff_name OR ch_completed.assigned_to = 'Staff Member')
        AND ch_completed.type_of_action IN ('Inspection done', 'Sent Invitation')
        AND c.status = 'Valid'
        ORDER BY ch_completed.action_datetime DESC
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
            
            formatted_complaints.append({
                'complaint_id': complaint.complaint_id,
                'type_of_complaint': complaint.type_of_complaint,
                'complainant': complaint.complainant_name or 'N/A',
                'area_name': complaint.area_name,
                'address': formatted_address,
                'priority_level': complaint.priority_level or 'Minor',
                'status': complaint.status,
                'date_received': complaint.date_received.strftime('%Y-%m-%d') if complaint.date_received else '',
                'date_resolved': complaint.completion_date.strftime('%Y-%m-%d') if complaint.completion_date else '',
                'resolution_action': complaint.resolution_action or 'Task Completed'
            })
        
        return jsonify({'success': True, 'complaints': formatted_complaints})
        
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
            'date_received': complaint.date_received.strftime('%Y-%m-%d') if complaint.date_received else '',
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
