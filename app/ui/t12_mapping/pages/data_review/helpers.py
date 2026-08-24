"""
pages/data_review/helpers.py — page-local helpers for the Map Categories page.

Three responsibilities:
  - effective_mapping_of(row)  — which category to display for a row
  - build_table_rows()         — per-row dict the template iterates over
  - compute_summary()          — bottom rows: Net Rental Income / Calculated NOI / Original NOI / NOI Difference
"""


def effective_mapping_of(row: dict) -> str | None:
    """User override → rulebook hit → AI suggestion → None."""
    return (
        row.get("final_mapping")
        or row.get("mapping")
        or row.get("ai_suggested_mapping")
    )


def _row_type_label(r: dict) -> str | None:
    """Human label for the row's structural type. None for data rows."""
    row_type = r.get("type")
    if row_type == "header":
        return "Header"
    if row_type == "subtotal":
        if r.get("is_total_revenue"):
            return "Total Revenue"
        if r.get("is_total_expense"):
            return "Total Expense"
        if r.get("is_noi"):
            return "NOI"
        return "Subtotal"
    return None


def _signed_values(row: dict) -> list:
    """Row values with flip_sign applied if True."""
    values = row.get("values") or []
    if row.get("flip_sign"):
        return [-v if isinstance(v, (int, float)) else v for v in values]
    return values


def _trailing_totals(values: list) -> tuple:
    """(last-3-months total, last-6-months total) — the client's model needs T3/T6 alongside
    the 12 monthly columns. The LAST value column is the annual total (noi.py treats months[-1]
    as the year total), so the monthly columns are `values[:-1]`; T3/T6 are the rightmost
    (most-recent) 3 and 6 of those. Sums only numeric cells; None if a window has none."""
    monthly = (values or [])[:-1]

    def _sum(window):
        nums = [v for v in window if isinstance(v, (int, float))]
        return round(sum(nums), 2) if nums else None

    return _sum(monthly[-3:]), _sum(monthly[-6:])


def build_export_workbook(mapped_data: dict, noi_months: list[dict], property_name: str = ""):
    """Excel export of the reviewed mapping — two sheets:
      1. "Mapped T12"        — every line item with its category, section and monthly values
                               (what the review page shows), so the mapping can be audited.
      2. "Summary by Category" — the standardized rollup: values summed per canonical category,
                               grouped revenue/expense, with the verified NOI at the bottom.
                               This is the normalized T12 that feeds a downstream model.
    Returns an openpyxl Workbook. openpyxl is already a pipeline dependency.
    """
    import openpyxl
    from openpyxl.styles import Font

    headers = mapped_data.get("column_headers", [])
    n = len(headers)
    rows = mapped_data.get("rows", [])
    bold = Font(bold=True)

    def _cell(v):
        return v if isinstance(v, (int, float)) else None

    wb = openpyxl.Workbook()

    # ── Sheet 1 · line items (mirrors the UI) ─────────────────────────────────
    ws = wb.active
    ws.title = "Mapped T12"
    if property_name:
        ws.append([property_name]); ws["A1"].font = bold; ws.append([])
    head = ["Row", "Description", "Category", "Section", *headers, "Last 3 Mo", "Last 6 Mo", "Note"]
    ws.append(head)
    for c in ws[ws.max_row]:
        c.font = bold
    for r in rows:
        if r.get("type") == "empty":
            continue
        is_data = r.get("type") == "data"
        category = effective_mapping_of(r) if is_data else (_row_type_label(r) or "")
        values = _signed_values(r)
        t3, t6 = _trailing_totals(values)
        note = (r.get("review_note") or "") if is_data else ""
        ws.append([r.get("row"), r.get("description", ""), category or "",
                   r.get("statement_side") or "", *[_cell(v) for v in values[:n]],
                   _cell(t3), _cell(t6), note])

    # ── Sheet 2 · rollup by canonical category ────────────────────────────────
    ws2 = wb.create_sheet("Summary by Category")
    buckets = {"revenue": {}, "expense": {}}          # side -> {category -> [monthly sums]}
    for r in rows:
        if r.get("type") != "data":
            continue
        side = r.get("statement_side")
        cat = effective_mapping_of(r)
        if side not in buckets or not cat:
            continue
        acc = buckets[side].setdefault(cat, [0.0] * n)
        for i, v in enumerate(_signed_values(r)[:n]):
            if isinstance(v, (int, float)):
                acc[i] += v

    ws2.append(["Category", *headers])
    for c in ws2[1]:
        c.font = bold
    rev_total = [0.0] * n
    exp_total = [0.0] * n
    for side, label, running in (("revenue", "REVENUE", rev_total), ("expense", "EXPENSE", exp_total)):
        ws2.append([label]); ws2[ws2.max_row][0].font = bold
        for cat in sorted(buckets[side]):
            vals = buckets[side][cat]
            ws2.append([cat, *[round(v, 2) for v in vals]])
            for i, v in enumerate(vals):
                running[i] += v
        ws2.append([f"Total {label.title()}", *[round(v, 2) for v in running]])
        for c in ws2[ws2.max_row]:
            c.font = bold
    # NOI — from Stage 2's verified result (the vendor-reported figure), not re-summed here
    noi_vendor = [m["noi"][0] for m in noi_months][:n]
    ws2.append([])
    ws2.append(["NET OPERATING INCOME (verified)", *[_cell(v) for v in noi_vendor]])
    for c in ws2[ws2.max_row]:
        c.font = bold

    for sheet in (ws, ws2):
        sheet.column_dimensions["A"].width = 16
        sheet.column_dimensions["B"].width = 40
        sheet.column_dimensions["C"].width = 26
    return wb


