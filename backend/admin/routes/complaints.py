import os
from flask import Blueprint, send_file, request, jsonify, session
from ...database.db import db
from ...database.models import Complaint, ComplaintHistory, Admin, Area, Beneficiary
from sqlalchemy import text, func
from datetime import datetime

complaints_bp = Blueprint("complaints", __name__, url_prefix="/admin/complaints")

frontend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../frontend"))

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

def get_complaint_data(status_filter=None, assigned_filter=None):
    """Get complaint data with proper joins and formatting"""
    try:
        # Simplified query that works with actual database structure
        query = """
        SELECT 
            c.complaint_id,
            c.type_of_complaint,
            c.priority_level,
            c.status,
            c.complaint_stage,
            c.date_received,
            c.description,
            COALESCE(r.first_name, 'N/A') as first_name,
            COALESCE(r.middle_name, '') as middle_name,
            COALESCE(r.last_name, 'N/A') as last_name,
            COALESCE(r.suffix, '') as suffix,
            COALESCE(r.lot_no, 0) as lot_no,
            COALESCE(r.block_no, 0) as block_no,
            COALESCE(a.area_name, 'N/A') as area_name
        FROM complaints c
        LEFT JOIN registration r ON c.registration_id = r.registration_id
        LEFT JOIN areas a ON r.hoa = a.area_id
        """
        
        params = {}
        where_clauses = []
        
        if status_filter:
            if status_filter == 'valid':
                where_clauses.append("c.status = 'Valid'")
            elif status_filter == 'invalid':
                where_clauses.append("c.status = 'Invalid'")
            elif status_filter in ['Pending', 'Ongoing', 'Resolved']:
                where_clauses.append("c.complaint_stage = :stage")
                params['stage'] = status_filter
        
        if assigned_filter:
            where_clauses.append("ch.assigned_to = :assigned_to")
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
            
            formatted_complaints.append({
                'complaint_id': complaint.complaint_id,
                'type_of_complaint': complaint.type_of_complaint,
                'complainant_name': formatted_name,
                'address': formatted_address,
                'priority_level': complaint.priority_level or 'Minor',
                'status': complaint.status,
                'complaint_stage': complaint.complaint_stage,
                'date_received': complaint.date_received.strftime('%Y-%m-%d') if complaint.date_received else '',
                'description': complaint.description or ''
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

@complaints_bp.route("/assigned.html")
def complaints_assigned():
    return send_file(os.path.join(frontend_path, "admin", "complaints", "assigned.html"))

@complaints_bp.route("/invalid.html")
def complaints_invalid():
    return send_file(os.path.join(frontend_path, "admin", "complaints", "invalid.html"))

@complaints_bp.route("/complaint_details_valid.html")
def complaint_details_valid():
    return send_file(os.path.join(frontend_path, "admin", "complaints", "complaint_details_valid.html"))

@complaints_bp.route("/complaint_details_invalid.html")
def complaint_details_invalid():
    return send_file(os.path.join(frontend_path, "admin", "complaints", "complaint_details_invalid.html"))

# API Routes for Admin
@complaints_bp.route('/api/all', methods=['GET'])
def get_all_complaints():
    """Get all valid complaints for admin"""
    try:
        # Check if user is admin - TEMPORARILY DISABLED FOR TESTING
        # if session.get('account') != 1:
        #     return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        print("[DEBUG] Getting all complaints...")
        complaints = get_complaint_data()
        print(f"[DEBUG] Found {len(complaints)} complaints")
        
        return jsonify(complaints)
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@complaints_bp.route('/api/pending', methods=['GET'])
def get_pending_complaints():
    """Get pending complaints for admin"""
    try:
        # Check if user is admin - TEMPORARILY DISABLED FOR TESTING
        # if session.get('account') != 1:
        #     return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        complaints = get_complaint_data(status_filter='Pending')
        
        return jsonify(complaints)
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@complaints_bp.route('/api/ongoing', methods=['GET'])
def get_ongoing_complaints():
    """Get ongoing complaints for admin"""
    try:
        # Check if user is admin - TEMPORARILY DISABLED FOR TESTING
        # if session.get('account') != 1:
        #     return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        complaints = get_complaint_data(status_filter='Ongoing')
        
        return jsonify(complaints)
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@complaints_bp.route('/api/resolved', methods=['GET'])
def get_resolved_complaints():
    """Get resolved complaints for admin"""
    try:
        # Check if user is admin - TEMPORARILY DISABLED FOR TESTING
        # if session.get('account') != 1:
        #     return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        complaints = get_complaint_data(status_filter='Resolved')
        
        return jsonify(complaints)
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@complaints_bp.route('/api/assigned', methods=['GET'])
def get_assigned_complaints():
    """Get complaints assigned by the current admin"""
    try:
        # Check if user is admin - TEMPORARILY DISABLED FOR TESTING
        # if session.get('account') != 1:
        #     return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        # Get complaints that have been assigned to staff
        query = """
        SELECT DISTINCT
            c.complaint_id,
            c.type_of_complaint,
            c.priority_level,
            c.status,
            c.complaint_stage,
            c.date_received,
            c.description,
            r.first_name,
            r.middle_name,
            r.last_name,
            r.suffix,
            r.lot_no,
            b.block_no,
            a.area_name,
            ch.assigned_to,
            ch.action_type,
            ch.description as action_description,
            ch.date_created as action_date
        FROM complaints c
        LEFT JOIN registration r ON c.complainant_name = CONCAT(r.first_name, ' ', IFNULL(CONCAT(LEFT(r.middle_name, 1), '. '), ''), r.last_name, IFNULL(CONCAT(', ', r.suffix), ''))
        LEFT JOIN areas a ON r.area_id = a.area_id  
        LEFT JOIN blocks b ON r.block_id = b.block_id
        INNER JOIN complaint_history ch ON c.complaint_id = ch.complaint_id
        WHERE ch.assigned_to IS NOT NULL AND ch.assigned_to != ''
        ORDER BY c.date_received DESC
        """
        
        result = db.session.execute(text(query))
        complaints = result.fetchall()
        
        formatted_complaints = []
        for complaint in complaints:
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
            
            formatted_complaints.append({
                'complaint_id': complaint.complaint_id,
                'type_of_complaint': complaint.type_of_complaint,
                'complainant_name': formatted_name,
                'address': formatted_address,
                'priority_level': complaint.priority_level,
                'status': complaint.status,
                'complaint_stage': complaint.complaint_stage,
                'date_received': complaint.date_received.strftime('%Y-%m-%d') if complaint.date_received else '',
                'description': complaint.description,
                'assigned_to': complaint.assigned_to,
                'action_type': complaint.action_type,
                'action_description': complaint.action_description,
                'action_date': complaint.action_date.strftime('%Y-%m-%d') if complaint.action_date else ''
            })
        
        return jsonify(formatted_complaints)
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@complaints_bp.route('/api/invalid', methods=['GET'])
def get_invalid_complaints():
    """Get invalid complaints for admin"""
    try:
        # Check if user is admin
        if session.get('account') != 1:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        complaints = get_complaint_data(status_filter='invalid')
        
        return jsonify(complaints)
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@complaints_bp.route('/api/<int:complaint_id>/action', methods=['POST'])
def handle_complaint_action(complaint_id):
    """Handle admin actions on complaints"""
    try:
        # Check if user is admin
        if session.get('account') != 1:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        data = request.get_json()
        action_type = data.get('action_type')
        assigned_to = data.get('assigned_to')
        description = data.get('description', '')
        
        if not action_type:
            return jsonify({'success': False, 'message': 'Missing action type'}), 400
        
        # Insert into complaint_history
        insert_query = """
        INSERT INTO complaint_history (complaint_id, assigned_to, action_type, description, created_by, date_created)
        VALUES (:complaint_id, :assigned_to, :action_type, :description, :created_by, NOW())
        """
        
        db.session.execute(text(insert_query), {
            'complaint_id': complaint_id,
            'assigned_to': assigned_to,
            'action_type': action_type,
            'description': description,
            'created_by': session.get('name', 'Admin')
        })
        
        # Update complaint stage based on action
        new_stage = None
        if 'assign' in action_type.lower() or assigned_to:
            new_stage = 'Ongoing'
        elif 'resolved' in action_type.lower():
            new_stage = 'Resolved'
        
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
        if session.get('account') != 1:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        admin_name = session.get('name')
        
        # Update complaint stage to resolved
        update_query = "UPDATE complaints SET complaint_stage = 'Resolved' WHERE complaint_id = :complaint_id"
        db.session.execute(text(update_query), {'complaint_id': complaint_id})
        
        # Insert history record
        insert_query = """
        INSERT INTO complaint_history (complaint_id, action_type, description, created_by, date_created)
        VALUES (:complaint_id, 'Resolved', :description, :created_by, NOW())
        """
        
        db.session.execute(text(insert_query), {
            'complaint_id': complaint_id,
            'description': f'Complaint marked as resolved by {admin_name}',
            'created_by': admin_name
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
            SUM(CASE WHEN complaint_stage = 'Pending' THEN 1 ELSE 0 END) as pending,
            SUM(CASE WHEN complaint_stage = 'Ongoing' THEN 1 ELSE 0 END) as ongoing,
            SUM(CASE WHEN complaint_stage = 'Resolved' THEN 1 ELSE 0 END) as resolved,
            SUM(CASE WHEN complaint_stage != 'Resolved' THEN 1 ELSE 0 END) as unresolved,
            SUM(CASE WHEN status = 'Valid' THEN 1 ELSE 0 END) as valid,
            SUM(CASE WHEN status = 'Invalid' THEN 1 ELSE 0 END) as invalid
        FROM complaints
        """
        
        result = db.session.execute(text(stats_query))
        stats = result.fetchone()
        print(f"[DEBUG] Stats result: total={stats.total}, pending={stats.pending}, ongoing={stats.ongoing}, resolved={stats.resolved}, unresolved={stats.unresolved}")
        
        return jsonify({
            'total': stats.total or 0,
            'pending': stats.pending or 0,
            'ongoing': stats.ongoing or 0,
            'resolved': stats.resolved or 0,
            'unresolved': stats.unresolved or 0,
            'valid': stats.valid or 0,
            'invalid': stats.invalid or 0,
            'assigned': 0  # Will be calculated from complaint_history if needed
        })
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@complaints_bp.route("/api/complaint/<int:complaint_id>")
def api_complaint_details(complaint_id):
    """Get detailed complaint information"""
    try:
        # Check if user is admin or staff
        if session.get('account') not in [1, 2]:
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
            ch.action_type,
            ch.description as action_description,
            ch.date_created as action_date,
            ch.created_by
        FROM complaints c
        LEFT JOIN registration r ON c.complainant_name = CONCAT(r.first_name, ' ', IFNULL(CONCAT(LEFT(r.middle_name, 1), '. '), ''), r.last_name, IFNULL(CONCAT(', ', r.suffix), ''))
        LEFT JOIN areas a ON r.area_id = a.area_id  
        LEFT JOIN blocks b ON r.block_id = b.block_id
        LEFT JOIN complaint_history ch ON c.complaint_id = ch.complaint_id
        WHERE c.complaint_id = :complaint_id
        ORDER BY ch.date_created DESC
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
        
        return jsonify(result_data)
        
    except Exception as e:
        print(f"Error getting complaint details: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@complaints_bp.route("/api/staff")
def api_get_staff():
    """Get list of staff members for assignment"""
    try:
        # Check if user is admin
        if session.get('account') != 1:
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
    """Add action to complaint"""
    try:
        # Check if user is admin
        if session.get('account') != 1:
            return jsonify({'error': 'Unauthorized'}), 403
            
        data = request.get_json()
        complaint_id = data.get('complaint_id')
        action_type = data.get('action_type')
        description = data.get('description')
        assigned_to = data.get('assigned_to')
        
        if not complaint_id or not action_type:
            return jsonify({'error': 'Missing required fields'}), 400
        
        # Insert into complaint_history
        insert_query = """
        INSERT INTO complaint_history (complaint_id, assigned_to, action_type, description, created_by, date_created)
        VALUES (:complaint_id, :assigned_to, :action_type, :description, :created_by, NOW())
        """
        
        db.session.execute(text(insert_query), {
            'complaint_id': complaint_id,
            'assigned_to': assigned_to,
            'action_type': action_type,
            'description': description,
            'created_by': session.get('name', 'Admin')
        })
        
        # Update complaint stage if action_type indicates a status change
        if action_type in ['Assign', 'Investigation']:
            update_query = "UPDATE complaints SET complaint_stage = 'Ongoing' WHERE complaint_id = :complaint_id"
            db.session.execute(text(update_query), {'complaint_id': complaint_id})
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Action added successfully'})
        
    except Exception as e:
        print(f"Error adding action: {e}")
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500

@complaints_bp.route("/api/resolve", methods=['POST'])
def api_resolve_complaint():
    """Resolve a complaint"""
    try:
        # Check if user is admin
        if session.get('account') != 1:
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
        INSERT INTO complaint_history (complaint_id, action_type, description, created_by, date_created)
        VALUES (:complaint_id, 'Resolved', 'Complaint has been resolved', :created_by, NOW())
        """
        
        db.session.execute(text(insert_query), {
            'complaint_id': complaint_id,
            'created_by': session.get('name', 'Admin')
        })
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Complaint resolved successfully'})
        
    except Exception as e:
        print(f"Error resolving complaint: {e}")
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500
