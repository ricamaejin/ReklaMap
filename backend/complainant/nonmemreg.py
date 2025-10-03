from flask import Blueprint, render_template, request, jsonify, session
from werkzeug.utils import secure_filename
import os
from datetime import datetime
from backend.database.db import db
from backend.database.models import Registration, Area, Beneficiary, RegistrationNonMember, Block
from pathlib import Path
import json

# Directories
BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / ".." / ".." / "frontend" / "complainant" / "home"

nonmemreg_bp = Blueprint(
    "nonmemreg",
    __name__,
    url_prefix="/complainant",
    template_folder=str(TEMPLATE_DIR)
)

UPLOAD_FOLDER = "uploads/signatures"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@nonmemreg_bp.route("/nonmemreg", methods=["GET", "POST"])
def nonmemreg():
    if request.method == "POST":
        try:
            user_id = session.get("user_id")
            if not user_id:
                return jsonify({"success": False, "error": "User not logged in"}), 401

            # --- Form fields ---
            category = request.form.get("category", "non_member")
            last = request.form.get("reg_last")
            first = request.form.get("reg_first")
            mid = request.form.get("reg_mid")
            suffix = request.form.get("reg_suffix")
            dob = request.form.get("reg_dob")
            sex = request.form.get("reg_sex")
            cit = request.form.get("reg_cit")
            age = request.form.get("reg_age")
            year = request.form.get("reg_year")
            civil = request.form.get("fam_civil")
            cur_add = request.form.get("reg_cur_add")
            recipient = request.form.get("recipient")
            phone = request.form.get("reg_num")

            # --- Handle signature upload ---
            sig_file = request.files.get("signatureInput")
            sig_filename = None
            if sig_file and sig_file.filename:
                sig_filename = secure_filename(sig_file.filename)
                sig_file.save(os.path.join(UPLOAD_FOLDER, sig_filename))

            # --- Save main registration ---
            new_reg = Registration(
                user_id=user_id,
                category=category,
                last_name=last,
                first_name=first,
                middle_name=mid,
                suffix=suffix,
                date_of_birth=datetime.strptime(dob, "%Y-%m-%d") if dob else None,
                sex=sex,
                citizenship=cit,
                age=int(age) if age else None,
                year_of_residence=year,
                civil_status=civil,
                current_address=cur_add,
                recipient_of_other_housing=recipient,
                phone_number=phone,
                signature_path=sig_filename,
                beneficiary_id=None
            )
            db.session.add(new_reg)
            db.session.flush()  # get registration_id before committing

            # --- Process "connections" checkboxes ---
            connections = []
            checkbox_labels = [
                "I live on the lot but I am not the official beneficiary",
                "I live near the lot and I am affected by the issue",
                "I am claiming ownership of the lot",
                "I am related to the person currently occupying the lot",
                "I was previously assigned to this lot but was replaced or removed"
            ]

            for idx, label in enumerate(checkbox_labels, start=1):
                if request.form.get(f"connection_{idx}") == "on":
                    connections.append(label)

            other_text = request.form.get("connection_other")
            if other_text:
                connections.append(other_text.strip())

            # --- Save non-member registration details ---
            if category == "non_member":
                non_mem = RegistrationNonMember(
                    registration_id=new_reg.registration_id,
                    connections=json.dumps(connections)
                )
                db.session.add(non_mem)

            db.session.commit()
            return jsonify({"success": True, "message": "Registered successfully!"})

        except Exception as e:
            db.session.rollback()
            return jsonify({"success": False, "error": str(e)}), 500

    # GET → show form with HOA areas
    areas = Area.query.order_by(Area.area_name).all()
    selected_category = request.args.get("category", "non_member")
    return render_template("non-mem_reg.html", areas=areas, category=selected_category)
