import uuid
from pathlib import Path

from django.conf import settings
from django.shortcuts import render, redirect

from pipeline_bridge import t12 as bridge


ALLOWED_EXTENSIONS = {".xlsx", ".xls"}

FLAG_LABELS = [
    ("is_total_revenue", "Total Revenue", "total_revenue_row"),
    ("is_total_expense", "Total Expense", "total_expense_row"),
    ("is_noi",           "NOI",           "noi_row"),
]


def home(request):
    return render(request, "home.html")


def upload(request):
    if request.method == "GET":
        return render(request, "t12_mapping/upload.html")

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
        return render(request, "t12_mapping/upload.html", {
            "errors": errors,
            "property_name": property_name,
        })

    upload_id    = uuid.uuid4().hex
    upload_root  = Path(settings.MEDIA_ROOT) / upload_id
    original_dir = upload_root / "original"
    pipeline_dir = upload_root / "pipeline"
    original_dir.mkdir(parents=True, exist_ok=True)

    file_path = original_dir / file.name
    with open(file_path, "wb") as f:
        for chunk in file.chunks():
            f.write(chunk)

    try:
        bridge.run_detection(file_path, pipeline_dir)
    except Exception as e:
        return render(request, "t12_mapping/upload.html", {
            "errors": {"t12_file": f"Pipeline error: {e}"},
            "property_name": property_name,
        })

    return redirect("t12_subtotals", upload_id=upload_id)


def subtotals_stub(request, upload_id):
    pipeline_dir = Path(settings.MEDIA_ROOT) / upload_id / "pipeline"

    try:
        annotated  = bridge.load_annotated_blocks(pipeline_dir)
        comparison = bridge.load_comparison(pipeline_dir)
    except FileNotFoundError:
        return render(request, "t12_mapping/upload.html", {
            "errors": {"t12_file": "Upload not found. Please upload the file again."},
        })

    recompute_error = None

    if request.method == "POST":
        corrections = {
            "total_revenue_row": _int_or_none(request.POST.get("total_revenue_row")),
            "total_expense_row": _int_or_none(request.POST.get("total_expense_row")),
            "noi_row":           _int_or_none(request.POST.get("noi_row")),
        }
        try:
            annotated, comparison = bridge.apply_and_recompute(pipeline_dir, corrections)
        except Exception as e:
            recompute_error = str(e)

    return render(request, "t12_mapping/subtotals_stub.html",
                  _subtotals_context(upload_id, annotated, comparison, recompute_error))


def _ui_pass(annotated, comparison):
    """
    UI-level pass/fail. Three checks:
      1. NOI match          — overall_pass from pipeline
      2. Revenue row check  — comparison["total_revenue_check"]["match"] already
                              uses vendor_egi from is_total_revenue row, so it
                              catches a wrong revenue row selection directly
      3. Expense row check  — total_expense_check["row_method"] is the expense
                              data-row sum; we compare the flagged is_total_expense
                              row value against it, because overall_pass and
                              total_expense_check["match"] don't depend on which
                              row is selected as is_total_expense

    Threshold for check 3 mirrors the pipeline's STRICT flag: derived from
    tolerance_used == 0 (strict) so the two stay in sync automatically.
    """
    if not comparison.get("overall_pass", False):
        return False

    rev_check = comparison.get("total_revenue_check")
    if rev_check and not rev_check.get("match", True):
        return False

    exp_check = comparison.get("total_expense_check")
    if exp_check:
        rows = annotated.get("rows", [])
        flagged = next(
            (r for r in rows if r.get("is_total_expense") and r.get("type") == "subtotal"),
            None,
        )
        if flagged:
            values = [v for v in (flagged.get("values") or []) if v is not None]
            if values:
                row_val  = values[-1]
                comp_val = exp_check["row_method"]
                diff     = abs(round(row_val, 2) - round(comp_val, 2))
                strict   = comparison.get("tolerance_used", 0) == 0
                threshold = 0 if strict else max(1.0, abs(comp_val) * 0.01)
                if diff > threshold:
                    return False

    return True


def _subtotals_context(upload_id, annotated, comparison, recompute_error=None):
    rows = annotated.get("rows", [])

    def _last_value(r):
        vals = [v for v in (r.get("values") or []) if v is not None]
        return vals[-1] if vals else 0

    all_subtotals = [
        {
            "row":          r["row"],
            "description":  r["description"],
            "total_amount": _last_value(r),
        }
        for r in rows if r.get("type") == "subtotal"
    ]

    key_subtotals = []
    for flag, label, field_name in FLAG_LABELS:
        for r in rows:
            if r.get("type") == "subtotal" and r.get(flag):
                key_subtotals.append({
                    "flag":         flag,
                    "field_name":   field_name,
                    "label":        label,
                    "row":          r["row"],
                    "description":  r["description"],
                    "total_amount": _last_value(r),
                })
                break

    return {
        "upload_id":      upload_id,
        "file_name":      annotated.get("file", ""),
        "row_count":      len(rows),
        "noi_pass":       _ui_pass(annotated, comparison),
        "actual_noi":     comparison.get("total_actual_noi",   0),
        "computed_noi":   comparison.get("total_computed_noi", 0),
        "key_subtotals":  key_subtotals,
        "all_subtotals":  all_subtotals,
        "recompute_error": recompute_error,
    }


def _int_or_none(val):
    try:
        return int(val)
    except (TypeError, ValueError):
        return None
