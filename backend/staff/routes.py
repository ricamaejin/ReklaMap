import os
from flask import Blueprint, request, jsonify, session, redirect, Response, render_template
from ..database.models import Admin, Complaint, ComplaintHistory, Area
from ..database.db import db
from sqlalchemy import text

staff_bp = Blueprint('staff', __name__, url_prefix='/staff')

# Path to frontend
frontend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../frontend"))

def is_authenticated():
    """Check if user is logged in"""
    return 'admin_id' in session and 'admin_name' in session

def is_staff_member():
    """Check if logged in user is a staff member"""
    if not is_authenticated():
        return False
    return session.get('account_type') == 2  # Staff account type

def require_staff_auth():
    """Decorator to require staff authentication"""
    if not is_authenticated():
        return redirect('/portal/admin_login.html')
    if not is_staff_member():
        return redirect('/admin/dashboard')  # Redirect admins to admin area
    return None

def get_staff_complaint_data_with_proper_areas(staff_name=None, stage_filter=None):
    """Get staff complaint data with proper area joins"""
    try:
        # Query that properly joins complaints.area_id = areas.area_id
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
        
        # Always filter for valid complaints
        where_clauses.append("c.status = 'Valid'")
        
        if staff_name:
            where_clauses.append("ch_latest.assigned_to = :staff_name")
            params['staff_name'] = staff_name
        
        if stage_filter:
            if stage_filter == 'Resolved':
                # For resolved view: show complaints where this staff completed their task
                where_clauses.append("""
                    EXISTS (
                        SELECT 1 FROM complaint_history ch_completed 
                        WHERE ch_completed.complaint_id = c.complaint_id 
                        AND ch_completed.assigned_to = :staff_name
                        AND ch_completed.type_of_action IN ('Inspection done', 'Sent Invitation')
                    )
                """)
            else:
                where_clauses.append("c.complaint_stage = :stage")
                params['stage'] = stage_filter
        else:
            # For assigned complaints: exclude those where staff has completed their task
            where_clauses.append("""
                NOT EXISTS (
                    SELECT 1 FROM complaint_history ch_completed 
                    WHERE ch_completed.complaint_id = c.complaint_id 
                    AND ch_completed.assigned_to = :staff_name
                    AND ch_completed.type_of_action IN ('Inspection done', 'Sent Invitation')
                )
            """)
        
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        
        query += " ORDER BY c.date_received DESC"
        
        print(f"[DEBUG STAFF] Executing query: {query}")
        print(f"[DEBUG STAFF] With params: {params}")
        
        result = db.session.execute(text(query), params)
        complaints = result.fetchall()
        
        print(f"[DEBUG STAFF] Raw query returned {len(complaints)} rows")
        for i, complaint in enumerate(complaints[:3]):  # Show first 3 for debugging
            print(f"[DEBUG STAFF] Complaint {i+1}: complaint_id={complaint.complaint_id}, area_id={complaint.area_id}, area_name='{complaint.area_name}'")
        
        complaints_data = []
        for complaint in complaints:
            # Format the address using area_name, block_no, and lot_no
            address_parts = []
            if complaint.area_name and complaint.area_name != 'N/A':
                address_parts.append(complaint.area_name)
            if complaint.block_no and int(complaint.block_no) > 0:
                address_parts.append(f"Block {int(complaint.block_no)}")
            if complaint.lot_no and int(complaint.lot_no) > 0:
                address_parts.append(f"Lot {int(complaint.lot_no)}")
            formatted_address = ", ".join(address_parts) if address_parts else complaint.address or 'N/A'
            
            # Extract deadline from complaint_history details JSON (same logic as admin)
            deadline = None
            try:
                deadline_query = """
                SELECT ch.details 
                FROM complaint_history ch 
                WHERE ch.complaint_id = :complaint_id 
                  AND ch.type_of_action = 'Inspection'
                  AND ch.details IS NOT NULL 
                ORDER BY ch.action_datetime DESC 
                LIMIT 1
                """
                deadline_result = db.session.execute(text(deadline_query), {'complaint_id': complaint.complaint_id})
                deadline_row = deadline_result.fetchone()
                
                if deadline_row and deadline_row.details:
                    import json
                    try:
                        # Parse the JSON details
                        details_data = json.loads(deadline_row.details)
                        if isinstance(details_data, dict) and 'details' in details_data:
                            nested_details = details_data['details']
                            if isinstance(nested_details, dict) and 'deadline' in nested_details:
                                deadline = nested_details['deadline']
                    except (json.JSONDecodeError, TypeError, KeyError) as e:
                        print(f"[STAFF] Error parsing deadline JSON for complaint {complaint.complaint_id}: {e}")
            except Exception as e:
                print(f"[STAFF] Error extracting deadline for complaint {complaint.complaint_id}: {e}")

            complaints_data.append({
                'complaint_id': complaint.complaint_id,
                'date_received': complaint.date_received.isoformat() if complaint.date_received else 'N/A',
                'complainant': complaint.complainant_name or 'N/A',
                'type_of_complaint': complaint.type_of_complaint or 'N/A',
                'hoa': complaint.area_name or 'N/A',
                'area_name': complaint.area_name or 'N/A',
                'address': formatted_address,
                'priority_level': complaint.priority_level or 'Minor',
                'complaint_stage': complaint.complaint_stage or 'N/A',
                'assigned_to': complaint.assigned_to or 'N/A',
                'latest_action': complaint.latest_action or 'N/A',
                'action_datetime': complaint.action_datetime.isoformat() if complaint.action_datetime else None,
                'action_needed': complaint.latest_action or 'Assignment',  # Map latest_action to action_needed
                'deadline': deadline  # Add deadline field from complaint_history details
            })
        
        print(f"[DEBUG STAFF] Found {len(complaints_data)} complaints")
        return complaints_data
        
    except Exception as e:
        print(f"Error getting staff complaint data: {e}")
        return []

