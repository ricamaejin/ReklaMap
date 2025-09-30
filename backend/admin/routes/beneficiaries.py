import os
from flask import Blueprint, jsonify, request
from backend.database.models import Beneficiary, Block, Area, GeneratedLots
from backend.database.db import db
from sqlalchemy import func, union_all

beneficiaries_bp = Blueprint("beneficiaries", __name__, url_prefix="/admin/beneficiaries")

# GET all beneficiaries with pagination (optionally include generated_lots with name fields)
@beneficiaries_bp.route("/")
def get_all_beneficiaries():
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        include_generated_lots = request.args.get('include_generated_lots', 'false').lower() == 'true'
        
        # Calculate offset
        offset = (page - 1) * per_page
        
        if include_generated_lots:
            # Get all beneficiaries
            beneficiaries = db.session.query(
                Beneficiary, Block, Area
            ).join(
                Block, Beneficiary.block_id == Block.block_id
            ).join(
                Area, Beneficiary.area_id == Area.area_id
            ).all()
            
            # Get generated_lots with name fields
            generated_lots = db.session.query(
                GeneratedLots, Block, Area
            ).join(
                Block, GeneratedLots.block_id == Block.block_id
            ).join(
                Area, GeneratedLots.area_id == Area.area_id
            ).filter(
                (GeneratedLots.first_name.isnot(None)) | (GeneratedLots.last_name.isnot(None))
            ).all()
            
            # Combine results
            combined_results = []
            
            # Process beneficiaries
            for beneficiary, block, area in beneficiaries:
                full_name = " ".join(
                    filter(None, [beneficiary.first_name, beneficiary.middle_initial, beneficiary.last_name, beneficiary.suffix])
                )
                combined_results.append({
                    "name": full_name,
                    "block_no": block.block_no,
                    "lot_no": beneficiary.lot_no,
                    "sqm": beneficiary.sqm,
                    "area_name": area.area_name,
                    "is_generated_lot": False,
                    "sort_key": f"{area.area_name}_{block.block_no:03d}_{beneficiary.lot_no:03d}"
                })
            
            # Process generated_lots with name fields
            for gen_lot, block, area in generated_lots:
                full_name = " ".join(
                    filter(None, [gen_lot.first_name, gen_lot.middle_initial, gen_lot.last_name, gen_lot.suffix])
                )
                # Add remarks in parentheses or default (GLS)
                if gen_lot.remarks:
                    display_name = f"{full_name} ({gen_lot.remarks})"
                else:
                    display_name = f"{full_name} (GLS)"
                
                combined_results.append({
                    "name": display_name,
                    "block_no": block.block_no,
                    "lot_no": gen_lot.lot_no,
                    "sqm": gen_lot.sqm,
                    "area_name": area.area_name,
                    "is_generated_lot": True,
                    "sort_key": f"{area.area_name}_{block.block_no:03d}_{gen_lot.lot_no:03d}"
                })
            
            # Sort combined results
            combined_results.sort(key=lambda x: x["sort_key"])
            
            # Remove sort_key from results
            for item in combined_results:
                del item["sort_key"]
            
            # Apply pagination
            total_count = len(combined_results)
            paginated_results = combined_results[offset:offset + per_page]
            
            result = paginated_results
            
        else:
            # Original logic - beneficiaries only
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
                    "beneficiary_id": beneficiary.beneficiary_id,
                    "is_generated_lot": False
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
    try:
        # Get beneficiaries with blocks
        beneficiaries = db.session.query(Beneficiary, Block).join(
            Block, Beneficiary.block_id == Block.block_id
        ).filter(Beneficiary.area_id == area_id).all()

        # Get generated_lots with blocks for the same area
        generated_lots = db.session.query(GeneratedLots, Block).join(
            Block, GeneratedLots.block_id == Block.block_id
        ).filter(GeneratedLots.area_id == area_id).all()

        result = []
        
        # Process beneficiaries
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
                "source": "beneficiary"
            })

        # Process generated_lots
        for gen_lot, block in generated_lots:
            # Handle name formatting for generated lots
            if gen_lot.first_name or gen_lot.last_name:
                # If name fields exist, combine them and add remarks in parentheses
                name_parts = [gen_lot.first_name, gen_lot.middle_initial, gen_lot.last_name, gen_lot.suffix]
                full_name = " ".join(filter(None, name_parts))
                display_name = f"{full_name} ({gen_lot.remarks})" if gen_lot.remarks else full_name
            else:
                # If no name fields, show only remarks
                display_name = gen_lot.remarks or "N/A"
            
            result.append({
                "name": display_name,
                "block_id": gen_lot.block_id,
                "block_no": block.block_no,
                "lot_no": gen_lot.lot_no,
                "sqm": gen_lot.sqm,
                "source": "generated_lot"
            })

        # Sort by block_no, then lot_no
        result.sort(key=lambda x: (x["block_no"], x["lot_no"]))
        
        return jsonify(result)
        
    except Exception as e:
        print(f"Error fetching beneficiaries and generated lots: {e}")
        return jsonify({"error": "Failed to fetch data"}), 500

# GET member count for an area (only beneficiaries with name fields)
@beneficiaries_bp.route("/count/<int:area_id>")
def get_member_count(area_id):
    try:
        # Count only beneficiaries with name fields
        member_count = db.session.query(func.count(Beneficiary.beneficiary_id)).filter(
            Beneficiary.area_id == area_id,
            (Beneficiary.first_name.isnot(None)) | (Beneficiary.last_name.isnot(None))
        ).scalar()
        
        return jsonify({"count": member_count or 0})
        
    except Exception as e:
        print(f"Error fetching member count: {e}")
        return jsonify({"error": "Failed to fetch member count"}), 500
