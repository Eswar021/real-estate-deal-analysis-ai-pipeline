"""
pages/data_review/views.py

URL:    /t12/<upload_id>/review/

GET:
    - Read ai_mapped.json + actual_noi.json
    - Build per-row table (description, dropdown category, flip-sign, monthly values)
    - Build bottom summary (Net Rental Income, Calculated NOI, Original NOI, NOI Difference)
    - Render

POST (one row update):
    - Read row_number from form, plus optional new_category and flip_sign
    - Patch ai_mapped.json in place: row.final_mapping = new_category, row.flip_sign = bool
    - Re-render with recomputed summary
"""

from django.shortcuts import get_object_or_404, render

from t12_mapping import debug_log, pipeline_bridge
from t12_mapping.models import Upload

from .helpers import build_table_rows, compute_summary


def review(request, upload_id):
    upload_obj = get_object_or_404(Upload, pk=upload_id)

    try:
        state = pipeline_bridge.get_state(upload_obj.id, with_grid=False)
    except FileNotFoundError:
        state = None
    mapped = (state or {}).get("mapping")
    if mapped is None:
        return render(request, "upload/upload.html", {
            "errors": {"t12_file": "Mapped data not found. Please run NOI verification and click Save & Continue."},
        })

    save_error = None

    if request.method == "POST":
        try:
            mapped = _apply_row_update(mapped, request.POST)
            pipeline_bridge.save_mapping(upload_obj.id, mapped)
        except Exception as e:
            save_error = str(e)

    # Original-NOI (per month) comes from the classification slice's NOI verification.
    noi_months = ((state.get("classification") or {}).get("noi") or {}).get("months") or []
    actual_noi = {"noi": {"by_month": [m["noi"][0] for m in noi_months]}}

    debug_log.log_mapping(mapped)
    categories = pipeline_bridge.load_categories()
    summary    = compute_summary(mapped, actual_noi)
    rows       = build_table_rows(mapped)

    return render(request, "data_review/review.html", {
        "upload_id":    upload_obj.id,
        "file_name":    mapped.get("file", "") or upload_obj.file_name,
        "categories":   categories,
        "rows":         rows,
        "summary":      summary,
        "save_error":   save_error,
    })


def _apply_row_update(mapped: dict, post_data) -> dict:
    """
    Mutates mapped in place: sets final_mapping and/or flip_sign on the row.
    Required POST keys:
        row_number       — int, the T12 row being updated
        new_category     — str (may be "" to clear an override)
        flip_sign        — "1" or absent
    Raises ValueError if row_number not found.
    """
    try:
        row_number = int(post_data.get("row_number"))
    except (TypeError, ValueError):
        raise ValueError("Missing or invalid row_number")

    new_category = (post_data.get("new_category") or "").strip()
    flip_sign    = post_data.get("flip_sign") == "1"

    for r in mapped.get("rows", []):
        if r.get("row") == row_number and r.get("type") == "data":
            r["final_mapping"] = new_category if new_category else None
            r["flip_sign"]     = flip_sign
            return mapped

    raise ValueError(f"Row {row_number} not found in mapped data")
