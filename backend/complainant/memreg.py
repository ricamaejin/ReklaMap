from flask import Blueprint, render_template, request, jsonify, session
from werkzeug.utils import secure_filename
import os
from datetime import datetime
from pathlib import Path

from backend.database.db import db
from backend.database.models import (
    Registration,
    Area,
    RegistrationFamOfMember,
    Beneficiary,
    RegistrationHOAMember  # import here directly
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # current file directory
TEMPLATE_DIR = os.path.join(BASE_DIR, '..', '..', 'frontend', 'complainant', 'home')

mem_reg_bp = Blueprint(
    "mem_reg",
    __name__,
    url_prefix="/complainant",
    template_folder=TEMPLATE_DIR
)

UPLOAD_FOLDER = "uploads/signatures"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@mem_reg_bp.route("/memreg", methods=["GET", "POST"])
def mem_reg():
    if request.method == "POST":
        try:
            # ✅ logged in user
            user_id = session.get("user_id")
            if not user_id:
                return jsonify({"success": False, "error": "User not logged in"}), 401

            # ✅ get category and other form fields
            category = request.form.get("category")
            if not category:
                return jsonify({"success": False, "error": "Category is required"}), 400

            last = request.form.get("reg_last")
            first = request.form.get("reg_first")
            mid = request.form.get("reg_mid")
            suffix = request.form.get("reg_suffix")
            dob = request.form.get("reg_dob")
            sex = request.form.get("reg_sex")
            cit = request.form.get("reg_cit")
            age = request.form.get("reg_age")
            year = request.form.get("reg_year")
            hoa = request.form.get("reg_hoa")
            blk = request.form.get("reg_blk")
            phone = request.form.get("reg_phone")
            lot_asn = request.form.get("reg_lot_asn")
            lot_size = request.form.get("reg_lot_size")
            civil = request.form.get("fam_civil")
            cur_add = request.form.get("reg_cur_add")
            recipient = request.form.get("recipient")

            # ✅ handle signature upload
            sig_file = request.files.get("signature")
            sig_filename = None
            if sig_file and sig_file.filename:
                sig_filename = secure_filename(sig_file.filename)
                sig_file.save(os.path.join(UPLOAD_FOLDER, sig_filename))

            # ✅ cross-check with beneficiaries table
            existing_beneficiary = Beneficiary.query.filter_by(
                first_name=first.strip(),
                last_name=last.strip(),
                lot_no=lot_asn,
                block_id=blk
            ).first()

            beneficiary_id = existing_beneficiary.beneficiary_id if existing_beneficiary else None

            # ✅ prepare registration data
            first_registration = Registration.query.first()
            reg_data = dict(
                user_id=user_id,
                beneficiary_id=beneficiary_id,
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
                hoa=hoa,
                block_no=blk,
                phone_number=phone,
                lot_no=lot_asn,
                lot_size=lot_size,
                civil_status=civil,
                current_address=cur_add,
                recipient_of_other_housing=recipient,
                signature_path=sig_filename
            )

            if not first_registration:
                reg_data["registration_id"] = 1  # start at 1 if table empty

            # ✅ add new member
            new_member = Registration(**reg_data)
            db.session.add(new_member)
            db.session.flush()  # ensures registration_id is available

            # ✅ optionally link to HOA member if exists
            if existing_beneficiary:
                hoa_link = RegistrationHOAMember(
                    registration_id=new_member.registration_id,
                    supporting_documents=None
                )
                db.session.add(hoa_link)

            db.session.commit()
            return jsonify({"success": True, "message": "Member registered successfully!"})

        except Exception as e:
            db.session.rollback()
            return jsonify({"success": False, "error": str(e)})

    # GET → show form with HOA areas
    areas = Area.query.order_by(Area.area_name).all()
    selected_category = request.args.get("category", "hoa_member")
    return render_template("mem-reg.html", areas=areas, category=selected_category)


# ✅ Route for overlapping complaint form
@mem_reg_bp.route("/complaints/overlapping")
def overlapping_form():
    return render_template("../complaints/overlapping.html")
