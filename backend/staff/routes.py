import os
from flask import Blueprint, request, jsonify, session, redirect, Response
from ..database.models import Admin, Complaint, ComplaintHistory, Area
from ..database.db import db

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

@staff_bp.route('/complaints/assigned')
def assigned_complaints():
    """Show complaints assigned to the current staff member"""
    auth_check = require_staff_auth()
    if auth_check:
        return auth_check
    
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
    
    return Response(html_content, mimetype='text/html')

@staff_bp.route('/complaints/resolved')
def resolved_complaints():
    """Show complaints resolved by the current staff member"""
    auth_check = require_staff_auth()
    if auth_check:
        return auth_check
    
    # Read the HTML file and inject staff navigation
    html_path = os.path.join(frontend_path, "admin", "staff", "complaints", "resolved.html")
    print(f"[DEBUG] Loading HTML from: {html_path}")  # Debug log
    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # Replace the empty navigation with staff navigation  
    staff_nav = '<a href="/staff/complaints/assigned" class="nav-item">Complaints</a>'
    original_nav = '<!-- Navigation will be populated by navigation.js -->'
    if original_nav in html_content:
        print(f"[DEBUG] Replacing navigation for staff user: {session.get('admin_name')}")  # Debug log
        html_content = html_content.replace(original_nav, staff_nav)
    else:
        print(f"[DEBUG] Navigation placeholder not found in resolved.html")  # Debug log
    
    return Response(html_content, mimetype='text/html')

