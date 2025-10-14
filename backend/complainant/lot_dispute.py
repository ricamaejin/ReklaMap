from datetime import datetime
from flask import Blueprint, session, send_from_directory, jsonify, request, render_template
from werkzeug.utils import secure_filename
from backend.database.models import (
    Registration,
    Complaint,
    LotDispute,
    Beneficiary,
    Block,
    Area,
    RegistrationFamOfMember,
    GeneratedLots,
)
from backend.database.db import db
import os, json, time


# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "..", "frontend", "complainant", "complaints"))
UPLOAD_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "uploads", "signatures"))
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Blueprint for Lot Dispute-only routes
lot_dispute_bp = Blueprint(
    "lot_dispute",
    __name__,
    url_prefix="/complainant/lot_dispute",
)


# -----------------------------
# Helpers
# -----------------------------

def get_area_name(area_id):
    """Resolve an area identifier (id, code, or name) to the canonical area_name.

    Handles numeric area_id, area_code, or area_name values robustly and
    falls back to returning the original input as a string when no match found.
    """
    if not area_id:
        return ""
    # Try numeric id first
    try:
        candidate = int(area_id)
        area = Area.query.get(candidate)
        if area:
            return area.area_name
    except Exception:
        # not an int or lookup failed: continue to try other lookups
        pass

    # Try by area_code or area_name
    try:
        s = str(area_id)
        area = Area.query.filter((Area.area_code == s) | (Area.area_name == s)).first()
        if area:
            return area.area_name
    except Exception:
        pass

    # Last resort: return the original value as string
    return str(area_id)


def resolve_hoa_for_registration(registration):
    """Robustly determine the Area.area_name for a Registration.

    Order:
    1. Try registration.hoa (id/code/name) via get_area_name()
    2. Fallback to beneficiary lookup using registration.block_no and registration.lot_no
    """
    try:
        # 1) Try registration.hoa
        hoa_val = getattr(registration, 'hoa', None)
        if hoa_val:
            s = str(hoa_val).strip()
            if s:
                # Try numeric/id resolution first
                resolved = get_area_name(s)
                # Try exact name match
                a = Area.query.filter_by(area_name=resolved).first() if resolved else None
                if a:
                    return a.area_name
                # Try exact code or exact name on original input
                a2 = Area.query.filter((Area.area_code == s) | (Area.area_name == s)).first()
                if a2:
                    return a2.area_name
                # Try case-insensitive contains match for area_name (helps with small formatting differences)
                try:
                    a3 = Area.query.filter(Area.area_name.ilike(f"%{s}%")).first()
                    if a3:
                        return a3.area_name
                except Exception:
                    pass

        # 1b) If registration references a beneficiary directly, prefer that
        try:
            ben_id = getattr(registration, 'beneficiary_id', None)
            if ben_id:
                ben = Beneficiary.query.get(ben_id)
                if ben:
                    a = Area.query.get(ben.area_id)
                    if a:
                        return a.area_name
        except Exception:
            pass

        # 2) Fallback: derive via block_no / lot_no -> Beneficiary -> Area
        bn = getattr(registration, 'block_no', None)
        ln = getattr(registration, 'lot_no', None)
        if bn and ln:
            try:
                bn_c = int(bn)
            except Exception:
                bn_c = bn
            try:
                ln_c = int(ln)
            except Exception:
                ln_c = ln
            ben = Beneficiary.query.filter_by(block_id=bn_c, lot_no=ln_c).first()
            if not ben:
                blk = Block.query.filter_by(block_no=bn_c).first()
                if blk:
                    ben = Beneficiary.query.filter_by(block_id=blk.block_id, lot_no=ln_c).first()
            if ben:
                a = Area.query.get(ben.area_id)
                if a:
                    return a.area_name
    except Exception:
        pass
    return ""


