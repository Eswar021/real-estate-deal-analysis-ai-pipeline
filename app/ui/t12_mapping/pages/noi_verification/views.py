"""
pages/noi_verification/views.py

URL:    /t12/<upload_id>/noi/

GET / POST `action=recompute`: read annotated_blocks + comparison, optionally
apply corrections + recompute NOI, render verify page.

POST `action=continue`: persist any pending corrections, then run Stage 2
(mapping + AI fallback) synchronously, then redirect to /review/.

Reads:  annotated_blocks.json, comparison.json
Writes: annotated_blocks.json, comparison.json    (on Recompute)
        auto_mapped.json, ai_mapped.json, ai_mapping_logs.json   (on Save & Continue)
DB:     Upload.current_step bumped to 'data_review' on Save & Continue
"""

from django.shortcuts import get_object_or_404, redirect, render

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
        action = request.POST.get("action", "recompute")

        try:
            annotated, comparison = pipeline_bridge.apply_and_recompute(
                upload_obj.id, corrections
            )
        except Exception as e:
            recompute_error = str(e)
        else:
            if action == "continue":
                try:
                    pipeline_bridge.run_mapping(upload_obj.id)
                    upload_obj.current_step = Upload.STEP_DATA_REVIEW
                    upload_obj.save(update_fields=["current_step", "updated_at"])
                    return redirect("data_review", upload_id=upload_obj.id)
                except Exception as e:
                    recompute_error = f"Mapping error: {e}"
            else:
                upload_obj.current_step = Upload.STEP_NOI_VERIFICATION
                upload_obj.save(update_fields=["current_step", "updated_at"])

    return render(
        request,
        "noi_verification/verify.html",
        build_context(upload_obj, annotated, comparison, recompute_error),
    )
