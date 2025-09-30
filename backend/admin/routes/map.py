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

# 🆕 API endpoint to get complaint stats for an area (placeholder for now)
@map_bp.route("/api/complaints/<int:area_id>")
def get_complaint_stats(area_id):
    # TODO: Replace with actual complaint data from database
    # For now, return placeholder data
    return jsonify({
        "total": 0,
        "resolved": 0,
        "ongoing": 0,
        "unresolved": 0
    })
