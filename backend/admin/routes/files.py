import os
from flask import Blueprint, current_app, send_from_directory, abort, request, jsonify
from werkzeug.utils import safe_join, secure_filename

# Blueprint dedicated to serving uploaded files that are not under the frontend static folder
files_bp = Blueprint("files_bp", __name__)


def _candidate_dirs(*parts: str):
	"""Return a list of candidate absolute directories to search for files.
	We try a few common roots based on this repository layout:
	  - <repo_root>/uploads
	  - <repo_root>/backend/uploads
	And append the provided parts (e.g., "staff" or "complaints").
	"""
	# Determine repo root from this file location
	here = os.path.abspath(os.path.dirname(__file__))
	repo_root = os.path.abspath(os.path.join(here, "..", "..", ".."))  # back to project root
	# Build specific subpath first (e.g., uploads/staff)
	subpath = os.path.join(*parts) if parts else ""
	candidates = [
		os.path.join(repo_root, "uploads", subpath),
		os.path.join(repo_root, "backend", "uploads", subpath),
		os.path.join(repo_root, "backend", "staff", "uploads", subpath),
		os.path.join(repo_root, "backend", "admin", "uploads", subpath),
		os.path.join(repo_root, "frontend", "uploads", subpath),
	]
	# Also add plain uploads roots as fallbacks if a subpath was provided and not found
	if parts:
		candidates.extend([
			os.path.join(repo_root, "uploads"),
			os.path.join(repo_root, "backend", "uploads"),
			os.path.join(repo_root, "backend", "staff", "uploads"),
			os.path.join(repo_root, "backend", "admin", "uploads"),
			os.path.join(repo_root, "frontend", "uploads"),
			os.path.join(repo_root, "database", "temp"),
		])
	# De-duplicate while preserving order
	seen = set()
	unique = []
	for p in candidates:
		if p not in seen:
			seen.add(p)
			unique.append(p)
	return unique


def _send_from_candidates(candidates, filename):
	"""Try to serve filename from the first candidate directory that contains it.
	Uses safe_join to prevent path traversal.
	"""
	filename = filename.replace("\\", "/")  # normalize
	for base in candidates:
		try:
			# Ensure base exists
			if not os.path.isdir(base):
				continue
			# Prevent path traversal
			safe_path = safe_join(base, filename)
			if not safe_path:
				continue
			if os.path.isfile(safe_path):
				# Honor simple inline viewing for PDFs/images by default
				as_attachment = request.args.get("download") == "1"
				return send_from_directory(base, filename, as_attachment=as_attachment)
		except Exception:
			# Try next candidate on any error
			continue
	abort(404)


@files_bp.route("/uploads/staff/<path:filename>")
def serve_staff_upload(filename):
	"""Serve files uploaded by staff.
	Frontend uses URLs like: /uploads/staff/<filename>
	"""
	candidates = _candidate_dirs("staff")
	return _send_from_candidates(candidates, filename)


@files_bp.route("/uploads/staff", methods=["POST"])
def upload_staff_files():
	"""Upload one or more files from staff and save them under uploads/staff.
	Returns JSON with the stored filenames and public paths.
	Frontend will then reference them at /uploads/staff/<filename>.
	"""
	try:
		# Determine repository root and target upload dir: <repo_root>/uploads/staff
		here = os.path.abspath(os.path.dirname(__file__))
		repo_root = os.path.abspath(os.path.join(here, "..", "..", ".."))
		target_dir = os.path.join(repo_root, "uploads", "staff")
		os.makedirs(target_dir, exist_ok=True)

		# Accept files via common keys: 'files' (multiple) or any file fields
		saved_filenames = []
		saved_paths = []

		# Collect all FileStorage objects from request.files
		incoming_files = []
		if request.files:
			# If client sent under 'files', use list; else gather all
			list_under_key = request.files.getlist('files')
			if list_under_key:
				incoming_files.extend(list_under_key)
			else:
				incoming_files.extend([f for _, f in request.files.items()])

		if not incoming_files:
			return jsonify({"success": False, "message": "No files received"}), 400

		# Basic extension allow-list (pdf, images). Reject others.
		allowed_ext = {".pdf", ".png", ".jpg", ".jpeg"}

		def _unique_name(base_dir, filename):
			"""Ensure filename uniqueness by appending a counter if needed."""
			name, ext = os.path.splitext(filename)
			candidate = filename
			counter = 1
			while os.path.exists(os.path.join(base_dir, candidate)):
				candidate = f"{name} ({counter}){ext}"
				counter += 1
			return candidate

		for storage in incoming_files:
			if not storage:
				continue
			original = storage.filename or "file"
			safe_name = secure_filename(original)
			if not safe_name:
				# Fallback if secure_filename stripped everything
				safe_name = "upload.pdf"
			_, ext = os.path.splitext(safe_name)
			if ext.lower() not in allowed_ext:
				# Skip unsupported extensions
				continue

			# Prevent overwriting existing files; make unique if needed
			unique_name = _unique_name(target_dir, safe_name)
			dest_path = os.path.join(target_dir, unique_name)
			storage.save(dest_path)
			saved_filenames.append(unique_name)
			saved_paths.append(f"/uploads/staff/{unique_name}")

		if not saved_filenames:
			return jsonify({"success": False, "message": "No valid files saved (unsupported type?)"}), 400

		return jsonify({
			"success": True,
			"files": saved_filenames,
			"paths": saved_paths
		})
	except Exception as e:
		return jsonify({"success": False, "message": str(e)}), 500


@files_bp.route("/files/complaints/<path:filename>")
def serve_complaint_files(filename):
	"""Serve admin complaint files accessed via placeholder URL in UI.
	Frontend uses URLs like: /files/complaints/<filename>
	We look under uploads/complaints and backend/uploads/complaints.
	"""
	candidates = _candidate_dirs("complaints")
	return _send_from_candidates(candidates, filename)


# Optional generic uploads route if needed later (kept narrow to avoid conflicts)
@files_bp.route("/uploads/signatures/<path:filename>")
def serve_signatures(filename):
	candidates = _candidate_dirs("signatures")
	return _send_from_candidates(candidates, filename)

# Generic uploads route: serves any file directly under the uploads root (and backend/uploads)
@files_bp.route("/uploads/<path:filename>")
def serve_generic_upload(filename):
	candidates = _candidate_dirs()
	# Also consider common temp directory root-level
	here = os.path.abspath(os.path.dirname(__file__))
	repo_root = os.path.abspath(os.path.join(here, "..", "..", ".."))
	candidates.append(os.path.join(repo_root, "database", "temp"))
	return _send_from_candidates(candidates, filename)

