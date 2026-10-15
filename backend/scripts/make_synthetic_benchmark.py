"""Write the committed synthetic benchmark (`opera-synthetic-v1`). It only exercises the evaluation harness."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.eval.synthetic import write_synthetic_dataset  # noqa: E402

if __name__ == "__main__":
    print(write_synthetic_dataset(get_settings().benchmark_dir))
