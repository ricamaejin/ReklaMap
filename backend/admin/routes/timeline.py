from flask import Blueprint, jsonify, request
from ...database.db import db
from ...database.models import ComplaintHistory

def generate_action_description(action_type, assigned_to):
    """Generate a description for the action since description column may not exist in database"""
    descriptions = {
        'Assessment': f'Assessment completed by {assigned_to}' if assigned_to else 'Assessment completed',
        'Mediation': f'Mediation session conducted by {assigned_to}' if assigned_to else 'Mediation session conducted',
        'Inspection': f'Site inspection completed by {assigned_to}' if assigned_to else 'Site inspection completed',
        'Invitation': f'Invitation sent by {assigned_to}' if assigned_to else 'Invitation sent to involved parties',
        'Accepted Invitation': 'Both parties have accepted the invitation',
        'Task Completed': 'Task completed and passed back to admin',
        'Task completed/resolved, passed to admin': 'Task completed/resolved, passed to admin',
        'Submitted': 'Submitted a valid complaint',
        'Resolved': 'Complaint resolved'
    }
    return descriptions.get(action_type, f'{action_type} action completed')

from sqlalchemy import text
import json

timeline_bp = Blueprint("timeline", __name__, url_prefix="/admin/complaints")

@timeline_bp.route('/api/timeline/<int:complaint_id>', methods=['GET'])
def get_complaint_timeline(complaint_id):
    """Get timeline entries for a specific complaint with role-based filtering"""
    try:
        # Get role parameter from query string (default to 'admin')
        role = request.args.get('role', 'admin').lower()
        
        # Validate role
        if role not in ['admin', 'staff', 'complainant']:
            role = 'admin'
        
        # Query real data from database using actual structure (details JSON column instead of description)
        query = text("""
            SELECT 
                ch.history_id,
                ch.complaint_id,
                ch.type_of_action,
                ch.assigned_to,
                ch.action_datetime,
                ch.details,
                0 as has_file,
                NULL as file_path,
                NULL as file_name
            FROM complaint_history ch
            WHERE ch.complaint_id = :complaint_id
            ORDER BY ch.action_datetime DESC
        """)
        
        try:
            result = db.session.execute(query, {'complaint_id': complaint_id})
            entries = result.fetchall()
            print(f"Timeline query for complaint {complaint_id} returned {len(entries)} entries")
        except Exception as query_error:
            print(f"Timeline query failed: {query_error}")
            entries = []
        
        # Convert to list of dictionaries - only real data, no sample data
        timeline_entries = []
        
        for entry in entries:
            # Parse details JSON field and extract description or generate one
            details_dict = {}
            description = ''
            
            try:
                if entry.details:
                    import json
                    details_dict = json.loads(entry.details) if isinstance(entry.details, str) else entry.details
                    # Try to get description from details, or generate one
                    description = details_dict.get('description', '') or generate_action_description(entry.type_of_action, entry.assigned_to)
                else:
                    description = generate_action_description(entry.type_of_action, entry.assigned_to)
            except (json.JSONDecodeError, TypeError):
                description = generate_action_description(entry.type_of_action, entry.assigned_to)
                details_dict = {}
            
            timeline_entry = {
                'history_id': entry.history_id,
                'complaint_id': entry.complaint_id,
                'type_of_action': entry.type_of_action,
                'assigned_to': entry.assigned_to,
                'description': description,
                'action_datetime': entry.action_datetime.isoformat() if entry.action_datetime else '',
                'details': details_dict,
                'has_file': bool(entry.has_file),
                'file_path': entry.file_path,
                'file_name': entry.file_name
            }
            
            # Create dual entries for staff assignments (one for assignment, one for completion)
            if entry.type_of_action in ['Inspection', 'Invitation'] and entry.assigned_to:
                # Add assignment entry
                assignment_entry = timeline_entry.copy()
                assignment_entry['type_of_action'] = f"Assign {entry.type_of_action}"
                assignment_entry['description'] = f"{entry.type_of_action} assigned to {entry.assigned_to}"
                timeline_entries.append(assignment_entry)
                
                # Add completion entry (modify original)
                timeline_entry['description'] = f"{entry.type_of_action} completed by {entry.assigned_to}"
            
            timeline_entries.append(timeline_entry)
        
        # If no entries found, return empty array (no sample data)
        print(f"Processed {len(timeline_entries)} timeline entries for complaint {complaint_id}")
        
        # Apply role-based filtering
        filtered_entries = filter_entries_by_role(timeline_entries, role)
        
        return jsonify({
            'success': True,
            'timeline': filtered_entries,
            'role': role,
            'total_entries': len(filtered_entries)
        })
        
    except Exception as e:
        print(f"Error getting timeline for complaint {complaint_id}: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'timeline': []
        }), 500

def generate_action_description(action_type, assigned_to):
    """Generate a description for the action since description column may not exist in database"""
    descriptions = {
        'Assessment': f'Assessment completed by {assigned_to}' if assigned_to else 'Assessment completed',
        'Mediation': f'Mediation session conducted by {assigned_to}' if assigned_to else 'Mediation session conducted',
        'Inspection': f'Site inspection completed by {assigned_to}' if assigned_to else 'Site inspection completed',
        'Invitation': f'Invitation sent by {assigned_to}' if assigned_to else 'Invitation sent to involved parties',
        'Task Completed': 'Task completed and passed back to admin'
    }
    return descriptions.get(action_type, f'{action_type} action completed')

def filter_entries_by_role(entries, role):
    """Filter timeline entries based on user role"""
    if role == 'admin':
        # Admin sees all entries
        return entries
    
    elif role == 'staff':
        # Staff sees actions they performed + current status + Task completed/resolved passed to admin
        staff_entries = []
        for entry in entries:
            # Include if assigned to staff, is a task completion, or shows current status
            if (entry.get('assigned_to') and 
                ('staff' in entry['assigned_to'].lower() or 
                 entry['assigned_to'].lower() in ['ram', 'inspector', 'field_staff'])) or \
               entry.get('type_of_action') in ['Task Completed', 'Resolved', 'Task completed/resolved, passed to admin']:
                staff_entries.append(entry)
        
        # Ensure staff timeline ends with task completion
        has_completion = any(entry.get('type_of_action') in ['Task Completed', 'Resolved', 'Task completed/resolved, passed to admin'] for entry in staff_entries)
        if not has_completion and staff_entries:
            # Add a completion entry if none exists
            completion_entry = staff_entries[-1].copy()
            completion_entry['type_of_action'] = 'Task completed/resolved, passed to admin'
            completion_entry['description'] = 'Task completed/resolved, passed to admin'
            staff_entries.append(completion_entry)
        
        return staff_entries
    
    elif role == 'complainant':
        # Complainant sees simplified view: only completed task milestones
        milestone_actions = ['Inspection', 'Invitation', 'Assessment', 'Mediation', 'Resolved']
        complainant_entries = []
        
        # Always start with submission
        if entries:
            submission_entry = entries[0].copy()
            submission_entry['type_of_action'] = 'Submitted'
            submission_entry['description'] = 'Submitted a valid complaint'
            complainant_entries.append(submission_entry)
        
        # Add only completed milestones (not assignments)
        for entry in entries:
            if (entry.get('type_of_action') in milestone_actions and 
                not entry['type_of_action'].startswith('Assign')):
                complainant_entries.append(entry)
        
        return complainant_entries
    
    return entries
