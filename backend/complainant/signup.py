from flask import Blueprint, request, jsonify
from backend.database.db import db
from backend.database.models import User
from sqlalchemy.exc import IntegrityError

complainant_bp = Blueprint("complainant", __name__)

@complainant_bp.route("/signup", methods=["POST"])
def signup():
    firstName = request.form.get("firstName", "").strip()
    lastName = request.form.get("lastName", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    # Check if email already exists
    existing_email = User.query.filter_by(email=email).first()
    if existing_email:
        return jsonify({"success": False, "message": "This email is already taken."}), 400

    new_user = User(
        first_name=firstName,
        last_name=lastName,
        email=email,
        password_hash=password
    )

    try:
        db.session.add(new_user)
        db.session.commit()
        return jsonify({"success": True, "message": "Sign-up successful!"}), 201

    except IntegrityError as e:
        db.session.rollback()
        # Show friendly message if duplicate full name
        error_str = str(e.orig)
        if "uq_fullname" in error_str or "Duplicate entry" in error_str:
            return jsonify({"success": False, "message": "This full name is already taken."}), 400
        return jsonify({"success": False, "message": "A database error occurred."}), 500

    except Exception:
        db.session.rollback()
        return jsonify({"success": False, "message": "An unexpected error occurred."}), 500
