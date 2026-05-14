# Oakdale Capital — Deal Analysis Automation

AI-driven due diligence pipeline for multifamily real estate acquisitions.
Automates T12 financial statement mapping, NOI verification, and property
intelligence report generation to support Oakdale Capital's deal underwriting.

---

## Project Tracks

| Track | Folder | Stack |
|---|---|---|
| T12 Mapping Pipeline | `logic/mapping_rulebook/` | Python |
| Property Intelligence Report (SWOT) | `logic/intial_swot_pdf_prototype/` | Python + Node.js |

---

## Prerequisites

**Python 3.10+**

**Node.js 18+** (only needed for the SWOT track — used by Puppeteer for PDF generation)

**LLM configuration** — create a `.env` file inside `logic/mapping_rulebook/` with the provider-specific keys used by `llm/llm_client.py`.

Common options:
```
OPENAI_API_KEY_AI_MAPPING=your_key_here
OPENAI_MODEL=gpt-5-nano

# Optional if switching provider
GOOGLE_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-flash-lite

# Optional if using LM Studio
LMSTUDIO_BASE_URL=http://localhost:1234/v1
LMSTUDIO_MODEL=qwen/qwen2.5-coder-14b
```

---

## Setup

### 1. Install Python dependencies

From the project root (or inside a virtual environment):
```bash
pip install openpyxl langchain langchain-openai langchain-google-genai pydantic python-dotenv
```

### 2. Install Node dependencies (SWOT track only)

```bash
cd logic/intial_swot_pdf_prototype/scripts
npm install
```

This installs Puppeteer (headless Chrome) used to render HTML reports to PDF.
The `node_modules/` folder is not committed — this step is required after every fresh clone.

---

## Running the T12 Mapping Pipeline

All commands run from `logic/mapping_rulebook/`.

### One-time rulebook build (run when adding new source files)

```bash
python pipeline/0_build_rulebook/extract_mappings_v2.py
python pipeline/0_build_rulebook/build_rulebook_v2.py
# Review the audit file, then copy the approved rulebook:
cp output_docs/<date>/0_build_rulebook/mapping_rulebook_v2/mapping_rule_book_v2.json db/
python pipeline/0_build_rulebook/category_config.py
```

### Per-file mapping (run for every new T12 file received)

Place raw `.xlsx` T12 files in `data/input_T12_docs/`, then:

```bash
python pipeline/1_mapping/detect_blocks.py
python pipeline/1_mapping/map_blocks.py
python pipeline/1_mapping/find_mapping.py
```

### NOI verification

```bash
python pipeline/2_noi_verification/compute_noi.py
python pipeline/2_noi_verification/compare_noi.py
```

### Export to Excel (on demand)

```bash
python pipeline/utils/ai_results_to_excel.py
```

Outputs land in `output_docs/<YYYY_MM_DD>/` — a new dated folder is created automatically each day.

---

## Running the Property Intelligence Report (SWOT)

All commands run from `logic/intial_swot_pdf_prototype/`.

### 1. Fill in property data

Edit `property.json` with the target property's details.

### 2. Generate the report data

```bash
python scripts/generate_report_v2.py
```

Output: `output/report_data_v2.json`

### 3. Render to HTML + PDF

```bash
python scripts/render_report_v2.py
```

Output: `output/PIR_<PropertyName>_<City>_<Date>.pdf`

---

## Folder Structure

```
├── logic/
│   ├── mapping_rulebook/       T12 mapping pipeline
│   │   ├── pipeline/           Numbered pipeline scripts (0–2 + utils)
│   │   ├── analysis/           Diagnostic notebooks (read-only)
│   │   ├── config/             paths, runtime rulebook selection, and agent model config
│   │   ├── data/               Input Excel files (gitignored)
│   │   ├── db/                 Active rulebook + category classification JSON
│   │   ├── llm/                LLM client wrapper (Gemini / OpenAI / LM Studio)
│   │   ├── output_docs/        All pipeline outputs, dated by run (gitignored)
│   │   └── docs/               Mapping rulebook docs, decisions, and audits
│   │
│   └── intial_swot_pdf_prototype/   Property Intelligence Report generator
│       ├── scripts/            Python + JS scripts
│       ├── pages/              Report page instructions (JSON)
│       ├── output/             Generated reports
│       └── property.json       Input — fill this per property
│
└── master_docs/                Meeting recordings and client docs
```

---

## Documentation

| File | Contents |
|---|---|
| `logic/mapping_rulebook/docs/README.md` | T12 pipeline overview and run guide |
| `logic/mapping_rulebook/docs/LOGIC.md` | Algorithm deep-dive (format detection, conflict resolution, NOI) |
| `logic/mapping_rulebook/docs/CONTEXT.md` | Developer reference — all paths, inputs/outputs, run commands |
| `logic/mapping_rulebook/docs/WORKING_STYLE.md` | Repo-specific coding style and module design rules |
| `logic/mapping_rulebook/docs/DECISIONS.md` | Key implementation decisions and the reasons behind them |
| `logic/mapping_rulebook/docs/audits/` | Dated system audits and change audits for state tracking |
| `master_docs/` | External meeting recordings, transcripts, and client-shared materials |
