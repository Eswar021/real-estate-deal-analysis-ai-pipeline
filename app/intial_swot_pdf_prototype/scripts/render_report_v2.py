#!/usr/bin/env python3
"""
Render Report v2 — Reads report_data_v2.json, outputs HTML+PDF.
Maps each page to its instruction page_title and layout_order.
Report named per instructions: PIR_PropertyName_City_Date.
"""
import json, os, subprocess, re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(BASE, "output", "report_data_v2.json")) as f:
    D = json.load(f)
with open(os.path.join(BASE, "pages", "Instructions.json")) as f:
    INS = json.load(f)

dh = D["page_1"]["deal_header"]
prop_name = dh["property_name"]
city = dh["submarket_label"].split(",")[0].strip()
date_str = dh["report_date"]

# Report filename per instructions
safe = re.sub(r'[^a-zA-Z0-9_]', '_', f"PIR_{prop_name}_{city}_{date_str}")
OUT_HTML = os.path.join(BASE, "output", f"{safe}.html")
OUT_PDF = OUT_HTML.replace(".html", ".pdf")

def esc(v):
    if v is None: return '<span style="color:var(--red);">N/A</span>'
    return str(v).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def pill(val, color=None):
    if val is None: return '<span class="pill slate">N/A</span>'
    if isinstance(val, (int, float)):
        if val > 0: return f'<span class="pill green">+{val:g}</span>'
        elif val < 0: return f'<span class="pill red">{val:g}</span>'
        else: return f'<span class="pill slate">0</span>'
    c = color or "slate"
    return f'<span class="pill {c}">{esc(val)}</span>'

def top_bar():
    return f'<div class="top-bar"><div class="brand">Oakdale AI</div><div class="meta">{esc(prop_name)} · Property Intelligence Report</div></div>'

def footer(n, total=9):
    return f'<div class="footer"><div>Oakdale AI · Internal Use Only · Confidential</div><div>Page {n} of {total}</div></div>'

def page_label(page_key):
    num = page_key.replace("page_","")
    title = INS.get(page_key, {}).get("page_title", "")
    return f'<div class="page-label">Page {num} · {esc(title)}</div>'

def section_tag(text):
    return f'<div class="section-tag">{esc(text)}</div>'

# ──── PAGE BUILDERS ────

def build_page_1():
    ds = D["page_1"]["decision_snapshot"]
    ip = D["page_1"]["investment_perspective"]
    tr = D["page_1"]["top_reasons_and_risks"]
    sd = D["page_1"]["score_dashboard"]

    # deal_header
    deal = f'''<div class="card-row c4">
      <div class="card"><div class="card-label">Property</div><div class="card-value" style="font-size:13px;">{esc(dh["property_name"])}</div><div class="card-sub">{esc(dh["full_address"])}</div></div>
      <div class="card"><div class="card-label">Submarket</div><div class="card-value" style="font-size:13px;">{esc(dh["submarket_label"])}</div><div class="card-sub">{esc(dh["data_sources_summary"])}</div></div>
      <div class="card"><div class="card-label">Total Units / Vintage</div><div class="card-value" style="font-size:13px;">{dh["total_units"]} · {int(dh["year_built"])}</div><div class="card-sub">Broker: {esc(dh["broker"])}</div></div>
      <div class="card"><div class="card-label">Asking Price / Unit</div><div class="card-value gold" style="font-size:13px;">{esc(dh["asking_price_per_unit"])}</div><div class="card-sub">{esc(dh["implied_total_price"])} total</div></div>
    </div>'''

    # decision_snapshot
    vcolor = "red" if "No-Go" in ds["verdict_label"] else ("gold" if "Conditional" in ds["verdict_label"] else "green")
    blocks = " · ".join(ds["blocking_conditions"])
    snap = f'''{section_tag("Decision Snapshot")}
    <div class="alert {"red" if ds["blocking_conditions"][0]!="None identified" else "green"}"><span class="alert-icon">⚠</span> {esc(blocks)}</div>
    <div class="verdict-row">
      <div class="verdict-box"><div class="vb-label">Verdict</div><div class="vb-value {vcolor}">{ds["verdict_label"].upper()}</div><div class="vb-sub">Blocking: {"; ".join(ds["must_be_true_to_proceed"])}</div></div>
      <div class="verdict-box"><div class="vb-label">Thesis</div><div class="vb-value gold">{esc(ds["thesis_label"])}</div><div class="vb-sub">{ds["confidence_label"].upper()}</div></div>
    </div>'''

    # investment_perspective
    persp = f'''{section_tag("Investment Perspective")}
    <div class="narrative">{esc(ip["paragraph"])}</div>'''

    # top_reasons_and_risks
    def reason_list(items, cls):
        h = ""
        for i, r in enumerate(items):
            h += f'<div class="reason"><div class="r-num {cls}">{i+1}</div><div class="r-body"><div class="r-title">{esc(r["title"])} {pill(r.get("rubric_score"))}</div><div class="r-detail"><strong>Fact:</strong> {esc(r["fact_line"])}<br>{esc(r["why_it_matters"])}</div></div></div>'
        return h
    reasons = f'''{section_tag("Top Supporting Reasons")}
    {reason_list(tr["top_supporting_reasons"], "support")}
    {section_tag("Top Risk Reasons")}
    {reason_list(tr["top_risk_reasons"], "risk")}'''

    # score_dashboard
    dm = sd["dimension_scores"]
    ms = sd["missing_data_summary"]
    dash = f'''{section_tag("Score Dashboard")}
    <div class="card-row c4" style="margin-bottom:6px;">
      <div class="card" style="border-color:var(--gold-dim); text-align:center;"><div class="card-label">Oakdale Score</div><div class="card-value gold" style="font-size:28px;">{sd["composite_score"]}</div><div class="card-sub">{ms["score_completeness_percent"]}% complete ({len(ms["missing_score_fields"])} missing)</div></div>
      <div class="card" style="text-align:center;"><div class="card-label">Building</div><div class="card-value green">+{dm["building_attributes"]:g}</div></div>
      <div class="card" style="text-align:center;"><div class="card-label">Location</div><div class="card-value green">+{dm["location_walkability"]:g}</div></div>
      <div class="card" style="text-align:center;"><div class="card-label">Demographics</div><div class="card-value green">+{dm["demographics_demand"]:g}</div></div>
    </div>'''

    return f'''<div class="page">{top_bar()}{page_label("page_1")}{deal}{snap}{persp}{reasons}{dash}{footer(1)}</div>'''

