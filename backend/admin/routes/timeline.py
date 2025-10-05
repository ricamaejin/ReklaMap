from flask import Blueprint, jsonify, request
from ...database.db import db
from ...database.models import ComplaintHistory

def generate_action_description(action_type, assigned_to, role='admin'):
    """Generate descriptions based on UPDATED SEQUENTIAL FLOW requirements"""
    
    # ADMIN VIEW (admin.account == 1) - Only 7 allowed statuses
    admin_descriptions = {
        'Submitted': 'Submitted a Valid Complaint (default status after complaint submitted)',
        'Inspection': f'Site inspection assigned to {assigned_to}' if assigned_to else 'Inspection task assigned to staff',
        'Inspection done': f'Site inspection completed by {assigned_to}' if assigned_to else 'Site inspection completed by staff',
        'Send Invitation': f'Send Invitation task assigned to {assigned_to}' if assigned_to else 'Send Invitation task assigned to staff', 
        'Sent Invitation': f'Invitation sent by {assigned_to}' if assigned_to else 'Invitation sent to involved parties by staff',
        'Task Completed': 'Task completed by staff and passed back to admin',
        'Resolved': 'Complaint resolved and moved to resolved view'
    }
    
    # STAFF VIEW (admin.account == 2) - Previously saved status entries + Task Completed
    staff_descriptions = {
        'Submitted': 'Complaint submitted and validated',
        'Assessment': 'Initial assessment completed by admin',
        'Inspection': f'Site inspection assigned to you ({assigned_to})' if assigned_to else 'Site inspection assigned to you',
        'Inspection done': 'Site inspection completed - task done',
        'Invitation': f'Send Invitation assigned to you ({assigned_to})' if assigned_to else 'Send Invitation assigned to you',
        'Sent Invitation': 'Invitation sent to parties - task done', 
        'Task Completed': 'Task completed and passed back to admin for further processing'
    }
    
    # COMPLAINANT VIEW - Simplified milestones only
    complainant_descriptions = {
        'Submitted': 'Submitted a valid complaint',
        'Inspection done': 'Site inspection completed',
        'Sent Invitation': 'Invitation sent to involved parties',
        'Assessment': 'Assessment completed',
        'Resolved': 'Complaint has been resolved'
    }
    
    # Select appropriate description set based on role
    if role == 'staff':
        descriptions = staff_descriptions
    elif role == 'complainant':
        descriptions = complainant_descriptions
    else:
        descriptions = admin_descriptions
    
    return descriptions.get(action_type, f'{action_type} completed')

from sqlalchemy import text
import json

timeline_bp = Blueprint("timeline", __name__, url_prefix="/admin/complaints")

# Add test data route for debugging timeline
@timeline_bp.route('/api/timeline/test/<int:complaint_id>', methods=['POST'])
def add_test_timeline_data(complaint_id):
    """Add test timeline data for a complaint - for debugging purposes"""
    try:
        from datetime import datetime, timedelta
        from ...database.models import ComplaintHistory
        
        # Check if test data already exists
        existing = ComplaintHistory.query.filter_by(complaint_id=complaint_id).first()
        if existing:
            return jsonify({
                'success': True,
                'message': 'Test data already exists for this complaint'
            })
        
        # Create test timeline entries
        test_entries = [
            {
                'action_type': 'Assessment',
                'assigned_to': 'Admin Staff',
                'description': 'Initial assessment completed',
                'date_offset': 0  # Current time
            },
            {
                'action_type': 'Inspection',
                'assigned_to': 'Inspector John',
                'description': 'Site inspection assigned to field staff',
                'date_offset': -1  # 1 day ago
            },
            {
                'action_type': 'Invitation',
                'assigned_to': 'Assistant Mary',
                'description': 'Invitation sent to involved parties',
                'date_offset': -2  # 2 days ago
            }
        ]
        
        for entry_data in test_entries:
            entry_date = datetime.now() + timedelta(days=entry_data['date_offset'])
            
            details = {
                'description': entry_data['description']
            }
            
            timeline_entry = ComplaintHistory(
                complaint_id=complaint_id,
                type_of_action=entry_data['action_type'],
                assigned_to=entry_data['assigned_to'],
                details=details,
                action_datetime=entry_date
            )
            db.session.add(timeline_entry)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Added {len(test_entries)} test timeline entries for complaint {complaint_id}'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@timeline_bp.route('/api/timeline/<int:complaint_id>', methods=['GET'])