def mapping_stats(rows: list[dict]) -> dict:
    """Counts for the header banner — how the Stage-3 mapping landed, over the DATA rows only.
    `mapped` = has an effective category (rulebook, AI suggestion, or user override);
    `unmapped` = none yet (needs a manual pick); `ai_suggested` = category came from the AI
    fallback, not the rulebook (worth a glance)."""
    data = [r for r in rows if r.get("is_data")]
    unmapped = sum(1 for r in data if r.get("is_unmapped"))
    return {
        "total":        len(data),
        "mapped":       len(data) - unmapped,
        "unmapped":     unmapped,
        "ai_suggested": sum(1 for r in data if r.get("is_ai_only")),
    }


def build_table_rows(mapped_data: dict) -> list[dict]:
    """
    One entry per non-empty row (data + subtotal + header).

    Data rows get the full mapping/flip-sign/override metadata.
    Non-data rows get a type_label ("Header" / "Subtotal" / "Total Revenue" /
    "Total Expense" / "NOI") and their values, but no mapping fields — they
    aren't user-categorizable.
    """
    rows_out = []
    for r in mapped_data.get("rows", []):
        row_type = r.get("type")
        if row_type == "empty":
            continue

        is_data           = row_type == "data"
        is_subtotal       = row_type == "subtotal"
        is_final_subtotal = is_subtotal and (
            r.get("is_total_revenue") or r.get("is_total_expense") or r.get("is_noi")
        )

        signed = _signed_values(r)
        t3, t6 = _trailing_totals(signed)

        rows_out.append({
            "row":               r["row"],
            "description":       r.get("description", ""),
            "type":              row_type,
            "type_label":        _row_type_label(r),
            "is_data":           is_data,
            "is_header":         row_type == "header",
            "is_subtotal":       is_subtotal,
            "is_final_subtotal": bool(is_final_subtotal),
            "section_context":   r.get("section_context", ""),
            "statement_side":    r.get("statement_side"),
            "effective_mapping": effective_mapping_of(r) if is_data else None,
            "original_mapping":  (r.get("mapping") or r.get("ai_suggested_mapping")) if is_data else None,
            "flip_sign":         bool(r.get("flip_sign")) if is_data else False,
            "values":            signed,
            "trailing_3":        t3,
            "trailing_6":        t6,
            "note":              r.get("review_note") or "" if is_data else "",
            "ai_suggested":      r.get("ai_suggested_mapping") if is_data else None,
            "ai_confidence":     r.get("ai_confidence") if is_data else None,
            "is_user_override":  is_data and (r.get("final_mapping") is not None),
            "is_ai_only":        is_data and (r.get("mapping") is None) and (r.get("ai_suggested_mapping") is not None),
            "is_unmapped":       is_data and effective_mapping_of(r) is None,
        })
    return rows_out


def compute_summary(noi_months: list[dict], column_headers: list) -> dict:
    """
    Bottom summary rows, read straight from Stage 2's verified NOI result: the same numbers,
    and the same per-month pass/fail, that the classification gate showed.

    The page does NOT re-derive them. It used to sum the mapped rows itself, which was a second
    implementation of a question the pipeline had already answered — and it drifted: it summed
    `revenue - expense` where the pipeline sums `revenue - |expense|`, so a vendor who signs
    expenses negative (Chateau in the Woods) showed a $730k difference on a file Stage 2 had
    passed. Mapping only assigns categories; it cannot move the money, so there is nothing here
    for a second opinion to catch.

    Each month of `noi_months` is {"rev"/"exp"/"noi": (vendor_actual, our_computed, match)}.
    """
    net_rental_income = [m["rev"][1] for m in noi_months]
    calculated_noi    = [m["noi"][1] for m in noi_months]
    original_noi      = [m["noi"][0] for m in noi_months]

    diff_by_month = []
    for m in noi_months:
        actual, computed, match = m["noi"]
        if actual is None or computed is None:
            diff_by_month.append({"value": None, "material": False})
        else:
            diff_by_month.append({"value": round(computed - actual, 2), "material": match is False})

    diff_values = [d["value"] for d in diff_by_month]
    nri_t3, nri_t6 = _trailing_totals(net_rental_income)
    cnoi_t3, cnoi_t6 = _trailing_totals(calculated_noi)
    onoi_t3, onoi_t6 = _trailing_totals(original_noi)
    diff_t3, diff_t6 = _trailing_totals(diff_values)

    return {
        "column_headers":         column_headers,
        "net_rental_income":      net_rental_income,
        "calculated_noi":         calculated_noi,
        "original_noi":           original_noi,
        "noi_difference":         diff_by_month,
        "any_diff_material":      any(d["material"] for d in diff_by_month),
        "net_rental_income_t3":   nri_t3, "net_rental_income_t6": nri_t6,
        "calculated_noi_t3":      cnoi_t3, "calculated_noi_t6": cnoi_t6,
        "original_noi_t3":        onoi_t3, "original_noi_t6": onoi_t6,
        "noi_difference_t3":      diff_t3, "noi_difference_t6": diff_t6,
    }