def build_page_2():
    p = D["page_2"]
    ppo = p["property_product_overview"]
    am = p["amenity_matrix"]
    pos = p["positive_score_drivers"]["cards"]
    neg = p["structural_constraints"]["cards"]
    mix = p["mixed_factors_and_neutral_signals"]["mixed_factors"]
    pcr = p["physical_condition_and_product_read"]

    product = f'''{section_tag("Property Product Overview")}
    <div class="g2"><div>
    <table><tr><th>Attribute</th><th>Value</th></tr>
    <tr><td>Year Built</td><td><strong>{int(ppo["year_built"])}</strong></td></tr>
    <tr><td>Total Units</td><td><strong>{ppo["total_units"]}</strong></td></tr>
    <tr><td>Asking Price/Unit</td><td>{esc(ppo["asking_price_per_unit"])}</td></tr>
    <tr><td>Implied Total</td><td>{esc(ppo["implied_total_price"])} {pill("derived","gold")}</td></tr>
    <tr><td>Unit Mix</td><td style="font-size:9px;">{esc(ppo["unit_mix_raw"])}</td></tr>
    <tr><td>1BR Sqft</td><td>{esc(ppo["parsed_1br_sqft_basis"])}</td></tr>
    <tr><td>Ceiling Height</td><td>{esc(ppo["ceiling_height_raw"])}</td></tr>
    <tr><td>Size Label</td><td>{esc(ppo["apartment_size_helper_label"])} {pill("helper","slate")}</td></tr>
    </table></div>
    <div>{section_tag("Amenity Matrix")}
    <table><tr><th>Feature</th><th>Status</th><th>Confidence</th></tr>
    {"".join(f'<tr><td>{esc(a["feature"])}</td><td>{pill("Yes","green") if a["status"]=="Yes" else esc(a["status"])}</td><td>High</td></tr>' for a in am["high_confidence_features"])}
    {"".join(f'<tr><td>{esc(a["feature"])}</td><td>{pill(a["status"],"gold")}</td><td style="color:var(--orange);">Low (scrape)</td></tr>' for a in am["low_confidence_features"])}
    </table></div></div>'''

    pos_html = f'''{section_tag("Positive Score Drivers")}
    <table><tr><th>Variable</th><th>Raw Value</th><th>Rubric</th><th>Fact Line</th></tr>
    {"".join(f'<tr><td>{esc(c["variable_name"])}</td><td>{esc(c["raw_value"])}</td><td>{pill(c["rubric_score"])}</td><td style="font-size:9px;">{esc(c["fact_line"])}</td></tr>' for c in pos)}
    </table>'''

    neg_html = f'''{section_tag("Structural Constraints")}
    <table><tr><th>Variable</th><th>Raw Value</th><th>Rubric</th><th>Fact Line</th></tr>
    {"".join(f'<tr><td>{esc(c["variable_name"])}</td><td>{esc(c["raw_value"])}</td><td>{pill(c["rubric_score"])}</td><td style="font-size:9px;">{esc(c["fact_line"])}</td></tr>' for c in neg)}
    </table>'''

    mix_html = f'''{section_tag("Mixed Factors & Neutral Signals")}
    <table><tr><th>Variable</th><th>Raw</th><th>Rubric</th><th>Status</th><th>Note</th></tr>
    {"".join(f'<tr><td>{esc(m["variable_name"])}</td><td>{esc(m["raw_value"]) if m["raw_value"] is not None else "<span style=color:var(--red)>MISSING</span>"}</td><td>{pill(m["rubric_score"])}</td><td>{pill(m["status"],"orange" if "missing" in str(m["status"]) else "slate")}</td><td style="font-size:9px;">{esc(m["note"])}</td></tr>' for m in mix)}
    </table>'''

    phys = f'''{section_tag("Physical Condition & Product Read")}
    <div class="narrative">{esc(pcr["paragraph"])}<br><br><strong>Capex Signal:</strong> {pill(pcr["capex_signal_label"],"gold")}</div>'''

    return f'<div class="page">{top_bar()}{page_label("page_2")}{product}{pos_html}{neg_html}{mix_html}{phys}{footer(2)}</div>'

