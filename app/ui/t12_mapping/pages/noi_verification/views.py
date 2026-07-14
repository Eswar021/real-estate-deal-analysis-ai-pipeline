"""
pages/noi_verification/views.py — the classification review (2nd hard stop).

URL:    /t12/<upload_id>/noi/

Shows the Stage-2 result: NOI verification on top + every classified row bucketed by
section. Every file stops here (pass or fail) before mapping.

GET:                  render the Stage-2 result from the run-state.
POST action=recompute: the user changed the R / E / NOI anchors → re-enter the classify step;
                      the GRAPH decides what runs (a failing NOI triggers the AI diagnosis).
POST action=continue:  run the mapping stage, then redirect to /review/. Does NOT re-classify —
                      re-running it here would discard the classification just reviewed (and the
                      diagnosis's corrections), which is exactly the bug that produced a phantom
                      multi-million NOI difference at data_review.

Reads:  classification.json
Writes: classification.json + annotated_blocks.json + comparison.json + actual_noi.json
        (on Recompute, via apply_and_recompute)
        auto_mapped.json, ai_mapped.json, ai_mapping_logs.json (on Save & Continue)
DB:     Upload.current_step bumped to 'data_review' on Save & Continue
"""

from django.shortcuts import get_object_or_404, redirect, render

from t12_mapping import pipeline_bridge
from t12_mapping.models import Upload

from .helpers import build_context, int_or_none


def verify(request, upload_id):
    upload_obj = get_object_or_404(Upload, pk=upload_id)

    try:
        state = pipeline_bridge.get_state(upload_obj.id, with_grid=False)
    except FileNotFoundError:
        return render(request, "upload/upload.html", {
            "errors": {"t12_file": "Upload data not found. Please re-upload."},
        })

    recompute_error = None

    if request.method == "POST":
        action = request.POST.get("action", "recompute")

        try:
            if action == "recompute":
                # ONLY a recompute re-classifies: the user changed the anchors, so we re-enter
                # the graph and IT decides what runs (a failing NOI triggers the diagnosis).
                # 'continue' must never re-classify — that would silently throw away the
                # classification just reviewed on this page, including the diagnosis's fixes.
                anchors = {"revenue_end_row": int_or_none(request.POST.get("total_revenue_row")),
                           "expense_end_row": int_or_none(request.POST.get("total_expense_row")),
                           "noi_row":         int_or_none(request.POST.get("noi_row"))}
                state = pipeline_bridge.run_step(upload_obj.id, "classify", anchors=anchors)
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

    return render(
        request,
        "noi_verification/verify.html",
        build_context(upload_obj, state, recompute_error),
    )
