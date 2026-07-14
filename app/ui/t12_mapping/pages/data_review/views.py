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
        # The user overrode one row's category / flip_sign. Re-enter Stage 3 through its
        # edit workflow — which applies the override and nothing else (no re-map, no AI).
        try:
            row_edit = {"row":       int(request.POST.get("row_number")),
                        "category":  (request.POST.get("new_category") or "").strip() or None,
                        "flip_sign": request.POST.get("flip_sign") == "1"}
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
        "save_error":   save_error,
    })