def build_page_3():
    p = D["page_3"]
    gc = p["geographic_context"]
    mob = p["mobility_and_environment"]["mobility_metrics"]
    ret = p["retail_access_and_adjacency"]["retail_metrics"]
    sch = p["school_context"]
    dem = p["demographic_demand_table"]["table_rows"]
    ldr = p["location_demand_read"]

    geo = f'''{section_tag("Geographic Context")}
    <div class="card-row c4">
      <div class="card"><div class="card-label">Location</div><div class="card-value" style="font-size:11px;">{esc(gc["location_label"])}</div></div>
      <div class="card"><div class="card-label">Census Tract</div><div class="card-value" style="font-size:11px;">{gc["census_tract"]}</div><div class="card-sub">{esc(gc["county"])}</div></div>
      <div class="card"><div class="card-label">FIPS</div><div class="card-value" style="font-size:9px;">{gc["fips_summary"]["state_code"]}-{gc["fips_summary"]["county_code"]}-{gc["fips_summary"]["tract_code"]}</div></div>
      <div class="card"><div class="card-label">Missing Location</div><div class="card-value red" style="font-size:9px;">{", ".join(gc["location_missing_fields"]) if gc["location_missing_fields"] else "None"}</div></div>
    </div>'''

    mob_html = f'''{section_tag("Mobility & Environment")}
    <table><tr><th>Metric</th><th>Value</th><th>Rubric</th><th>Note</th></tr>
    {"".join(f'<tr><td>{esc(m["metric"])}</td><td>{"<span style=color:var(--red)>MISSING</span>" if m["raw_value"]=="Not available" else esc(m["raw_value"])}</td><td>{pill(m["rubric_score"])}</td><td style="font-size:9px;">{esc(m["status_note"])}</td></tr>' for m in mob)}
    </table>'''

    ret_html = f'''{section_tag("Retail Access & Adjacency")}
    <table><tr><th>Metric</th><th>Distance</th><th>Rubric</th></tr>
    {"".join(f'<tr><td>{esc(r["metric"])}</td><td>{r["raw_value"]} mi</td><td>{pill(r["rubric_score"])}</td></tr>' for r in ret)}
    </table>'''

    sch_html = f'''{section_tag("School Context")}
    <div class="card" style="margin-bottom:8px;"><div class="card-label">Composite GreatSchools Score</div><div style="font-size:13px; font-weight:700; color:var(--white);">{sch["school_summary"]["composite_score"]} / 5.0 {pill(sch["school_summary"]["rubric_score"])}</div></div>
    <table><tr><th>School</th><th>Level</th><th>Rating</th><th>Distance</th></tr>
    {"".join(f'<tr><td>{esc(s["school_name"])}</td><td>{esc(s["level_codes"])}</td><td>{esc(s["rating_label"])}</td><td>{s["distance_miles"]} mi</td></tr>' for s in sch["schools"])}
    </table>'''

    dem_html = f'''{section_tag("Demographic & Demand Table")}
    <table><tr><th>Metric</th><th>Value</th><th>Rubric</th><th>Note</th></tr>
    {"".join(f'<tr><td>{esc(r["metric"])}</td><td>{esc(r["raw_value"])}</td><td>{pill(r["rubric_score"])}</td><td style="font-size:9px;">{esc(r.get("note",""))}</td></tr>' for r in dem)}
    </table>'''

    ldr_html = f'''{section_tag("Location Demand Read")}
    <div class="narrative">{esc(ldr["paragraph"])}<br><br><strong>Location Support:</strong> {pill(ldr["location_support_label"],"orange")} &nbsp; <strong>Gap:</strong> {esc(ldr["data_gap_note"])}</div>'''

    return f'<div class="page">{top_bar()}{page_label("page_3")}<div class="g2"><div>{geo}{mob_html}</div><div>{ret_html}{sch_html}</div></div>{dem_html}{ldr_html}{footer(3)}</div>'

