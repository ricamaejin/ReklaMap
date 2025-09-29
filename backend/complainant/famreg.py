from flask import Blueprint, render_template, request, jsonify, session
from datetime import datetime
from backend.database.db import db
from backend.database.models import RegistrationFamOfMember, Area, Registration


famreg_bp = Blueprint(
    "famreg",
    __name__,
    url_prefix="/complainant",
    template_folder=r"C:\Users\win10\Documents\GitHub\ReklaMap\frontend\complainant\home"
)

# -----------------------------
# FAMILY REGISTRATION
# -----------------------------
@famreg_bp.route("/famreg", methods=["GET", "POST"])
def famreg():
    if request.method == "POST":
        try:
            user_id = session.get("user_id")
            if not user_id:
                return jsonify({"success": False, "error": "User not logged in"}), 401

            # --- Gather parent info from form ---
            parent_last = (request.form.get("parent_last") or "").strip()
            parent_first = (request.form.get("parent_first") or "").strip()
            parent_mid = (request.form.get("parent_mid") or "").strip()
            parent_suffix = request.form.get("parent_suffix") or ""
            parent_sex = request.form.get("parent_sex") or ""

            # --- Step 1: Find by last+first ---
            parent_registration = Registration.query.filter_by(
                last_name=parent_last,
                first_name=parent_first
            ).first()

            if not parent_registration:
                return jsonify({
                    "success": False,
                    "error": "No HOA member found with that first and last name."
                }), 404

            # --- Step 2: Check for mismatches ---
            mismatches = []

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

            # --- Step 3: Save family member ---
            dob = request.form.get("parent_dob")
            fam = RegistrationFamOfMember(
                registration=parent_registration,
                last_name=request.form.get("reg_last"),
                first_name=request.form.get("reg_first"),
                middle_name=request.form.get("reg_mid"),
                suffix=request.form.get("reg_suffix"),
                date_of_birth=datetime.strptime(dob, "%Y-%m-%d") if dob else None,
                sex=request.form.get("reg_sex"),
                citizenship=request.form.get("reg_cit"),
                age=int(request.form.get("reg_age")) if request.form.get("reg_age") else None,
                phone_number=request.form.get("reg_phone"),
                year_of_residence=request.form.get("reg_year"),
                relationship=request.form.get("reg_relationship"),
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

    # ✅ For GET request
    areas = Area.query.order_by(Area.area_name).all()
    selected_category = request.args.get("category", "fam_member")
    return render_template("fam_reg.html", areas=areas, category=selected_category)

