import json
import os

html_template = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>The Jeff on 10th - Report</title>
    <style>
        body {
            font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
            background-color: #ffffff;
            color: #333333;
            margin: 0;
            padding: 0;
            font-size: 11px;
            line-height: 1.4;
        }
        .page {
            width: 8.5in;
            height: 11in;
            box-sizing: border-box;
            padding: 0.5in;
            page-break-after: always;
            position: relative;
        }
        @media print {
            body { margin: 0; padding: 0; }
            .page { page-break-after: always; padding: 0.5in; border: none; }
        }
        .header {
            background-color: #0f1f38;
            color: #ffffff;
            padding: 15px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 4px solid #d4af37;
            margin-bottom: 20px;
            margin-top: -0.5in;
            margin-left: -0.5in;
            margin-right: -0.5in;
        }
        .header h1 {
            margin: 0;
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .header .subtitle {
            font-size: 11px;
            color: #a0aec0;
        }
        .section-header {
            background-color: #0f1f38;
            color: #ffffff;
            padding: 6px 10px;
            font-size: 12px;
            font-weight: bold;
            text-transform: uppercase;
            margin-top: 20px;
            margin-bottom: 0;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 15px;
        }
        th, td {
            border: 1px solid #e2e8f0;
            padding: 8px 10px;
            text-align: left;
            vertical-align: top;
        }
        th {
            background-color: #f7fafc;
            color: #4a5568;
            font-size: 10px;
            font-weight: normal;
        }
        td {
            font-size: 11px;
            color: #1a202c;
        }
        .dark-th th {
            background-color: #1a202c;
            color: #ffffff;
            border-color: #2d3748;
        }
        
        .alert-box {
            background-color: #fff9f9;
            border: 1px solid #fed7d7;
            color: #c53030;
            padding: 8px 10px;
            font-weight: bold;
            margin-bottom: 15px;
        }
        .verdict-container {
            display: flex;
            margin-bottom: 15px;
        }
        .verdict-box {
            border: 2px solid #d4af37;
            background-color: #fffbf0;
            padding: 15px;
            flex: 1;
            margin-right: 15px;
        }
        .thesis-box {
            background-color: #f7fafc;
            border: 1px solid #e2e8f0;
            padding: 15px;
            flex: 1;
        }
        .verdict-title {
            font-size: 10px;
            color: #4a5568;
            font-weight: bold;
            text-transform: uppercase;
            margin-bottom: 5px;
        }
        .verdict-value {
            font-size: 24px;
            color: #c53030;
            font-weight: bold;
            margin: 0 0 5px 0;
        }
        .verdict-sub {
            font-style: italic;
            color: #c53030;
            font-size: 10px;
            margin: 0;
        }
        .thesis-value {
            font-size: 18px;
            color: #d4af37;
            font-weight: bold;
            margin: 0 0 5px 0;
        }
        .thesis-sub {
            font-style: italic;
            color: #4a5568;
            font-size: 10px;
            margin: 0;
        }
        p {
            margin: 0 0 10px 0;
            text-align: justify;
        }
        .positive { color: #2e8540; font-weight: bold; }
        .negative { color: #c53030; font-weight: bold; }
        
        .huge-score {
            font-size: 24px;
            font-weight: bold;
        }
        
        .grid-2 {
            display: grid;
            grid-template-columns: 1fr 1fr;
            grid-gap: 15px;
        }
        
        .footer {
            position: absolute;
            bottom: 0.25in;
            left: 0.5in;
            right: 0.5in;
            display: flex;
            justify-content: space-between;
            font-size: 9px;
            color: #a0aec0;
            border-top: 1px solid #e2e8f0;
            padding-top: 5px;
        }
    </style>
</head>
<body>

<!-- PAGE 1 -->
<div class="page">
    <div class="header">
        <h1>THE JEFF ON 10TH</h1>
        <div class="subtitle">OAKDALE AI | Property Intelligence Report</div>
    </div>

    <div class="section-header">PAGE 1 &middot; DEAL HEADER & INVESTMENT VERDICT</div>
    <table>
        <tr class="dark-th">
            <th>Property</th>
            <th>Address</th>
            <th>Submarket</th>
            <th>Report Date</th>
        </tr>
        <tr>
            <td><strong>The Jeff on 10th</strong></td>
            <td>3500 Ellingsworth Dairy Dr<br>Jeffersonville, IN 47130</td>
            <td>Jeffersonville, IN<br>(Clark County)</td>
            <td>April 9, 2026</td>
        </tr>
        <tr class="dark-th">
            <th>Total Units</th>
            <th>Year Built</th>
            <th>Asking Price/Unit</th>
            <th>Broker</th>
        </tr>
        <tr>
            <td><strong>190</strong></td>
            <td><strong>2022</strong></td>
            <td><strong>$238,800</strong> (~$45.4M total)</td>
            <td>Northmarq</td>
        </tr>
    </table>
    
    <div class="alert-box">
        &#9632; MISSING TIER 1: Transit Score &middot; Crime Score &middot; Location Score | Missing Tier 2: Market Scale | Rubric completeness: ~75%
    </div>

    <div class="section-header">INVESTMENT VERDICT</div>
    <div style="padding-top: 15px;"></div>
    <div class="verdict-container">
        <div class="verdict-box">
            <div class="verdict-title">Verdict</div>
            <h2 class="verdict-value">CONDITIONAL NO-GO</h2>
            <p class="verdict-sub">Blocking condition: Backfill Transit Score, Crime Score, Location Score (Tier 1)</p>
        </div>
        <div class="thesis-box">
            <div class="verdict-title">Thesis</div>
            <h2 class="thesis-value">Pending Location Data</h2>
            <p class="thesis-sub">HYPOTHESIS &mdash; Tier 1 variables incomplete</p>
        </div>
    </div>

    <div class="section-header">INVESTMENT PERSPECTIVE</div>
    <div style="border: 1px solid #e2e8f0; padding: 15px; margin-bottom: 20px; background-color: #f7fafc;">
        <p>The Jeff on 10th is a 2022-vintage opportunity with a total property score of 31, but moving forward is blocked by missing critical location data. The strongest positive signal is the high local demand, reflected in a Heatmap Score of 189.0 (+4 rubric). The most significant concern is the presence of undesirable retail within 0.38 miles (−2 rubric), as well as a low population density of 10,599 persons per square mile (−2 rubric). The investment cannot achieve a full Go verdict until Transit Score, Crime Score, and Location Score are acquired and incorporated into the model.</p>
    </div>

    <div class="section-header">TOP 3 SUPPORTING REASONS</div>
    <table>
        <tr>
            <td style="width: 30px; font-weight: bold; color: #a0aec0; font-size: 14px;">1</td>
            <td><strong>Strong Underlying Demand (Heatmap: 189.0, Rubric: <span class="positive">+4</span>)</strong><br>High baseline demand visibility supports leasing velocity against an otherwise mixed market profile.</td>
        </tr>
        <tr>
            <td style="width: 30px; font-weight: bold; color: #a0aec0; font-size: 14px;">2</td>
            <td><strong>2022 Vintage (Tier 1, rubric: <span class="positive">+3</span>)</strong><br>Eliminates near-term capex risk and positions the asset competitively against older submarket supply.</td>
        </tr>
        <tr>
            <td style="width: 30px; font-weight: bold; color: #a0aec0; font-size: 14px;">3</td>
            <td><strong>Median Household Income (Rubric: <span class="positive">+3</span>)</strong><br>$78,780 at census tract level (Justice Map) provides a supportive demand backdrop for the current rent profile.</td>
        </tr>
    </table>
    
    <div class="section-header">TOP 3 RISK REASONS</div>
    <table>
        <tr>
            <td style="width: 30px; font-weight: bold; color: #a0aec0; font-size: 14px;">1</td>
            <td><strong>Undesirable Retail Adjacency (Distance: 0.38 miles, Rubric: <span class="negative">-2</span>)</strong><br>Close proximity to undesirable retail weakens everyday walkability and lifestyle appeal.</td>
        </tr>
        <tr>
            <td style="width: 30px; font-weight: bold; color: #a0aec0; font-size: 14px;">2</td>
            <td><strong>Low Population Density (10,599 p/sq mi, Rubric: <span class="negative">-2</span>)</strong><br>Lower density may constrain renter pool depth, absorption resilience, and exit liquidity.</td>
        </tr>
        <tr>
            <td style="width: 30px; font-weight: bold; color: #a0aec0; font-size: 14px;">3</td>
            <td><strong>Incomplete Tier 1 Variables (Missing Transit, Crime, Location)</strong><br>The absence of these critical fields prevents a fully informed geographic diligence read and blocks a Go verdict.</td>
        </tr>
    </table>

    <div class="footer">
        <div>OAKDALE AI | Internal Use Only | Confidential</div>
        <div>Page 1</div>
    </div>
</div>

<!-- PAGE 2 -->
<div class="page">
    <div class="header">
        <h1>THE JEFF ON 10TH</h1>
        <div class="subtitle">OAKDALE AI | Property Intelligence Report</div>
    </div>

    <div class="section-header" style="margin-top: 0;">SCORE DASHBOARD</div>
    <table style="text-align: center;">
        <tr class="dark-th">
            <th style="text-align: center;">OAKDALE SCORE<br><span style="font-weight: normal; font-size: 9px;">(Raw Rubric)</span></th>
            <th style="text-align: center;">BUILDING<br>ATTRIBUTES</th>
            <th style="text-align: center;">LOCATION &<br>WALKABILITY</th>
            <th style="text-align: center;">DEMOGRAPHICS &<br>DEMAND</th>
            <th style="text-align: center;">OPERATIONAL<br>SENTIMENT</th>
        </tr>
        <tr>
            <td class="huge-score">31</td>
            <td class="huge-score positive">+5</td>
            <td class="huge-score positive">+10</td>
            <td class="huge-score positive">+8</td>
            <td class="huge-score" style="color: #a0aec0;">N/A</td>
        </tr>
        <tr>
            <td style="color: #718096; font-size: 10px;">~75% complete (5 missing)</td>
            <td style="color: #718096; font-size: 10px;">Missing: Market Scale, Unit Size</td>
            <td style="color: #718096; font-size: 10px;">Missing: Transit, Crime, Location</td>
            <td style="color: #718096; font-size: 10px;">Data complete</td>
            <td style="color: #718096; font-size: 10px;">Data absent from payload</td>
        </tr>
    </table>
    
    <div class="section-header">PHYSICAL CONDITION & PRODUCT OVERVIEW</div>
    <div class="grid-2" style="margin-bottom: 20px;">
        <table style="margin-bottom: 0;">
            <tr class="dark-th"><th colspan="2">Asset Product Profile</th></tr>
            <tr><td><strong>Year Built</strong></td><td>2022</td></tr>
            <tr><td><strong>Total Units</strong></td><td>190</td></tr>
            <tr><td><strong>Unit Mix</strong></td><td>1x1 (664-714 sf), 2x2 (1,138 sf)</td></tr>
            <tr><td><strong>Ceiling Height</strong></td><td>Unconfirmed (likely <= 8 ft)</td></tr>
        </table>
        <table style="margin-bottom: 0;">
            <tr class="dark-th"><th colspan="2">Amenities (Present)</th></tr>
            <tr><td><strong>In-Unit</strong></td><td>Washer/Dryer</td></tr>
            <tr><td><strong>Common</strong></td><td>Swimming Pool, Fitness Center</td></tr>
            <tr><td><strong>Layout</strong></td><td>2nd bath for 2BR+ units</td></tr>
            <tr><td><strong>Scrape/Low-Conf.</strong></td><td>Patio, Balcony, Yard</td></tr>
        </table>
    </div>

    <div class="section-header">LOCATION, ACCESS & DEMAND CONTEXT</div>
    <div class="grid-2">
        <table style="margin-bottom: 0;">
            <tr class="dark-th"><th colspan="2">Walkability & Transit</th></tr>
            <tr><td><strong>Walk Score</strong></td><td>33 (rubric: <span class="positive">+2</span>) - Car Dependent</td></tr>
            <tr><td><strong>Bike Score</strong></td><td>27 (rubric: <span class="positive">+1</span>)</td></tr>
            <tr><td><strong>Transit Score</strong></td><td><span class="negative">MISSING</span> (Tier 1 Constraint)</td></tr>
            <tr><td><strong>Sound Score</strong></td><td>78 (rubric: <span class="positive">+3</span>)</td></tr>
        </table>
        <table style="margin-bottom: 0;">
            <tr class="dark-th"><th colspan="2">Retail Adjacency</th></tr>
            <tr><td><strong>Starbucks</strong></td><td>0.33 mi (rubric: <span class="positive">+3</span>)</td></tr>
            <tr><td><strong>Nat. Cluster</strong></td><td>0.25 mi (rubric: <span class="positive">+2</span>)</td></tr>
            <tr><td><strong>Nat. Grocer</strong></td><td>0.18 mi (rubric: <span class="positive">+2</span>)</td></tr>
            <tr><td><strong>Undesirable</strong></td><td>0.38 mi (rubric: <span class="negative">-2</span>)</td></tr>
        </table>
    </div>
    
    <div class="grid-2" style="margin-top: 15px;">
        <table style="margin-bottom: 0;">
            <tr class="dark-th"><th colspan="2">Demographic Profile (Tract 50603)</th></tr>
            <tr><td><strong>Population Density</strong></td><td>10,599 p/sq mi (rubric: <span class="negative">-2</span>)</td></tr>
            <tr><td><strong>Median Income</strong></td><td>$78,780 (rubric: <span class="positive">+3</span>)</td></tr>
            <tr><td><strong>Heatmap Score</strong></td><td>189.0 (rubric: <span class="positive">+4</span>)</td></tr>
            <tr><td><strong>Mod. Heatmap</strong></td><td>145.0 (rubric: <span class="positive">+3</span>)</td></tr>
        </table>
        <table style="margin-bottom: 0;">
            <tr class="dark-th"><th colspan="2">School Quality</th></tr>
            <tr><td><strong>Composite Score</strong></td><td>1.67 / 5.0 (rubric: 0)</td></tr>
            <tr><td><strong>W E Wilson (Elem)</strong></td><td>1.0 mi (Average)</td></tr>
            <tr><td><strong>River Valley (Mid)</strong></td><td>1.4 mi (Average)</td></tr>
            <tr><td><strong>Jeffersonville (High)</strong></td><td>1.1 mi (Below Average)</td></tr>
        </table>
    </div>

    <div class="footer">
        <div>OAKDALE AI | Internal Use Only | Confidential</div>
        <div>Page 2</div>
    </div>
</div>

<!-- PAGE 3 -->
<div class="page">
    <div class="header">
        <h1>THE JEFF ON 10TH</h1>
        <div class="subtitle">OAKDALE AI | Property Intelligence Report</div>
    </div>
    
    <div class="section-header" style="margin-top:0;">RESIDENT SENTIMENT & OPERATING HEALTH</div>
    <table style="text-align: center; margin-bottom: 20px;">
        <tr class="dark-th">
            <th style="text-align: center;">OPERATIONAL RATING</th>
            <th style="text-align: center;">REVIEW SENTIMENT</th>
            <th style="text-align: center;">REVIEW CORPUS</th>
        </tr>
        <tr>
            <td class="huge-score" style="color: #a0aec0;">N/A</td>
            <td class="huge-score" style="color: #a0aec0;">N/A</td>
            <td class="huge-score" style="color: #a0aec0;">N/A</td>
        </tr>
        <tr>
            <td style="color: #718096; font-size: 10px;">out of 5.0</td>
            <td style="color: #718096; font-size: 10px;">Not available</td>
            <td style="color: #718096; font-size: 10px;">reviews considered</td>
        </tr>
    </table>
    
    <div style="border: 1px dashed #cbd5e0; padding: 20px; text-align: center; color: #718096; background-color: #f7fafc; margin-bottom: 20px;">
        <em>Current operating sentiment for The Jeff on 10th cannot be determined based on the available data. Metrics including operational rating, sentiment analysis date, and review corpus counts are entirely absent. There is no evidence to evaluate whether management stability or building condition generates significant patterns. This area remains unverified and requires data acquisition.</em>
    </div>

    <div class="section-header">RISK REGISTER & DECISION GATES</div>
    
    <table>
        <tr style="background-color: #fed7d7; color: #c53030;">
            <th colspan="2" style="background-color: #c53030; color: white;">DEAL-BREAKER FLAGS</th>
        </tr>
        <tr>
            <td style="width: 25%;"><strong>Missing Critical Data</strong></td>
            <td>Transit Score, Crime Score, and Location Score are missing. These Tier 1 fields must be acquired; their absence directly blocks a full underwriting evaluation and results in a Conditional No-Go.</td>
        </tr>
    </table>
    
    <table>
        <tr style="background-color: #feebc8; color: #c05621;">
            <th colspan="2" style="background-color: #dd6b20; color: white;">NOTABLE FLAGS (Require Investigation)</th>
        </tr>
        <tr>
            <td style="width: 25%;"><strong>Undesirable Retail Proximity</strong></td>
            <td>Located just 0.38 miles away (Structural Tier 2).<br><strong>Open Question:</strong> Does this proximity materially limit tenant quality?<br><strong>Action:</strong> Inspect a site map and assess direct visibility and noise/traffic impact from the property.</td>
        </tr>
        <tr>
            <td style="width: 25%;"><strong>Shallow Tenant Pool</strong></td>
            <td>Population density is 10,599.5 (Demographic Tier 2).<br><strong>Open Question:</strong> Will a shallow local tenant base limit leasing momentum or exit liquidity?<br><strong>Action:</strong> Pull comparable property absorption velocities and verify stabilization history.</td>
        </tr>
    </table>
    
    <table>
        <tr style="background-color: #e2e8f0; color: #4a5568;">
            <th colspan="2" style="background-color: #4a5568; color: white;">MONITOR FLAGS & CONTRADICTIONS</th>
        </tr>
        <tr>
            <td style="width: 25%;"><strong>Missing Market Scale</strong></td>
            <td>Requires confirmation to assess relative liquidity (Missing Tier 2).</td>
        </tr>
        <tr>
            <td style="width: 25%;"><strong>Neutral School Rating (1.67)</strong></td>
            <td>If larger family units are heavily weighted, lack of premium schools may impact rental limits.</td>
        </tr>
        <tr>
            <td style="width: 25%;"><strong>Contradiction: Heatmap vs Density</strong></td>
            <td>A Heatmap score of 189.0 usually correlates with dense locations, yet the population density here is low. This suggests concentrated, high-velocity local demand despite thin absolute population numbers.</td>
        </tr>
    </table>

    <div class="footer">
        <div>OAKDALE AI | Internal Use Only | Confidential</div>
        <div>Page 3</div>
    </div>
</div>

</body>
</html>
"""

with open("/Users/manikantamb/_MyFiles/Work_/Freelancing/Shivam_Excel_AI_Automation/logic/output/The_Jeff_on_10th_Report_Styled.html", "w") as f:
    f.write(html_template)

print("Beautiful HTML created.")
