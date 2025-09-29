from flask import Blueprint, render_template, request, jsonify, session
from pathlib import Path
from datetime import datetime
from backend.database.db import db
from backend.database.models import RegistrationFamOfMember, Area, Registration, Beneficiary

# Directories
BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / ".." / ".." / "frontend" / "complainant" / "home"

famreg_bp = Blueprint(
    "famreg",
    __name__,
    url_prefix="/complainant",
    template_folder=str(TEMPLATE_DIR)
)


@famreg_bp.route("/famreg", methods=["GET", "POST"])
def famreg():
    if request.method == "POST":
        try:
            user_id = session.get("user_id")
            if not user_id:
                return jsonify({"success": False, "error": "User not logged in"}), 401

            # --- Parent info (to verify in Beneficiaries) ---
            parent_last = (request.form.get("parent_last") or "").strip()
            parent_first = (request.form.get("parent_first") or "").strip()
            parent_mid = (request.form.get("parent_mid") or "").strip()
            parent_suffix = (request.form.get("parent_suffix") or "").strip()
            parent_sex = (request.form.get("parent_sex") or "").strip()

            # --- Step 1: Verify parent exists in Beneficiaries ---
            parent_beneficiary = Beneficiary.query.filter_by(
                first_name=parent_first,
                last_name=parent_last
            ).first()

            if not parent_beneficiary:
                return jsonify({
                    "success": False,
                    "error": "Family member not found in HOA beneficiaries. Please ensure the person is a registered HOA member."
                }), 400

            # --- Step 1b: Check for field mismatches ---
            mismatches = []
            input_middle = parent_mid if parent_mid not in ("", "NA", "N/A") else None
            input_suffix = parent_suffix if parent_suffix not in ("", "NA", "N/A") else None

            if (parent_beneficiary.middle_initial or None) != input_middle:
                mismatches.append("Middle Name")
            if (parent_beneficiary.suffix or None) != input_suffix:
                mismatches.append("Suffix")

            # Add block, lot, or HOA checks if these fields exist in your form
            blk = request.form.get("parent_blk")
            lot_asn = request.form.get("parent_lot")
            hoa = request.form.get("parent_hoa")

            if blk and int(blk) != parent_beneficiary.block_id:
                mismatches.append("Block Assignment")
            if lot_asn and int(lot_asn) != parent_beneficiary.lot_no:
                mismatches.append("Lot Number")
            if hoa and int(hoa) != parent_beneficiary.area_id:
                mismatches.append("HOA")

            if mismatches:
                return jsonify({
                    "success": False,
                    "error": "Mismatch found in the following field(s): " + ", ".join(mismatches)
                }), 400

            # --- Step 2: Ensure parent registration exists ---
            parent_registration = Registration.query.filter_by(
                last_name=parent_last,
                first_name=parent_first
            ).first()

            if not parent_registration:
                parent_registration = Registration(
                    user_id=user_id,
                    last_name=parent_last,
                    first_name=parent_first,
                    middle_name=input_middle,
                    suffix=input_suffix,
                    sex=parent_sex or None,
                    category="hoa_member",
                    beneficiary_id=parent_beneficiary.beneficiary_id
                )
                db.session.add(parent_registration)
                db.session.commit()

            # --- Step 3: Get registrant/family member info from reg_* ---
            reg_first = (request.form.get("reg_first") or "").strip()
            reg_last = (request.form.get("reg_last") or "").strip()
            reg_mid = (request.form.get("reg_mid") or "").strip()
            reg_suffix = (request.form.get("reg_suffix") or "").strip()
            reg_dob = request.form.get("reg_dob")
            reg_sex = request.form.get("reg_sex")
            reg_citizenship = request.form.get("reg_cit")
            reg_age = request.form.get("reg_age")
            reg_phone = request.form.get("reg_phone")
            reg_year = request.form.get("reg_year")
            relationship = request.form.get("reg_relationship")

            # --- Step 4: Save family member with link to parent beneficiary ---
            fam_member = RegistrationFamOfMember(
                registration_id=parent_registration.registration_id,
                last_name=reg_last,
                first_name=reg_first,
                middle_name=reg_mid if reg_mid not in ("", "NA", "N/A") else None,
                suffix=reg_suffix if reg_suffix not in ("", "NA", "N/A") else None,
                date_of_birth=datetime.strptime(reg_dob, "%Y-%m-%d") if reg_dob else None,
                sex=reg_sex,
                citizenship=reg_citizenship,
                age=int(reg_age) if reg_age else None,
                phone_number=reg_phone,
                year_of_residence=reg_year,
                relationship=relationship,
                supporting_documents={
                    "title": bool(request.form.get("doc_title")),
                    "contract": bool(request.form.get("doc_contract")),
                    "fullpay": bool(request.form.get("doc_fullpay")),
                    "award": bool(request.form.get("doc_award")),
                    "agreement": bool(request.form.get("doc_agreement")),
                    "deed": bool(request.form.get("doc_deed")),
                },
                beneficiary_id=parent_beneficiary.beneficiary_id  # Link back to parent
            )
            db.session.add(fam_member)
            db.session.commit()

            return jsonify({"success": True, "message": "Registered successfully!"})

        except Exception as e:
            db.session.rollback()
            return jsonify({"success": False, "error": str(e)}), 500

    # GET → render form
    areas = Area.query.order_by(Area.area_name).all()
    selected_category = request.args.get("category", "fam_member")
    return render_template("fam_reg.html", areas=areas, category=selected_category)
