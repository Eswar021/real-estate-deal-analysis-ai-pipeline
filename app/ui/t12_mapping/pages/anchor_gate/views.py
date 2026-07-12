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

Reads:  the run-state (anchor_lock + anchor_rows) via bridge.get_state
Writes: on Confirm — the classify step (Stage 2) into the run-state. Re-verify writes nothing.
DB:     Upload.current_step = 'noi_verification' (on Confirm)
Next:   noi_verification (the classification review)
"""

from django.shortcuts import get_object_or_404, redirect, render

from t12_mapping import debug_log, pipeline_bridge
from t12_mapping.models import Upload

from .helpers import build_context, int_or_none


def anchors(request, upload_id):
    upload_obj = get_object_or_404(Upload, pk=upload_id)

    try:
        state = pipeline_bridge.get_state(upload_obj.id, with_grid=False)
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
                # Stage 2 into the run-state (classify + AI diagnosis on NOI fail)
                s = pipeline_bridge.run_step(upload_obj.id, "classify",
                                             anchors=chosen, run_feedback=True)
                debug_log.log_classification(s)
                upload_obj.current_step = Upload.STEP_NOI_VERIFICATION
                upload_obj.save(update_fields=["current_step", "updated_at"])
                return redirect("noi_verify", upload_id=upload_obj.id)
            # light re-verify — the check_anchors step, nothing persisted, no cell_grid loaded
            reconciles = pipeline_bridge.run_step(
                upload_obj.id, "check_anchors", save=False, with_grid=False,
                anchors=chosen)["reconcile"]["reconciles"]
        except Exception as e:
            error = str(e)

    ctx = build_context(upload_obj, state, chosen, reconciles, error)
    debug_log.log_gate(ctx)
    return render(request, "anchor_gate/anchors.html", ctx)
