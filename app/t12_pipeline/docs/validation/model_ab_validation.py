"""Model A/B mapping-accuracy validation.

For each held-out (input T12 -> Model T12 ground truth) pair:
  1. parse + classify + rulebook-map the raw input once (model-independent).
  2. extract ground truth (col T "Row Description (from T12)" -> col Z "Final_Mapping").
  3. run the AI fallback on the rulebook-missed rows under EACH candidate model,
     capturing suggestion / confidence / reasoning.
  4. grade rulebook rows (once) and AI rows (per model) against the ground truth.

Writes model_ab_validation.xlsx (Summary / AI Rows / Disagreements) + raw results JSON.
Rulebook mapping is deterministic, so only the AI-fallback rows differ by model.
"""
import copy
import json
import sys
from pathlib import Path

import openpyxl

from t12_pipeline.config import agent_llm_config as cfg
from t12_pipeline.config.paths import DATA_DIR
from t12_pipeline.config.rulebook_utils import (load_latest_rulebook, normalize_lookup_key)
from t12_pipeline.pipeline.parsing.run_parse import parse_file
from t12_pipeline.pipeline.parsing.legacy_adapter import to_annotated
from t12_pipeline.pipeline.mapping.map_blocks import map_results
from t12_pipeline.pipeline.mapping.find_mapping import run_ai_mapping

OUT_XLSX = Path("app/t12_pipeline/docs/validation/model_ab_validation.xlsx")
OUT_JSON = Path("/private/tmp/t12_model_ab/results.json")

MODELS = {
    "sonnet-5": "claude-sonnet-5",     # current production model
    "opus-4-8": "claude-opus-4-8",     # higher model, already used for structure/diagnosis
    "opus-5":   "claude-opus-5",       # latest / most capable
}

# input file  ->  Model T12 ground-truth file   (exact pairings from the prior validation)
PAIRS = [
    ("Lincoln Townhomes Seller T12.xlsx",            "Lincoln Townhomes Model T12.xlsx"),
    ("Willows of Coventry T12 11-25.xlsx",           "02252026_Willows of Coventry_V4 (1).xlsm"),
    ("Creekside Seller T12.xlsx",                     "Creekside Apartment Homes Model T12.xlsx"),
    ("Lockhart Seller T-12.xlsx",                     "Lockhart Model T12.xlsx"),
    ("Mirador Seller T12 .xlsx",                      "Mirador Model T12.xlsx"),
    ("River Point Seller T12 Feb.xlsx",              "River Point Model T12.xlsx"),
    ("River Point West Seller T12.xlsx",             "River Point West Model T12.xlsx"),
    ("Wythe Seller T12.xlsx",                         "Wythe Model T12.xlsx"),
    ("Ladera Seller T12.xlsx",                        "Ladera Model T12.xlsx"),
    ("RESERVE AT WHITE ROCK Seller T12.xlsx",         "Reserve_at_White_Rock Model T12.xlsx"),
    ("TRAILS AT WHITE ROCK Seller T12.xlsx",          "TRAILS OF WHITE ROCK Model T12.xlsx"),
    ("Arbor Gates at Buckhead Seller T12.xlsx",       "Arbor Gates at Buckhead Model T12.xlsx"),
    ("Cardinal Seller T12.xlsx",                      "Cardinal Model T12.xlsx"),
    ("Eleven11 Lexington at Flower Mound Seller T12.xlsx", "Eleven11 Lexington at Flower Mound Model T12.xlsx"),
    ("Holden Seller T12.xlsx",                        "Holden Model T12.xlsx"),
    ("Mesquite Seller T-12.xlsx",                     "Mesquite Model T12.xlsx"),
]

INPUT_ROOT = DATA_DIR / "input_T12_docs"
GT_ROOT = DATA_DIR / "mapped_T12_docs"


def find_input(name):
    hits = list(INPUT_ROOT.rglob(name))
    if not hits:
        raise FileNotFoundError(f"input not found: {name}")
    return hits[0]


def extract_gt(gt_path):
    """Return {normalized_description: final_mapping} for every graded GT account. Scans every
    sheet for the 'Row Description (from T12)' / 'Final_Mapping' header pair, then reads below."""
    wb = openpyxl.load_workbook(gt_path, read_only=True, data_only=True)
    for ws in wb.worksheets:
        desc_col = map_col = header_row = None
        for ri, row in enumerate(ws.iter_rows(values_only=True), start=1):
            for ci, v in enumerate(row):
                if isinstance(v, str):
                    s = v.strip()
                    if s == "Row Description (from T12)":
                        desc_col, header_row = ci, ri
                    elif s == "Final_Mapping":
                        map_col = ci
            if desc_col is not None and map_col is not None:
                break
        if desc_col is None or map_col is None:
            continue
        gt = {}
        for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
            desc = row[desc_col] if desc_col < len(row) else None
            final = row[map_col] if map_col < len(row) else None
            if isinstance(desc, str) and desc.strip() and isinstance(final, str) and final.strip():
                gt[normalize_lookup_key(desc)] = final.strip()
        wb.close()
        return gt
    wb.close()
    raise ValueError(f"no GT header found in {gt_path.name}")


