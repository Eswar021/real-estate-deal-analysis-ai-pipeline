"""
pages/noi_verification/views.py

URL:    /t12/<upload_id>/noi/
Reads:  annotated_blocks.json, comparison.json
Writes: annotated_blocks.json, comparison.json   (on every Recompute, so refresh works)
DB:     bumps Upload.current_step on Save & Continue (future)
Next:   data_review (future)
"""

from django.shortcuts import get_object_or_404, render

from t12_mapping import pipeline_bridge
from t12_mapping.models import Upload

from .helpers import build_context, int_or_none


def verify(request, upload_id):
    upload_obj = get_object_or_404(Upload, pk=upload_id)

    try:
        annotated  = pipeline_bridge.load_annotated_blocks(upload_obj.id)
        comparison = pipeline_bridge.load_comparison(upload_obj.id)
    except FileNotFoundError:
        return render(request, "upload/upload.html", {
            "errors": {"t12_file": "Upload data not found. Please re-upload."},
        })

    recompute_error = None

    if request.method == "POST":
        corrections = {
            "total_revenue_row": int_or_none(request.POST.get("total_revenue_row")),
            "total_expense_row": int_or_none(request.POST.get("total_expense_row")),
            "noi_row":           int_or_none(request.POST.get("noi_row")),
        }
        try:
            annotated, comparison = pipeline_bridge.apply_and_recompute(
                upload_obj.id, corrections
            )
            upload_obj.current_step = Upload.STEP_NOI_VERIFICATION
            upload_obj.save(update_fields=["current_step", "updated_at"])
        except Exception as e:
            recompute_error = str(e)

    return render(
        request,
        "noi_verification/verify.html",
        build_context(upload_obj, annotated, comparison, recompute_error),
    )
