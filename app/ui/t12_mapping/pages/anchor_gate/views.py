"""
pages/anchor_gate/views.py

URL:    /t12/<upload_id>/anchors/

The Stage-1 anchor gate — shown when the R − E = NOI lock is ambiguous
(GATE / DERIVED / NONE). The user confirms/adjusts the three anchor rows; confirming
runs STAGE 2 (classify → section → NOI verify) on those rows, WITHOUT re-calling the AI.
Classification does not run until this gate is confirmed.

GET:                  read anchor_lock + parse_state (anchor_rows); render the selectors.
POST action=verify:   LIGHT re-check R − |E| = NOI on the chosen rows (no classification,
                      no AI, nothing persisted) and show the verdict.
POST action=continue: CONFIRM — run Stage 2 (classify + AI diagnosis on fail), redirect to
                      the classification review.

Reads:  anchor_lock.json, parse_state.json
Writes: classification.json, annotated_blocks.json, comparison.json, actual_noi.json
        (Stage 2, ONLY on Confirm via confirm_anchors — Re-verify writes nothing)
DB:     Upload.current_step = 'noi_verification' (on Confirm)
Next:   noi_verification (the classification review)
"""

from django.shortcuts import get_object_or_404, redirect, render

from t12_mapping import pipeline_bridge
from t12_mapping.models import Upload

from .helpers import build_context, int_or_none


def anchors(request, upload_id):
    upload_obj = get_object_or_404(Upload, pk=upload_id)

    try:
        anchor_lock = pipeline_bridge.load_anchor_lock(upload_obj.id)
        parse_state = pipeline_bridge.load_parse_state(upload_obj.id)
    except FileNotFoundError:
        return render(request, "upload/upload.html", {
            "errors": {"t12_file": "Upload data not found. Please re-upload."},
        })

    chosen, reconciles, error = None, None, None
    if request.method == "POST":
        chosen = {
            "revenue_end_row": int_or_none(request.POST.get("revenue_end_row")),
            "expense_end_row": int_or_none(request.POST.get("expense_end_row")),
            "noi_row":         int_or_none(request.POST.get("noi_row")),
        }
        try:
            if request.POST.get("action") == "continue":
                pipeline_bridge.confirm_anchors(upload_obj.id, chosen)  # Stage 2 (+ AI diagnosis)
                upload_obj.current_step = Upload.STEP_NOI_VERIFICATION
                upload_obj.save(update_fields=["current_step", "updated_at"])
                return redirect("noi_verify", upload_id=upload_obj.id)
            reconciles = pipeline_bridge.check_anchors(upload_obj.id, chosen)["reconciles"]
        except Exception as e:
            error = str(e)

    return render(
        request,
        "anchor_gate/anchors.html",
        build_context(upload_obj, anchor_lock, parse_state, chosen, reconciles, error),
    )
