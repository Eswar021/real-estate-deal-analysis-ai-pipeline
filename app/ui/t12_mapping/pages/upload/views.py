"""
pages/upload/views.py

URL:    /t12/
Reads:  nothing (entry point)
Writes: via pipeline_bridge.run_detection — block_detection.json,
        annotated_blocks.json, actual_noi.json, computed_noi.json, comparison.json
DB:     creates Upload row (status=draft, current_step='upload')
Next:   redirects to noi_verification
"""

from pathlib import Path

from django.shortcuts import redirect, render

from shared import storage
from t12_mapping import pipeline_bridge
from t12_mapping.models import Upload


ALLOWED_EXTENSIONS = {".xlsx", ".xls"}


def upload(request):
    if request.method == "GET":
        return render(request, "upload/upload.html")

    file = request.FILES.get("t12_file")
    property_name = request.POST.get("property_name", "").strip()

    errors = {}
    if not property_name:
        errors["property_name"] = "Property name is required."
    if not file:
        errors["t12_file"] = "Please choose a file to upload."
    elif Path(file.name).suffix.lower() not in ALLOWED_EXTENSIONS:
        errors["t12_file"] = "Only .xlsx and .xls files are supported."

    if errors:
        return render(request, "upload/upload.html", {
            "errors": errors,
            "property_name": property_name,
        })

    upload_obj = Upload.objects.create(
        file=file,
        file_name=file.name,
        property_name=property_name,
        current_step=Upload.STEP_UPLOAD,
    )

    try:
        xlsx_path = storage.get_local_path(upload_obj.file)
        comparison = pipeline_bridge.run_detection(upload_obj.id, xlsx_path)
    except Exception as e:
        upload_obj.delete()  # cascades file deletion via FileField
        return render(request, "upload/upload.html", {
            "errors": {"t12_file": f"Pipeline error: {e}"},
            "property_name": property_name,
        })

    upload_obj.current_step = Upload.STEP_NOI_VERIFICATION
    upload_obj.save(update_fields=["current_step", "updated_at"])

    # Ambiguous R−E=NOI lock (GATE / DERIVED / NONE) → confirm the anchors first;
    # a clean AUTO lock skips straight to NOI verification.
    if comparison.get("anchor_status") not in ("AUTO", None):
        return redirect("anchor_gate", upload_id=upload_obj.id)
    return redirect("noi_verify", upload_id=upload_obj.id)
