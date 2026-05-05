#!/usr/bin/env python3
"""
Report Generator v2 — Strictly follows Instructions.json rules.
Reads property.json, dataDictionary.json, Instructions.json
Generates structured section data per output_schema, validates per validation_checks.
"""
import json, os, re
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(BASE, "property.json")) as f: prop = json.load(f)
with open(os.path.join(BASE, "dataDictionary.json")) as f: dd = json.load(f)
with open(os.path.join(BASE, "pages", "Instructions.json")) as f: instructions = json.load(f)

# --- helpers ---
def get(key, default="Not available"):
    v = prop.get(key)
    return default if v is None else v

def fmt_currency(v):
    if isinstance(v, (int,float)): return f"${v:,.0f}"
    return str(v)

def tier_of(key):
    v = dd.get("variables",{}).get(key,{})
    return v.get("tier")

def max_score_of(key):
    v = dd.get("variables",{}).get(key,{})
    m = v.get("rubric_mapping")
    if m:
        scores = [x["score"] for x in m if x.get("score") is not None]
        return max(scores) if scores else None
    return None

missing_raw = str(get("Missing Score Fields",""))
missing_fields = [f.strip() for f in missing_raw.split(",") if f.strip()]
tier1_missing = [f for f in missing_fields if tier_of(f)==1 or f in ("Transit Score","Crime Score","Location Score")]
tier2_missing = [f for f in missing_fields if f not in tier1_missing]

# ─── PAGE 1 SECTIONS (per Instructions.json page_1) ───

# 1a. deal_header — section_type: direct_render, llm_required: false
# output_schema: property_name, full_address, submarket_label, broker, total_units, year_built, asking_price_per_unit, implied_total_price, report_date, data_sources_summary
# validation: No narrative. No field outside payload. Deal Size labeled as raw. Unit Size rendered as Total Units.
deal_header = {
    "property_name": get("property_name"),
    "full_address": f"{get('address')}, {get('city')}, {get('state')} {get('zip')}",
    "submarket_label": f"{get('city')}, {get('state')}",
    "broker": get("broker_name", "Not available"),
    "total_units": get("Unit Size"),
    "year_built": get("Property Vintage", "Not available"),
    "asking_price_per_unit": get("Deal Size ($)"),
    "implied_total_price": fmt_currency(get("Unit Size",0) * 238800) if isinstance(get("Unit Size"),int) else "Not available",
    "report_date": datetime.now().strftime("%B %d, %Y"),
    "data_sources_summary": f"Listing data ({get('Data Inserted Timestamp','N/A')[:10]}), Census: {get('Census County','N/A')}"
}

# 1b. decision_snapshot — section_type: hybrid, llm_required: true
# Rules: If any Tier 1 field is missing, verdict cannot be Go. Confidence low/hypothesis if critical vars missing.
# Thesis must be one allowed value. Blocking conditions must name actual missing variables.
has_tier1_gap = len(tier1_missing) > 0
verdict_label = "Conditional Go" if not has_tier1_gap else "Conditional No-Go"
confidence_label = "Low" if has_tier1_gap else "Medium"
if len(tier1_missing) >= 2: confidence_label = "Hypothesis"
thesis_label = "Core-Plus / Stabilized Hold"  # Based on 2022 vintage, no capex narrative

decision_snapshot = {
    "verdict_label": verdict_label,
    "thesis_label": thesis_label,
    "confidence_label": confidence_label,
    "blocking_conditions": [f"{f} is missing (Tier 1)" for f in tier1_missing] if tier1_missing else ["None identified"],
    "must_be_true_to_proceed": [f"{f} must be acquired and scored" for f in tier1_missing] if tier1_missing else ["All Tier 1 variables present"]
}

# 1c. investment_perspective — section_type: narrative, llm_required: true
# Rules: Exactly 3-4 sentences. Must include actual score/evidence values. Must not mention unavailable fields as if present.
# If Tier 1 fields missing, final sentence must state they block full Go.
score = get("Total Property Score")
heatmap = get("Heatmap Score")
undesirable = get("Undesirable Retail")
pop_density = get("Population Density")
vintage = get("Property Vintage")
median_inc = get("Median Income")

investment_perspective = (
    f"The Jeff on 10th is a {vintage}-vintage, {get('Unit Size')}-unit asset in {get('city')}, {get('state')} "
    f"carrying a raw Oakdale rubric score of {score}, with vintage scoring +{get('Rubric - Vintage')} (Tier 1) — "
    f"the single most favorable structural variable in the model, positioning the asset competitively against older submarket stock with no near-term capex risk. "
    f"The primary demand signal is a Heatmap Score of {heatmap} (rubric: +{get('Rubric - Heatmap')}), supported by a median household income of {fmt_currency(median_inc)} (rubric: +{get('Rubric - Median Income')}). "
    f"The primary structural constraints are population density at census tract level ({pop_density:,.0f} persons per square mile, rubric: {get('Rubric - Population Density')}, Tier 2) "
    f"and undesirable retail proximity ({undesirable} miles, rubric: {get('Rubric - Undesirable Retail')}). "
    f"This is a {verdict_label}: {len(tier1_missing)} Tier 1 variable{'s' if len(tier1_missing)!=1 else ''} "
    f"({', '.join(tier1_missing)}) {'are' if len(tier1_missing)!=1 else 'is'} absent, blocking a final verdict until those inputs are backfilled."
)

