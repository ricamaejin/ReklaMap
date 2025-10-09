from flask import Blueprint, render_template, request, jsonify, session, redirect
import logging
import traceback
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

logger = logging.getLogger(__name__)

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
            # Store as None if empty, 'NA', or 'N/A'
            if suffix is not None and str(suffix).strip().upper() in ("NA", "N/A", ""):
                suffix = None
            dob = request.form.get("reg_dob")
            sex = request.form.get("reg_sex")
            cit = request.form.get("reg_cit")
            age = request.form.get("reg_age")
            year = request.form.get("reg_year")
            civil = request.form.get("fam_civil")
            cur_add = request.form.get("reg_cur_add")
            recipient = request.form.get("recipient")
            if recipient:
                recipient_l = recipient.strip().lower()
                if recipient_l in ("yes", "y"): recipient = "Yes"
                elif recipient_l in ("no", "n"): recipient = "No"
            phone = request.form.get("reg_num")
            hoa_area_id = request.form.get("hoa_area_id")

            # Quick debug logs for diagnostics (safe fields only)
            try:
                logger.debug("[nonmemreg] form keys: %s", list(request.form.keys()))
                logger.debug("[nonmemreg] hoa_area_id=%s dob=%s age=%s recipient=%s", hoa_area_id, dob, age, recipient)
                # Also print to console in case logging isn't configured
                print(f"[nonmemreg] hoa_area_id={hoa_area_id} dob={dob} age={age} recipient={recipient}")
            except Exception:
                pass

            # --- Handle signature upload ---
            sig_file = request.files.get("signatureInput")
            sig_filename = None
            if sig_file and sig_file.filename:
                sig_filename = secure_filename(sig_file.filename)
                sig_file.save(os.path.join(UPLOAD_FOLDER, sig_filename))

            # --- Resolve HOA (Area) to store area_id in Registration.hoa (DB expects integer) ---
            hoa_value = None
            if hoa_area_id:
                area_obj = None
                try:
                    area_id_int = int(hoa_area_id)
                except (TypeError, ValueError):
                    area_id_int = None

                if area_id_int is not None:
                    try:
                        # Prefer SQLAlchemy 2.x style if available
                        get_method = getattr(db.session, "get", None)
                        if callable(get_method):
                            area_obj = db.session.get(Area, area_id_int)
                        else:
                            area_obj = Area.query.get(area_id_int)
                    except Exception:
                        # Fallback to query.get
                        try:
                            area_obj = Area.query.get(area_id_int)
                        except Exception:
                            area_obj = None

                if area_obj:
                    # Store numeric area_id in 'hoa' column due to DB type
                    hoa_value = area_obj.area_id

            # --- Save main registration ---
            # Safe parse helpers
            def parse_int(v):
                try:
                    return int(v) if v not in (None, "") else None
                except Exception:
                    return None

            def parse_date(v):
                try:
                    return datetime.strptime(v, "%Y-%m-%d") if v else None
                except Exception:
                    return None

            new_reg = Registration(
                user_id=user_id,
                category=category,
                last_name=last,
                first_name=first,
                middle_name=mid,
                suffix=suffix,
                date_of_birth=parse_date(dob),
                sex=sex,
                citizenship=cit,
                age=parse_int(age),
                year_of_residence=year,
                civil_status=civil,
                current_address=cur_add,
                recipient_of_other_housing=recipient,
                phone_number=phone,
                hoa=hoa_value,
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

            # Commit main registration first
            db.session.commit()

            # --- Save non-member registration details (best-effort) ---
            if category == "non_member":
                try:
                    non_mem = RegistrationNonMember(
                        registration_id=new_reg.registration_id,
                        connections=connections
                    )
                    db.session.add(non_mem)
                    db.session.commit()
                except Exception:
                    db.session.rollback()

            return jsonify({"success": True, "message": "Registered successfully!"})

        except Exception as e:
            db.session.rollback()
            trace = traceback.format_exc()
            # Log the full traceback to server logs and print for visibility
            try:
                logger.exception("[nonmemreg] Registration failed: %s", e)
            except Exception:
                pass
            try:
                print("[nonmemreg] ERROR:\n", trace)
            except Exception:
                pass
            return jsonify({"success": False, "error": str(e), "trace": trace}), 500

    # GET → show form with HOA areas
    areas = Area.query.order_by(Area.area_name).all()
    selected_category = request.args.get("category", "non_member")
    return render_template("non-mem_reg.html", areas=areas, category=selected_category)