@staff_bp.route('/api/complaints/assigned')
def api_assigned_complaints():
    """API endpoint for assigned complaints data"""
    auth_check = require_staff_auth()
    if auth_check:
        return jsonify({'error': 'Unauthorized'}), 401
    
    staff_name = session.get('admin_name')
    
    try:
        from sqlalchemy import text
        
        # Get complaints assigned to this staff member that are not resolved
        query = """
        SELECT DISTINCT
            c.complaint_id,
            c.date_received,
            c.type_of_complaint,
            c.status,
            c.complaint_stage,
            c.priority_level,
            c.description,
            r.first_name,
            r.middle_name,
            r.last_name,
            r.suffix,
            r.lot_no,
            b.block_no,
            a.area_name,
            ch.assigned_to
        FROM complaints c
        LEFT JOIN registration r ON c.complainant_name = CONCAT(r.first_name, ' ', IFNULL(CONCAT(LEFT(r.middle_name, 1), '. '), ''), r.last_name, IFNULL(CONCAT(', ', r.suffix), ''))
        LEFT JOIN areas a ON r.area_id = a.area_id
        LEFT JOIN blocks b ON r.block_id = b.block_id
        INNER JOIN complaint_history ch ON c.complaint_id = ch.complaint_id
        WHERE c.status = 'Valid' 
        AND ch.assigned_to = :staff_name
        AND c.complaint_stage != 'Resolved'
        ORDER BY c.date_received DESC
        """
        
        result = db.session.execute(text(query), {'staff_name': staff_name})
        complaints = result.fetchall()
        
        # Format the data
        complaints_data = []
        for complaint in complaints:
            # Format complainant name
            name_parts = []
            if complaint['first_name']:
                name_parts.append(complaint['first_name'].strip())
            if complaint['middle_name']:
                middle_initial = complaint['middle_name'].strip()[:1] + "." if complaint['middle_name'].strip() else ""
                if middle_initial:
                    name_parts.append(middle_initial)
            if complaint['last_name']:
                name_parts.append(complaint['last_name'].strip())
            formatted_name = " ".join(name_parts)
            if complaint['suffix'] and complaint['suffix'].strip():
                formatted_name += f", {complaint['suffix'].strip()}"
            
            # Format address
            address_parts = []
            if complaint['area_name']:
                address_parts.append(complaint['area_name'].strip())
            if complaint['block_no']:
                address_parts.append(f"Block {int(complaint['block_no'])}")
            if complaint['lot_no']:
                address_parts.append(f"Lot {int(complaint['lot_no'])}")
            formatted_address = ", ".join(address_parts)
            
            complaints_data.append({
                'complaint_id': complaint['complaint_id'],
                'date_received': complaint['date_received'].strftime('%m/%d/%Y') if complaint['date_received'] else 'N/A',
                'complainant': formatted_name,
                'type_of_complaint': complaint['type_of_complaint'] or 'N/A',
                'hoa': complaint['area_name'] or 'N/A',
                'address': formatted_address,
                'action_needed': 'Investigation',
                'priority_level': complaint['priority_level'] or 'Minor',
                'complaint_stage': complaint['complaint_stage']
            })
        
        return jsonify({
            'success': True,
            'complaints': complaints_data
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@staff_bp.route('/api/complaints/resolved')
def api_resolved_complaints():
    """API endpoint for resolved complaints data"""
    auth_check = require_staff_auth()
    if auth_check:
        return jsonify({'error': 'Unauthorized'}), 401
    
    staff_name = session.get('admin_name')
    
    try:
        from sqlalchemy import text
        
        # Get resolved complaints assigned to this staff member
        query = """
        SELECT DISTINCT
            c.complaint_id,
            c.date_received,
            c.type_of_complaint,
            c.status,
            c.complaint_stage,
            c.priority_level,
            c.description,
            r.first_name,
            r.middle_name,
            r.last_name,
            r.suffix,
            r.lot_no,
            b.block_no,
            a.area_name,
            ch.assigned_to
        FROM complaints c
        LEFT JOIN registration r ON c.complainant_name = CONCAT(r.first_name, ' ', IFNULL(CONCAT(LEFT(r.middle_name, 1), '. '), ''), r.last_name, IFNULL(CONCAT(', ', r.suffix), ''))
        LEFT JOIN areas a ON r.area_id = a.area_id
        LEFT JOIN blocks b ON r.block_id = b.block_id
        INNER JOIN complaint_history ch ON c.complaint_id = ch.complaint_id
        WHERE c.status = 'Valid' 
        AND ch.assigned_to = :staff_name
        AND c.complaint_stage = 'Resolved'
        ORDER BY c.date_received DESC
        """
        
        result = db.session.execute(text(query), {'staff_name': staff_name})
        complaints = result.fetchall()
        
        # Format the data
        complaints_data = []
        for complaint in complaints:
            # Format complainant name
            name_parts = []
            if complaint['first_name']:
                name_parts.append(complaint['first_name'].strip())
            if complaint['middle_name']:
                middle_initial = complaint['middle_name'].strip()[:1] + "." if complaint['middle_name'].strip() else ""
                if middle_initial:
                    name_parts.append(middle_initial)
            if complaint['last_name']:
                name_parts.append(complaint['last_name'].strip())
            formatted_name = " ".join(name_parts)
            if complaint['suffix'] and complaint['suffix'].strip():
                formatted_name += f", {complaint['suffix'].strip()}"
            
            # Format address
            address_parts = []
            if complaint['area_name']:
                address_parts.append(complaint['area_name'].strip())
            if complaint['block_no']:
                address_parts.append(f"Block {int(complaint['block_no'])}")
            if complaint['lot_no']:
                address_parts.append(f"Lot {int(complaint['lot_no'])}")
            formatted_address = ", ".join(address_parts)
            
            complaints_data.append({
                'complaint_id': complaint['complaint_id'],
                'date_received': complaint['date_received'].strftime('%m/%d/%Y') if complaint['date_received'] else 'N/A',
                'complainant': formatted_name,
                'type_of_complaint': complaint['type_of_complaint'] or 'N/A',
                'hoa': complaint['area_name'] or 'N/A',
                'address': formatted_address,
                'action_needed': 'Investigation',
                'priority_level': complaint['priority_level'] or 'Minor',
                'complaint_stage': complaint['complaint_stage']
            })
        
        return jsonify({
            'success': True,
            'complaints': complaints_data
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@staff_bp.route('/api/stats')
def api_staff_stats():
    """API endpoint for staff complaint statistics"""
    auth_check = require_staff_auth()
    if auth_check:
        return jsonify({'error': 'Unauthorized'}), 401
    
    staff_name = session.get('admin_name')
    
    try:
        from sqlalchemy import text
        
        # Get total assigned to this staff (not resolved)
        assigned_query = """
            SELECT COUNT(DISTINCT c.complaint_id) as count 
            FROM complaints c
            INNER JOIN complaint_history ch ON c.complaint_id = ch.complaint_id
            WHERE c.status = 'Valid' 
            AND ch.assigned_to = :staff_name
            AND c.complaint_stage != 'Resolved'
        """
        result = db.session.execute(text(assigned_query), {'staff_name': staff_name})
        total_assigned = result.scalar()
        
        # Get resolved by this staff
        resolved_query = """
            SELECT COUNT(DISTINCT c.complaint_id) as count 
            FROM complaints c
            INNER JOIN complaint_history ch ON c.complaint_id = ch.complaint_id
            WHERE c.status = 'Valid' 
            AND c.complaint_stage = 'Resolved' 
            AND ch.assigned_to = :staff_name
        """
        result = db.session.execute(text(resolved_query), {'staff_name': staff_name})
        resolved_count = result.scalar()
        
        return jsonify({
            'success': True,
            'total_assigned': total_assigned,
            'resolved': resolved_count
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@staff_bp.route('/complaints/details/<int:complaint_id>')
def complaint_details(complaint_id):
    """Show complaint details for staff members"""
    auth_check = require_staff_auth()
    if auth_check:
        return auth_check
    
    try:
        # Get the specific complaint and verify staff access
        from backend.database.models import Complaint
        
        staff_name = session.get('admin_name')
        complaint = Complaint.query.filter_by(id=complaint_id, assigned_staff=staff_name).first()
        
        if not complaint:
            return "Complaint not found or not assigned to you", 404
        
        # Read the HTML file and inject staff navigation
        html_path = os.path.join(frontend_path, "admin", "staff", "complaints", "complaint_details_valid.html")
        print(f"[DEBUG] Loading HTML from: {html_path}")  # Debug log
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        # Replace the empty navigation with staff navigation
        staff_nav = '<a href="/staff/complaints/assigned" class="nav-item">Complaints</a>'
        original_nav = '<!-- Navigation will be populated by navigation.js -->'
        if original_nav in html_content:
            print(f"[DEBUG] Replacing navigation for staff user: {session.get('admin_name')}")  # Debug log
            html_content = html_content.replace(original_nav, staff_nav)
        else:
            print(f"[DEBUG] Navigation placeholder not found in complaint_details_valid.html")  # Debug log
        
        return Response(html_content, mimetype='text/html')
        
    except Exception as e:
        print(f"Error loading complaint details: {e}")
        return f"Error: {e}", 500