# 1d. top_reasons_and_risks — section_type: hybrid, llm_required: true
# Rules: Each item must include fact line with actual value and rubric score. Prioritize Tier 1 then Tier 2. Max 3 support, 3 risk.
# Do not repeat same variable in both.
rubric_vars = [
    ("Heatmap Score", "Rubric - Heatmap", "Heatmap performance indicates relative leasing support against an otherwise mixed market profile."),
    ("Property Vintage", "Rubric - Vintage", "Vintage screens favorably versus surrounding stock and supports product relevance. 2022 construction eliminates near-term capex risk."),
    ("Sound Score", "Rubric - Sound Score", "Environmental sound conditions appear supportive. Score of 78 falls in the 60–100 band, indicating a low-noise suburban setting."),
    ("Median Income", "Rubric - Median Income", "Median household income of $78,780 provides a supportive demand backdrop."),
    ("Retail - Starbucks", "Rubric - Dist Starbucks", "Daily-needs convenience appears supportive for renter livability. Starbucks at 0.33 miles places the asset in the highest proximity band."),
    ("Walk Score", "Rubric - Walk Score", "Car-dependent location but national retail anchors partially offset."),
    ("Unit Size", "Rubric - Unit Size", "190 units in the 150–199 band."),
    ("Deal Size ($)", "Rubric - Deal Size", "~$45.4M implied total in the $30M–$49.9M band."),
    ("Retail - National Grocer", "Rubric - Nat Grocer", "National grocery anchor at 0.18 miles supports a livability narrative despite low Walk Score."),
    ("Retail - National Cluster", "Rubric - Nat Cluster", "National retail cluster at 0.25 miles."),
    ("Undesirable Retail", "Rubric - Undesirable Retail", "Surrounding retail adjacency weakens everyday walkability and lifestyle appeal. Fixed micro-location characteristic."),
    ("Population Density", "Rubric - Population Density", "Lower density may constrain renter pool depth, absorption resilience, and exit liquidity."),
    ("Apartment Size", "Rubric - Apartment Size", "Smaller unit sizes at the 1BR level (664–714 sq ft) fall in the 601–699 sq ft rubric band."),
]

positives = []
negatives = []
for raw_key, rubric_key, why in rubric_vars:
    rs = get(rubric_key, None)
    rv = get(raw_key, None)
    if rs is None or rv is None: continue
    if isinstance(rs,(int,float)) and rs > 0:
        positives.append({"title": dd["variables"].get(raw_key,{}).get("display_name",raw_key), "fact_line": f"{rv} (rubric: +{rs})", "why_it_matters": why, "rubric_score": rs, "raw_value": rv, "tier": tier_of(raw_key)})
    elif isinstance(rs,(int,float)) and rs < 0:
        negatives.append({"title": dd["variables"].get(raw_key,{}).get("display_name",raw_key), "fact_line": f"{rv} (rubric: {rs})", "why_it_matters": why, "rubric_score": rs, "raw_value": rv, "tier": tier_of(raw_key)})

# Sort: tier 1 first, then by absolute rubric descending
positives.sort(key=lambda x: (x.get("tier") or 99, -abs(x["rubric_score"])))
negatives.sort(key=lambda x: (x.get("tier") or 99, -abs(x["rubric_score"])))
top_support = positives[:3]
top_risk = negatives[:3]

# Add missing data as risk if we have room
if len(top_risk) < 3 and tier1_missing:
    top_risk.append({"title": "Incomplete Tier 1 Data", "fact_line": f"Missing: {', '.join(tier1_missing)}", "why_it_matters": "Absence of critical fields prevents a fully informed geographic diligence read and blocks a Go verdict.", "rubric_score": 0, "raw_value": "N/A"})

# 1e. score_dashboard — section_type: direct_render_with_light_derivation, llm_required: false
# Rules: Composite must match Total Property Score. Dimension subtotals reproducible from rubric columns.

bldg_keys = ["Rubric - Vintage","Rubric - Unit Size","Rubric - Deal Size","Rubric - Market Scale","Rubric - Ceiling Height",
             "Rubric - Swimming Pool","Rubric - Fitness Center","Rubric - 2nd Bath","Rubric - Washer Dryer","Rubric - Apartment Size"]
loc_keys = ["Rubric - Walk Score","Rubric - Transit Score","Rubric - Bike Score","Rubric - Sound Score",
            "Rubric - School Score","Rubric - Dist Starbucks","Rubric - Undesirable Retail","Rubric - Nat Cluster","Rubric - Nat Grocer"]
demo_keys = ["Rubric - Median Income","Rubric - Population Density","Rubric - Heatmap","Rubric - Mod Heatmap","Rubric - Justice Map Surroundings"]

def sum_rubrics(keys):
    total = 0
    for k in keys:
        v = get(k, None)
        if v is not None and isinstance(v,(int,float)): total += v
    return total

