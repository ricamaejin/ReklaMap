from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from werkzeug.utils import secure_filename
import os
from datetime import datetime

from backend.database.db import db
from backend.database.models import Registration, Area

nonmemreg_bp = Blueprint(
    "nonmemreg",
    __name__,
    url_prefix="/complainant",
    template_folder=r"C:\Users\win10\Documents\GitHub\ReklaMap\frontend\complainant\home"
)

UPLOAD_FOLDER = "uploads/signatures"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# -----------------------------
# NON-MEMBER REGISTRATION
# -----------------------------
@nonmemreg_bp.route("/nonmemreg", methods=["GET", "POST"])
def nonmemreg():
    if request.method == "POST":
        try:
            # ✅ logged in user
            user_id = session.get("user_id")
            if not user_id:
                return jsonify({"success": False, "error": "User not logged in"}), 401

            # ✅ get category from form (hidden input or query param)
            category = request.form.get("category", "non_member")

            # ✅ form fields
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
            lot_add = request.form.get("reg_lot_add")
            lot_size = request.form.get("reg_lot_size")
            civil = request.form.get("fam_civil")
            cur_add = request.form.get("reg_cur_add")
            recipient = request.form.get("recipient")
            phone = request.form.get("reg_num")

            # ✅ handle signature
            sig_file = request.files.get("signatureInput")
            sig_filename = None
            if sig_file and sig_file.filename:
                sig_filename = secure_filename(sig_file.filename)
                sig_file.save(os.path.join(UPLOAD_FOLDER, sig_filename))

      # ✅ save to DB
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
                hoa=hoa,
                phone_number=phone,
                lot_no=lot_add,
                lot_size=lot_size,
                civil_status=civil,
                current_address=cur_add,
                recipient_of_other_housing=recipient,
                signature_path=sig_filename
            )

            db.session.add(new_reg)
            db.session.commit()  # <-- This saves new_reg and assigns registration_id

            # -------------------------
            # If non-member → insert into registration_non_member
            # -------------------------
            if category == "non_member":
                from backend.database.models import RegistrationNonMember  # make sure this exists
                # Example: store connections as empty JSON or from form
                connections = request.form.get("connections", "{}")  # JSON string
                non_mem = RegistrationNonMember(
                    registration_id=new_reg.registration_id,
                    connections=connections
                )
                db.session.add(non_mem)
                db.session.commit()

            return jsonify({"success": True, "message": "Non-member registered successfully!"})

        except Exception as e:
            db.session.rollback()
            return jsonify({"success": False, "error": str(e)})

    # GET → show form with HOA areas
    areas = Area.query.order_by(Area.area_name).all()
    selected_category = request.args.get("category", "non_member")
    return render_template("non-mem_reg.html", areas=areas, category=selected_category)