def _parse_list(val):
    try:
        if isinstance(val, list):
            return val
        if isinstance(val, str):
            s = val.strip()
            if not s:
                return []
            if s.startswith("["):
                return json.loads(s)
            if "," in s:
                return [p.strip() for p in s.split(",") if p.strip()]
            return [s]
    except Exception:
        pass
    return []


# -----------------------------
# Preview route (optional)
# -----------------------------

@lot_dispute_bp.route("/complaint/<int:complaint_id>")
def view_lot_dispute_complaint(complaint_id):
    user_id = session.get("user_id")
    if not user_id:
        return "Not logged in", 401

    complaint = Complaint.query.get_or_404(complaint_id)
    registration = Registration.query.get(complaint.registration_id)
    if not registration or registration.user_id != user_id:
        return "Unauthorized", 403

    # Attach supporting documents for templates
    try:
        from backend.database.models import RegistrationHOAMember
        hoa_member = RegistrationHOAMember.query.filter_by(
            registration_id=registration.registration_id
        ).first()
        if hoa_member and getattr(hoa_member, "supporting_documents", None):
            setattr(registration, "supporting_documents", hoa_member.supporting_documents)
        else:
            if not hasattr(registration, "supporting_documents"):
                setattr(registration, "supporting_documents", None)
    except Exception:
        if not hasattr(registration, "supporting_documents"):
            setattr(registration, "supporting_documents", None)

    # Use local helper directly (avoid re-importing this module)
    form_structure = (
        get_form_structure("Lot Dispute") if complaint.type_of_complaint == "Lot Dispute" else []
    )

    answers = {}
    lot = None
    if complaint.type_of_complaint == "Lot Dispute":
        lot = LotDispute.query.filter_by(complaint_id=complaint_id).first()
        if lot:
            q2_list = _parse_list(getattr(lot, "q2", None))
            q4_list = _parse_list(getattr(lot, "q4", None))
            q5_list = _parse_list(getattr(lot, "q5", None))
            q6_list = _parse_list(getattr(lot, "q6", None))
            q7_list = _parse_list(getattr(lot, "q7", None))
            q8_list = _parse_list(getattr(lot, "q8", None))

            # q9 dict { claim, documents }
            q9_raw = getattr(lot, "q9", None)
            q9_data = {"claim": "", "documents": []}
            try:
                if isinstance(q9_raw, dict):
                    q9_data = {"claim": q9_raw.get("claim", ""), "documents": q9_raw.get("documents", [])}
                elif isinstance(q9_raw, str) and q9_raw.strip():
                    parsed = json.loads(q9_raw)
                    if isinstance(parsed, dict):
                        q9_data = {"claim": parsed.get("claim", ""), "documents": parsed.get("documents", [])}
            except Exception:
                pass

            # q10 dict
            q10_raw = getattr(lot, "q10", None)
            q10_data = {}
            try:
                if isinstance(q10_raw, dict):
                    q10_data = q10_raw
                elif isinstance(q10_raw, str) and q10_raw.strip():
                    q10_data = json.loads(q10_raw)
            except Exception:
                q10_data = {}

            q3_val = lot.q3.strftime("%Y-%m-%d") if getattr(lot, "q3", None) else ""

            answers = {
                "q1": getattr(lot, "q1", "") or "",
                "q2": q2_list,
                "q3": q3_val,
                "q4": q4_list,
                "q5": q5_list,
                "q6": q6_list,
                "q7": q7_list,
                "q8": q8_list,
                "q9": q9_data,
                "q10": q10_data,
                "description": (
                    getattr(lot, "description", None) or getattr(complaint, "description", "") or ""
                ),
                "signature": (
                    getattr(lot, "signature", None) or getattr(registration, "signature_path", "") or ""
                ),
            }

    # Family of member parent info
    parent_info = None
    relationship = None
    try:
        if registration.category == "family_of_member":
            fam_member = RegistrationFamOfMember.query.filter_by(
                registration_id=registration.registration_id
            ).first()
            if fam_member:
                relationship = fam_member.relationship
                def safe(v):
                    return str(v).strip() if v else ""
                parts = [
                    safe(fam_member.first_name),
                    safe(fam_member.middle_name),
                    safe(fam_member.last_name),
                    safe(fam_member.suffix),
                ]
                sd = getattr(fam_member, "supporting_documents", {}) or {}
                hoa_raw = sd.get("hoa")
                parent_info = {
                    "full_name": " ".join([p for p in parts if p]),
                    "first_name": fam_member.first_name,
                    "middle_name": fam_member.middle_name,
                    "last_name": fam_member.last_name,
                    "suffix": fam_member.suffix,
                    "date_of_birth": fam_member.date_of_birth,
                    "sex": fam_member.sex,
                    "citizenship": fam_member.citizenship,
                    "age": fam_member.age,
                    "phone_number": fam_member.phone_number,
                    "year_of_residence": fam_member.year_of_residence,
                    "supporting_documents": getattr(fam_member, "supporting_documents", None),
                    # Additional mapped fields for templates
                    "hoa": get_area_name(hoa_raw) if hoa_raw else "",
                    "block_no": sd.get("block_assignment") or "",
                    "lot_no": sd.get("lot_assignment") or "",
                    "lot_size": sd.get("lot_size") or "",
                    "civil_status": sd.get("civil_status") or "",
                    "recipient_of_other_housing": sd.get("recipient_of_other_housing") or "",
                    "current_address": getattr(fam_member, "current_address", None) or sd.get("current_address") or "",
                }
    except Exception:
        pass


    return render_template(
        "complaint_details_valid.html" if complaint.status == "Valid" else "complaint_details_invalid.html",
        complaint=complaint,
        registration=registration,
        form_structure=form_structure,
        answers=answers,
        parent_info=parent_info,
        relationship=relationship,
        get_area_name=get_area_name,
        lot_dispute=lot,
    )