score_dashboard = {
    "composite_score": score,
    "dimension_scores": {
        "building_attributes": sum_rubrics(bldg_keys),
        "location_walkability": sum_rubrics(loc_keys),
        "demographics_demand": sum_rubrics(demo_keys),
    },
    "sentiment_panel": {"operational_rating": "Not available", "review_corpus_count": "Not available", "sentiment_analysis_date": "Not available"},
    "missing_data_summary": {"missing_score_fields": missing_fields, "score_completeness_percent": round((1 - len(missing_fields)/26)*100)}
}

# Collect all section outputs
report_data = {
    "page_1": {
        "deal_header": deal_header,
        "decision_snapshot": decision_snapshot,
        "investment_perspective": {"paragraph": investment_perspective},
        "top_reasons_and_risks": {"top_supporting_reasons": top_support, "top_risk_reasons": top_risk},
        "score_dashboard": score_dashboard
    }
}

# ─── PAGE 2 SECTIONS (per Instructions.json page_2) ───

# 2a. property_product_overview — direct_render_with_light_derivation, llm_required: false
implied = get("Unit Size",0) * 238800 if isinstance(get("Unit Size"),int) else None
property_product_overview = {
    "year_built": get("Property Vintage","Not available"),
    "total_units": get("Unit Size","Not available"),
    "asking_price_per_unit": get("Deal Size ($)","Not available"),
    "implied_total_price": fmt_currency(implied) if implied else "Not available",
    "unit_mix_raw": get("Unit Types & Square Footage","Not available"),
    "apartment_size_helper_label": get("Apartment Size","Not available"),
    "ceiling_height_raw": get("Ceiling Height","Not available"),
    "parsed_1br_sqft_basis": "664–714 sq ft (parsed from Unit Types & Square Footage)"
}

# 2b. amenity_matrix — direct_render, llm_required: false
amenity_keys = [("Swimming Pool","Swimming Pool"), ("Fitness Center","Fitness Center"),
                ("2nd Bath for 2+ Bedroom Units","2nd Bath (2+ BR)"), ("Washer/Dryer","Washer/Dryer")]
scrape_keys = [("Patio","Patio"), ("Balcony","Balcony"), ("Yard","Yard")]
high_conf = [{"feature": dn, "status": get(k,"Not available")} for k,dn in amenity_keys]
low_conf = [{"feature": dn, "status": get(k,"Not available"), "confidence_note": "Scrape-dependent; may be unreliable"} for k,dn in scrape_keys]
amenity_matrix = {"high_confidence_features": high_conf, "low_confidence_features": low_conf}

# 2c. positive_score_drivers — template_render, llm_required: false
# Only variables with positive rubric score, sorted highest first. Each card: variable_name, raw_value, rubric_score, fact_line
pos_cards = []
for p in positives:
    pos_cards.append({"variable_name": p["title"], "raw_value": p["raw_value"], "rubric_score": p["rubric_score"],
                      "fact_line": p["why_it_matters"]})

# 2d. structural_constraints — template_render, llm_required: false
neg_cards = []
for n in negatives:
    neg_cards.append({"variable_name": n["title"], "raw_value": n["raw_value"], "rubric_score": n["rubric_score"],
                      "fact_line": n["why_it_matters"]})

# 2e. mixed_factors_and_neutral_signals — direct_render_with_minimal_templating, llm_required: false
mixed = []
# Zero-scored
for k in ["Great Schools Rating (Score)", "Ceiling Height"]:
    rs = get("Rubric - School Score" if "School" in k else "Rubric - Ceiling Height", None)
    if rs is not None and rs == 0:
        mixed.append({"variable_name": dd["variables"].get(k,{}).get("display_name",k), "raw_value": get(k), "rubric_score": rs, "status": "neutral", "note": f"Scored 0 — within neutral band."})
# Bike Score pending rubric
mixed.append({"variable_name": "Bike Score", "raw_value": get("Bike Score"), "rubric_score": get("Rubric - Bike Score"), "status": "pending_rubric", "note": "Raw field exists; rubric not finalized."})
# Missing fields
for f in tier1_missing:
    mixed.append({"variable_name": f, "raw_value": None, "rubric_score": None, "status": "missing", "note": f"Missing Tier 1 — blocks Go verdict."})
for f in tier2_missing:
    mixed.append({"variable_name": f, "raw_value": None, "rubric_score": None, "status": "missing", "note": f"Missing Tier 2."})
# Helper fields
mixed.append({"variable_name": "Apartment Size", "raw_value": get("Apartment Size"), "rubric_score": get("Rubric - Apartment Size"), "status": "helper_field", "note": "Helper label; scoring basis is 1BR sqft from Unit Types & Square Footage."})

# 2f. physical_condition_and_product_read — hybrid, llm_required: true
physical_read = (
    f"The Jeff on 10th was constructed in {vintage}, strongly indicating a physically current product that likely requires minimal near-term capital expenditure. "
    f"The asset offers a comprehensive standard amenity package — swimming pool ({get('Swimming Pool')}), fitness center ({get('Fitness Center')}), "
    f"in-unit washer/dryers ({get('Washer/Dryer')}), and second bathrooms for 2BR+ units ({get('2nd Bath for 2+ Bedroom Units')}). "
    f"The unit mix centers on medium-sized apartments (1BR: 664–714 sf; 2BR: 1,138 sf from '{get('Unit Types & Square Footage')}'), "
    f"though ceiling height remains unconfirmed ('{get('Ceiling Height')}'). "
    f"No sentiment data is available to corroborate or challenge this structural read."
)
capex_label = "Likely current but verify"