def build_page_4():
    p = D["page_4"]
    cards = p["sentiment_overview_cards"]["cards"]
    ohc = p["operating_health_by_category"]
    ohr = p["operating_health_read"]
    pats = p["notable_patterns_and_threshold_signals"]["pattern_bullets"]

    cards_html = f'''<div class="card-row c4">
    {"".join(f'<div class="card" style="text-align:center;"><div class="card-label">{esc(c["card_name"])}</div><div class="card-value" style="color:var(--slate);">{esc(c["value"])}</div><div class="card-sub">{esc(c["subtext"])}</div></div>' for c in cards)}
    </div>'''

    alert = '<div class="alert orange"><span class="alert-icon">ℹ</span> No sentiment data is available for this property. All operational assessment sections require data acquisition.</div>'

    cats = ""
    for cat_key, v in ohc.items():
        label = cat_key.replace("_"," ").title()
        cats += f'<div class="flag-row"><div class="flag-header"><div class="flag-name">{label}</div>{pill(v["signal_label"],"slate")}</div><div class="flag-detail">{esc(v["paragraph"])}</div></div>'

    pats_html = f'''{section_tag("Notable Patterns & Threshold Signals")}
    <ul class="checklist monitor">{"".join(f"<li>{esc(p)}</li>" for p in pats)}</ul>'''

    ohr_html = f'''{section_tag("Operating Health Read")}
    <div class="narrative">{esc(ohr["paragraph"])}<br><br><strong>Operating Health:</strong> {pill(ohr["operating_health_label"],"slate")}</div>'''

    return f'<div class="page">{top_bar()}{page_label("page_4")}{section_tag("Sentiment Overview")}{cards_html}{alert}{section_tag("Operating Health by Category")}{cats}{pats_html}{ohr_html}{footer(4)}</div>'

def build_page_5():
    p = D["page_5"]
    dbf = p["deal_breaker_flags"]
    nf = p["notable_flags"]["flags"]
    mf = p["monitor_flags"]["flags"]
    sc = p["signal_contradictions"]["contradictions"]
    ku = p["known_unknowns_and_data_gaps"]
    dg = p["decision_gate_checklist"]

    db_html = f'''{section_tag("Deal-Breaker Flags")}
    <div class="card" style="border-left:3px solid var(--red); margin-bottom:10px;"><div class="card-label" style="color:var(--red);">{esc(dbf["deal_breaker_status"])}</div></div>
    {"".join(f'<div class="flag-row" style="border-color:rgba(248,113,113,0.3);"><div class="flag-header"><div class="flag-name">⚠ {esc(f["flag_name"])}</div>{pill("BLOCKING","red")}</div><div class="flag-detail"><strong>Evidence:</strong> {esc(f["evidence"])}<br><strong>Why blocks:</strong> {esc(f["why_it_blocks"])}<br><strong>Resolution:</strong> {esc(f["resolution_path"])}</div></div>' for f in dbf["flags"])}'''

    nf_html = f'''{section_tag("Notable Flags")}
    {"".join(f'<div class="flag-row"><div class="flag-header"><div class="flag-name">{esc(f["flag_name"])}</div>{pill(f.get("tier_or_category",""),"orange")}</div><div class="flag-detail"><strong>Evidence:</strong> {esc(f["evidence"])}<br><strong>Open Q:</strong> {esc(f.get("open_question",""))}<br><strong>→ Next:</strong> {esc(f.get("next_step",""))}</div></div>' for f in nf)}'''

    mf_html = f'''{section_tag("Monitor Flags")}
    {"".join(f'<div class="flag-row" style="border-color:var(--border);"><div class="flag-header"><div class="flag-name">{esc(f["flag_name"])}</div>{pill("Monitor","slate")}</div><div class="flag-detail">{esc(f["evidence"])} — {esc(f["why_monitor_only"])}</div></div>' for f in mf)}'''

    sc_html = f'''{section_tag("Signal Contradictions")}
    {"".join(f'<div class="flag-row" style="border-left:3px solid var(--gold);"><div class="flag-header"><div class="flag-name" style="font-size:10px;">{esc(c["signal_a"])}<br>vs {esc(c["signal_b"])}</div>{pill("Conflict","gold")}</div><div class="flag-detail"><strong>Implication:</strong> {esc(c["conflict_implication"])}<br><strong>Resolution:</strong> {esc(c["resolution_path"])}</div></div>' for c in sc)}'''

    ku_html = f'''{section_tag("Known Unknowns & Data Gaps")}
    <div class="g2">
      <div><div style="font-size:9px; font-weight:700; color:var(--red); text-transform:uppercase; letter-spacing:2px; margin-bottom:4px;">Tier 1 Missing</div><ul class="checklist must">{"".join(f"<li>{esc(x)}</li>" for x in ku["tier_1_missing"])}</ul>
      <div style="font-size:9px; font-weight:700; color:var(--orange); text-transform:uppercase; letter-spacing:2px; margin-bottom:4px; margin-top:8px;">Tier 2 Missing</div><ul class="checklist should">{"".join(f"<li>{esc(x)}</li>" for x in ku["tier_2_missing"])}</ul></div>
      <div><div style="font-size:9px; font-weight:700; color:var(--gold); text-transform:uppercase; letter-spacing:2px; margin-bottom:4px;">Transform-Dependent</div><ul class="checklist monitor">{"".join(f"<li>{esc(x)}</li>" for x in ku["transformation_dependent"])}</ul>
      <div style="font-size:9px; font-weight:700; color:var(--slate); text-transform:uppercase; letter-spacing:2px; margin-bottom:4px; margin-top:8px;">Rubric Reconciliation</div><ul class="checklist monitor">{"".join(f"<li>{esc(x)}</li>" for x in ku["rubric_reconciliation_needed"])}</ul></div>
    </div>'''

    dg_html = f'''{section_tag("Decision Gate Checklist")}
    <div class="g2">
      <div><div style="font-size:9px; font-weight:700; color:var(--red); text-transform:uppercase; letter-spacing:2px; margin-bottom:4px;">Must Have Before Underwriting</div><ul class="checklist must">{"".join(f"<li>{esc(x)}</li>" for x in dg["must_have_before_underwriting"])}</ul></div>
      <div><div style="font-size:9px; font-weight:700; color:var(--orange); text-transform:uppercase; letter-spacing:2px; margin-bottom:4px;">Should Have</div><ul class="checklist should">{"".join(f"<li>{esc(x)}</li>" for x in dg["should_have_before_underwriting"])}</ul>
      <div style="font-size:9px; font-weight:700; color:var(--slate); text-transform:uppercase; letter-spacing:2px; margin-bottom:4px; margin-top:6px;">Can Monitor</div><ul class="checklist monitor">{"".join(f"<li>{esc(x)}</li>" for x in dg["can_monitor_later"])}</ul></div>
    </div>'''

    return f'<div class="page">{top_bar()}{page_label("page_5")}{db_html}{nf_html}{mf_html}{sc_html}{ku_html}{dg_html}{footer(5)}</div>'