# -----------------------------
# New form and session data
# -----------------------------

@lot_dispute_bp.route("/new_lot_dispute_form")
def new_lot_dispute_form():
    user_id = session.get("user_id")
    if not user_id:
        return "Not logged in", 401
    registration = Registration.query.filter_by(user_id=user_id).first()
    if not registration:
        return "No registration found for user", 400
    complaint_id = f"{user_id}-{int(time.time())}"
    session["complaint_id"] = complaint_id
    session["registration_id"] = registration.registration_id
    html_dir = TEMPLATE_DIR
    return send_from_directory(html_dir, "lot_dispute.html")


@lot_dispute_bp.route("/get_lot_session_data")
def get_lot_session_data():
    registration_id = session.get("registration_id")
    complaint_id = session.get("complaint_id")
    
    if not registration_id:
        return jsonify({"error": "No registration found in session"}), 400
    
    reg = Registration.query.get(registration_id)
    if not reg:
        return jsonify({"error": "Registration not found"}), 404

    # Helper to safely handle empty or NA values
    def safe(val):
        if not val:
            return ""
        val_str = str(val).strip()
        if val_str.lower() in {"na", "n/a", "none"}:
            return ""
        return val_str

    # Compose full name
    name_parts = [safe(reg.first_name), safe(reg.middle_name), safe(reg.last_name), safe(reg.suffix)]
    full_name = " ".join([p for p in name_parts if p])

    data = {
        "complaint_id": complaint_id,
        "registration_id": reg.registration_id,
        "category": reg.category,
        "full_name": full_name,
        "date_of_birth": reg.date_of_birth.isoformat() if reg.date_of_birth else "",
        "sex": reg.sex,
        "civil_status": reg.civil_status,
        "citizenship": reg.citizenship,
        "age": reg.age,
        "cur_add": reg.current_address or "",
        "phone_number": reg.phone_number,
        "year_of_residence": reg.year_of_residence,
        "recipient_of_other_housing": reg.recipient_of_other_housing,
        "hoa": resolve_hoa_for_registration(reg) if reg else "",
        "blk_num": getattr(reg, "block_no", "") or "",
        "lot_num": getattr(reg, "lot_no", "") or "",
        "lot_size": getattr(reg, "lot_size", "") or "",
        "supporting_documents": None,
    }

    # Handle HOA members
    if reg.category == "hoa_member":
        from backend.database.models import RegistrationHOAMember
        hoa_member = RegistrationHOAMember.query.filter_by(registration_id=reg.registration_id).first()
        if hoa_member and hoa_member.supporting_documents:
            data["supporting_documents"] = hoa_member.supporting_documents

    # Handle non-members
    elif reg.category == "non_member":
        from backend.database.models import RegistrationNonMember
        non_member = RegistrationNonMember.query.filter_by(registration_id=reg.registration_id).first()
        connections_val = ""
        if non_member and hasattr(non_member, "connections") and non_member.connections:
            conn = non_member.connections
            checkbox_labels = [
                "I live on the lot but I am not the official beneficiary",
                "I live near the lot and I am affected by the issue",
                "I am claiming ownership of the lot",
                "I am related to the person currently occupying the lot",
                "I was previously assigned to this lot but was replaced or removed"
            ]
            display_labels = []
            if isinstance(conn, dict):
                for idx, label in enumerate(checkbox_labels, start=1):
                    if conn.get(f"connection_{idx}"):
                        display_labels.append(label)
                if conn.get("connection_other"):
                    display_labels.append(str(conn["connection_other"]))
            elif isinstance(conn, list):
                display_labels = [str(x) for x in conn if x]
            elif isinstance(conn, str):
                display_labels = [conn]
            else:
                display_labels = [str(conn)]
            connections_val = ", ".join(display_labels)
            data["supporting_documents"] = non_member.connections
        data["connections"] = connections_val

    # Handle family of HOA members
    elif reg.category == "family_of_member":
        from backend.database.models import RegistrationFamOfMember, Beneficiary
        fam = RegistrationFamOfMember.query.filter_by(registration_id=reg.registration_id).first()
        if fam:
            # Supporting documents for family member
            if fam.supporting_documents:
                data["supporting_documents"] = fam.supporting_documents

            # Parent info
            parent_name_parts = [safe(fam.first_name), safe(fam.middle_name), safe(fam.last_name), safe(fam.suffix)]
            parent_full_name = " ".join([p for p in parent_name_parts if p])
            data["relationship"] = fam.relationship
            parent_info = {
                "full_name": parent_full_name,
                "date_of_birth": fam.date_of_birth.isoformat() if fam.date_of_birth else "",
                "sex": fam.sex,
                "citizenship": fam.citizenship,
                "age": fam.age,
                "phone_number": fam.phone_number,
                "year_of_residence": fam.year_of_residence,
                "current_address": fam.current_address or "",
            }
            data["parent_info"] = parent_info

            # Override HOA, Block, Lot, Lot Size from family member or linked beneficiary
            sd = getattr(fam, "supporting_documents", {}) or {}
            if sd.get("hoa"):
                # family supporting docs may contain hoa id/code/name
                data["hoa"] = get_area_name(sd["hoa"]) or data.get("hoa", "")
            else:
                try:
                    if fam.beneficiary_id:
                        ben = Beneficiary.query.get(fam.beneficiary_id)
                        if ben:
                            a = Area.query.get(ben.area_id)
                            if a:
                                data["hoa"] = a.area_name
                except Exception:
                    pass

            data["blk_num"] = sd.get("block_assignment") or data["blk_num"]
            data["lot_num"] = sd.get("lot_assignment") or data["lot_num"]
            data["lot_size"] = sd.get("lot_size") or data["lot_size"]

    return jsonify(data)



