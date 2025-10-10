"""Centralized redirect utilities for complainant flows.

Having a single module avoids circular imports and keeps mapping logic DRY.
"""
from __future__ import annotations

from typing import Optional


_COMPLAINT_PATHS_REGISTERED = {
    "Lot Dispute": "/complainant/lot_dispute/new_lot_dispute_form",
    "Boundary Dispute": "/complainant/boundary_dispute/new_boundary_dispute_form",
    "Pathway Dispute": "/complainant/complaints/pathway_dispute.html",
    "Unauthorized Occupation": "/complainant/complaints/unauthorized_occupation.html",
    "Illegal Construction": "/complainant/complaints/illegal_construction.html",
}

_DASHBOARD_FALLBACK = "/complainant/home/dashboard.html"
_NOT_REGISTERED = "/complainant/not_registered"


def complaint_redirect_path(complaint_type: Optional[str], has_registration: bool) -> str:
    """Return the redirect path for a given complaint type.

    Args:
        complaint_type: Human readable complaint type stored in session.
        has_registration: Whether user has an existing registration record.
    """
    if not has_registration:
        return _NOT_REGISTERED
    if not complaint_type:
        return _DASHBOARD_FALLBACK
    return _COMPLAINT_PATHS_REGISTERED.get(complaint_type, _DASHBOARD_FALLBACK)


__all__ = ["complaint_redirect_path"]
