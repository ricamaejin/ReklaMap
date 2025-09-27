from flask import Blueprint, jsonify
from backend.database.models import Policy
from backend.database.db import db

policies_bp = Blueprint("policies", __name__, url_prefix="/admin/policies")

# Get all policies: /admin/policies/
@policies_bp.route("/")
def get_all_policies():
    try:
        policies = Policy.query.all()
        result = []
        
        for policy in policies:
            result.append({
                "policy_id": policy.policy_id,
                "policy_code": policy.policy_code,
                "law": policy.law,
                "section_number": policy.section_number,
                "description": policy.description,
                "application": policy.application
            })
        
        return jsonify(result)
        
    except Exception as e:
        print(f"Error fetching policies: {e}")
        return jsonify({"error": "Failed to fetch policies"}), 500