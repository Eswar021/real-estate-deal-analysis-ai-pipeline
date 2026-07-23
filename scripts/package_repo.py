#!/usr/bin/env python3
"""
Package the repository into a timestamped .zip for delivery to the client.

    python3 scripts/package_repo.py

WHAT GOES IN: exactly the files git tracks (`git ls-files`). This is deliberate — it means
every path in .gitignore is excluded automatically and for free:
  - the secret  app/.env  (untracked)          → never shipped
  - master_docs/, data/, app/ui/storage/        → the large / client-private files
  - __pycache__/, *.pyc, .git/, logs/, db.sqlite3
The working-tree content is read (not the committed blob), so any uncommitted edits are
captured as-is. On top of that, a hard denylist + a final ".env must be absent" assertion make
leaking a secret effectively impossible — the script aborts rather than build an unsafe zip.

Configuration lives in the CONFIG block below — edit those to change the output folder, the
name, or what is force-excluded. Nothing else needs changing.
"""
from __future__ import annotations

import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

# ─── CONFIG — edit these ──────────────────────────────────────────────────────────────────────
# Repo root. Defaults to the parent of this script's folder (scripts/..). Hardcode a path here
# if you ever move this file, e.g. REPO_ROOT = Path("/Users/me/…/Shivam_Excel_AI_Automation").
REPO_ROOT: Path = Path(__file__).resolve().parents[1]

# Where the .zip is written. ~ expands to your home dir.
OUTPUT_DIR: Path = Path.home() / "Downloads"

# Zip file name = f"{ZIP_PREFIX}_{timestamp}.zip"; the same prefix is the top folder INSIDE the
# zip, so it extracts to one clean directory instead of scattering files.
ZIP_PREFIX: str = "Shivam_Excel_AI_Automation"
TIMESTAMP_FMT: str = "%Y%m%d_%H%M%S"

# Belt-and-suspenders. A tracked file is EXCLUDED if any of its path components equals one of
# these. Kept exact-match (not substring) so "app/.env.example" is never mistaken for ".env".
FORCE_EXCLUDE_COMPONENTS: frozenset[str] = frozenset({".env", ".git", "__pycache__", ".DS_Store"})
FORCE_EXCLUDE_SUFFIXES: tuple[str, ...] = (".pyc", ".pyo")
# ──────────────────────────────────────────────────────────────────────────────────────────────


def tracked_files(root: Path) -> list[str]:
    """Repo-relative paths of every git-tracked file (respects .gitignore)."""
    result = subprocess.run(
        ["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def is_force_excluded(rel_path: str) -> bool:
    parts = rel_path.split("/")
    if FORCE_EXCLUDE_COMPONENTS.intersection(parts):
        return True
    return rel_path.endswith(FORCE_EXCLUDE_SUFFIXES)


def looks_like_secret(rel_path: str) -> bool:
    """A real dotenv (`.env`, `foo/.env`) but NOT `.env.example` / `.env.sample`."""
    name = Path(rel_path).name
    return name == ".env" or (name.startswith(".env.") and name.endswith((".local", ".prod")))


def git_is_dirty(root: Path) -> bool:
    out = subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, check=True
    )
    return bool(out.stdout.strip())


def build_zip() -> Path:
    root = REPO_ROOT
    if not (root / ".git").exists():
        sys.exit(f"ABORT: {root} is not a git repository (git ls-files drives this script).")

    files = [f for f in tracked_files(root) if not is_force_excluded(f)]

    # Hard safety gate: never build a zip that contains a real secret file.
    leaked = [f for f in files if looks_like_secret(f)]
    if leaked:
        sys.exit(f"ABORT: secret file(s) would be included, refusing to build: {leaked}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime(TIMESTAMP_FMT)
    zip_path = OUTPUT_DIR / f"{ZIP_PREFIX}_{stamp}.zip"

    written = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in files:
            src = root / rel
            if src.is_file():  # skip submodule gitlinks / deleted-but-tracked paths
                zf.write(src, arcname=f"{ZIP_PREFIX}/{rel}")
                written += 1

    # Post-build verification: prove no .env slipped into the archive.
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        secrets_in_zip = [n for n in names if looks_like_secret(n)]
    if secrets_in_zip:
        zip_path.unlink(missing_ok=True)
        sys.exit(f"ABORT: secret found in built zip, deleted it: {secrets_in_zip}")

    size_mb = zip_path.stat().st_size / 1_000_000
    print(f"✓ {zip_path}")
    print(f"  {written} files · {size_mb:.1f} MB · .env present: no ✓")
    if git_is_dirty(root):
        print("  note: working tree has uncommitted changes — they ARE included as-is.")
    return zip_path


if __name__ == "__main__":
    build_zip()
