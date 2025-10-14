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
from backend.complainant.redirects import complaint_redirect_path

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

# Redirect helper now imported from backend.complainant.redirects


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
            doc_map = {
                "doc_title": "title",
                "doc_contract": "contract_to_sell",
                "doc_fullpay": "certificate_of_full_payment",
                "doc_award": "pre_qualification_stub",
                "doc_agreement": "contract_agreement",
                "doc_deed": "deed_of_sale"
            }
            docs_selected = [v for k, v in doc_map.items() if request.form.get(k) == "on"]
            # Create supporting documents JSON with expected keys (for RegistrationHOAMember)
            supporting_docs = {v: (request.form.get(k) == "on") for k, v in doc_map.items()}

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
            if not hoa:
                field_errors["reg_hoa"] = "HOA is required."
            if not blk:
                field_errors["reg_blk"] = "Block Assignment is required."
            if not lot_asn:
                field_errors["reg_lot_asn"] = "Lot Assignment is required."
            if not lot_size:
                field_errors["reg_lot_size"] = "Lot Size is required."
            if recipient not in ("yes", "no"):
                field_errors["recipient"] = "Please select Yes or No."
            if not docs_selected:
                field_errors["supporting_docs"] = "Select at least one supporting document."

            if field_errors:
                # AJAX: return field errors for inline display
                if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
                    return jsonify({"success": False, "field_errors": field_errors}), 400
                # Fallback: show error popup
                return jsonify({"success": False, "error": "Please complete the required fields."}), 400

            # Ensure NA/N/A/empty are saved as None
            mid = mid if mid not in ("", "NA", "N/A") else None
            suffix = suffix if suffix not in ("", "NA", "N/A") else None

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

            # Middle initial: only validate if the user supplied one.
            # Ignore periods and case, only compare first letter
            def normalize_mi(val):
                if not val: return None
                return str(val).replace('.', '').strip().upper()[:1] or None
            # Only enforce MI mismatch when user provided a middle initial
            if input_middle:
                if normalize_mi(existing_beneficiary.middle_initial) != normalize_mi(input_middle):
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
                "signature_path": sig_filename,
                # Store as JSON array of selected doc keys for preview
                "supporting_documents": docs_selected
            }

            # --- Add registration ---
            new_member = Registration(**reg_data)
            db.session.add(new_member)
            db.session.flush()  # Get the registration_id before commit
            
            # --- Create RegistrationHOAMember record with supporting documents ---
            from backend.database.models import RegistrationHOAMember
            hoa_member = RegistrationHOAMember(
                registration_id=new_member.registration_id,
                supporting_documents=supporting_docs
            )
            db.session.add(hoa_member)
            
            db.session.commit()
            # Use centralized redirect logic
            complaint_type = session.get("type_of_complaint")
            next_url = complaint_redirect_path(complaint_type, has_registration=True)

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
