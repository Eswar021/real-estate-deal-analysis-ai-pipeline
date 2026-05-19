# Oakdale Capital — Deal Analysis Automation

AI-driven due diligence pipeline for multifamily real estate acquisitions.
Automates T12 financial statement mapping, NOI verification, and property
intelligence report generation to support Oakdale Capital's deal underwriting.

---

## Project Tracks

| Track | Folder | Stack |
|---|---|---|
| T12 Mapping Pipeline | `app/t12_pipeline/` | Python |
| Property Intelligence Report (SWOT) | `app/intial_swot_pdf_prototype/` | Python + Node.js |

---

## Prerequisites

**Python 3.10+**

**Node.js 18+** (only needed for the SWOT track — used by Puppeteer for PDF generation)

**LLM configuration** — create a `.env` file inside `app/t12_pipeline/` with the provider-specific keys used by `llm/llm_client.py`.

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

## Running the T12 Mapping Pipeline

All commands run from `app/t12_pipeline/`.

```bash
# Build rulebook (run once when new reviewed .xlsm files arrive)
python src/build_rulebook/run.py

# Full pipeline (manifest + detection + mapping)
python src/pipeline/run_pipeline.py --stages 0,1,2

# Most common: reuse existing manifest, run detection + mapping
python src/pipeline/run_pipeline.py --stages 1,2

# Limit AI calls while testing
python src/pipeline/run_pipeline.py --stages 1,2 --ai-limit 5
```

See `app/t12_pipeline/docs/README.md` for the full run guide.

---

## Running the Property Intelligence Report (SWOT)

All commands run from `app/intial_swot_pdf_prototype/`.

### 1. Install Node dependencies (first time only)

```bash
cd app/intial_swot_pdf_prototype/scripts
npm install
```

### 2. Fill in property data

Edit `property.json` with the target property's details.

### 3. Generate and render

```bash
python scripts/generate_report_v2.py
python scripts/render_report_v2.py
```

Output: `output/PIR_<PropertyName>_<City>_<Date>.pdf`

---

## Folder Structure

```
├── app/
│   ├── t12_pipeline/           T12 mapping + NOI verification pipeline
│   │   ├── src/                Pipeline stages, config, LLM client
│   │   ├── data/               Input Excel files
│   │   ├── db/                 Versioned rulebook snapshots
│   │   ├── output_docs/        All pipeline outputs (date-stamped)
│   │   └── docs/               Pipeline docs, decisions, detection logic
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
| `app/t12_pipeline/docs/README.md` | T12 pipeline overview and run guide |
| `app/t12_pipeline/docs/DECISIONS.md` | Key implementation decisions and reasons |
| `app/t12_pipeline/docs/detection_logic/` | Per-format row classification decision trees |
| `app/t12_pipeline/CLAUDE.md` | Claude Code instructions for the T12 pipeline |
| `master_docs/` | Meeting recordings, transcripts, and client-shared materials |
