import os
from pathlib import Path
from datetime import datetime

# Base project directory (this file lives at project_root/src/t12_pipeline/config/paths.py)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
REPO_ROOT = PROJECT_ROOT.parent.parent

# ── Data Directories (source Excel files) ────────────────────────────────────
DATA_DIR              = PROJECT_ROOT / "data"
INPUT_T12_DOCS_DIR    = DATA_DIR / "input_T12_docs"
MAPPED_T12_DOCS_DIR   = DATA_DIR / "mapped_T12_docs"

# ── Database ──────────────────────────────────────────────────────────────────
DB_DIR                = PROJECT_ROOT / "db"
DB_RULEBOOKS_DIR      = DB_DIR / "rulebooks"

# ── Manifest (current-run pointer) ────────────────────────────────────────────
OUTPUT_DOCS_BASE_DIR  = PROJECT_ROOT / "output_docs"
MANIFEST_PATH         = OUTPUT_DOCS_BASE_DIR / "current_manifest.json"

# ── Per-run Output Root ───────────────────────────────────────────────────────
_RUN_TIMESTAMP = os.environ.get("T12_RUN_TIMESTAMP") or datetime.now().strftime("%Y_%m_%d_%H%M")
OUTPUT_DOCS_DIR = OUTPUT_DOCS_BASE_DIR / _RUN_TIMESTAMP

# ── Build-rulebook intermediates (audit trail) ────────────────────────────────
BUILD_RULEBOOK_OUT_DIR      = OUTPUT_DOCS_DIR / "build_rulebook"
REVIEWED_ROW_HISTORY_DIR    = BUILD_RULEBOOK_OUT_DIR / "reviewed_row_history"
REVIEWED_ROW_HISTORY_PER_FILE_DIR = REVIEWED_ROW_HISTORY_DIR / "per_file"
HISTORICAL_RULE_SUPPORT_DIR = BUILD_RULEBOOK_OUT_DIR / "historical_rule_support"
RULEBOOK_OUTPUT_DIR         = BUILD_RULEBOOK_OUT_DIR / "mapping_rulebook"
CLIENT_REVIEW_RULES_OUT_DIR = BUILD_RULEBOOK_OUT_DIR / "client_review_rules"

REVIEWED_ROW_HISTORY_INDEX_PATH = REVIEWED_ROW_HISTORY_DIR / "reviewed_row_history_index.json"
NO_CONFLICT_RULEBOOK_PATH       = HISTORICAL_RULE_SUPPORT_DIR / "no_conflict_rulebook.json"
HISTORICAL_CONFLICTS_PATH       = HISTORICAL_RULE_SUPPORT_DIR / "historical_conflicts.json"
AUTO_ASSIGNED_CONFLICTS_PATH    = HISTORICAL_RULE_SUPPORT_DIR / "auto_assigned_unresolved.json"
AUTO_ASSIGNED_CONFLICTS_XLSX    = HISTORICAL_RULE_SUPPORT_DIR / "auto_assigned_unresolved.xlsx"
CLIENT_REVIEW_RULES_PATH        = CLIENT_REVIEW_RULES_OUT_DIR / "client_review_rulebook_phase1.json"

# Rulebook written to db/rulebooks/ (not output_docs/)
RULEBOOK_DB_OUTPUT_PATH = DB_RULEBOOKS_DIR / f"mapping_rulebook_{_RUN_TIMESTAMP}.json"

# ── Stage 1 — Detection + NOI Verification ───────────────────────────────────
DETECTION_OUT_DIR    = OUTPUT_DOCS_DIR / "1_detection"
BLOCK_DETECTION_DIR  = DETECTION_OUT_DIR / "block_detection"
ANNOTATED_BLOCKS_DIR = DETECTION_OUT_DIR / "annotated_blocks"
NOI_VERIFICATION_DIR = DETECTION_OUT_DIR / "noi_verification"
ACTUAL_NOI_DIR       = NOI_VERIFICATION_DIR / "actual_noi"
COMPUTED_NOI_DIR     = NOI_VERIFICATION_DIR / "computed_noi"
NOI_COMPARISON_DIR   = NOI_VERIFICATION_DIR / "comparison"

# ── Stage 2 — Mapping ─────────────────────────────────────────────────────────
MAPPING_OUT_DIR      = OUTPUT_DOCS_DIR / "2_mapping"
AUTO_MAPPED_DIR      = MAPPING_OUT_DIR / "auto_mapped"
AI_MAPPED_DIR        = MAPPING_OUT_DIR / "ai_mapped"
AI_MAPPING_LOGS_DIR  = MAPPING_OUT_DIR / "ai_mapping_logs"

# ── Utils (export / inspection tools) ────────────────────────────────────────
UTILS_OUT_DIR          = OUTPUT_DOCS_DIR / "utils"
RESULTS_TO_EXCEL_DIR   = UTILS_OUT_DIR / "auto_mapped_to_excel"
AI_MAPPED_TO_EXCEL_DIR = UTILS_OUT_DIR / "ai_mapped_to_excel"
RULEBOOK_EXCEL_PATH    = UTILS_OUT_DIR / "mapping_rule_book.xlsx"

# ── Analysis ──────────────────────────────────────────────────────────────────
ANALYSIS_OUTPUT_DIR = OUTPUT_DOCS_DIR / "analysis"

# ── Client-reviewed source docs ───────────────────────────────────────────────
CLIENT_REVIEW_DOCS_DIR = DATA_DIR / "client_review_docs"
CLIENT_REVIEW_CONFLICTS_FILE = (
    CLIENT_REVIEW_DOCS_DIR / "conflict_sources_report_v2_J VM Notes.xlsx"
)

# ── Documentation ─────────────────────────────────────────────────────────────
DOCS_DIR = PROJECT_ROOT / "docs"

# ── Static dirs to create on import ──────────────────────────────────────────
for _d in [
    DB_RULEBOOKS_DIR,
    OUTPUT_DOCS_BASE_DIR,
    CLIENT_REVIEW_DOCS_DIR,
]:
    _d.mkdir(parents=True, exist_ok=True)
