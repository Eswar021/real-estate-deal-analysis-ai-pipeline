import subprocess
import sys


def run_python_module(module: str, args: list[str] | None = None) -> None:
    """Invoke a Python module via `python -m`."""
    command = [sys.executable, "-m", module, *(args or [])]
    print(f"[runner] python -m {module} {' '.join(args or [])}".rstrip())
    subprocess.run(command, check=True)