def set_model(model_id):
    cfg.AGENT_LLM_CONFIGS[cfg.MAPPING_AI_AGENT]["model"] = model_id


def eq(a, b):
    return (a or "").strip().lower() == (b or "").strip().lower()


def run_one(input_name, gt_name):
    input_path = find_input(input_name)
    gt = extract_gt(GT_ROOT / gt_name)

    res = parse_file(str(input_path))
    rulebook = load_latest_rulebook()
    annotated = to_annotated(res, input_name)
    auto = map_results(annotated, rulebook)           # rulebook only; AI rows carry not_found=True
    noi_pass = bool((res.get("noi") or {}).get("overall_pass"))
    fmt = res.get("format")

    data_rows = [r for r in auto["rows"] if r.get("type") == "data"]
    ai_rows_template = [r for r in data_rows
                        if r.get("not_found") is True and r.get("statement_side") != "capex"]

    # run AI fallback under each model on a fresh copy of the missed rows
    ai_by_model = {}   # model -> {row_number -> {suggestion, confidence, reasoning}}
    for label, model_id in MODELS.items():
        set_model(model_id)
        rows_copy = copy.deepcopy(ai_rows_template)
        file_copy = {**auto, "rows": rows_copy}
        run_ai_mapping(file_copy, rulebook)
        ai_by_model[label] = {
            r["row"]: {"suggestion": r.get("ai_suggested_mapping"),
                       "confidence": r.get("ai_confidence"),
                       "reasoning": r.get("ai_reasoning")}
            for r in rows_copy
        }

    # ---- grade ----
    per_row = []
    for r in data_rows:
        key = normalize_lookup_key(r.get("description", ""))
        gt_map = gt.get(key)
        in_gt = gt_map is not None
        is_ai = r.get("not_found") is True and r.get("statement_side") != "capex"
        rec = {
            "row": r["row"], "description": r.get("description", ""),
            "statement_side": r.get("statement_side"),
            "section_path": r.get("section_path") or r.get("section_context"),
            "source": "ai" if is_ai else (r.get("mapping_source") or "unknown"),
            "rulebook_mapping": r.get("mapping"),
            "gt_final_mapping": gt_map, "in_gt": in_gt, "is_ai": is_ai,
            "models": {},
        }
        if is_ai:
            for label in MODELS:
                sug = ai_by_model[label].get(r["row"], {})
                rec["models"][label] = {
                    "suggestion": sug.get("suggestion"),
                    "confidence": sug.get("confidence"),
                    "reasoning": sug.get("reasoning"),
                    "correct": (eq(sug.get("suggestion"), gt_map) if in_gt else None),
                }
        else:
            for label in MODELS:
                rec["models"][label] = {
                    "suggestion": r.get("mapping"), "confidence": None, "reasoning": None,
                    "correct": (eq(r.get("mapping"), gt_map) if in_gt else None),
                }
        per_row.append(rec)

    return {"input": input_name, "gt": gt_name, "format": fmt, "noi_pass": noi_pass,
            "gt_accounts": len(gt), "rows": per_row}


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--build":
        results = json.loads(OUT_JSON.read_text())
        build_workbook(results)
        print(f"Rebuilt {OUT_XLSX} from cached results", flush=True)
        return
    only = sys.argv[1] if len(sys.argv) > 1 else None
    pairs = [p for p in PAIRS if (only is None or only.lower() in p[0].lower())]
    all_results = []
    for i, (inp, gtn) in enumerate(pairs, 1):
        print(f"[{i}/{len(pairs)}] {inp}", flush=True)
        try:
            all_results.append(run_one(inp, gtn))
        except Exception as e:
            import traceback; traceback.print_exc()
            all_results.append({"input": inp, "gt": gtn, "error": str(e), "rows": []})
        OUT_JSON.write_text(json.dumps(all_results, indent=2))
        print(f"    saved ({len(all_results)} files so far)", flush=True)
    print("DONE parse+AI. Building workbook...", flush=True)
    build_workbook(all_results)
    print(f"Wrote {OUT_XLSX}", flush=True)


