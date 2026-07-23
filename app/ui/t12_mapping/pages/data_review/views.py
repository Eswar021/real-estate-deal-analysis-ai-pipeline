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

from t12_mapping import pipeline_bridge
from t12_mapping.models import Upload

from .helpers import build_table_rows, compute_summary, effective_mapping_of, mapping_stats


def _row_edit(post, mapped) -> dict:
    """The row the user touched, carrying ONLY the fields they actually changed. Every edit
    posts the whole row (category + flip_sign), so passing both through would record a user
    override on a category the rulebook or the AI chose and the user never picked. Mirrors
    noi_verification's _class_edits, which diffs against the current classification."""
    row = int(post.get("row_number"))
    current = next((r for r in mapped.get("rows", []) if r.get("row") == row), {})

    edit = {"row": row}
    category = (post.get("new_category") or "").strip() or None
    if category != effective_mapping_of(current):      # None = "clear my override"
        edit["category"] = category
    flip_sign = post.get("flip_sign") == "1"
    if flip_sign != bool(current.get("flip_sign")):
        edit["flip_sign"] = flip_sign
    return edit


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
        # The user overrode one row's category / flip_sign. Re-enter Stage 3 through its
        # edit workflow — which applies the override and nothing else (no re-map, no AI).
        try:
            row_edit = _row_edit(request.POST, mapped)
        except (TypeError, ValueError):
            save_error = "Missing or invalid row_number"
        else:
            try:
                state = pipeline_bridge.run_step(upload_obj.id, "stage3_update_mapping",
                                                 with_grid=False, row_edit=row_edit)
                mapped = state["mapping"]
            except Exception as e:
                save_error = str(e)

    # The summary IS Stage 2's verified NOI result — this page never re-derives the money.
    noi_months = ((state.get("classification") or {}).get("noi") or {}).get("months") or []

    categories = pipeline_bridge.load_categories()
    summary    = compute_summary(noi_months, mapped.get("column_headers", []))
    rows       = build_table_rows(mapped)

    return render(request, "data_review/review.html", {
        "upload_id":    upload_obj.id,
        "file_name":    mapped.get("file", "") or upload_obj.file_name,
        "categories":   categories,
        "rows":         rows,
        "summary":      summary,
        "map_stats":    mapping_stats(rows),
        "save_error":   save_error,
    })

