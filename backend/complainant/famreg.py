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
            parent_dob = request.form.get("parent_dob")
            parent_sex = (request.form.get("parent_sex") or "").strip()
            parent_cit = (request.form.get("parent_cit") or "").strip()
            parent_age = request.form.get("parent_age")
            parent_year = (request.form.get("parent_year") or "").strip()
            parent_hoa = request.form.get("parent_hoa")
            parent_blk = request.form.get("parent_blk")
            parent_lot_asn = request.form.get("parent_lot_asn")
            parent_lot_size = request.form.get("parent_lot_size")
            fam_civil = request.form.get("fam_civil")

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
            try:
                if parent_blk and parent_beneficiary.block and str(parent_blk) != str(parent_beneficiary.block.block_no):
                    mismatches.append("Block Assignment")
            except Exception as e:
                print(f"Block comparison error: {e}")
                
            try:
                if parent_lot_asn and str(parent_lot_asn) != str(parent_beneficiary.lot_no):
                    mismatches.append("Lot Number")
            except Exception as e:
                print(f"Lot comparison error: {e}")
                
            try:
                if parent_hoa and str(parent_hoa) != str(parent_beneficiary.area_id):
                    mismatches.append("HOA")
            except Exception as e:
                print(f"HOA comparison error: {e}")

            if mismatches:
                return jsonify({
                    "success": False,
                    "error": "Mismatch found in the following field(s): " + ", ".join(mismatches)
                }), 400

            # --- Step 2: Get registrant/family member info from reg_* (the person actually registering) ---
            reg_first = (request.form.get("reg_first") or "").strip()
            reg_last = (request.form.get("reg_last") or "").strip()
            reg_mid = (request.form.get("reg_mid") or "").strip()
            reg_suffix = (request.form.get("reg_suffix") or "").strip()
            # Ensure NA/N/A/empty are saved as None
            reg_mid = reg_mid if reg_mid not in ("", "NA", "N/A") else None
            reg_suffix = reg_suffix if reg_suffix not in ("", "NA", "N/A") else None
            reg_dob = request.form.get("reg_dob")
            reg_sex = request.form.get("reg_sex")
            reg_citizenship = request.form.get("reg_cit")
            reg_age = request.form.get("reg_age")
            reg_phone = request.form.get("reg_phone")
            reg_year = request.form.get("reg_year")
            reg_cur_add = request.form.get("reg_cur_add")
            relationship = request.form.get("reg_relationship")
            recipient = request.form.get("recipient")

            # --- Step 3: Create main Registration record for the person registering (family member) ---
            try:
                print(f"Creating registration for: {reg_first} {reg_last}")
                registration = Registration(
                    user_id=user_id,
                    category="family_of_member",
                    last_name=reg_last,
                    first_name=reg_first,
                    middle_name=reg_mid,
                    suffix=reg_suffix,
                    date_of_birth=datetime.strptime(reg_dob, "%Y-%m-%d") if reg_dob else None,
                    sex=reg_sex,
                    citizenship=reg_citizenship,
                    age=int(reg_age) if reg_age else None,
                    phone_number=reg_phone,
                    year_of_residence=reg_year,
                    current_address=reg_cur_add,
                    civil_status=fam_civil,
                    recipient_of_other_housing=recipient,
                    # Reference to parent's beneficiary info - with safe access
                    hoa=str(parent_beneficiary.area_id) if parent_beneficiary.area_id else None,
                    block_no=str(parent_beneficiary.block.block_no) if parent_beneficiary.block else None,
                    lot_no=str(parent_beneficiary.lot_no) if parent_beneficiary.lot_no else None,
                    lot_size=str(parent_beneficiary.sqm) if parent_beneficiary.sqm else None
                )
                db.session.add(registration)
                db.session.flush()  # Get the registration_id
                print(f"Registration created with ID: {registration.registration_id}")
            except Exception as e:
                print(f"Error creating registration: {e}")
                raise

            # --- Step 4: Save parent HOA member info in RegistrationFamOfMember ---
            try:
                print(f"Creating family member record for parent: {parent_first} {parent_last}")
                fam_member = RegistrationFamOfMember(
                    registration_id=registration.registration_id,
                    last_name=parent_last,
                    first_name=parent_first,
                    middle_name=input_middle,
                    suffix=input_suffix,
                    date_of_birth=datetime.strptime(parent_dob, "%Y-%m-%d") if parent_dob else None,
                    sex=parent_sex,
                    citizenship=parent_cit,
                    age=int(parent_age) if parent_age else None,
                    phone_number=None,  # Parent phone not collected in form
                    year_of_residence=int(parent_year) if parent_year and parent_year.isdigit() else None,
                    relationship=relationship,
                    supporting_documents={
                        "title": bool(request.form.get("doc_title")),
                        "contract": bool(request.form.get("doc_contract")),
                        "fullpay": bool(request.form.get("doc_fullpay")),
                        "award": bool(request.form.get("doc_award")),
                        "agreement": bool(request.form.get("doc_agreement")),
                        "deed": bool(request.form.get("doc_deed")),
                    },
                    beneficiary_id=parent_beneficiary.beneficiary_id  # Link to parent's beneficiary record
                )
                db.session.add(fam_member)
                db.session.commit()
                print("Family member record created successfully")
            except Exception as e:
                print(f"Error creating family member record: {e}")
                raise

            return jsonify({"success": True, "message": "Registered successfully!"})

        except Exception as e:
            db.session.rollback()
            print(f"Error in famreg: {str(e)}")  # Add logging
            import traceback
            traceback.print_exc()  # Print full traceback for debugging
            return jsonify({"success": False, "error": str(e)}), 500

    # GET → render form
    areas = Area.query.order_by(Area.area_name).all()
    selected_category = request.args.get("category", "fam_member")
    return render_template("fam_reg.html", areas=areas, category=selected_category)
