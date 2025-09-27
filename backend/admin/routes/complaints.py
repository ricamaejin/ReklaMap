import os
from flask import Blueprint, send_file

complaints_bp = Blueprint("complaints", __name__, url_prefix="/admin/complaints")

frontend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../frontend"))

@complaints_bp.route("/")
def complaints():
    return send_file(os.path.join(frontend_path, "admin", "complaints", "all.html"))

# 👇 Allow `/admin/complaints/all.html` to work too
@complaints_bp.route("/all.html")
def complaints_all():
    return send_file(os.path.join(frontend_path, "admin", "complaints", "all.html"))
