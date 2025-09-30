import os
from flask import Blueprint, render_template, request, jsonify, session, redirect, send_file
from ..database.models import Complaints, ComplaintHistory, Area, Admin
from ..database.db import db

shared_bp = Blueprint('shared', __name__, url_prefix='/complaints')

# Path to frontend
frontend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../frontend"))

def is_authenticated():
    """Check if user is logged in"""
    return 'admin_id' in session and 'admin_name' in session

@shared_bp.route('/details/<int:complaint_id>')
def complaint_details(complaint_id):
    """Shared complaint details page for both admin and staff"""
    if not is_authenticated():
        return redirect('/portal/admin_login.html')
    
    # Determine if user is staff or admin for appropriate template rendering
    staff_names = ['Alberto Nonato Jr.', 'Maybelen Jamorawon', 'Agnes Bartolome']
    is_staff = session.get('admin_name') in staff_names
    
    if is_staff:
        return send_file(os.path.join(frontend_path, "admin", "staff", "complaints", "complaint_details_valid.html"))
    else:
        return send_file(os.path.join(frontend_path, "admin", "complaints", "complaint_details_valid.html"))

@shared_bp.route('/api/details/<int:complaint_id>')
def api_complaint_details(complaint_id):
    """API endpoint for complaint details"""
    if not is_authenticated():
        return jsonify({'error': 'Unauthorized'}), 401
    
    # Check if user is staff and restrict access accordingly
    staff_names = ['Alberto Nonato Jr.', 'Maybelen Jamorawon', 'Agnes Bartolome']
    is_staff = session.get('admin_name') in staff_names
    
    try:
        # Get complaint details with area information
        complaint = db.session.query(
            Complaints,
            Area.area_name
        ).join(
            Area, Complaints.area_id == Area.area_id
        ).filter(
            Complaints.complaint_id == complaint_id
        ).first()
        
        if not complaint:
            return jsonify({'error': 'Complaint not found'}), 404
        
        # If user is staff, verify they have access to this complaint
        if is_staff:
            staff_name = session.get('admin_name')
            # Check if this complaint is assigned to the current staff member
            has_access = db.session.query(ComplaintHistory).filter(
                ComplaintHistory.complaint_id == complaint_id,
                ComplaintHistory.assigned_to == staff_name
            ).first()
            
            if not has_access:
                return jsonify({'error': 'Access denied - complaint not assigned to you'}), 403
        
        complaint_data, area_name = complaint
        
        # Get complaint history/timeline
        history = db.session.query(ComplaintHistory).filter_by(
            complaint_id=complaint_id
        ).order_by(ComplaintHistory.created_at.desc()).all()
        
        timeline_data = []
        for entry in history:
            timeline_data.append({
                'date': entry.created_at.strftime('%m/%d/%Y') if entry.created_at else 'N/A',
                'action_type': entry.action_type or 'N/A',
                'description': entry.description or 'No description provided',
                'assigned_to': entry.assigned_to or 'Unassigned',
                'status': entry.status or 'pending',
                'files': entry.files or []
            })
        
        return jsonify({
            'success': True,
            'complaint': {
                'complaint_id': complaint_data.complaint_id,
                'complainant': f"{complaint_data.first_name or ''} {complaint_data.middle_initial or ''} {complaint_data.last_name or ''}".strip(),
                'complaint_type': complaint_data.complaint_type,
                'date_submitted': complaint_data.date_submitted.strftime('%m/%d/%Y') if complaint_data.date_submitted else 'N/A',
                'area_name': area_name,
                'block_no': complaint_data.block_no,
                'lot_no': complaint_data.lot_no,
                'priority_level': complaint_data.priority_level,
                'description': complaint_data.description,
                'coordinates': complaint_data.coordinates
            },
            'timeline': timeline_data
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500