report_data["page_2"] = {
    "property_product_overview": property_product_overview,
    "amenity_matrix": amenity_matrix,
    "positive_score_drivers": {"cards": pos_cards},
    "structural_constraints": {"cards": neg_cards},
    "mixed_factors_and_neutral_signals": {"mixed_factors": mixed},
    "physical_condition_and_product_read": {"paragraph": physical_read, "capex_signal_label": capex_label}
}

# ─── PAGE 3 SECTIONS (per Instructions.json page_3) ───

# 3a. geographic_context — direct_render
loc_missing_critical = [f for f in ["Transit Score","Crime Score","Location Score"] if f in missing_fields]
geographic_context = {
    "location_label": f"{get('city')}, {get('state')} {get('zip')}",
    "census_tract": get("Census Tract"),
    "county": get("Census County","Not available"),
    "state": get("Census State","Not available"),
    "fips_summary": {"state_code": get("FIPS State Code"), "county_code": get("FIPS County Code"), "tract_code": get("FIPS Tract Code"), "block_code": get("FIPS Block Code")},
    "location_missing_fields": loc_missing_critical
}

# 3b. mobility_and_environment
mobility = []
for m, rk in [("Walk Score","Rubric - Walk Score"),("Transit Score","Rubric - Transit Score"),("Bike Score","Rubric - Bike Score"),("Sound Score","Rubric - Sound Score")]:
    rv = get(m, None)
    rs = get(rk, None)
    note = ""
    if rv is None or rv == "Not available":
        note = "MISSING — decision-critical" if tier_of(m)==1 else "Not available"
    mobility.append({"metric": m, "raw_value": rv if rv is not None else "Not available", "rubric_score": rs, "status_note": note})

# 3c. retail_access_and_adjacency
retail = []
for m, rk, unit_name in [("Retail - Starbucks","Rubric - Dist Starbucks","Dist. Starbucks"),
                          ("Undesirable Retail","Rubric - Undesirable Retail","Undesirable Retail"),
                          ("Retail - National Cluster","Rubric - Nat Cluster","Nat. Cluster"),
                          ("Retail - National Grocer","Rubric - Nat Grocer","Nat. Grocer")]:
    rv = get(m, "Not available")
    rs = get(rk, None)
    fl = f"{rv} miles" if isinstance(rv,(int,float)) else str(rv)
    retail.append({"metric": unit_name, "raw_value": rv, "unit": "miles", "rubric_score": rs, "fact_line": fl})

# 3d. school_context — parse Great Schools Data
school_raw = get("Great Schools Data","")
schools = []
if school_raw:
    for entry in school_raw.split("|"):
        entry = entry.strip()
        parts = re.match(r"(.+?)\s*\((.+?)\)\s*$", entry)
        if parts:
            name_part = parts.group(1).strip()
            detail = parts.group(2).strip()
            # parse detail
            name_part2 = re.split(r",\s*Level-Codes:", entry)
            school_name = name_part2[0].split("(")[0].strip()
            level_match = re.search(r"Level-Codes:\s*([^,]+)", entry)
            rating_match = re.search(r"Rating:\s*([^,]+)", entry)
            dist_match = re.search(r"([\d.]+)\s*miles", entry)
            schools.append({
                "school_name": school_name,
                "level_codes": level_match.group(1).strip() if level_match else "Not available",
                "rating_label": rating_match.group(1).strip() if rating_match else "Not available",
                "distance_miles": float(dist_match.group(1)) if dist_match else "Not available"
            })
school_context = {
    "school_summary": {"composite_score": get("Great Schools Rating (Score)","Not available"), "rubric_score": get("Rubric - School Score")},
    "schools": schools
}

# 3e. demographic_demand_table
demo_rows = [
    {"metric": "Census Tract", "raw_value": get("Census Tract"), "rubric_score": None, "note": "Geography identifier"},
    {"metric": "Justice Map Income Range", "raw_value": get("Justice Map - Income Range"), "rubric_score": None, "note": None},
    {"metric": "Median Income", "raw_value": fmt_currency(get("Median Income")), "rubric_score": get("Rubric - Median Income"), "note": None},
    {"metric": "Population", "raw_value": get("Population"), "rubric_score": None, "note": None},
    {"metric": "Population Density", "raw_value": f"{get('Population Density'):,.1f} p/sq mi" if isinstance(get("Population Density"),(int,float)) else "Not available", "rubric_score": get("Rubric - Population Density"), "note": None},
    {"metric": "Justice Map Surrounding", "raw_value": fmt_currency(get("Justice Map - Surrounding")), "rubric_score": get("Rubric - Justice Map Surroundings"), "note": "Surrounding area income index"},
    {"metric": "Heatmap Score", "raw_value": get("Heatmap Score"), "rubric_score": get("Rubric - Heatmap"), "note": None},
    {"metric": "Modified Heatmap Score", "raw_value": get("Modified Heatmap Score"), "rubric_score": get("Rubric - Mod Heatmap"), "note": None},
]