# -----------------------------
# Validation and submission
# -----------------------------

@lot_dispute_bp.route("/validate_pairs", methods=["POST"])
def validate_pairs():
    try:
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"success": False, "message": "User not logged in"}), 401
        registration_id = session.get("registration_id")
        reg = Registration.query.get(registration_id) if registration_id else None
        if not reg:
            return jsonify({"success": False, "message": "Registration not found"}), 400

        area_id = None
        if getattr(reg, "hoa", None):
            try:
                area_id_candidate = int(reg.hoa)
                if Area.query.get(area_id_candidate):
                    area_id = area_id_candidate
            except Exception:
                area_id = None
        if area_id is None and reg.block_no and reg.lot_no:
            try:
                bn = int(reg.block_no)
            except Exception:
                bn = reg.block_no
            try:
                ln = int(reg.lot_no)
            except Exception:
                ln = reg.lot_no
            beneficiary = Beneficiary.query.filter_by(block_id=bn, lot_no=ln).first()
            if not beneficiary:
                blk = Block.query.filter_by(block_no=bn).first()
                if blk:
                    beneficiary = Beneficiary.query.filter_by(block_id=blk.block_id, lot_no=ln).first()
            if beneficiary:
                area_id = beneficiary.area_id

        if area_id is None:
            return jsonify({"success": False, "message": "Area assignment not found from your registration."}), 400

        payload = request.get_json(silent=True) or {}
        pairs = payload.get("pairs")
        if not isinstance(pairs, list):
            return jsonify({"success": False, "message": "Invalid payload."}), 400

        found_invalid = False
        for idx, item in enumerate(pairs, start=1):
            b_str = str(item.get("block", "")).strip()
            l_str = str(item.get("lot", "")).strip()
            if not b_str or not l_str:
                found_invalid = True
                break
            try:
                b_no = int(b_str)
            except Exception:
                found_invalid = True
                break
            try:
                l_no = int(l_str)
            except Exception:
                found_invalid = True
                break
            blk = Block.query.filter_by(area_id=area_id, block_no=b_no).first()
            if not blk:
                found_invalid = True
                break
            ben = Beneficiary.query.filter_by(block_id=blk.block_id, lot_no=l_no).first()
            if not ben:
                gen = GeneratedLots.query.filter_by(block_id=blk.block_id, lot_no=l_no).first()
                if not gen:
                    found_invalid = True
                    break
        if found_invalid:
            return jsonify({
                "success": False,
                "message": "Block or lot could not be found for your HOA.",
                "mismatches": ["Block or lot could not be found for your HOA."],
            }), 400
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": f"Server error: {e}"}), 500


