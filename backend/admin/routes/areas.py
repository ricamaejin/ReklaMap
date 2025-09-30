import os
from flask import Blueprint, jsonify
from backend.database.models import Area, Block, Beneficiary, GeneratedLots
from backend.database.db import db
from sqlalchemy import text, func

areas_bp = Blueprint("areas", __name__, url_prefix="/admin/areas")

# Get area by area_code: /admin/areas/by_code/sjc
@areas_bp.route("/by_code/<area_code>")
def get_area_by_code(area_code):
    area = Area.query.filter_by(area_code=area_code.lower()).first()
    if not area:
        return jsonify({"error": "Area not found"}), 404

    return jsonify({
        "area_id": area.area_id,
        "area_code": area.area_code,
        "area_name": area.area_name,
        "president": area.president,
        "designation": area.designation,
        "contact_no": area.contact_no
    })

# Get blocks for an area: /admin/areas/<area_id>/blocks
@areas_bp.route("/<int:area_id>/blocks")
def get_area_blocks(area_id):
    blocks = Block.query.filter_by(area_id=area_id).order_by(Block.block_no).all()
    result = [{
        "block_id": block.block_id,
        "block_no": block.block_no
    } for block in blocks]
    
    return jsonify(result)

# Get area statistics for hover tooltip: /admin/areas/stats/<area_code>
@areas_bp.route("/stats/<area_code>")
def get_area_stats(area_code):
    area = Area.query.filter_by(area_code=area_code.lower()).first()
    if not area:
        return jsonify({"error": "Area not found"}), 404

    # Count only beneficiaries with name fields (exclude generated_lots and unnamed entries)
    beneficiaries_count = Beneficiary.query.filter(
        Beneficiary.area_id == area.area_id,
        (Beneficiary.first_name.isnot(None)) | (Beneficiary.last_name.isnot(None))
    ).count()
    
    # Count complaints in this area by joining with registration and beneficiaries tables
    complaints_query = text("""
        SELECT COUNT(DISTINCT c.complaint_id) as complaint_count
        FROM complaints c
        LEFT JOIN registration r ON c.registration_id = r.registration_id
        LEFT JOIN beneficiaries b ON r.beneficiary_id = b.beneficiary_id
        WHERE b.area_id = :area_id
    """)
    
    result = db.session.execute(complaints_query, {'area_id': area.area_id})
    complaints_count = result.fetchone()[0] or 0
    
    return jsonify({
        "area_name": area.area_name,
        "beneficiaries": beneficiaries_count,
        "complaints": complaints_count,
        "resolved": 0  # Keep as 0 or N/A as requested
    })