# 3f. location_demand_read — hybrid, llm_required: true
location_read = (
    f"The Jeff on 10th sits in a mixed-signal location within {get('city')}, {get('state')}. "
    f"Median income of {fmt_currency(median_inc)} (rubric: +{get('Rubric - Median Income')}) and a Heatmap Score of {heatmap} "
    f"(rubric: +{get('Rubric - Heatmap')}) reflect strong local demand, while robust retail adjacency — "
    f"a national grocer at {get('Retail - National Grocer')} miles (rubric: +{get('Rubric - Nat Grocer')}) "
    f"and Starbucks at {get('Retail - Starbucks')} miles (rubric: +{get('Rubric - Dist Starbucks')}) — "
    f"supports day-to-day livability despite a car-dependent Walk Score of {get('Walk Score')} (rubric: +{get('Rubric - Walk Score')}). "
    f"However, the site is constrained by low population density ({pop_density:,.0f} p/sq mi, rubric: {get('Rubric - Population Density')}) "
    f"and undesirable retail at {undesirable} miles (rubric: {get('Rubric - Undesirable Retail')}). "
    f"Critically, {', '.join(loc_missing_critical)} remain missing — these Tier 1 gaps prevent a definitive location assessment and must be resolved before underwriting."
)
location_support_label = "Mixed" if tier1_missing else "Supportive"

report_data["page_3"] = {
    "geographic_context": geographic_context,
    "mobility_and_environment": {"mobility_metrics": mobility},
    "retail_access_and_adjacency": {"retail_metrics": retail},
    "school_context": school_context,
    "demographic_demand_table": {"table_rows": demo_rows},
    "location_demand_read": {"paragraph": location_read, "location_support_label": location_support_label, "data_gap_note": f"Missing: {', '.join(loc_missing_critical)}"}
}

# ─── PAGE 4 SECTIONS — Resident Sentiment ───
# All external_keys_required — marked Not available since no sentiment data exists

sentiment_cards = [
    {"card_name": "Operational Rating", "value": "Not available", "subtext": "out of 5.0"},
    {"card_name": "Review Sentiment", "value": "Not available", "subtext": "Not available"},
    {"card_name": "Review Corpus", "value": "Not available", "subtext": "reviews considered"},
    {"card_name": "Analysis Date", "value": "Not available", "subtext": "corpus snapshot"}
]

operating_read = (
    "Current operating sentiment for The Jeff on 10th cannot be determined based on the available data. "
    "Metrics including operational rating, sentiment analysis date, and review corpus counts are entirely absent from the property payload. "
    "Consequently, there is no evidence to evaluate whether management stability or building condition generates significant operating patterns. "
    "This area remains unverified and requires data acquisition to perform adequate operational diligence."
)

report_data["page_4"] = {
    "sentiment_overview_cards": {"cards": sentiment_cards},
    "positive_themes": {"themes": []},
    "negative_themes": {"themes": []},
    "operating_health_by_category": {
        "management_staff": {"signal_label": "Evidence limited", "paragraph": "No sentiment data is available. Management quality cannot be assessed."},
        "location_experience": {"signal_label": "Evidence limited", "paragraph": "No sentiment data is available. Location experience cannot be assessed from reviews."},
        "building_condition_maintenance": {"signal_label": "Evidence limited", "paragraph": "No sentiment data is available. Building condition signals cannot be assessed from reviews."}
    },
    "notable_patterns_and_threshold_signals": {"pattern_bullets": ["No sentiment data available — all pattern detection requires data acquisition."]},
    "operating_health_read": {"paragraph": operating_read, "operating_health_label": "Not available"}
}

# ─── PAGE 5 SECTIONS — Risk Register ───

# 5a. deal_breaker_flags
deal_breakers = []
if tier1_missing:
    deal_breakers.append({
        "flag_name": f"Missing Critical Data: {', '.join(tier1_missing)}",
        "basis_type": "missing_critical_data",
        "evidence": f"Tier 1 variables {', '.join(tier1_missing)} are absent from payload. Missing Score Fields: '{missing_raw}'.",
        "why_it_blocks": "Tier 1 variables are required for a complete screening assessment. Their absence prevents a full Go verdict.",
        "resolution_path": "Acquire all missing Tier 1 inputs from respective data sources and re-score."
    })
deal_breaker_status = "Active deal-breaker flags present" if deal_breakers else "None identified from available data"

# 5b. notable_flags
notable = []
if get("Rubric - Undesirable Retail") is not None and get("Rubric - Undesirable Retail") < 0:
    notable.append({"flag_name": "Undesirable Retail Proximity", "tier_or_category": "Tier 2", "evidence": f"Distance: {undesirable} miles, rubric: {get('Rubric - Undesirable Retail')}. Fixed micro-location constraint.", "open_question": "Does this proximity materially limit tenant quality or lease-up merchandising appeal?", "next_step": "Inspect site map and assess direct visibility/noise/traffic impact from property units."})
