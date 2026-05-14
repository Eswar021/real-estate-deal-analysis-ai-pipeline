from pathlib import Path
from datetime import date

# Base project directory (this file lives at project_root/config/paths.py)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── Data Directories (source Excel files) ────────────────────────────────────
DATA_DIR              = PROJECT_ROOT / "data"
INPUT_T12_DOCS_DIR    = DATA_DIR / "input_T12_docs"
MAPPED_T12_DOCS_BASE  = DATA_DIR / "mapped_T12_docs"
MAPPED_T12_DOCS_DIR   = MAPPED_T12_DOCS_BASE / "t12_docs"
NEW_MAPPED_T12_DOCS_DIR = MAPPED_T12_DOCS_BASE / "new_t12_docs"

# ── Database (core knowledge base) ───────────────────────────────────────────
DB_DIR                       = PROJECT_ROOT / "db"
RULEBOOK_DB_PATH             = DB_DIR / "mapping_rule_book.json"
RULEBOOK_DB_V2_PATH          = DB_DIR / "mapping_rule_book_v2.json"
CATEGORY_CLASSIFICATION_PATH = DB_DIR / "category_classification.json"

# ── Output Directories ────────────────────────────────────────────────────────
_RUN_DATE = date.today().strftime("%Y_%m_%d")
OUTPUT_DOCS_DIR = PROJECT_ROOT / "output_docs" / _RUN_DATE

# Step 0 — Rulebook build
BUILD_RULEBOOK_OUT_DIR    = OUTPUT_DOCS_DIR / "0_build_rulebook"
EXTRACTED_MAPPINGS_V2_DIR = BUILD_RULEBOOK_OUT_DIR / "extracted_mappings_v2"
RULEBOOK_V2_OUTPUT_DIR    = BUILD_RULEBOOK_OUT_DIR / "mapping_rulebook_v2"

# Step 1 — Mapping
MAPPING_OUT_DIR    = OUTPUT_DOCS_DIR / "1_mapping"
BLOCK_DETECTION_DIR = MAPPING_OUT_DIR / "block_detection"
AUTO_MAPPED_DIR     = MAPPING_OUT_DIR / "auto_mapped"
AI_MAPPED_DIR       = MAPPING_OUT_DIR / "ai_mapped"
AI_MAPPING_LOGS_DIR = MAPPING_OUT_DIR / "ai_mapping_logs"

# Step 2 — NOI Verification
NOI_VERIFICATION_DIR = OUTPUT_DOCS_DIR / "2_noi_verification"
ACTUAL_NOI_DIR       = NOI_VERIFICATION_DIR / "actual_noi"
COMPUTED_NOI_DIR     = NOI_VERIFICATION_DIR / "computed_noi"
NOI_COMPARISON_DIR   = NOI_VERIFICATION_DIR / "comparison"

# Utils (export / inspection tools — not part of the main pipeline flow)
UTILS_OUT_DIR          = OUTPUT_DOCS_DIR / "utils"
RESULTS_TO_EXCEL_DIR   = UTILS_OUT_DIR / "auto_mapped_to_excel"
AI_MAPPED_TO_EXCEL_DIR = UTILS_OUT_DIR / "ai_mapped_to_excel"
RULEBOOK_EXCEL_PATH    = UTILS_OUT_DIR / "mapping_rule_book.xlsx"

# Analysis (diagnostic scripts output)
ANALYSIS_OUTPUT_DIR = OUTPUT_DOCS_DIR / "analysis"

# ── Documentation ─────────────────────────────────────────────────────────────
DOCS_DIR = PROJECT_ROOT / "docs"

# ── Create directories on import ──────────────────────────────────────────────
for _d in [
    EXTRACTED_MAPPINGS_V2_DIR,
    RULEBOOK_V2_OUTPUT_DIR,
    BLOCK_DETECTION_DIR,
    AUTO_MAPPED_DIR,
    AI_MAPPED_DIR,
    AI_MAPPING_LOGS_DIR,
    ACTUAL_NOI_DIR,
    COMPUTED_NOI_DIR,
    NOI_COMPARISON_DIR,
    RESULTS_TO_EXCEL_DIR,
    AI_MAPPED_TO_EXCEL_DIR,
    ANALYSIS_OUTPUT_DIR,
]:
    _d.mkdir(parents=True, exist_ok=True)