def build_page_6():
    p = D["page_6"]
    tc = p["thesis_classification"]
    sr = p["supporting_rationale"]
    pua = p["primary_underwriting_assumption"]
    aa = p["alternative_archetypes_ruled_out"]["archetypes"]
    tcd = p["thesis_confidence_and_dependency_note"]

    tc_html = f'''{section_tag("Thesis Classification")}
    <div class="verdict-row">
      <div class="verdict-box"><div class="vb-label">Investment Thesis</div><div class="vb-value gold">{esc(tc["thesis_label"])}</div><div class="vb-sub">{tc["thesis_hypothesis_suffix"] or ""} — Driver: {tc["primary_driver_type"]}</div></div>
      <div class="verdict-box"><div class="vb-label">Confidence</div><div class="vb-value {"red" if tcd["confidence_label"]=="Hypothesis" else "orange"}">{tcd["confidence_label"].upper()}</div><div class="vb-sub">{len(tcd["critical_dependencies"])} dependencies</div></div>
    </div>'''

    sr_html = f'''{section_tag("Supporting Rationale")}<div class="narrative">{esc(sr["paragraph"])}</div>'''

    pua_html = f'''{section_tag("Primary Underwriting Assumption")}
    <div class="card" style="border-left:3px solid var(--gold); margin-bottom:12px;">
      <div style="font-size:12px; font-weight:700; color:var(--white); margin-bottom:6px;">{esc(pua["assumption_title"])}</div>
      <div style="font-size:10px; color:var(--slate); line-height:1.6;">{esc(pua["assumption_statement"])}</div>
      <div style="margin-top:6px;"><strong style="color:var(--gold); font-size:9px;">Must Confirm:</strong> <span style="font-size:9px; color:var(--slate);">{" · ".join(pua["must_confirm_inputs"])}</span></div>
    </div>'''

    aa_html = f'''{section_tag("Alternative Archetypes Ruled Out")}
    <table><tr><th>Archetype</th><th>Ruling</th><th>Reason</th></tr>
    {"".join(f'<tr><td>{esc(a["archetype_name"])}</td><td>{pill(a["status"],"red")}</td><td style="font-size:9px;">{esc(a["reason"])}</td></tr>' for a in aa)}
    </table>'''

    tcd_html = f'''{section_tag("Thesis Confidence & Dependencies")}
    <div class="alert orange"><span class="alert-icon">◉</span> <strong>Confidence: {tcd["confidence_label"].upper()}</strong> — {esc(tcd["dependency_note"])}</div>
    <ul class="checklist must" style="margin-top:6px;">{"".join(f"<li>{esc(d)}</li>" for d in tcd["critical_dependencies"])}</ul>'''

    return f'<div class="page">{top_bar()}{page_label("page_6")}{tc_html}{sr_html}{pua_html}{aa_html}{tcd_html}{footer(6)}</div>'