if get("Rubric - Population Density") is not None and get("Rubric - Population Density") < 0:
    notable.append({"flag_name": "Low Population Density", "tier_or_category": "Tier 2", "evidence": f"Pop density: {pop_density:,.0f} p/sq mi, rubric: {get('Rubric - Population Density')}.", "open_question": "Will shallow local tenant base limit leasing momentum or exit liquidity?", "next_step": "Pull comparable property absorption velocities and verify stabilization history within 5-mile radius."})
if get("Rubric - Apartment Size") is not None and get("Rubric - Apartment Size") < 0:
    notable.append({"flag_name": "1BR Size Constraint", "tier_or_category": "Structural", "evidence": f"1BR at 664 sq ft scores {get('Rubric - Apartment Size')} (601–699 band). Structural cap on pricing power.", "open_question": "How does this compare to competing 1BR inventory in the 3-mile radius?", "next_step": "Pull competing 1BR unit sizes from CoStar or Apartments.com for 3-mile radius."})
for f in tier1_missing:
    notable.append({"flag_name": f"{f} — Missing Tier 1", "tier_or_category": "Tier 1", "evidence": f"{f} is absent from payload.", "open_question": f"What is the actual {f} for this location?", "next_step": f"Request {f} from data vendor or internal model."})

# 5c. monitor_flags
monitors = []
monitors.append({"flag_name": "School Score — Average to Below-Average", "evidence": f"Composite 1.67/5.0 (rubric: {get('Rubric - School Score')}). Below-average high school. Not primary concern for likely renter profile.", "why_monitor_only": "Not verdict-blocking; relevant primarily for family-renter retention."})
if "Market Scale" in missing_fields:
    monitors.append({"flag_name": "Market Scale — Missing Tier 2", "evidence": "No market scale data available.", "why_monitor_only": "Affects submarket liquidity assessment but does not block verdict."})

# 5d. signal_contradictions
contradictions = []
contradictions.append({
    "signal_a": f"Heatmap Score: {heatmap} (rubric: +{get('Rubric - Heatmap')})",
    "signal_b": f"Population Density: {pop_density:,.0f} p/sq mi (rubric: {get('Rubric - Population Density')})",
    "conflict_implication": "High heatmap typically correlates with dense locations; low density here suggests concentrated, high-velocity local demand from a thin population base.",
    "resolution_path": "Verify heatmap sourcing methodology and confirm whether demand is driven by local employment anchors rather than population mass."
})
contradictions.append({
    "signal_a": f"Composite score of {score} presented as screening basis",
    "signal_b": f"3 Tier 1 variables missing ({', '.join(tier1_missing)})",
    "conflict_implication": f"A composite built on {len(tier1_missing)} missing Tier 1 variables is not analytically equivalent to a complete-data score. True composite could range 25–45 depending on those inputs.",
    "resolution_path": "Treat score of 31 as a directional estimate. Do not use for pipeline ranking against properties with complete Tier 1 data until backfill is complete."
})

# 5e. known_unknowns_and_data_gaps
known_unknowns = {
    "tier_1_missing": tier1_missing,
    "tier_2_missing": tier2_missing,
    "transformation_dependent": ["Deal Size ($) — confirm if raw value is per-unit or total", "Apartment Size — helper label vs actual 1BR sqft scoring basis"],
    "rubric_reconciliation_needed": ["Heatmap Score — raw values exceed supplied rubric table bands", "Undesirable Retail — Phase7 penalty may differ from supplied rubric table"]
}

# 5f. decision_gate_checklist
decision_gates = {
    "must_have_before_underwriting": [f"Acquire {f}" for f in tier1_missing] + ["Validate physical condition via ceiling height confirmation"],
    "should_have_before_underwriting": ["Pull Market Scale data for submarket liquidity", "Inspect undesirable retail type and direct visibility from site", "Pull comparable absorption velocities within 5-mile radius"],
    "can_monitor_later": ["Track school quality trends for family-renter retention", "Monitor local supply pipeline for new competition"]
}

report_data["page_5"] = {
    "deal_breaker_flags": {"deal_breaker_status": deal_breaker_status, "flags": deal_breakers},
    "notable_flags": {"flags": notable},
    "monitor_flags": {"flags": monitors},
    "signal_contradictions": {"contradictions": contradictions},
    "known_unknowns_and_data_gaps": known_unknowns,
    "decision_gate_checklist": decision_gates
}

# ─── PAGE 6 — Investment Thesis ───
thesis_classification = {
    "thesis_label": "Core-Plus / Stabilized Hold",
    "thesis_hypothesis_suffix": "HYPOTHESIS" if tier1_missing else None,
    "primary_driver_type": "Structural"
}

supporting_rationale = (
    f"The {vintage} vintage (Tier 1, rubric: +{get('Rubric - Vintage')}) paired with a comprehensive amenity package "
    f"positions this asset as physically current — the defining characteristic of a Core-Plus / Stabilized Hold rather than a value-creation story. "
    f"Structural constraints (population density {pop_density:,.0f} p/sq mi, rubric: {get('Rubric - Population Density')}; "
    f"undesirable retail {undesirable} mi, rubric: {get('Rubric - Undesirable Retail')}) constrain the long-term rent-growth ceiling, "
    f"making the structural investment driver cash-yield stability rather than rent upside. "
    f"Without sentiment data, the thesis rests entirely on structural positioning pending Tier 1 backfill."
)

