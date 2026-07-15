"""
pages/upload/views.py

URL:    /t12/
Reads:  nothing (entry point)
Screens: STAGE 0 via pipeline_bridge.run_preflight — rejects rent rolls / Model-T12 files /
         non-T12 spreadsheets before any parsing (deletes the Upload, re-renders the error).
Writes: STAGE 1 ONLY via pipeline_bridge.run_detection — anchor_lock.json,
        parse_state.json, cell_grid.json. Classification (annotated_blocks / comparison /
        actual_noi) is NOT written here — the anchor gate writes it on Confirm.
DB:     creates Upload row (status=draft, current_step='upload')
Next:   anchor_gate (always — Stage 2 runs only after the anchors are confirmed there)
"""

from pathlib import Path

from django.shortcuts import redirect, render

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
        if not preflight["ok"]:
            upload_obj.delete()  # not a T12 input — reject cleanly, nothing parsed
            return render(request, "upload/upload.html", {
                "errors": {"t12_file": preflight["reason"]},
                "property_name": property_name,
            })
        state = pipeline_bridge.run_step(                        # STAGE 1 only (no classification)
            upload_obj.id, "stage1_parse",
            file={"name": Path(xlsx_path).name, "path": str(xlsx_path)})
    except Exception as e:
        upload_obj.delete()  # cascades file deletion via FileField
        return render(request, "upload/upload.html", {
            "errors": {"t12_file": f"Pipeline error: {e}"},
            "property_name": property_name,
        })

    # TRUE STAGING — every upload stops at the anchor gate. Classification (Stage 2) runs
    # ONLY after the user confirms the R / E / NOI anchors there, never at upload. A clean
    # AUTO lock just arrives pre-filled and already reconciling (a one-click confirm).
    # current_step stays 'upload' until the gate is confirmed (the gate bumps it to 'noi').
    return redirect("anchor_gate", upload_id=upload_obj.id)
