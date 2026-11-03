"""Export the API contract for the frontend (BACKEND.md B10).

Writes backend/openapi.json. The frontend generates types from it, e.g.:
  npx openapi-typescript openapi.json -o lib/api-types.ts

Usage: uv run python scripts/export_openapi.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "openapi.json"


def main() -> None:
    schema = app.openapi()
    OUT.write_text(json.dumps(schema, indent=2) + "\n")
    print(f"wrote {OUT} ({len(schema['paths'])} paths)")


if __name__ == "__main__":
    main()
