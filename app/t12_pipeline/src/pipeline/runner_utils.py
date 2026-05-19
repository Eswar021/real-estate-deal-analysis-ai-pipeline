import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def run_python_script(script_path: Path, args: list[str] | None = None) -> None:
    command = [sys.executable, str(script_path), *(args or [])]
    rel_path = script_path.relative_to(PROJECT_ROOT)
    print(f"[runner] {' '.join(command[:1])} {rel_path} {' '.join(args or [])}".rstrip())
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)