@lot_dispute_bp.route("/submit_lot_dispute", methods=["POST"])
def submit_lot_dispute():
    try:
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"success": False, "message": "User not logged in"}), 401
        registration_id = request.form.get("registration_id") or session.get("registration_id")
        registration = Registration.query.get(registration_id)
        if not registration:
            return jsonify({"success": False, "message": "Parent registration not found"}), 400

        def clean_field(val):
            if not val:
                return None
            val_str = str(val).strip()
            if val_str.lower() in {"na", "n/a", "none", ""}:
                return None
            return val_str

        middle_name = clean_field(registration.middle_name)
        suffix = clean_field(registration.suffix)
        name_parts = [registration.first_name, middle_name, registration.last_name, suffix]
        complainant_name = " ".join([p for p in name_parts if p])
        address = registration.current_address or ""

        area_id = None
        # Prefer direct registration.hoa when present
        if getattr(registration, "hoa", None):
            try:
                area_id_candidate = int(registration.hoa)
                if Area.query.get(area_id_candidate):
                    area_id = area_id_candidate
            except Exception:
                area_id = None
        # For family_of_member, use family JSON or beneficiary link
        if area_id is None and registration.category == "family_of_member":
            try:
                fam = RegistrationFamOfMember.query.filter_by(registration_id=registration.registration_id).first()
                if fam:
                    sd = getattr(fam, "supporting_documents", {}) or {}
                    hoa_src = sd.get("hoa")
                    if hoa_src:
                        try:
                            candidate = int(hoa_src)
                            if Area.query.get(candidate):
                                area_id = candidate
                        except Exception:
                            pass
                    if area_id is None and fam.beneficiary_id:
                        ben = Beneficiary.query.get(fam.beneficiary_id)
                        if ben:
                            area_id = ben.area_id
            except Exception:
                area_id = None
        # Fallback: derive via registration block/lot
        try:
            if area_id is None and registration.block_no and registration.lot_no:
                bn = registration.block_no
                ln = registration.lot_no
                try:
                    bn = int(bn)
                except Exception:
                    pass
                try:
                    ln = int(ln)
                except Exception:
                    pass
                beneficiary = Beneficiary.query.filter_by(block_id=bn, lot_no=ln).first()
                if not beneficiary:
                    blk = Block.query.filter_by(block_no=bn).first()
                    if blk:
                        beneficiary = Beneficiary.query.filter_by(block_id=blk.block_id, lot_no=ln).first()
                if beneficiary:
                    area_id = beneficiary.area_id
        except Exception:
            area_id = None

        if area_id is None:
            return jsonify({
                "success": False,
                "message": "Cannot submit complaint: Area assignment not found from your registration.",
                "mismatches": ["Area Assignment"],
            }), 400

        description = request.form.get("description")

        new_complaint = Complaint(
            registration_id=registration.registration_id,
            type_of_complaint="Lot Dispute",
            status="Valid",
            complainant_name=complainant_name,
            area_id=area_id,
            address=address,
            description=description,
        )
        db.session.add(new_complaint)
        db.session.flush()

        q1 = request.form.get("possession")
        block_lot_raw = request.form.get("block_lot")
        block_lot = None
        if block_lot_raw:
            try:
                parsed = json.loads(block_lot_raw)
                if isinstance(parsed, list):
                    block_lot = [
                        {"block": str(item.get("block", "")).strip(), "lot": str(item.get("lot", "")).strip()}
                        for item in parsed
                        if isinstance(item, dict)
                    ]
                else:
                    block_lot = None
            except Exception:
                block_lot = None

        if block_lot:
            found_invalid = False
            for idx, item in enumerate(block_lot, start=1):
                b_str = (item.get("block") or "").strip()
                l_str = (item.get("lot") or "").strip()
                if not b_str or not l_str:
                    found_invalid = True
                    break
                try:
                    b_no = int(b_str)
                except Exception:
                    found_invalid = True
                    break
                try:
                    l_no = int(l_str)
                except Exception:
                    found_invalid = True
                    break
                blk = Block.query.filter_by(area_id=area_id, block_no=b_no).first()
                if not blk:
                    found_invalid = True
                    break
                ben = Beneficiary.query.filter_by(block_id=blk.block_id, lot_no=l_no).first()
                if not ben:
                    gen = GeneratedLots.query.filter_by(block_id=blk.block_id, lot_no=l_no).first()
                    if not gen:
                        found_invalid = True
                        break
            if found_invalid:
                db.session.rollback()
                return jsonify(
                    {
                        "success": False,
                        "message": "Block or lot could not be found for your HOA.",
                        "mismatches": ["Block or lot could not be found for your HOA."],
                    }
                ), 400

        try:
            q2_list = request.form.getlist("nature")
        except Exception:
            q2_list = []
        q2 = json.dumps(q2_list) if q2_list else None

        q3_raw = request.form.get("dispute_start_date")
        q3 = None
        if q3_raw:
            try:
                q3 = datetime.strptime(q3_raw, "%Y-%m-%d").date()
            except Exception:
                q3 = None

        try:
            q4_list = request.form.getlist("reason")
        except Exception:
            q4_list = []
        q4 = json.dumps(q4_list) if q4_list else None

        try:
            q5_list = request.form.getlist("boundary_reported_to[]")
        except Exception:
            q5_list = []
        q5 = json.dumps(q5_list)

        try:
            q6_list = request.form.getlist("site_result[]")
        except Exception:
            q6_list = []
        q6 = json.dumps(q6_list) if q6_list else None

        opposing_names = []
        for key in request.form:
            if key == "opposing_name[]":
                opposing_names.extend(request.form.getlist(key))
        q7 = json.dumps([name.strip() for name in opposing_names if name.strip()])

        relationships = []
        for key in request.form:
            if key == "relationship_with_person[]":
                relationships.extend(request.form.getlist(key))
        q8 = json.dumps([rel.strip() for rel in relationships if rel.strip()])

        legal_docs_claim = request.form.get("claimDocs")
        q9_data = {"claim": legal_docs_claim}
        if legal_docs_claim == "Yes":
            docs_checked = []
            for key in request.form:
                if key == "docs":
                    docs_checked.extend(request.form.getlist(key))
            if docs_checked:
                q9_data["documents"] = docs_checked
        q9 = json.dumps(q9_data)

        reside_answer = request.form.get("reside")
        q10 = json.dumps({"reside": reside_answer}) if reside_answer else None

        lot_dispute_entry = LotDispute(
            complaint_id=new_complaint.complaint_id,
            q1=q1,
            block_lot=block_lot,
            q2=q2,
            q3=q3,
            q4=q4,
            q5=q5,
            q6=q6,
            q7=q7,
            q8=q8,
            q9=q9,
            q10=q10,
            description=description,
        )
        db.session.add(lot_dispute_entry)

        try:
            file = request.files.get("signature")
            if file and getattr(file, "filename", ""):
                fname = secure_filename(file.filename)
                safe_name = f"{int(time.time())}_{fname}"
                dest = os.path.join(UPLOAD_DIR, safe_name)
                file.save(dest)
                registration.signature_path = safe_name
                lot_dispute_entry.signature = safe_name
        except Exception:
            pass

        # Create initial timeline entry for "Submitted" status with actual submission time
        from backend.database.models import ComplaintHistory
        import json as timeline_json
        
        submitted_timeline = ComplaintHistory(
            complaint_id=new_complaint.complaint_id,
            type_of_action='Submitted',
            assigned_to='',
            details=timeline_json.dumps({'description': 'Submitted a Valid Complaint'}),
            action_datetime=new_complaint.date_received  # Use actual submission time from complaints table
        )
        db.session.add(submitted_timeline)

        db.session.commit()
        return jsonify(
            {
                "success": True,
                "message": "Lot dispute submitted successfully!",
                "complaint_id": new_complaint.complaint_id,
            }
        )
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Server error: {e}"}), 500