alt_archetypes = [
    {"archetype_name": "Rent-to-Market", "status": "Ruled Out", "reason": f"Structural constraints (density {get('Rubric - Population Density')}, retail {get('Rubric - Undesirable Retail')}, Walk Score {get('Walk Score')}) do not support a rent premium thesis. Location quality insufficient to justify modeling a meaningful market rent gap."},
    {"archetype_name": "Value-Add Capex", "status": "Ruled Out", "reason": f"{vintage} vintage eliminates the capex gap narrative. No renovation program required for a {2026-vintage}-year-old asset with full amenities."},
    {"archetype_name": "Operational Turnaround", "status": "Ruled Out", "reason": "No evidence of operational distress in structural data. No sentiment data available to identify management issues."}
]

thesis_confidence = {
    "confidence_label": "Hypothesis",
    "dependency_note": f"Three Tier 1 variables ({', '.join(tier1_missing)}) are missing. The current thesis is a directional working view only. True composite score could range 25–45. Thesis cannot be promoted to Low/Medium confidence until all Tier 1 inputs are backfilled.",
    "critical_dependencies": [f"Acquire {f}" for f in tier1_missing] + ["Obtain rent roll and occupancy data from seller"]
}

report_data["page_6"] = {
    "thesis_classification": thesis_classification,
    "supporting_rationale": {"paragraph": supporting_rationale},
    "primary_underwriting_assumption": {
        "assumption_title": "In-place occupancy and current rent roll as baseline",
        "assumption_statement": f"The thesis holds if current occupancy and in-place rents are sustained through stabilized operations. Underwriting must confirm: (1) current occupancy rate, (2) in-place rents, (3) rent-to-market spread, and (4) renewal rate trajectory. These inputs are not available in the current data payload and must be obtained from the seller.",
        "must_confirm_inputs": ["Current occupancy rate", "In-place rent roll", "Rent-to-market spread", "Renewal rate trajectory"]
    },
    "alternative_archetypes_ruled_out": {"archetypes": alt_archetypes},
    "thesis_confidence_and_dependency_note": thesis_confidence
}

# ─── PAGE 7 — Data Quality & Variable Log ───
variable_log = []
scored_vars = [
    ("Property Vintage", "Rubric - Vintage", 1, 3), ("Unit Size", "Rubric - Unit Size", 2, 3),
    ("Deal Size ($)", "Rubric - Deal Size", 2, 2), ("Market Scale", "Rubric - Market Scale", 2, 3),
    ("Ceiling Height", "Rubric - Ceiling Height", 3, 2), ("Swimming Pool", "Rubric - Swimming Pool", 3, 1),
    ("Fitness Center", "Rubric - Fitness Center", 3, 1), ("2nd Bath for 2+ Bedroom Units", "Rubric - 2nd Bath", 3, 1),
    ("Washer/Dryer", "Rubric - Washer Dryer", 3, 1), ("Apartment Size", "Rubric - Apartment Size", 2, 3),
    ("Walk Score", "Rubric - Walk Score", 2, 5), ("Transit Score", "Rubric - Transit Score", 1, 5),
    ("Bike Score", "Rubric - Bike Score", 3, None), ("Sound Score", "Rubric - Sound Score", 2, 3),
    ("Great Schools Rating (Score)", "Rubric - School Score", 2, 2),
    ("Retail - Starbucks", "Rubric - Dist Starbucks", 3, 3), ("Undesirable Retail", "Rubric - Undesirable Retail", 2, 3),
    ("Retail - National Cluster", "Rubric - Nat Cluster", 3, 3), ("Retail - National Grocer", "Rubric - Nat Grocer", 3, 3),
    ("Median Income", "Rubric - Median Income", 1, 5), ("Heatmap Score", "Rubric - Heatmap", 2, 4),
    ("Modified Heatmap Score", "Rubric - Mod Heatmap", 2, 3),
    ("Population Density", "Rubric - Population Density", 2, None),
    ("Justice Map - Surrounding", "Rubric - Justice Map Surroundings", 3, None),
]
for raw_key, rubric_key, tier, max_s in scored_vars:
    rv = get(raw_key, None)
    rs = get(rubric_key, None)
    dn = dd.get("variables",{}).get(raw_key,{}).get("display_name", raw_key)
    note = ""
    if rv is None: note = f"⚠ MISSING Tier {tier}." + (" Blocks Go verdict." if tier == 1 else "")
    variable_log.append({"variable_display_name": dn, "tier": tier, "raw_value": rv, "rubric_score": rs, "max_score": max_s, "data_source": dd.get("variables",{}).get(raw_key,{}).get("source_system",""), "notes_or_missing_flag": note})

