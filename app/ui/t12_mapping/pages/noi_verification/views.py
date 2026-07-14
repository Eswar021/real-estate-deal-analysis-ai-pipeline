"""
pages/noi_verification/views.py — the classification review (2nd hard stop).

URL:    /t12/<upload_id>/noi/

Shows the Stage-2 result: NOI verification on top + every classified row bucketed by
section. Every file stops here (pass or fail) before mapping.

GET:   render the Stage-2 result from the run-state.
POST:  run Stage 3 (mapping), then redirect to /review/. Nothing else — the anchors were locked
       at the gate and stages are go/no-go, so this page never re-classifies. (The old
       "Recompute" did, which discarded the reviewed classification + the diagnosis's fixes and
       mapped the wiped result — a phantom multi-million NOI difference at data_review.)

Reads:  classification.json
Writes: classification.json + annotated_blocks.json + comparison.json + actual_noi.json
        (on Recompute, via apply_and_recompute)
        auto_mapped.json, ai_mapped.json, ai_mapping_logs.json (on Save & Continue)
DB:     Upload.current_step bumped to 'data_review' on Save & Continue
"""

from django.shortcuts import get_object_or_404, redirect, render

from t12_mapping import pipeline_bridge
from t12_mapping.models import Upload

from .helpers import build_context


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
        # The ONLY action here is "continue". The Stage-1 anchors were locked at the gate, and
        # the stages are go/no-go: a page never reaches backwards into a finished stage. (The
        # old Recompute re-ran classify from here, which silently discarded the reviewed
        # classification — including the AI diagnosis's fixes — and mapped the wiped result.)
        try:
            pipeline_bridge.run_step(upload_obj.id, "stage3_mapping")
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