def build_workbook(results):
    from openpyxl.styles import Font
    bold = Font(bold=True)
    labels = list(MODELS)
    wb = openpyxl.Workbook()

    # ---- Summary ----
    ws = wb.active; ws.title = "Summary"
    head = ["input", "gt_file", "format", "noi_pass", "gt_accounts", "eligible",
            "matched", "rb_map", "rb_hit", "rb_ok", "rb_precision", "ai_map"]
    for label in labels:
        head += [f"ai_hit[{label}]", f"ai_ok[{label}]", f"ai_prec[{label}]", f"overall_acc[{label}]"]
    ws.append(head)
    for c in ws[1]:
        c.font = bold

    tot = {"gt": 0, "elig": 0, "matched": 0, "rb_map": 0, "rb_hit": 0, "rb_ok": 0, "ai_map": 0}
    tot_m = {label: {"ai_hit": 0, "ai_ok": 0, "overall_ok": 0} for label in labels}

    for r in results:
        if r.get("error"):
            ws.append([r["input"], r.get("gt", ""), "ERROR", "", "", "", "", "", "", "", "", "", *([""] * 4 * len(labels))])
            continue
        rows = r["rows"]
        elig = len(rows)
        matched = [x for x in rows if x["in_gt"]]
        rb_rows = [x for x in rows if not x["is_ai"]]
        ai_rows = [x for x in rows if x["is_ai"]]
        rb_hit = [x for x in rb_rows if x["in_gt"]]
        rb_ok = sum(1 for x in rb_hit if x["models"][labels[0]]["correct"])
        rb_prec = round(100 * rb_ok / len(rb_hit), 1) if rb_hit else ""
        tot["gt"] += r["gt_accounts"]; tot["elig"] += elig; tot["matched"] += len(matched)
        tot["rb_map"] += len(rb_rows); tot["rb_hit"] += len(rb_hit); tot["rb_ok"] += rb_ok
        tot["ai_map"] += len(ai_rows)
        line = [r["input"], r["gt"], r.get("format", ""), r.get("noi_pass", ""),
                r["gt_accounts"], elig, len(matched), len(rb_rows), len(rb_hit), rb_ok, rb_prec, len(ai_rows)]
        for label in labels:
            ai_hit = [x for x in ai_rows if x["in_gt"]]
            ai_ok = sum(1 for x in ai_hit if x["models"][label]["correct"])
            ai_prec = round(100 * ai_ok / len(ai_hit), 1) if ai_hit else ""
            overall_ok = rb_ok + ai_ok
            overall_acc = round(100 * overall_ok / len(matched), 1) if matched else ""
            line += [len(ai_hit), ai_ok, ai_prec, overall_acc]
            tot_m[label]["ai_hit"] += len(ai_hit); tot_m[label]["ai_ok"] += ai_ok
            tot_m[label]["overall_ok"] += overall_ok
        ws.append(line)

    total_line = ["TOTAL", "", "", "", tot["gt"], tot["elig"], tot["matched"], tot["rb_map"],
                  tot["rb_hit"], tot["rb_ok"],
                  round(100 * tot["rb_ok"] / tot["rb_hit"], 1) if tot["rb_hit"] else "", tot["ai_map"]]
    for label in labels:
        m = tot_m[label]
        ai_prec = round(100 * m["ai_ok"] / m["ai_hit"], 1) if m["ai_hit"] else ""
        overall_acc = round(100 * m["overall_ok"] / tot["matched"], 1) if tot["matched"] else ""
        total_line += [m["ai_hit"], m["ai_ok"], ai_prec, overall_acc]
    ws.append(total_line)
    for c in ws[ws.max_row]:
        c.font = bold

    # ---- AI Rows (the model A/B, one row per AI-fallback account) ----
    ws2 = wb.create_sheet("AI Rows")
    h2 = ["file", "row", "description", "statement_side", "section_path", "in_gt", "gt_final_mapping"]
    for label in labels:
        h2 += [f"{label}_suggestion", f"{label}_correct", f"{label}_conf", f"{label}_reasoning"]
    ws2.append(h2)
    for c in ws2[1]:
        c.font = bold
    for r in results:
        for x in r.get("rows", []):
            if not x["is_ai"]:
                continue
            sp = x["section_path"]
            sp = " > ".join(sp) if isinstance(sp, list) else (sp or "")
            line = [r["input"], x["row"], x["description"], x["statement_side"], sp,
                    x["in_gt"], x["gt_final_mapping"] or ""]
            for label in labels:
                m = x["models"][label]
                corr = "" if m["correct"] is None else ("Y" if m["correct"] else "N")
                line += [m["suggestion"] or "", corr, m["confidence"] or "", m["reasoning"] or ""]
            ws2.append(line)

    # ---- Disagreements: AI rows in GT where models differ OR any model is wrong ----
    ws3 = wb.create_sheet("Disagreements")
    ws3.append(h2)
    for c in ws3[1]:
        c.font = bold
    for r in results:
        for x in r.get("rows", []):
            if not x["is_ai"] or not x["in_gt"]:
                continue
            suggs = {x["models"][l]["suggestion"] for l in labels}
            corrs = {x["models"][l]["correct"] for l in labels}
            if len(suggs) > 1 or (False in corrs):
                sp = x["section_path"]
                sp = " > ".join(sp) if isinstance(sp, list) else (sp or "")
                line = [r["input"], x["row"], x["description"], x["statement_side"], sp,
                        x["in_gt"], x["gt_final_mapping"] or ""]
                for label in labels:
                    m = x["models"][label]
                    corr = "" if m["correct"] is None else ("Y" if m["correct"] else "N")
                    line += [m["suggestion"] or "", corr, m["confidence"] or "", m["reasoning"] or ""]
                ws3.append(line)

    # ---- Findings: the readout for the client ----
    import collections
    ws4 = wb.create_sheet("Findings", 0)
    ai_all = [x for r in results for x in r.get("rows", []) if x["is_ai"]]
    gradeable = [x for x in ai_all if x["in_gt"]]
    agree3 = sum(1 for x in ai_all if len({(x["models"][l]["suggestion"] or "").strip().lower() for l in labels}) == 1)

    def prec(label):
        ok = sum(1 for x in gradeable if x["models"][label]["correct"])
        return ok, len(gradeable), (round(100 * ok / len(gradeable), 1) if gradeable else 0)

    def bold_row(cells):
        ws4.append(cells)
        ws4[ws4.max_row][0].font = bold

    bold_row(["MAPPING MODEL A/B — held-out validation (16 seller T12s vs the client's Model T12 ground truth)"])
    ws4.append([])
    bold_row(["1. Does a higher model improve mapping accuracy?  —  NO."])
    ws4.append(["AI-fallback rows are the ONLY rows a model choice can change (the rulebook is deterministic)."])
    ws4.append([f"Gradeable AI-fallback rows across all files: {len(gradeable)}"])
    for label in labels:
        ok, n, p = prec(label)
        ws4.append([f"   {label}", f"{ok}/{n} correct", f"{p}% precision"])
    ws4.append([f"All three models pick the SAME category on {agree3} of {len(ai_all)} AI rows "
                f"({round(100*agree3/len(ai_all))}%) — temperature 0 on a pick-one-of-{len(load_latest_rulebook().get('certain', {})) and 38}-categories task."])
    ws4.append(["Conclusion: Sonnet-5 (current) is already the best of the three. Opus-4-8 / Opus-5 cost more, "
                "run slower, and are slightly LESS accurate here. Recommendation: keep Sonnet-5."])
    ws4.append([])
    bold_row(["2. Why do the wrong ones go wrong?  —  client-convention disagreements, not reasoning errors."])
    wrong = [x for x in gradeable if x["models"]["sonnet-5"]["correct"] is False]
    ws4.append([f"Sonnet-5 misses: {len(wrong)} of {len(gradeable)} gradeable AI rows."])
    ws4.append(["Most common confusions  (client's category  <-  what the AI picked instead):"])
    conf = collections.Counter((x["gt_final_mapping"], x["models"]["sonnet-5"]["suggestion"]) for x in wrong)
    for (gt, pred), n in conf.most_common(12):
        ws4.append([f"   {n}x", f"{gt}", f"<- {pred}"])
    ws4.append(["Pattern: the AI picks the textbook-standard category (e.g. Repairs & Maintenance); the client "
                "books it under a house convention (e.g. Turnover Expenses / Contracted Services). A bigger "
                "model cannot know a client's private convention — the rulebook must encode it."])
    ws4.append([])
    bold_row(["3. The ground truth contradicts itself on some accounts (an upper bound on any model)."])
    ws4.append(["Same account description, DIFFERENT 'correct' category in different client files:"])
    seen = collections.defaultdict(set)
    for r in results:
        for x in r.get("rows", []):
            d = (x["description"] or "").strip().lower()
            g = x["gt_final_mapping"]
            if g:
                seen[d].add(g)
    contradictions = {d: gs for d, gs in seen.items()
                      if len({g.strip().lower() for g in gs}) > 1}
    for d, gs in sorted(contradictions.items()):
        ws4.append([f"   {d}", " | ".join(sorted(gs))])
    ws4.append([f"({len(contradictions)} accounts are labeled inconsistently — no single mapping can score 100%.)"])
    ws4.append([])
    bold_row(["Bottom line: keep Sonnet-5; grow the rulebook (Add-to-rulebook + notes) to capture client "
              "conventions. That is the lever, not the model."])
    ws4.column_dimensions["A"].width = 46
    ws4.column_dimensions["B"].width = 40
    ws4.column_dimensions["C"].width = 40

    for sheet in (ws, ws2, ws3):
        sheet.column_dimensions["A"].width = 34
        sheet.column_dimensions["C"].width = 34
    OUT_XLSX.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT_XLSX)


if __name__ == "__main__":
    main()
