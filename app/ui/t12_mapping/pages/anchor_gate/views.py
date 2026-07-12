"""
pages/anchor_gate/views.py

URL:    /t12/<upload_id>/anchors/

The Stage-1 anchor gate — shown when the R − E = NOI lock is ambiguous
(GATE / DERIVED / NONE). The user confirms/adjusts the three anchor rows; the
pipeline re-verifies (R − E = NOI) and re-classifies without re-calling the AI.

GET / POST action=verify:  read anchor_lock + annotated + comparison, optionally
                           re-lock to the user's rows and re-verify, render.
POST action=continue:      persist the confirmed anchors, redirect to /noi/.

Reads:  anchor_lock.json, annotated_blocks.json, comparison.json
Writes: annotated_blocks.json, comparison.json  (via confirm_anchors)
DB:     Upload.current_step = 'noi_verification'
Next:   noi_verification
"""

from django.shortcuts import get_object_or_404, redirect, render

from t12_mapping import pipeline_bridge
from t12_mapping.models import Upload

from .helpers import build_context, int_or_none


def anchors(request, upload_id):
    upload_obj = get_object_or_404(Upload, pk=upload_id)

    try:
        anchor_lock = pipeline_bridge.load_anchor_lock(upload_obj.id)
        annotated   = pipeline_bridge.load_annotated_blocks(upload_obj.id)
        comparison  = pipeline_bridge.load_comparison(upload_obj.id)
    except FileNotFoundError:
        return render(request, "upload/upload.html", {
            "errors": {"t12_file": "Upload data not found. Please re-upload."},
        })

    error = None
    if request.method == "POST":
        chosen = {
            "revenue_end_row": int_or_none(request.POST.get("revenue_end_row")),
            "expense_end_row": int_or_none(request.POST.get("expense_end_row")),
            "noi_row":         int_or_none(request.POST.get("noi_row")),
        }
        try:
            annotated, comparison = pipeline_bridge.confirm_anchors(upload_obj.id, chosen)
        except Exception as e:
            error = str(e)
        else:
            if request.POST.get("action") == "continue":
                upload_obj.current_step = Upload.STEP_NOI_VERIFICATION
                upload_obj.save(update_fields=["current_step", "updated_at"])
                return redirect("noi_verify", upload_id=upload_obj.id)

    return render(
        request,
        "anchor_gate/anchors.html",
        build_context(upload_obj, anchor_lock, annotated, comparison, error),
    )
