"""Write the OpenAPI schema to docs/openapi.json (generated; docs/API.md adds the prose and examples)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import REPO_ROOT, Settings
from app.main import create_app

out = Path(REPO_ROOT) / "docs" / "openapi.json"
schema = create_app(Settings(api_key="x")).openapi()
out.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
print(f"wrote {out}")
