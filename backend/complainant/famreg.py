from flask import Blueprint, render_template, request, jsonify, session
from pathlib import Path
from datetime import datetime
from backend.database.db import db
from backend.database.models import Area, Registration, Beneficiary, RegistrationFamOfMember
from backend.complainant.redirects import complaint_redirect_path

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
            # Store as None if empty, 'NA', or 'N/A'
            if parent_suffix.upper() in ("NA", "N/A", ""):
                parent_suffix = None
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

            # Middle initial: only validate if the user supplied one.
            # Ignore periods and case, only compare first letter
            def normalize_mi(val):
                if not val: return None
                return str(val).replace('.', '').strip().upper()[:1] or None
            if input_middle:
                if normalize_mi(parent_beneficiary.middle_initial) != normalize_mi(input_middle):
                    mismatches.append("Middle Name")
            if (parent_beneficiary.suffix or None) != input_suffix:
                mismatches.append("Suffix")

            # Add block, lot, or HOA checks if these fields exist in your form
            try:
                if parent_blk and parent_beneficiary.block:
                    # Compare as integers when possible
                    try:
                        submitted_blk = int(parent_blk)
                    except (TypeError, ValueError):
                        submitted_blk = None
                    benef_blk_no = parent_beneficiary.block.block_no
                    if submitted_blk != benef_blk_no:
                        mismatches.append("Block Assignment")
            except Exception as e:
                print(f"Block comparison error: {e}")
                
            try:
                if parent_lot_asn and str(parent_lot_asn) != str(parent_beneficiary.lot_no):
                    mismatches.append("Lot Assignment")
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

            # Normalize recipient (Yes/No) and civil status to match Registration enums
            recipient_norm = None
            if recipient is not None:
                _rc = str(recipient).strip().lower()
                if _rc in ("yes", "y", "true", "1"):
                    recipient_norm = "Yes"
                elif _rc in ("no", "n", "false", "0"):
                    recipient_norm = "No"

            civil_map = {
                "single": "Single",
                "married": "Married",
                "widowed": "Widowed",
                "separated": "Separated",
                "divorced": "Divorced",
                "annulled": "Annulled",
            }
            fam_civil_norm = None
            if fam_civil:
                fam_civil_norm = civil_map.get(str(fam_civil).strip().lower())

            # --- Step 3: Create main Registration record for the person registering (complainant) ---
            try:
                print(f"Creating registration for registrant (complainant): {reg_first} {reg_last}")
                
                # Supporting documents from form (if present) – these belong to the HOA member (parent)
                doc_map = {
                    "doc_title": "title",
                    "doc_contract": "contract_to_sell",
                    "doc_fullpay": "certificate_of_full_payment",
                    "doc_award": "pre_qualification_stub",
                    "doc_agreement": "contract_agreement",
                    "doc_deed": "deed_of_sale"
                }
                docs_selected = [v for k, v in doc_map.items() if request.form.get(k) == "on"]
                # Build a comprehensive JSON blob for the family member (parent) extra fields
                fam_supporting_meta = {v: (request.form.get(k) == "on") for k, v in doc_map.items()}
                # Include HOA/lot/civil status/recipient/current address and explicit parent identity details
                fam_supporting_meta.update({
                    "parent_first_name": parent_first,
                    "parent_last_name": parent_last,
                    "parent_middle_name": input_middle,
                    "parent_suffix": input_suffix,
                    "parent_age": int(parent_age) if parent_age and str(parent_age).isdigit() else None,
                    "parent_citizenship": parent_cit,
                    # HOA and lot info straight from form (string-typed); DB links via beneficiary_id as well
                    "hoa": parent_hoa,
                    "block_assignment": parent_blk,
                    "lot_assignment": parent_lot_asn,
                    "lot_size": parent_lot_size,
                    # Family member (parent) civil status and program recipient (normalized)
                    "civil_status": fam_civil_norm,
                    "recipient_of_other_housing": recipient_norm,
                    # Parent current address captured from dedicated field
                    "current_address": request.form.get("parent_cur_add")
                })

                # Normalize and mirror HOA Member Information into Registration as requested
                try:
                    mirrored_hoa = int(parent_hoa) if parent_hoa and str(parent_hoa).strip().isdigit() else (parent_beneficiary.area_id if parent_beneficiary else None)
                except Exception:
                    mirrored_hoa = parent_beneficiary.area_id if parent_beneficiary else None
                try:
                    mirrored_block = int(parent_blk) if parent_blk and str(parent_blk).strip().isdigit() else None
                except Exception:
                    mirrored_block = None
                try:
                    mirrored_lot = int(parent_lot_asn) if parent_lot_asn and str(parent_lot_asn).strip().isdigit() else None
                except Exception:
                    mirrored_lot = None
                try:
                    mirrored_lot_size = int(parent_lot_size) if parent_lot_size and str(parent_lot_size).strip().isdigit() else None
                except Exception:
                    mirrored_lot_size = None
                mirrored_civil = fam_civil_norm if fam_civil_norm else None
                mirrored_recipient = recipient_norm

                # Create base Registration record
                registration = Registration(
                    user_id=user_id,
                    category="family_of_member",
                    # Complainant (registrant) details → Registration table
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
                    # Keep link to verified HOA member for traceability
                    beneficiary_id=parent_beneficiary.beneficiary_id,
                    # Mirror these HOA member (parent) fields into Registration per requirement
                    hoa=mirrored_hoa,
                    block_no=mirrored_block,
                    lot_no=mirrored_lot,
                    lot_size=mirrored_lot_size,
                    civil_status=mirrored_civil,
                    recipient_of_other_housing=mirrored_recipient,
                    supporting_documents=None
                )
                
                db.session.add(registration)
                db.session.flush()  # Get the registration_id before commit
                
                # Create RegistrationFamOfMember record – this stores the HOA member (parent) information
                fam_member = RegistrationFamOfMember(
                    registration_id=registration.registration_id,
                    beneficiary_id=parent_beneficiary.beneficiary_id,
                    # Parent (family member) identity and demographics
                    last_name=parent_last,
                    first_name=parent_first,
                    middle_name=input_middle,
                    suffix=input_suffix,
                    date_of_birth=datetime.strptime(parent_dob, "%Y-%m-%d") if parent_dob else None,
                    sex=parent_sex,
                    citizenship=parent_cit,
                    age=int(parent_age) if parent_age and str(parent_age).isdigit() else None,
                    phone_number=None,
                    year_of_residence=int(parent_year) if parent_year and str(parent_year).isdigit() else None,
                    relationship=relationship,  # Store relationship directly in the field
                    current_address=request.form.get("parent_cur_add"),
                    # Store documents and extended HOA/lot/civil/recipient/current_address metadata
                    supporting_documents=fam_supporting_meta
                )
                
                db.session.add(fam_member)
                db.session.commit()
                print(f"Registration created with ID: {registration.registration_id} (family member saved under RegistrationFamOfMember)")
            except Exception as e:
                print(f"Error creating registration: {e}")
                raise
            except Exception as e:
                print(f"Error creating family member record: {e}")
                raise

            # Determine redirect target based on stored complaint type (centralized mapping)
            complaint_type = session.get("type_of_complaint")
            next_url = complaint_redirect_path(complaint_type, has_registration=True)

            return jsonify({"success": True, "message": "Registered successfully!", "redirect": next_url})

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
