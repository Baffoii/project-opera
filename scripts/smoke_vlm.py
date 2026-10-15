"""Repo-root entry point so `python scripts/smoke_vlm.py` works; runs the backend script in its venv."""

import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
venv_python = root / "backend" / ".venv" / "bin" / "python"
python = str(venv_python) if venv_python.exists() else sys.executable
sys.exit(subprocess.call([python, str(root / "backend" / "scripts" / "smoke_vlm.py"), *sys.argv[1:]], env=os.environ))