# -----------------------------
# Misc
# -----------------------------

@lot_dispute_bp.route("/areas")
def list_areas():
    try:
        areas = Area.query.order_by(Area.area_name.asc()).all()
        return jsonify(
            {
                "success": True,
                "areas": [{"area_id": a.area_id, "area_name": a.area_name} for a in areas],
            }
        )
    except Exception as e:
        return jsonify({"success": False, "message": f"Server error: {e}"}), 500

# Keep form structure provider here for preview rendering

def get_form_structure(type_of_complaint: str):
    if type_of_complaint != "Lot Dispute":
        return []
    return [
        {
            "type": "radio",
            "name": "q1",
            "label": "1. How did you come into possession of the lot?",
            "options": [
                ("Official assignment by NGCHDP/NHA", "I was officially assigned the lot by NGCHDP/NHA"),
                ("Passed on by a family member", "The lot was passed on to me by a family member"),
                ("Purchased from another occupant", "I purchased the lot from another occupant"),
                ("Living since project started", "I have been living here since the NCC project started"),
                ("Relocated after demolition/displacement", "I relocated here after demolition/displacement elsewhere"),
                ("Verbal promise by former officer/neighbor", "I was verbally promised the lot by a former officer or neighbor"),
            ],
        },
        {
            "type": "checkbox",
            "name": "q2",
            "label": "2. What is the nature of the ownership conflict?",
            "options": [
                ("Someone else has a contract", "Someone else has a contract for the same lot"),
                ("Someone else claiming lot", "Someone else is claiming my assigned lot"),
                ("Assigned different lot", "I was assigned a different lot than what I was told"),
                ("Lot not reflected in masterlist", "My lot is not reflected in the masterlist"),
                ("Name removed from list", "My name was removed or replaced in the beneficiary list"),
                ("Lot illegally sold", "The lot was illegally sold or reassigned to someone else"),
                ("Family member claiming", "A family member/relative is claiming the lot I currently occupy"),
                ("Lot details incorrect", "My assigned lot details (e.g., lot no., area) are incorrect in the records"),
                ("Not sure", "I am not sure what caused the dispute"),
            ],
        },
        {"type": "date", "name": "q3", "label": "3. When did the dispute start?"},
        {
            "type": "checkbox",
            "name": "q4",
            "label": "4. What led you to raise this complaint?",
            "options": [
                ("Asked to vacate", "I was asked to vacate the lot I’ve been occupying"),
                ("Denied access", "I was denied access to a lot I believe was assigned to me"),
                ("Received notice", "I received notice that someone else is the rightful owner"),
                ("Stopped from building", "I attempted to build on the lot and was stopped"),
                ("Discovered duplicate record", "I discovered another person listed in official records for my lot"),
                ("Clarification only", "I just want clarification about my assigned lot (no direct conflict yet)"),
            ],
        },
        {
            "type": "checkbox",
            "name": "q5",
            "label": "5. Have you reported this boundary issue to any office or authority?",
            "options": [
                ("Barangay", "Barangay"),
                ("HOA", "HOA"),
                ("NGC", "NGC"),
                ("USAD - PHASELAD", "USAD - PHASELAD"),
                ("None", "None"),
            ],
        },
        {
            "type": "checkbox",
            "name": "q6",
            "label": "6. What was the result of the report or inspection?",
            "options": [
                ("Advised to adjust or vacate", "The other party was advised to adjust or vacate"),
                ("Asked to provide more documents", "I was advised to provide more documents"),
                ("Still under investigation", "The issue is still under investigation"),
                ("No valid claim", "I was told I have no valid claim"),
                ("No action taken", "No action was taken"),
                ("Not applicable", "Not applicable / No inspection yet"),
            ],
        },
        {
            "type": "multiple_text",
            "name": "q7",
            "label": "7. Name of opposing claimant?",
            "description": "Multiple names can be added for each person involved",
        },
        {
            "type": "multiple_text",
            "name": "q8",
            "label": "8. Relationship with person involved?",
            "description": "Multiple relationships can be added corresponding to each person",
        },
        {
            "type": "radio",
            "name": "q9",
            "label": "9. Do they claim to have legal documents?",
            "options": [("Yes", "Yes"), ("No", "No"), ("Not Sure", "Not sure")],
            "conditional": {
                "show_when": "Yes",
                "additional_fields": [
                    {
                        "type": "checkbox",
                        "name": "docs",
                        "label": "What documents do they have?",
                        "options": [
                            ("Title", "Title"),
                            ("Contract to Sell", "Contract to Sell"),
                            ("Certificate of Full Payment", "Certificate of Full Payment"),
                            ("Pre-qualification Stub", "Pre-qualification Stub"),
                            ("Contract/Agreement", "Contract/Agreement"),
                            ("Deed of Sale", "Deed of Sale"),
                        ],
                    }
                ],
            },
        },
        {
            "type": "radio",
            "name": "q10",
            "label": "10. Do they reside on the disputed lot?",
            "options": [("Yes", "Yes"), ("No", "No"), ("Not Sure", "Not sure")],
        },
        {
            "type": "textarea",
            "name": "description",
            "label": "Please describe what happened briefly, including how you found out about the issue.",
        },
        {
            "type": "signature",
            "name": "signature",
            "label": "Signature",
        },
    ]
