from flask import Blueprint, request, jsonify
from backend.database.models import Area, Block, Beneficiary
from backend.database.db import db
from sqlalchemy import or_, func

search_bp = Blueprint("search", __name__, url_prefix="/admin")

@search_bp.route("/search")
def search():
    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify([])
    
    results = []
    search_pattern = f"%{query}%"
    
    try:
        # Search areas by name
        areas = Area.query.filter(
            Area.area_name.ilike(search_pattern)
        ).limit(10).all()
        
        for area in areas:
            results.append({
                'type': 'area',
                'area_name': area.area_name,
                'area_code': area.area_code,
                'match_type': 'area_name'
            })
        
        # Search beneficiaries by name (combining first, middle, last name)
        beneficiaries = db.session.query(
            Beneficiary, Area, Block
        ).join(
            Area, Beneficiary.area_id == Area.area_id
        ).join(
            Block, Beneficiary.block_id == Block.block_id
        ).filter(
            or_(
                Beneficiary.first_name.ilike(search_pattern),
                Beneficiary.last_name.ilike(search_pattern),
                func.concat(
                    Beneficiary.first_name, ' ',
                    func.coalesce(Beneficiary.middle_initial, ''), ' ',
                    Beneficiary.last_name, ' ',
                    func.coalesce(Beneficiary.suffix, '')
                ).ilike(search_pattern)
            )
        ).limit(15).all()
        
        for beneficiary, area, block in beneficiaries:
            # Build full name
            full_name = beneficiary.first_name or ''
            if beneficiary.middle_initial:
                full_name += f' {beneficiary.middle_initial}'
            if beneficiary.last_name:
                full_name += f' {beneficiary.last_name}'
            if beneficiary.suffix:
                full_name += f' {beneficiary.suffix}'
            
            results.append({
                'type': 'beneficiary',
                'name': full_name.strip(),
                'area_name': area.area_name,
                'area_code': area.area_code,
                'block_no': block.block_no,
                'lot_no': beneficiary.lot_no,
                'match_type': 'beneficiary_name'
            })
        
        # Search by block number (when query is numeric or contains "block")
        if query.isdigit() or 'block' in query.lower():
            block_num = None
            if query.isdigit():
                block_num = int(query)
            else:
                # Extract number from "block X" pattern
                words = query.lower().split()
                for i, word in enumerate(words):
                    if word == 'block' and i + 1 < len(words) and words[i + 1].isdigit():
                        block_num = int(words[i + 1])
                        break
            
            if block_num:
                blocks = db.session.query(
                    Block, Area
                ).join(
                    Area, Block.area_id == Area.area_id
                ).filter(
                    Block.block_no == block_num
                ).limit(10).all()
                
                for block, area in blocks:
                    results.append({
                        'type': 'block',
                        'area_name': area.area_name,
                        'area_code': area.area_code,
                        'block_no': block.block_no,
                        'match_type': 'block_number'
                    })
        
        # Search by lot number (when query is numeric or contains "lot")
        if query.isdigit() or 'lot' in query.lower():
            lot_num = None
            if query.isdigit():
                lot_num = int(query)
            else:
                # Extract number from "lot X" pattern
                words = query.lower().split()
                for i, word in enumerate(words):
                    if word == 'lot' and i + 1 < len(words) and words[i + 1].isdigit():
                        lot_num = int(words[i + 1])
                        break
            
            if lot_num:
                beneficiaries_by_lot = db.session.query(
                    Beneficiary, Area, Block
                ).join(
                    Area, Beneficiary.area_id == Area.area_id
                ).join(
                    Block, Beneficiary.block_id == Block.block_id
                ).filter(
                    Beneficiary.lot_no == lot_num
                ).limit(10).all()
                
                for beneficiary, area, block in beneficiaries_by_lot:
                    full_name = beneficiary.first_name or ''
                    if beneficiary.middle_initial:
                        full_name += f' {beneficiary.middle_initial}'
                    if beneficiary.last_name:
                        full_name += f' {beneficiary.last_name}'
                    if beneficiary.suffix:
                        full_name += f' {beneficiary.suffix}'
                    
                    results.append({
                        'type': 'beneficiary',
                        'name': full_name.strip(),
                        'area_name': area.area_name,
                        'area_code': area.area_code,
                        'block_no': block.block_no,
                        'lot_no': beneficiary.lot_no,
                        'match_type': 'lot_number'
                    })
        
        # Remove duplicates and limit results
        seen = set()
        unique_results = []
        for result in results:
            key = f"{result['type']}_{result.get('area_code')}_{result.get('block_no', '')}_{result.get('lot_no', '')}_{result.get('name', '')}"
            if key not in seen:
                seen.add(key)
                unique_results.append(result)
                if len(unique_results) >= 20:  # Limit total results
                    break
        
        return jsonify(unique_results)
        
    except Exception as e:
        print(f"Search error: {e}")
        return jsonify([])