@staff_bp.route('/complaints/assigned')
def assigned_complaints():
    """Show complaints assigned to the current staff member"""
    # TEMPORARILY DISABLE AUTH FOR DEBUGGING
    # auth_check = require_staff_auth()
    # if auth_check:
    #     return auth_check
    
    # Read the HTML file and inject staff navigation
    html_path = os.path.join(frontend_path, "admin", "staff", "complaints", "assigned.html")
    print(f"[DEBUG] Loading HTML from: {html_path}")  # Debug log
    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # Replace the empty navigation with staff navigation
    staff_nav = '<a href="/staff/complaints/assigned" class="nav-item active">Complaints</a>'
    original_nav = '<!-- Navigation will be populated by navigation.js -->'
    if original_nav in html_content:
        print(f"[DEBUG] Replacing navigation for staff user: {session.get('admin_name')}")  # Debug log
        html_content = html_content.replace(original_nav, staff_nav)
    else:
        print(f"[DEBUG] Navigation placeholder not found in assigned.html")  # Debug log
    
    return html_content

@staff_bp.route('/complaints/resolved')
def resolved_complaints():
    """Show resolved complaints for the current staff member"""
    # TEMPORARILY DISABLE AUTH FOR DEBUGGING
    # auth_check = require_staff_auth()
    # if auth_check:
    #     return auth_check
    
    # Read the HTML file and inject staff navigation
    html_path = os.path.join(frontend_path, "admin", "staff", "complaints", "resolved.html")
    print(f"[DEBUG] Loading resolved HTML from: {html_path}")  # Debug log
    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # Replace the empty navigation with staff navigation
    staff_nav = '<a href="/staff/complaints/assigned" class="nav-item">Complaints</a>'
    original_nav = '<!-- Navigation will be populated by navigation.js -->'
    if original_nav in html_content:
        print(f"[DEBUG] Replacing navigation for resolved page")  # Debug log
        html_content = html_content.replace(original_nav, staff_nav)
    else:
        print(f"[DEBUG] Navigation placeholder not found in resolved.html")  # Debug log
    
    return html_content