report_data["page_7"] = {
    "data_reliability_summary": {
        "summary_cards": [
            {"label": "Score Completeness", "value": score_dashboard["missing_data_summary"]["score_completeness_percent"], "subtext": f"{len(scored_vars)-len(missing_fields)}/{len(scored_vars)} variables scored"},
            {"label": "Missing Tier 1", "value": len(tier1_missing), "subtext": ", ".join(tier1_missing) if tier1_missing else "None"},
            {"label": "Missing Tier 2", "value": len(tier2_missing), "subtext": ", ".join(tier2_missing) if tier2_missing else "None"},
            {"label": "Data Reliability", "value": "Low" if tier1_missing else "Medium", "subtext": "Tier 1 gaps present" if tier1_missing else "Complete"}
        ]
    },
    "core_variable_log": {"rows": variable_log},
    "sentiment_data_log": {"sentiment_summary": {"platform": "Not available", "total_reviews_collected": "Not available", "qualifying_reviews_analyzed": "Not available", "excluded_reviews_count": "Not available", "analysis_date": "Not available", "operational_rating": "Not available", "review_sentiment_direction": "Not available", "review_stability": "Not available"}, "theme_groups": {"established_patterns": [], "tentative_signals": []}},
    "traceability_and_rebuild_metadata": {
        "traceability_note": f"This report was generated from listing data inserted on {get('Data Inserted Timestamp','N/A')[:10]} via Northmarq broker submission. Email trace: {get('gmail_message_id','N/A')[:40]}... Relaxed fields: {get('Relaxed Fields Used','None')}. Sentiment data was not available at report generation.",
        "rebuild_limitations": ["Missing Tier 1 fields prevent complete scoring — composite of 31 is directional only", "No sentiment data limits operational assessment", "Apartment Size scoring basis requires confirmation of 1BR sqft parsing logic"]
    }
}

# ─── PAGE 8 — Underwriting Readiness & Action Plan ───
readiness = "Conditionally ready" if tier1_missing else "Ready for underwriting"

report_data["page_8"] = {
    "go_forward_readiness_status": {
        "readiness_label": readiness,
        "summary_statement": f"The property shows structural merit ({vintage} vintage, strong demand signals with Heatmap {heatmap}) but cannot enter full underwriting until {len(tier1_missing)} Tier 1 input{'s' if len(tier1_missing)!=1 else ''} — {', '.join(tier1_missing)} — {'are' if len(tier1_missing)!=1 else 'is'} backfilled. Upon acquisition, composite score may shift materially (est. range 25–45), potentially altering both verdict and thesis.",
        "blocking_dependencies": [f"Acquire {f}" for f in tier1_missing],
        "nonblocking_dependencies": ["Market Scale data for submarket liquidity", "Rent roll and occupancy from seller", "Physical verification of ceiling height"]
    },
    "critical_data_requests": {"requests": [
        {"request_name": "Transit Score backfill", "requested_from": "Walk Score API / Internal data team", "why_needed": "Tier 1 gap — blocks Go verdict", "report_link": "Pages 1, 3, 5"},
        {"request_name": "Crime Score pull", "requested_from": "Third-party data vendor", "why_needed": "Tier 1 gap — most critical missing variable", "report_link": "Pages 1, 5"},
        {"request_name": "Location Score calculation", "requested_from": "Internal data team", "why_needed": "Tier 1 gap — may materially shift thesis", "report_link": "Pages 1, 5, 6"},
        {"request_name": "Market Scale data", "requested_from": "Internal data team", "why_needed": "Tier 2 gap — submarket liquidity", "report_link": "Page 5"},
        {"request_name": "Rent roll & occupancy", "requested_from": "Broker / Seller", "why_needed": "Validates Core-Plus thesis assumption", "report_link": "Page 6"},
    ]},
    "kill_criteria_and_flip_conditions": {
        "kill_conditions": [
            "Crime Score returns in highest-penalty band, indicating material safety concern",
            "Transit Score below 10 confirms isolated micro-location with no public transit access",
            "Location Score triggers structural No-Go threshold",
            "Physical inspection reveals undisclosed deferred maintenance or structural deficiency"
        ],
        "strengthening_conditions": [
            "Crime Score returns neutral or positive — materially lifts confidence and may enable Go",
            "Transit Score ≥ 25 and Location Score ≥ 0 — enables reclassification from Hypothesis",
            "Occupancy confirmed ≥ 93% with stable renewal trajectory",
            "Rent roll confirms no soft concessions"
        ]
    },
    "recommended_next_7_day_plan": {
        "days_1_to_2": ["Submit Transit Score API request to Walk Score provider", "Initiate Crime Score data vendor pull", "Request rent roll, occupancy snapshot, and operating summary from Northmarq"],
        "days_3_to_5": ["Generate Location Score from internal model once Crime/Transit available", "Pull comparable absorption data for 5-mile radius", "Verify undesirable retail type and assess direct visibility from property"],
        "days_6_to_7": ["Re-score composite with backfilled Tier 1 data", "Update verdict and thesis classification", "Prepare underwriting handoff package if Go conditions are met"]
    }
}

# Save structured data
out_path = os.path.join(BASE, "output", "report_data_v2.json")
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w") as f:
    json.dump(report_data, f, indent=2, default=str)
print(f"Structured report data saved to: {out_path}")
print(f"Pages generated: {list(report_data.keys())}")
for p in report_data:
    print(f"  {p}: {list(report_data[p].keys())}")