def build_page_7():
    p = D["page_7"]
    drs = p["data_reliability_summary"]["summary_cards"]
    rows = p["core_variable_log"]["rows"]
    sdl = p["sentiment_data_log"]
    trace = p["traceability_and_rebuild_metadata"]

    drs_html = f'''{section_tag("Data Reliability Summary")}
    <div class="card-row c4">{"".join(f'<div class="card" style="text-align:center;"><div class="card-label">{esc(c["label"])}</div><div class="card-value {"red" if isinstance(c["value"],int) and c["value"]>0 and "Missing" in c["label"] else "gold"}" style="font-size:18px;">{c["value"]}{"%" if c["label"]=="Score Completeness" else ""}</div><div class="card-sub">{esc(c["subtext"])}</div></div>' for c in drs)}</div>'''

    log_rows = ""
    for r in rows:
        rv = esc(r["raw_value"]) if r["raw_value"] is not None else '<span style="color:var(--red);">MISSING</span>'
        note = esc(r["notes_or_missing_flag"]) if r["notes_or_missing_flag"] else ""
        ms = r["max_score"] if r["max_score"] is not None else "—"
        log_rows += f'<tr><td>{esc(r["variable_display_name"])}</td><td>{r["tier"]}</td><td>{rv}</td><td>{pill(r["rubric_score"])}</td><td>{ms}</td><td style="font-size:8px;">{esc(r.get("data_source",""))}</td><td style="font-size:8px;">{note}</td></tr>'

    varlog = f'''{section_tag("Core Variable Log")}
    <table style="font-size:9px;"><tr><th>Variable</th><th>Tier</th><th>Raw Value</th><th>Rubric</th><th>Max</th><th>Source</th><th>Notes</th></tr>{log_rows}</table>'''

    sent = sdl["sentiment_summary"]
    sent_html = f'''{section_tag("Sentiment Data Log")}
    <table style="font-size:9px;"><tr><th>Item</th><th>Value</th></tr>
    {"".join(f'<tr><td>{k.replace("_"," ").title()}</td><td>{esc(v)}</td></tr>' for k,v in sent.items())}
    </table>'''

    trace_html = f'''{section_tag("Traceability & Rebuild Metadata")}
    <div class="narrative" style="font-size:9px;">{esc(trace["traceability_note"])}</div>
    <div style="margin-top:6px;"><strong style="color:var(--gold); font-size:9px;">Rebuild Limitations:</strong></div>
    <ul class="checklist monitor" style="font-size:9px;">{"".join(f"<li>{esc(x)}</li>" for x in trace["rebuild_limitations"])}</ul>'''

    return f'<div class="page">{top_bar()}{page_label("page_7")}{drs_html}{varlog}{sent_html}{trace_html}{footer(7)}</div>'

def build_page_8():
    p = D["page_8"]
    gf = p["go_forward_readiness_status"]
    cdr = p["critical_data_requests"]["requests"]
    kc = p["kill_criteria_and_flip_conditions"]
    plan = p["recommended_next_7_day_plan"]

    # site_and_operational_verification — page_8 section
    sovp = ""
    if "site_and_operational_verification_plan" in p:
        sv = p["site_and_operational_verification_plan"]
        sovp = f'''{section_tag("Site & Operational Verification")}
        <table><tr><th>Check</th><th>Reason</th><th>Evidence</th><th>Pass Condition</th></tr>
        {"".join(f'<tr><td>{esc(c["check_name"])}</td><td>{esc(c["reason"])}</td><td style="font-size:9px;">{esc(c["evidence"])}</td><td style="font-size:9px;">{esc(c["pass_condition"])}</td></tr>' for c in sv.get("site_checks",[]) + sv.get("operational_checks",[]))}
        </table>'''

    gf_html = f'''{section_tag("Go-Forward Readiness")}
    <div class="card" style="border-left:3px solid var(--orange); margin-bottom:12px;">
      <div style="display:flex; justify-content:space-between; align-items:center;"><div><div class="card-label">Readiness</div><div style="font-size:16px; font-weight:800; color:var(--orange);">{gf["readiness_label"].upper()}</div></div>{pill(f'{len(gf["blocking_dependencies"])} blocking',"orange")}</div>
      <div style="margin-top:6px; font-size:10px; color:var(--slate); line-height:1.6;">{esc(gf["summary_statement"])}</div>
      <div style="margin-top:6px;"><strong style="color:var(--red); font-size:9px;">Blocking:</strong> <span style="font-size:9px; color:var(--slate);">{" · ".join(gf["blocking_dependencies"])}</span></div>
      <div style="margin-top:3px;"><strong style="color:var(--slate); font-size:9px;">Non-blocking:</strong> <span style="font-size:9px; color:var(--text-dim);">{" · ".join(gf["nonblocking_dependencies"])}</span></div>
    </div>'''

    cdr_html = f'''{section_tag("Critical Data Requests")}
    <table><tr><th>Request</th><th>From</th><th>Why Needed</th><th>Link</th></tr>
    {"".join(f'<tr><td>{esc(r["request_name"])}</td><td style="font-size:9px;">{esc(r["requested_from"])}</td><td style="font-size:9px;">{esc(r["why_needed"])}</td><td style="font-size:9px;">{esc(r["report_link"])}</td></tr>' for r in cdr)}
    </table>'''

    # underwriting_focus_areas
    ufa = ""
    if "underwriting_focus_areas" in p:
        ufa_items = p["underwriting_focus_areas"].get("focus_areas",[])
        ufa = f'''{section_tag("Underwriting Focus Areas")}
        <table><tr><th>Focus</th><th>Why</th><th>Evidence</th><th>Modeling</th></tr>
        {"".join(f'<tr><td>{esc(f["focus_area"])}</td><td style="font-size:9px;">{esc(f["why_it_matters"])}</td><td style="font-size:9px;">{esc(f["evidence"])}</td><td style="font-size:9px;">{esc(f["modeling_implication"])}</td></tr>' for f in ufa_items)}
        </table>'''

    kc_html = f'''{section_tag("Kill Criteria & Strengthening Conditions")}
    <div class="g2">
      <div><div style="font-size:9px; font-weight:700; color:var(--red); text-transform:uppercase; letter-spacing:2px; margin-bottom:4px;">Kill Conditions</div><ul class="checklist must">{"".join(f"<li>{esc(x)}</li>" for x in kc["kill_conditions"])}</ul></div>
      <div><div style="font-size:9px; font-weight:700; color:var(--green); text-transform:uppercase; letter-spacing:2px; margin-bottom:4px;">Strengthening Conditions</div><ul class="checklist monitor">{"".join(f"<li>{esc(x)}</li>" for x in kc["strengthening_conditions"])}</ul></div>
    </div>'''

    plan_html = f'''{section_tag("Next 7-Day Action Plan")}
    <div class="g2" style="gap:10px;">
      <div class="card" style="border-top:2px solid var(--red);"><div style="font-size:9px; font-weight:700; color:var(--red); text-transform:uppercase; margin-bottom:4px;">Days 1–2</div><ul class="checklist must" style="font-size:9px;">{"".join(f"<li>{esc(x)}</li>" for x in plan["days_1_to_2"])}</ul></div>
      <div class="card" style="border-top:2px solid var(--orange);"><div style="font-size:9px; font-weight:700; color:var(--orange); text-transform:uppercase; margin-bottom:4px;">Days 3–5</div><ul class="checklist should" style="font-size:9px;">{"".join(f"<li>{esc(x)}</li>" for x in plan["days_3_to_5"])}</ul></div>
    </div>
    <div class="card" style="border-top:2px solid var(--green); margin-top:8px;"><div style="font-size:9px; font-weight:700; color:var(--green); text-transform:uppercase; margin-bottom:4px;">Days 6–7</div><ul class="checklist monitor" style="font-size:9px;">{"".join(f"<li>{esc(x)}</li>" for x in plan["days_6_to_7"])}</ul></div>'''

    return f'<div class="page">{top_bar()}{page_label("page_8")}{gf_html}{cdr_html}{sovp}{ufa}{kc_html}{plan_html}{footer(8)}</div>'

