import os
from flask import Blueprint, jsonify, request
from backend.database.models import Beneficiary, Block, Area
from backend.database.db import db
from sqlalchemy import func

beneficiaries_bp = Blueprint("beneficiaries", __name__, url_prefix="/admin/beneficiaries")

# GET all beneficiaries with pagination
@beneficiaries_bp.route("/")
def get_all_beneficiaries():
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        
        # Calculate offset
        offset = (page - 1) * per_page
        
        # Get total count
        total_count = db.session.query(func.count(Beneficiary.beneficiary_id)).scalar()
        
        # Join beneficiaries with blocks and areas to get all required data
        beneficiaries_query = db.session.query(
            Beneficiary, Block, Area
        ).join(
            Block, Beneficiary.block_id == Block.block_id
        ).join(
            Area, Beneficiary.area_id == Area.area_id
        ).order_by(
            Area.area_name, Block.block_no, Beneficiary.lot_no
        ).offset(offset).limit(per_page)
        
        beneficiaries = beneficiaries_query.all()
        
        result = []
        for beneficiary, block, area in beneficiaries:
            # Combine name parts into one string
            full_name = " ".join(
                filter(None, [beneficiary.first_name, beneficiary.middle_initial, beneficiary.last_name, beneficiary.suffix])
            )
            result.append({
                "name": full_name,
                "block_no": block.block_no,
                "lot_no": beneficiary.lot_no,
                "sqm": beneficiary.sqm,
                "area_name": area.area_name,
                "beneficiary_id": beneficiary.beneficiary_id
            })
        
        return jsonify({
            "beneficiaries": result,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total_count,
                "total_pages": (total_count + per_page - 1) // per_page
            }
        })
        
    except Exception as e:
        print(f"Error fetching beneficiaries: {e}")
        return jsonify({"error": "Failed to fetch beneficiaries"}), 500

# GET beneficiaries by area_id (keep existing route for compatibility)
@beneficiaries_bp.route("/<int:area_id>")
def get_beneficiaries(area_id):
    # Join beneficiaries with blocks to get block_no
    beneficiaries = db.session.query(Beneficiary, Block).join(
        Block, Beneficiary.block_id == Block.block_id
    ).filter(Beneficiary.area_id == area_id).order_by(Block.block_no, Beneficiary.lot_no).all()

    result = []
    for beneficiary, block in beneficiaries:
        # Combine name parts into one string
        full_name = " ".join(
            filter(None, [beneficiary.first_name, beneficiary.middle_initial, beneficiary.last_name, beneficiary.suffix])
        )
        result.append({
            "name": full_name,
            "block_id": beneficiary.block_id,
            "block_no": block.block_no,
            "lot_no": beneficiary.lot_no,
            "sqm": beneficiary.sqm,
        })

    return jsonify(result)
