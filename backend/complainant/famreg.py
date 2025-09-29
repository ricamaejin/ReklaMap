from flask import Blueprint, render_template, request, jsonify, session
from pathlib import Path
from datetime import datetime
from backend.database.db import db
from backend.database.models import RegistrationFamOfMember, Area, Registration, Beneficiary

# Get the folder of the current Python file
BASE_DIR = Path(__file__).resolve().parent

# Construct template folder path relative to this file
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

            # --- Parent info ---
            parent_last = (request.form.get("parent_last") or "").strip()
            parent_first = (request.form.get("parent_first") or "").strip()
            parent_mid = (request.form.get("parent_mid") or "").strip()
            parent_suffix = request.form.get("parent_suffix") or ""
            parent_sex = request.form.get("parent_sex") or ""

            # --- Step 1: Try to find parent registration ---
            parent_registration = Registration.query.filter_by(
                last_name=parent_last,
                first_name=parent_first
            ).first()

            # --- Step 2: Check parent in Beneficiaries ---
            parent_beneficiary = Beneficiary.query.filter_by(
                first_name=parent_first,
                last_name=parent_last
            ).first()

            if not parent_beneficiary:
                return jsonify({
                    "success": False,
                    "error": "This family member is not found in HOA beneficiaries. Cannot register."
                }), 400

            # --- Step 3: If registration missing, create placeholder ---
            if not parent_registration:
                parent_registration = Registration(
                    user_id=user_id,
                    last_name=parent_last,
                    first_name=parent_first,
                    middle_name=parent_mid or None,
                    suffix=parent_suffix or None,
                    sex=parent_sex or None
                )
                db.session.add(parent_registration)
                db.session.commit()

            # --- Step 4: Optional mismatch check ---
            mismatches = []
            if parent_registration:
                if parent_mid and parent_mid != (parent_registration.middle_name or ""):
                    mismatches.append(f"Middle Name (expected '{parent_registration.middle_name}', got '{parent_mid}')")
                if parent_suffix and parent_suffix != (parent_registration.suffix or ""):
                    mismatches.append(f"Suffix (expected '{parent_registration.suffix}', got '{parent_suffix}')")
                if parent_sex and parent_sex != (parent_registration.sex or ""):
                    mismatches.append(f"Sex (expected '{parent_registration.sex}', got '{parent_sex}')")
                if mismatches:
                    return jsonify({
                        "success": False,
                        "error": "Mismatch found in the following fields: " + "; ".join(mismatches)
                    }), 400

            # --- Step 5: Cross-check family member with Beneficiaries ---
            fam_first = (request.form.get("reg_first") or "").strip()
            fam_last = (request.form.get("reg_last") or "").strip()
            lot_no = request.form.get("reg_lot_asn")
            block_id = request.form.get("reg_blk")

            existing_beneficiary = Beneficiary.query.filter_by(
                first_name=fam_first,
                last_name=fam_last,
                lot_no=lot_no,
                block_id=block_id
            ).first()

            if not existing_beneficiary:
                return jsonify({
                    "success": False,
                    "error": "The family member is not found in HOA beneficiaries."
                }), 400

            # --- Step 6: Save family member ---
            dob = request.form.get("parent_dob")
            category = request.form.get("category") or "fam_member"  # fallback if not in form

            fam = RegistrationFamOfMember(
                registration_id=parent_registration.registration_id,
                last_name=fam_last,
                first_name=fam_first,
                middle_name=request.form.get("reg_mid"),
                suffix=request.form.get("reg_suffix"),
                date_of_birth=datetime.strptime(dob, "%Y-%m-%d") if dob else None,
                sex=request.form.get("reg_sex"),
                citizenship=request.form.get("reg_cit"),
                age=int(request.form.get("reg_age")) if request.form.get("reg_age") else None,
                phone_number=request.form.get("reg_phone"),
                year_of_residence=request.form.get("reg_year"),
                relationship=request.form.get("reg_relationship"),
                category=category,  # ✅ non-nullable column
                supporting_documents={
                    "title": bool(request.form.get("doc_title")),
                    "contract": bool(request.form.get("doc_contract")),
                    "fullpay": bool(request.form.get("doc_fullpay")),
                    "award": bool(request.form.get("doc_award")),
                    "agreement": bool(request.form.get("doc_agreement")),
                    "deed": bool(request.form.get("doc_deed")),
                }
            )
            db.session.add(fam)
            db.session.commit()

            return jsonify({"success": True, "message": "Family member registered successfully!"})

        except Exception as e:
            db.session.rollback()
            return jsonify({"success": False, "error": str(e)}), 500

    # GET → render form
    areas = Area.query.order_by(Area.area_name).all()
    selected_category = request.args.get("category", "fam_member")
    return render_template("fam_reg.html", areas=areas, category=selected_category)