# ──── CSS ────
CSS = '''
:root{--navy:#0a1628;--navy-light:#132038;--navy-mid:#1a2d4a;--gold:#c9a84c;--gold-light:#e8d48b;--gold-dim:rgba(201,168,76,0.15);--green:#34d399;--green-bg:rgba(52,211,153,0.08);--red:#f87171;--red-bg:rgba(248,113,113,0.08);--orange:#fb923c;--orange-bg:rgba(251,146,60,0.08);--slate:#94a3b8;--slate-light:#cbd5e1;--white:#f8fafc;--text:#e2e8f0;--text-dim:#64748b;--border:rgba(148,163,184,0.12)}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',system-ui,sans-serif;background:var(--navy);color:var(--text);font-size:10px;line-height:1.5;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.page{width:8.5in;min-height:11in;padding:0.4in 0.45in;page-break-after:always;position:relative;background:var(--navy)}
@media print{.page{padding:0.35in 0.4in}body{margin:0}}
.top-bar{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:8px;margin-bottom:14px}
.top-bar .brand{font-size:9px;letter-spacing:4px;text-transform:uppercase;color:var(--gold);font-weight:700}
.top-bar .meta{font-size:8px;color:var(--slate);letter-spacing:1px;text-transform:uppercase}
.section-tag{display:block;width:fit-content;font-size:8px;letter-spacing:3px;text-transform:uppercase;color:var(--gold);font-weight:700;margin-bottom:6px;margin-top:12px;padding:3px 0;border-bottom:2px solid var(--gold)}
.page-label{font-size:9px;letter-spacing:3px;text-transform:uppercase;color:var(--gold);font-weight:600;background:var(--gold-dim);padding:5px 12px;display:block;width:fit-content;margin-bottom:12px;border-left:3px solid var(--gold)}
.card-row{display:grid;gap:8px;margin-bottom:12px}.card-row.c4{grid-template-columns:repeat(4,1fr)}.card-row.c3{grid-template-columns:repeat(3,1fr)}.card-row.c2{grid-template-columns:repeat(2,1fr)}
.card{background:var(--navy-light);border:1px solid var(--border);border-radius:6px;padding:10px 12px}
.card .card-label{font-size:7.5px;letter-spacing:2px;text-transform:uppercase;color:var(--slate);font-weight:600;margin-bottom:3px}
.card .card-value{font-size:18px;font-weight:800;color:var(--white);line-height:1.2}
.card .card-value.gold{color:var(--gold)}.card .card-value.green{color:var(--green)}.card .card-value.red{color:var(--red)}
.card .card-sub{font-size:8px;color:var(--slate);margin-top:2px}
table{width:100%;border-collapse:collapse;margin-bottom:10px}
th{background:var(--navy-mid);color:var(--gold);font-size:7.5px;letter-spacing:2px;text-transform:uppercase;font-weight:700;padding:6px 8px;text-align:left;border-bottom:2px solid var(--gold-dim)}
td{padding:5px 8px;font-size:9.5px;color:var(--text);border-bottom:1px solid var(--border);vertical-align:top}
tr:last-child td{border-bottom:none}
.alert{padding:8px 12px;border-radius:5px;font-size:9.5px;margin-bottom:12px;display:flex;align-items:flex-start;gap:6px}
.alert.red{background:var(--red-bg);border-left:3px solid var(--red);color:var(--red)}
.alert.orange{background:var(--orange-bg);border-left:3px solid var(--orange);color:var(--orange)}
.alert.green{background:var(--green-bg);border-left:3px solid var(--green);color:var(--green)}
.alert .alert-icon{font-size:12px;flex-shrink:0}
.verdict-row{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px}
.verdict-box{background:linear-gradient(135deg,var(--navy-light),var(--navy-mid));border:1px solid var(--gold-dim);border-radius:8px;padding:14px 16px;position:relative;overflow:hidden}
.verdict-box::before{content:'';position:absolute;top:0;left:0;width:4px;height:100%;background:var(--gold)}
.verdict-box .vb-label{font-size:7.5px;letter-spacing:3px;text-transform:uppercase;color:var(--gold);font-weight:700;margin-bottom:4px}
.verdict-box .vb-value{font-size:20px;font-weight:900;letter-spacing:1px;line-height:1.2}
.verdict-box .vb-sub{font-size:8.5px;color:var(--slate);margin-top:4px;font-style:italic}
.narrative{background:var(--navy-light);border:1px solid var(--border);border-radius:6px;padding:12px 14px;margin-bottom:12px;font-size:10px;line-height:1.65;color:var(--slate-light);text-align:justify}
.reason{display:flex;gap:10px;padding:6px 0;border-bottom:1px solid var(--border)}
.reason:last-child{border-bottom:none}
.reason .r-num{width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:11px;flex-shrink:0}
.reason .r-num.support{background:var(--green-bg);color:var(--green);border:1px solid rgba(52,211,153,0.3)}
.reason .r-num.risk{background:var(--red-bg);color:var(--red);border:1px solid rgba(248,113,113,0.3)}
.reason .r-body{flex:1}.reason .r-title{font-weight:700;font-size:10px;color:var(--white);margin-bottom:1px}
.reason .r-detail{font-size:9px;color:var(--slate)}
.pill{display:inline-block;padding:1px 6px;border-radius:10px;font-size:7.5px;font-weight:700;letter-spacing:1px;text-transform:uppercase}
.pill.green{background:var(--green-bg);color:var(--green);border:1px solid rgba(52,211,153,0.3)}
.pill.red{background:var(--red-bg);color:var(--red);border:1px solid rgba(248,113,113,0.3)}
.pill.orange{background:var(--orange-bg);color:var(--orange);border:1px solid rgba(251,146,60,0.3)}
.pill.gold{background:var(--gold-dim);color:var(--gold);border:1px solid rgba(201,168,76,0.3)}
.pill.slate{background:rgba(148,163,184,0.1);color:var(--slate);border:1px solid rgba(148,163,184,0.2)}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:10px}
.flag-row{background:var(--navy-light);border:1px solid var(--border);border-radius:6px;padding:10px 12px;margin-bottom:8px}
.flag-row .flag-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:3px}
.flag-row .flag-name{font-weight:700;font-size:10px;color:var(--white)}
.flag-row .flag-detail{font-size:9px;color:var(--slate);line-height:1.5}
.checklist{list-style:none}.checklist li{padding:3px 0;font-size:9.5px;display:flex;align-items:flex-start;gap:5px}
.checklist.must li::before{content:'⬤';color:var(--red);font-size:6px;margin-top:4px;flex-shrink:0}
.checklist.should li::before{content:'◉';color:var(--orange);font-size:6px;margin-top:4px;flex-shrink:0}
.checklist.monitor li::before{content:'○';color:var(--slate);font-size:6px;margin-top:4px;flex-shrink:0}
.footer{position:absolute;bottom:0.25in;left:0.45in;right:0.45in;display:flex;justify-content:space-between;font-size:7px;color:var(--text-dim);letter-spacing:1px;text-transform:uppercase;border-top:1px solid var(--border);padding-top:5px}
'''

