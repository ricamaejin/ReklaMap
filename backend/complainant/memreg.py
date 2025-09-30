from flask import Blueprint, render_template, request, jsonify, session
from werkzeug.utils import secure_filename
import os
from datetime import datetime

from backend.database.db import db
from backend.database.models import (
    Registration,
    Area,
    Beneficiary,
    RegistrationHOAMember
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
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
            user_id = session.get("user_id")
            if not user_id:
                return jsonify({"success": False, "error": "User not logged in"}), 401

            # --- Get form fields ---
            category = request.form.get("category")
            if not category:
                return jsonify({"success": False, "error": "Category is required"}), 400

            last = request.form.get("reg_last", "").strip()
            first = request.form.get("reg_first", "").strip()
            mid = request.form.get("reg_mid", "").strip()
            suffix = request.form.get("reg_suffix", "").strip()
            # Ensure NA/N/A/empty are saved as None
            mid = mid if mid not in ("", "NA", "N/A") else None
            suffix = suffix if suffix not in ("", "NA", "N/A") else None
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

            # --- Convert numeric fields ---
            try:
                lot_asn = int(lot_asn) if lot_asn else None
                blk = int(blk) if blk else None
                hoa = int(hoa) if hoa else None
            except ValueError:
                return jsonify({"success": False, "error": "Invalid Lot, Block, or HOA"}), 400

            # --- Handle signature upload ---
            sig_file = request.files.get("signature")
            sig_filename = None
            if sig_file and sig_file.filename:
                sig_filename = secure_filename(sig_file.filename)
                sig_file.save(os.path.join(UPLOAD_FOLDER, sig_filename))

            # --- Cross-check with beneficiaries table ---
            existing_beneficiary = Beneficiary.query.filter_by(
                first_name=first,
                last_name=last
            ).first()

            if not existing_beneficiary:
                return jsonify({
                    "success": False,
                    "error": "Beneficiary not found. Please ensure you are a registered HOA member."
                }), 400

            # --- Check for mismatches ---
            # Treat empty / NA / N/A as None
            input_suffix = suffix if suffix not in ("", "NA", "N/A") else None
            input_middle = mid if mid not in ("", "NA", "N/A") else None

            mismatches = []

            if (existing_beneficiary.middle_initial or None) != input_middle:
                mismatches.append("Middle Name")
            if (existing_beneficiary.suffix or None) != input_suffix:
                mismatches.append("Suffix")
            if existing_beneficiary.lot_no != lot_asn:
                mismatches.append("Lot Number")
            if existing_beneficiary.block_id != blk:
                mismatches.append("Block Assignment")
            if existing_beneficiary.area_id != hoa:
                mismatches.append("HOA")

            if mismatches:
                return jsonify({
                    "success": False,
                    "error": "Mismatch found in the following field(s): " + ", ".join(mismatches)
                }), 400

            beneficiary_id = existing_beneficiary.beneficiary_id

            # --- Prepare registration data ---
            reg_data = {
                "user_id": user_id,
                "beneficiary_id": beneficiary_id,
                "category": category,
                "last_name": last,
                "first_name": first,
                "middle_name": mid,
                "suffix": suffix,
                "date_of_birth": datetime.strptime(dob, "%Y-%m-%d") if dob else None,
                "sex": sex,
                "citizenship": cit,
                "age": int(age) if age else None,
                "year_of_residence": year,
                "hoa": hoa,
                "block_no": blk,
                "phone_number": phone,
                "lot_no": lot_asn,
                "lot_size": lot_size,
                "civil_status": civil,
                "current_address": cur_add,
                "recipient_of_other_housing": recipient,
                "signature_path": sig_filename
            }

            # --- Add registration ---
            new_member = Registration(**reg_data)
            db.session.add(new_member)
            db.session.flush()  # ensures registration_id is available

            # --- Link to registration_hoa_member ---
            hoa_link = RegistrationHOAMember(
                registration_id=new_member.registration_id,
                supporting_documents=None
            )
            db.session.add(hoa_link)

            db.session.commit()
            return jsonify({"success": True, "message": "Registered successfully!"})

        except Exception as e:
            db.session.rollback()
            return jsonify({"success": False, "error": str(e)}), 500

    # GET → render form
    areas = Area.query.order_by(Area.area_name).all()
    selected_category = request.args.get("category", "hoa_member")
    return render_template("mem-reg.html", areas=areas, category=selected_category)
