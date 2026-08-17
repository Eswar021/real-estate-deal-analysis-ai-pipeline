"""
pages/upload/views.py

URL:    /t12/
Reads:  nothing (entry point)
Screens: STAGE 0 via pipeline_bridge.run_preflight — flags rent rolls / Model-T12 files /
         non-T12 spreadsheets before parsing. A rejection is NOT final: the file is kept and
         the page offers a "Continue anyway" override (the check can't recognise every vendor's
         wording, and a genuinely-wrong file just hits a wall at the anchor gate — no harm).
Writes: STAGE 1 via pipeline_bridge.run_step(stage1_parse) — cell_grid + parse state.
DB:     creates Upload row (status=draft, current_step='upload')
Next:   anchor_gate (always — Stage 2 runs only after the anchors are confirmed there)
"""

from pathlib import Path

from django.shortcuts import get_object_or_404, redirect, render

from shared import storage
from t12_mapping import pipeline_bridge
from t12_mapping.models import Upload


# .xlsx / .xlsm only. openpyxl cannot read the legacy .xls (BIFF) format at all — it raises
# "openpyxl does not support the old .xls file format" — so accepting .xls only trades a clear
# up-front message for a raw library traceback mid-parse. (Some vendor files ARE .xls; the user
# re-saves them as .xlsx.)
ALLOWED_EXTENSIONS = {".xlsx", ".xlsm"}
LEGACY_EXTENSIONS = {".xls"}


def upload(request):
    if request.method == "GET":
        return render(request, "upload/upload.html")

    # "Continue anyway" — the user is overriding a pre-check rejection on a file we already
    # saved. Skip the pre-check entirely and take it straight into Stage 1.
    bypass_id = request.POST.get("bypass_upload_id")
    if bypass_id:
        return _parse_and_go(request, get_object_or_404(Upload, pk=bypass_id))

    file = request.FILES.get("t12_file")
    property_name = request.POST.get("property_name", "").strip()

    errors = {}
    if not property_name:
        errors["property_name"] = "Property name is required."
    if not file:
        errors["t12_file"] = "Please choose a file to upload."
    elif Path(file.name).suffix.lower() in LEGACY_EXTENSIONS:
        errors["t12_file"] = ("The legacy .xls format isn't supported. Please open the file in "
                              "Excel and re-save it as .xlsx, then upload again.")
    elif Path(file.name).suffix.lower() not in ALLOWED_EXTENSIONS:
        errors["t12_file"] = "Only .xlsx files are supported."

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
        preflight = pipeline_bridge.run_preflight(xlsx_path)  # STAGE 0 — screen before parsing
    except Exception as e:
        upload_obj.delete()  # couldn't even read the file — cascades file deletion
        return render(request, "upload/upload.html", {
            "errors": {"t12_file": f"Could not read the file: {e}"},
            "property_name": property_name,
        })

    if not preflight["ok"]:
        # NOT a hard reject. Keep the file and let the user decide — the pre-check is a warning,
        # not a wall (see Pratt: a valid T12 whose expense total lacks the word "Total").
        return render(request, "upload/upload.html", {
            "reject_reason": preflight["reason"],
            "reject_kind": preflight.get("kind"),
            "bypass_upload_id": upload_obj.id,
            "property_name": property_name,
        })

    return _parse_and_go(request, upload_obj)


def _parse_and_go(request, upload_obj):
    """Run Stage 1 (parse up to the anchor lock) and hand off to the anchor gate. Every upload
    stops at the gate; Stage 2 (classification) runs only after the user confirms the anchors."""
    try:
        xlsx_path = storage.get_local_path(upload_obj.file)
        pipeline_bridge.run_step(
            upload_obj.id, "stage1_parse",
            file={"name": Path(xlsx_path).name, "path": str(xlsx_path)})
    except Exception as e:
        upload_obj.delete()
        return render(request, "upload/upload.html", {
            "errors": {"t12_file": f"Pipeline error: {e}"},
            "property_name": upload_obj.property_name,
        })
    return redirect("anchor_gate", upload_id=upload_obj.id)
