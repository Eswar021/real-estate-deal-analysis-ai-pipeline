"""
pages/noi_verification/views.py — the classification review (2nd hard stop).

URL:    /t12/<upload_id>/noi/

Shows the Stage-2 result: NOI verification on top + every classified row bucketed by
section. Every file stops here (pass or fail) before mapping.

GET:            render the Stage-2 result from the run-state.
POST reverify:  apply the user's class edits, re-verify NOI (stage2_reverify), re-render here.
POST continue:  run Stage 3 (mapping), then redirect to /review/.

The anchors were locked at the gate, so this page never re-runs Stage 2 from the top: it
re-enters the NOI check with the edits applied, and never re-classifies. (The old "Recompute"
re-ran classify, which discarded the reviewed classification + the diagnosis's fixes and mapped
the wiped result — a phantom multi-million NOI difference at data_review.)

Reads:  state.json (classification slice)
Writes: state.json — classification.classified/noi (reverify); mapping (Save & Continue)
DB:     Upload.current_step bumped to 'data_review' on Save & Continue
"""

from django.shortcuts import get_object_or_404, redirect, render

from t12_mapping import pipeline_bridge
from t12_mapping.models import Upload

from .helpers import build_context


def _class_edits(post, state) -> dict[int, str]:
    """The rows whose class the user actually CHANGED: {row: NEW_CLASS}. Compared against the
    current classification so an untouched dropdown never counts as an edit."""
    current = {r["row"]: r["class"] for r in state["classification"]["classified"]}
    edits = {}
    for key, value in post.items():
        if not key.startswith("class_"):
            continue
        row = int(key[len("class_"):])
        if value and current.get(row) != value:
            edits[row] = value
    return edits


def verify(request, upload_id):
    upload_obj = get_object_or_404(Upload, pk=upload_id)

    try:
        state = pipeline_bridge.get_state(upload_obj.id, with_grid=False)
    except FileNotFoundError:
        return render(request, "upload/upload.html", {
            "errors": {"t12_file": "Upload data not found. Please re-upload."},
        })

    # Stage 2 hasn't run (the file is parsed but still waiting at the anchor gate) — send the
    # user where the flow actually is. Reachable by bookmark / stale tab, not by the flow.
    if "classification" not in state:
        return redirect("anchor_gate", upload_id=upload_obj.id)

    error = None

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "reverify":
            try:
                # with_grid: verify_noi reads the vendor's own totals off the grid.
                state = pipeline_bridge.run_step(upload_obj.id, "stage2_reverify",
                                                 class_edits=_class_edits(request.POST, state))
            except Exception as e:
                error = f"Re-verify error: {e}"
        else:
            try:
                pipeline_bridge.run_step(upload_obj.id, "stage3_mapping")
                upload_obj.current_step = Upload.STEP_DATA_REVIEW
                upload_obj.save(update_fields=["current_step", "updated_at"])
                return redirect("data_review", upload_id=upload_obj.id)
            except Exception as e:
                error = f"Mapping error: {e}"

    return render(
        request,
        "noi_verification/verify.html",
        build_context(upload_obj, state, error, pipeline_bridge.load_classes()),
    )