@staff_bp.route('/api/complaints/assigned')
def api_assigned_complaints():
    """API endpoint for assigned complaints data"""
    # TEMPORARILY DISABLE AUTH FOR DEBUGGING
    # auth_check = require_staff_auth()
    # if auth_check:
    #     return jsonify({'error': 'Unauthorized'}), 401
    
    # Use test staff name if no session
    staff_name = session.get('admin_name') or "Test Staff"
    print(f"[DEBUG] Staff assigned API called with staff_name: {staff_name}")
    
    try:
        # Use the working query function
        complaints_data = get_staff_complaint_data_with_proper_areas(
            staff_name=staff_name, 
            stage_filter=None  # All stages except resolved
        )
        
        # Debug: Log the data structure for the first complaint
        if complaints_data:
            print(f"[DEBUG] First complaint data structure: {complaints_data[0]}")
        else:
            print(f"[DEBUG] No complaints found for staff: {staff_name}")
            
            # Debug: Show what staff names are actually in the database
            try:
                debug_query = """
                SELECT DISTINCT ch.assigned_to, COUNT(*) as count
                FROM complaint_history ch
                WHERE ch.assigned_to IS NOT NULL AND ch.assigned_to != ''
                GROUP BY ch.assigned_to
                ORDER BY count DESC
                """
                debug_result = db.session.execute(text(debug_query))
                available_staff = debug_result.fetchall()
                print(f"[DEBUG] Available staff assignments in database:")
                for staff in available_staff:
                    print(f"  - '{staff.assigned_to}': {staff.count} assignments")
            except Exception as debug_error:
                print(f"[DEBUG] Could not fetch available staff: {debug_error}")
        
        response = jsonify({
            'success': True,
            'complaints': complaints_data
        })
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
        
    except Exception as e:
        print(f"Error in assigned complaints API: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@staff_bp.route('/api/complaints/resolved')
def api_resolved_complaints():
    """API endpoint for staff task history - shows all tasks assigned regardless of complaint resolution status"""
    # TEMPORARILY DISABLE AUTH FOR DEBUGGING
    # auth_check = require_staff_auth()
    # if auth_check:
    #     return jsonify({'error': 'Unauthorized'}), 401
    
    staff_name = session.get('admin_name') or session.get('name')
    print(f"[DEBUG] Staff resolved API called with staff_name: {staff_name}")
    
    # If no staff name in session, use Alberto Nonato Jr. for testing (we know he has assignments)
    if not staff_name:
        staff_name = "Alberto Nonato Jr."
        print(f"[DEBUG] Using fallback staff name: {staff_name}")
    
    try:
        # Query to get the LATEST action per complaint for this staff member
        # Prioritizes completion actions (Inspection done, Sent Invitation) over assignment actions
        query = """
        WITH staff_latest_actions AS (
            SELECT 
                ch.complaint_id,
                ch.type_of_action,
                ch.action_datetime,
                ch.assigned_to,
                ROW_NUMBER() OVER (
                    PARTITION BY ch.complaint_id 
                    ORDER BY 
                        CASE 
                            WHEN ch.type_of_action IN ('Inspection done', 'Sent Invitation') THEN 1
                            WHEN ch.type_of_action IN ('Inspection', 'Invitation') THEN 2
                            ELSE 3
                        END ASC,
                        ch.action_datetime DESC
                ) as rn
            FROM complaint_history ch
            WHERE ch.assigned_to = :staff_name
            AND ch.assigned_to IS NOT NULL 
            AND ch.assigned_to != ''
        )
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
            sla.action_datetime as task_date,
            sla.type_of_action
        FROM staff_latest_actions sla
        JOIN complaints c ON sla.complaint_id = c.complaint_id
        LEFT JOIN registration r ON c.registration_id = r.registration_id
        LEFT JOIN areas a ON c.area_id = a.area_id
        WHERE sla.rn = 1
        ORDER BY sla.action_datetime DESC
        """
        
        result = db.session.execute(text(query), {'staff_name': staff_name})
        complaints = result.fetchall()
        
        print(f"[DEBUG] Query returned {len(complaints)} task records for {staff_name}")
        
        complaints_data = []
        for complaint in complaints:
            # Use address directly from complaints table if available, otherwise format from components
            if complaint.address:
                formatted_address = complaint.address
            else:
                # Format address using area_name, lot_no, block_no
                address_parts = []
                if complaint.area_name and complaint.area_name != 'N/A':
                    address_parts.append(complaint.area_name)
                if complaint.lot_no > 0:
                    address_parts.append(f"Lot {complaint.lot_no}")
                if complaint.block_no > 0:
                    address_parts.append(f"Block {complaint.block_no}")
                formatted_address = ', '.join(address_parts) if address_parts else 'Address not specified'
            
            # Show the latest action taken by staff (completion status if available, otherwise assignment)
            if complaint.type_of_action in ['Inspection done', 'Sent Invitation']:
                # Staff completed the task - show completion status
                task_description = complaint.type_of_action
                if complaint.complaint_stage == 'Resolved':
                    task_description
                elif complaint.complaint_stage == 'Out of Jurisdiction':
                    task_description += " (Out of Jurisdiction)"
            else:
                # Staff was assigned but hasn't completed yet - show assignment status
                task_description = f"{complaint.type_of_action} assigned"
                if complaint.complaint_stage == 'Resolved':
                    task_description
                elif complaint.complaint_stage == 'Out of Jurisdiction':
                    task_description += " (Out of Jurisdiction)"
            
            complaints_data.append({
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
        
        response = jsonify({
            'success': True,
            'complaints': complaints_data,
            'debug_staff_name': staff_name,
            'total_tasks': len(complaints_data)
        })
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
        
    except Exception as e:
        print(f"Error in resolved complaints API: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@staff_bp.route('/api/current-staff')
def api_current_staff():
    """API endpoint to get current staff info for routing"""
    # TEMPORARILY DISABLE AUTH FOR DEBUGGING
    # Allow testing with different staff names via query parameter
    test_staff = request.args.get('test_staff')
    
    if test_staff:
        staff_name = test_staff
    else:
        staff_name = session.get('admin_name') or "Alberto Nonato Jr."  # Default to Alberto for testing
    
    print(f"[DEBUG] Current staff API returning: {staff_name}")
    
    response = jsonify({
        'success': True,
        'admin_name': staff_name,
        'name': staff_name  # For compatibility with existing code
    })
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@staff_bp.route('/api/stats')
def api_staff_stats():
    """API endpoint for staff statistics"""
    # TEMPORARILY DISABLE AUTH FOR DEBUGGING
    # auth_check = require_staff_auth()
    # if auth_check:
    #     return jsonify({'error': 'Unauthorized'}), 401
    
    staff_name = session.get('admin_name') or "Test Staff"
    print(f"[DEBUG] Staff stats API called with staff_name: {staff_name}")
    
    try:
        # Get assigned complaints count (not resolved)
        assigned_query = """
        SELECT COUNT(DISTINCT c.complaint_id) as count
        FROM complaints c
        LEFT JOIN complaint_history ch_latest ON c.complaint_id = ch_latest.complaint_id
        AND ch_latest.action_datetime = (
            SELECT MAX(ch2.action_datetime) 
            FROM complaint_history ch2 
            WHERE ch2.complaint_id = c.complaint_id
        )
        WHERE c.status = 'Valid' 
        AND c.complaint_stage != 'Resolved'
        AND ch_latest.assigned_to = :staff_name
        """
        
        # Get resolved complaints count
        resolved_query = """
        SELECT COUNT(DISTINCT c.complaint_id) as count
        FROM complaints c
        LEFT JOIN complaint_history ch_latest ON c.complaint_id = ch_latest.complaint_id
        AND ch_latest.action_datetime = (
            SELECT MAX(ch2.action_datetime) 
            FROM complaint_history ch2 
            WHERE ch2.complaint_id = c.complaint_id
        )
        WHERE c.status = 'Valid' 
        AND c.complaint_stage = 'Resolved'
        AND ch_latest.assigned_to = :staff_name
        """
        
        assigned_result = db.session.execute(text(assigned_query), {'staff_name': staff_name})
        assigned_count = assigned_result.fetchone().count
        
        resolved_result = db.session.execute(text(resolved_query), {'staff_name': staff_name})
        resolved_count = resolved_result.fetchone().count
        
        print(f"[DEBUG] Staff stats - Assigned: {assigned_count}, Resolved: {resolved_count}")
        
        response = jsonify({
            'success': True,
            'total_assigned': assigned_count,
            'resolved': resolved_count
        })
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
        
    except Exception as e:
        print(f"Error in staff stats API: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500