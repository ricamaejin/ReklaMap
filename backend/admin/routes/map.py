import os
from flask import Blueprint, send_file, render_template_string, abort, jsonify
from backend.database.models import Area

map_bp = Blueprint("map", __name__, url_prefix="/admin/map")

# Path to frontend
frontend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../frontend"))

# Default dashboard route
@map_bp.route("/")
def dashboard():
    return send_file(os.path.join(frontend_path, "admin", "map", "index.html"))

# 👇 Extra route so `/admin/map/index.html` also works
@map_bp.route("/index.html")
def dashboard_index():
    return send_file(os.path.join(frontend_path, "admin", "map", "index.html"))

# 🆕 Dynamic area route - serves map.html with area data
@map_bp.route("/<area_code>")
def map_area(area_code):
    # Look up area by code
    area = Area.query.filter_by(area_code=area_code.lower()).first()
    if not area:
        abort(404)
    
    # Serve the dynamic map.html
    html_path = os.path.join(frontend_path, "admin", "map", "map.html")
    if os.path.exists(html_path):
        return send_file(html_path)
    else:
        abort(404)

# 🆕 SVG file route - serves area SVG files
@map_bp.route("/svg/<area_code>.svg")
def serve_area_svg(area_code):
    svg_path = os.path.join(frontend_path, "admin", "map", "svg", f"{area_code.lower()}.svg")
    if os.path.exists(svg_path):
        return send_file(svg_path, mimetype='image/svg+xml')
    else:
        abort(404)

# 🆕 API endpoint to get complaint stats for an area
@map_bp.route("/api/complaints/<int:area_id>")
def get_complaint_stats(area_id):
    from backend.database.db import db
    from sqlalchemy import text
    
    try:
        # Get area_code for this area_id first to handle different join patterns
        area_query = text("SELECT area_code FROM areas WHERE area_id = :area_id")
        area_result = db.session.execute(area_query, {'area_id': area_id})
        area_row = area_result.fetchone()
        
        if not area_row:
            return jsonify({"total": 0, "resolved": 0, "ongoing": 0, "unresolved": 0}), 404
            
        area_code = area_row[0]
        
        # Total Complaints: Count based on registration_id from complaints table, 
        # joined with both beneficiaries.area_id and registration.hoa patterns
        total_query = text("""
            SELECT COUNT(DISTINCT c.complaint_id) as total_count
            FROM complaints c
            LEFT JOIN registration r ON c.registration_id = r.registration_id
            LEFT JOIN beneficiaries b ON r.beneficiary_id = b.beneficiary_id
            LEFT JOIN areas a1 ON b.area_id = a1.area_id
            LEFT JOIN areas a2 ON r.hoa = a2.area_code OR r.hoa = a2.area_name
            WHERE (b.area_id = :area_id OR a2.area_id = :area_id)
        """)
        
        total_result = db.session.execute(total_query, {'area_id': area_id})
        total_count = total_result.fetchone()[0] or 0
        
        # Ongoing Complaints: Count where complaint_stage == 'Ongoing'
        ongoing_query = text("""
            SELECT COUNT(DISTINCT c.complaint_id) as ongoing_count
            FROM complaints c
            LEFT JOIN registration r ON c.registration_id = r.registration_id
            LEFT JOIN beneficiaries b ON r.beneficiary_id = b.beneficiary_id
            LEFT JOIN areas a1 ON b.area_id = a1.area_id
            LEFT JOIN areas a2 ON r.hoa = a2.area_code OR r.hoa = a2.area_name
            WHERE (b.area_id = :area_id OR a2.area_id = :area_id) AND c.complaint_stage = 'Ongoing'
        """)
        
        ongoing_result = db.session.execute(ongoing_query, {'area_id': area_id})
        ongoing_count = ongoing_result.fetchone()[0] or 0
        
        # Resolved Complaints: Count where complaint_stage == 'Resolved'
        resolved_query = text("""
            SELECT COUNT(DISTINCT c.complaint_id) as resolved_count
            FROM complaints c
            LEFT JOIN registration r ON c.registration_id = r.registration_id
            LEFT JOIN beneficiaries b ON r.beneficiary_id = b.beneficiary_id
            LEFT JOIN areas a1 ON b.area_id = a1.area_id
            LEFT JOIN areas a2 ON r.hoa = a2.area_code OR r.hoa = a2.area_name
            WHERE (b.area_id = :area_id OR a2.area_id = :area_id) AND c.complaint_stage = 'Resolved'
        """)
        
        resolved_result = db.session.execute(resolved_query, {'area_id': area_id})
        resolved_count = resolved_result.fetchone()[0] or 0
        
        return jsonify({
            "total": total_count,
            "resolved": resolved_count,
            "ongoing": ongoing_count,
            "unresolved": 0  # Keep as 0 for now unless needed
        })
        
    except Exception as e:
        print(f"Error getting complaint stats for area {area_id}: {str(e)}")
        return jsonify({
            "total": 0,
            "resolved": 0,
            "ongoing": 0,
            "unresolved": 0
        }), 500
