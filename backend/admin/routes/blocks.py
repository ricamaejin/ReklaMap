import os
from flask import Blueprint, jsonify
from backend.database.models import Block, Beneficiary
from backend.database.db import db

blocks_bp = Blueprint("blocks", __name__, url_prefix="/admin/blocks")

# Get blocks for an area: /admin/blocks/area/<area_id>
@blocks_bp.route("/area/<int:area_id>")
def get_blocks_by_area(area_id):
    blocks = Block.query.filter_by(area_id=area_id).order_by(Block.block_no).all()
    
    result = []
    for block in blocks:
        # Count beneficiaries in this block
        beneficiary_count = Beneficiary.query.filter_by(block_id=block.block_id).count()
        result.append({
            "block_id": block.block_id,
            "block_no": block.block_no,
            "area_id": block.area_id,
            "beneficiary_count": beneficiary_count
        })
    
    return jsonify(result)

# Get specific block details: /admin/blocks/<block_id>
@blocks_bp.route("/<int:block_id>")
def get_block_details(block_id):
    block = Block.query.get_or_404(block_id)
    
    # Get beneficiaries in this block
    beneficiaries = Beneficiary.query.filter_by(block_id=block_id).order_by(Beneficiary.lot_no).all()
    
    beneficiary_list = []
    for b in beneficiaries:
        full_name = " ".join(filter(None, [b.first_name, b.middle_initial, b.last_name, b.suffix]))
        beneficiary_list.append({
            "beneficiary_id": b.beneficiary_id,
            "name": full_name,
            "lot_no": b.lot_no,
            "sqm": b.sqm,
            "co_owner": b.co_owner
        })
    
    return jsonify({
        "block_id": block.block_id,
        "block_no": block.block_no,
        "area_id": block.area_id,
        "beneficiaries": beneficiary_list
    })