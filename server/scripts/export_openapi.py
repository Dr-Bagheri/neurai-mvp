"""Dump the OpenAPI schema for the webui's TS client generation (D6):

    python scripts/export_openapi.py [out.json]

then in webui/:  npx openapi-typescript openapi.json -o src/api/schema.d.ts
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# Isolated data dir so exporting the schema never touches a real install.
os.environ.setdefault("NEURAI_DATA_DIR", tempfile.mkdtemp(prefix="neurai-openapi-"))
os.environ.setdefault("NEURAI_ASR", "fake")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from neurai.main import create_app  # noqa: E402

out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2] / "webui" / "openapi.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(create_app().openapi(), ensure_ascii=False, indent=2), encoding="utf-8")
print(f"OpenAPI schema written to {out}")