def get_complaint_timeline(complaint_id):
    """Get timeline entries for a specific complaint with role-based filtering"""
    try:
        # Get role parameter from query string (default to 'admin')
        role = request.args.get('role', 'admin').lower()
        
        # Validate role
        if role not in ['admin', 'staff', 'complainant']:
            role = 'admin'
        
        # Query real data from database using actual database structure
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
                NULL as file_name,
                1 as admin_account_type,
                0 as completed_by_staff
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
            # Extract description from details JSON field or generate one
            description = ''
            try:
                if entry.details:
                    import json
                    details_dict = json.loads(entry.details) if isinstance(entry.details, str) else entry.details
                    description = details_dict.get('description', '') or generate_action_description(entry.type_of_action, entry.assigned_to)
                else:
                    description = generate_action_description(entry.type_of_action, entry.assigned_to)
            except (json.JSONDecodeError, TypeError):
                description = generate_action_description(entry.type_of_action, entry.assigned_to)
            
            timeline_entry = {
                'history_id': entry.history_id,
                'complaint_id': entry.complaint_id,
                'type_of_action': entry.type_of_action,
                'assigned_to': entry.assigned_to,
                'description': description,
                'action_datetime': entry.action_datetime.isoformat() if entry.action_datetime else '',
                'details': {},
                'has_file': bool(entry.has_file),
                'file_path': entry.file_path,
                'file_name': entry.file_name,
                'admin_account_type': getattr(entry, 'admin_account_type', 1),  # Default to admin entries
                'completed_by_staff': getattr(entry, 'completed_by_staff', False)
            }
            
            # Only show actual database entries - no artificial dual entries
            # Assignment entries are created when admin assigns tasks
            # Completion entries are only created when staff completes tasks via Update button
            timeline_entries.append(timeline_entry)
        
        # If no entries found, return empty array (no sample data)
        print(f"Processed {len(timeline_entries)} timeline entries for complaint {complaint_id}")
        
        # Apply role-based filtering
        print(f'[TIMELINE API] Before filtering: {len(timeline_entries)} entries')
        print(f'[TIMELINE API] Raw entries: {[entry.get("type_of_action") for entry in timeline_entries]}')
        
        filtered_entries = filter_entries_by_role(timeline_entries, role)
        
        print(f'[TIMELINE API] After filtering for {role}: {len(filtered_entries)} entries')
        print(f'[TIMELINE API] Filtered entries: {[entry.get("type_of_action") for entry in filtered_entries]}')
        
        return jsonify({
            'success': True,
            'timeline': filtered_entries,
            'role': role,
            'total_entries': len(filtered_entries),
            'debug_info': {
                'original_count': len(timeline_entries),
                'filtered_count': len(filtered_entries),
                'original_actions': [entry.get("type_of_action") for entry in timeline_entries],
                'filtered_actions': [entry.get("type_of_action") for entry in filtered_entries]
            }
        })
        
    except Exception as e:
        print(f"Error getting timeline for complaint {complaint_id}: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'timeline': []
        }), 500

def filter_entries_by_role(entries, role):
    """Filter timeline entries based on UPDATED SEQUENTIAL FLOW requirements"""
    
    if role == 'admin':
        # ADMIN VIEW (admin.account == 1): Full sequential flow
        # 1. "Submitted a Valid Complaint" → 2. "Inspection" → 3. "Inspection done" → 
        # 4. "Send Invitation" → 5. "Sent Invitation" → 6. "Accepted Invitation" → 
        # 7. "Mediation" → 8. "Assessment" → moves to resolved.html
        return entries
    
    elif role == 'staff':
        # STAFF VIEW (admin.account == 2): Show ALL admin entries (account_type=1) 
        # PLUS any staff completed entries. Frontend will handle additional filtering.
        print(f'[BACKEND STAFF FILTER] Processing {len(entries)} entries for staff view')
        
        staff_entries = []
        for entry in entries:
            entry_type = entry.get('type_of_action', '')
            admin_account = entry.get('admin_account_type', 1)
            completed_by_staff = entry.get('completed_by_staff', False)
            
            # Show all admin entries (from admin account type 1)
            if admin_account == 1:
                print(f'[BACKEND STAFF FILTER] Including admin entry: {entry_type}')
                staff_entries.append(entry)
            # Show staff completed entries  
            elif completed_by_staff:
                print(f'[BACKEND STAFF FILTER] Including staff completed entry: {entry_type}')
                staff_entries.append(entry)
            else:
                print(f'[BACKEND STAFF FILTER] Filtering out entry: {entry_type} (admin_account={admin_account}, completed_by_staff={completed_by_staff})')
        
        print(f'[BACKEND STAFF FILTER] Returning {len(staff_entries)} entries to staff view')
        return staff_entries
    
    elif role == 'complainant':
        # COMPLAINANT VIEW: Simplified View - Shows only completed task milestones
        # ✅ Submitted a valid complaint → ✅ Inspection done → ✅ Invitation Sent → 
        # ✅ Assessment → ✅ Resolved
        complainant_entries = []
        
        # Always include submission as first entry
        submission_entry = {
            'type_of_action': 'Submitted',
            'description': 'Submitted a valid complaint',
            'assigned_to': '',
            'action_datetime': entries[0]['action_datetime'] if entries else '',
            'has_file': False
        }
        complainant_entries.append(submission_entry)
        
        # Include only completed milestones (complainant-focused)
        milestone_actions = ['Inspection done', 'Sent Invitation', 'Assessment', 'Resolved']
        for entry in entries:
            if entry.get('type_of_action') in milestone_actions:
                # Simplify description for complainant view
                simplified_entry = entry.copy()
                action_type = entry['type_of_action']
                
                if action_type == 'Inspection done':
                    simplified_entry['description'] = 'Site inspection completed'
                elif action_type == 'Sent Invitation':
                    simplified_entry['description'] = 'Invitation sent to involved parties'
                elif action_type == 'Assessment':
                    simplified_entry['description'] = 'Assessment completed'
                elif action_type == 'Resolved':
                    simplified_entry['description'] = 'Complaint has been resolved'
                
                # Remove staff assignment details for clean complainant view
                simplified_entry['assigned_to'] = ''
                complainant_entries.append(simplified_entry)
        
        return complainant_entries
    
    return entries
