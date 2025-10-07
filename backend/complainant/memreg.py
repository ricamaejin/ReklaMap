from flask import Blueprint, render_template, request, jsonify, session, redirect
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
            # Supporting documents (at least one required)
            doc_fields = [
                "doc_title", "doc_contract", "doc_fullpay", "doc_award", "doc_agreement", "doc_deed"
            ]
            docs_selected = [f for f in doc_fields if request.form.get(f) == "on"]

            # --- Validate required fields ---
            field_errors = {}
            if not last:
                field_errors["reg_last"] = "Last Name is required."
            if not first:
                field_errors["reg_first"] = "First Name is required."
            if not cit:
                field_errors["reg_cit"] = "Citizenship is required."
            if not year:
                field_errors["reg_year"] = "Years of Residence is required."
            if not phone:
                field_errors["reg_phone"] = "Contact Number is required."
            if not blk:
                field_errors["reg_blk"] = "Block Assignment is required."
            if not lot_asn:
                field_errors["reg_lot_asn"] = "Lot Assignment is required."
            if not cur_add:
                field_errors["reg_cur_add"] = "Current Address is required."
            if not recipient:
                field_errors["recipient"] = "Please select Yes or No."
            if not docs_selected:
                field_errors["supporting_docs"] = "Select at least one supporting document."

            if field_errors:
                # AJAX: return field errors for inline display
                if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
                    return jsonify({"success": False, "field_errors": field_errors}), 400
                # Fallback: show error popup
                return jsonify({"success": False, "error": "Please complete the required fields."}), 400

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

            # Compare middle initials - normalize by removing periods for comparison
            db_middle = existing_beneficiary.middle_initial or None
            if db_middle:
                db_middle_normalized = db_middle.replace(".", "").strip().upper()
            else:
                db_middle_normalized = None
                
            if input_middle:
                input_middle_normalized = input_middle.replace(".", "").strip().upper()
            else:
                input_middle_normalized = None

            if db_middle_normalized != input_middle_normalized:
                mismatches.append("Middle Name")
            if (existing_beneficiary.suffix or None) != input_suffix:
                mismatches.append("Suffix")
            if existing_beneficiary.lot_no != lot_asn:
                mismatches.append("Lot Assignment")
            # Compare provided block number against beneficiary's block.block_no (not block_id)
            try:
                benef_block_no = existing_beneficiary.block.block_no if existing_beneficiary.block else None
            except Exception:
                benef_block_no = None
            if benef_block_no != blk:
                mismatches.append("Block Assignment")
            if existing_beneficiary.area_id != hoa:
                mismatches.append("HOA")
            try:
                beneficiary_sqm = int(existing_beneficiary.sqm) if existing_beneficiary.sqm is not None else None
                submitted_lot_size = int(lot_size) if lot_size not in (None, "", "NA", "N/A") else None
                if beneficiary_sqm != submitted_lot_size:
                    mismatches.append("Lot Size")
            except Exception:
                mismatches.append("Lot Size")

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
            # Use complaint type from session for redirect
            complaint_type = session.get("type_of_complaint")
            if complaint_type == "Overlapping":
                next_url = "/complainant/overlapping/new_overlap_form"
            elif complaint_type == "Lot Dispute":
                next_url = "/complainant/lot_dispute/new_lot_dispute_form"
            elif complaint_type == "Boundary Dispute":
                next_url = "/complainant/boundary_dispute/new_boundary_dispute_form"
            elif complaint_type == "Pathway Dispute":
                next_url = "/complainant/complaints/pathway_dispute.html"
            elif complaint_type == "Unauthorized Occupation":
                next_url = "/complainant/complaints/unauthorized_occupation.html"
            elif complaint_type == "Illegal Construction":
                next_url = "/complainant/complaints/illegal_construction.html"
            else:
                next_url = "/complainant/home/dashboard.html"

            # If AJAX/fetch, return JSON with redirect URL
            if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
                return jsonify({"success": True, "redirect": next_url})
            # Otherwise, do a normal redirect
            return redirect(next_url)

        except Exception as e:
            db.session.rollback()
            print(f"[ERROR] Exception during registration: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({"success": False, "error": str(e)}), 500

    # GET → render form
    areas = Area.query.order_by(Area.area_name).all()
    selected_category = request.args.get("category", "hoa_member")
    return render_template("mem-reg.html", areas=areas, category=selected_category)