# ──── ASSEMBLE ────
html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>PIR — {esc(prop_name)} — {esc(city)}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
{build_page_1()}
{build_page_2()}
{build_page_3()}
{build_page_4()}
{build_page_5()}
{build_page_6()}
{build_page_7()}
{build_page_8()}
</body></html>'''

with open(OUT_HTML, "w") as f:
    f.write(html)
print(f"HTML saved: {OUT_HTML}")

# PDF via Puppeteer
js = f'''const puppeteer = require('puppeteer');
(async () => {{
  const b = await puppeteer.launch();
  const p = await b.newPage();
  await p.goto('file://{OUT_HTML}', {{waitUntil: 'networkidle0'}});
  await p.pdf({{ path: '{OUT_PDF}', format: 'Letter', printBackground: true, margin: {{ top:'0px',right:'0px',bottom:'0px',left:'0px' }} }});
  await b.close();
  console.log('PDF: {OUT_PDF}');
}})();'''
js_path = os.path.join(os.path.dirname(__file__), "_print.js")
with open(js_path, "w") as f: f.write(js)
r = subprocess.run(["/opt/homebrew/bin/node", js_path], capture_output=True, text=True, cwd=os.path.dirname(__file__))
print(r.stdout.strip())
if r.stderr: print("STDERR:", r.stderr[:300])
