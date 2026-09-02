"""Regenerate `docs/reference/api-spec.yaml` from the running app.

The spec is a generated artefact — see `docs/conventions/README.md`. Run after changing any
endpoint or request/response model:

    cd backend && SCENEFLOW_DB_PATH=/tmp/sf_spec.db .venv/bin/python scripts/regen_api_spec.py
"""

from __future__ import annotations

from pathlib import Path

import yaml

from app.main import app


HEADER = (
    "# SceneFlow backend OpenAPI spec.\n"
    "# GENERATED FILE - do not hand-edit. Regenerate with scripts/regen_api_spec.py.\n"
)
TARGET = Path(__file__).resolve().parents[2] / "docs" / "reference" / "api-spec.yaml"


def main() -> None:
    with TARGET.open("w", encoding="utf-8") as handle:
        handle.write(HEADER)
        yaml.safe_dump(app.openapi(), handle, allow_unicode=True, sort_keys=False, width=100)
    print(f"regenerated {TARGET}")


if __name__ == "__main__":
    main()
