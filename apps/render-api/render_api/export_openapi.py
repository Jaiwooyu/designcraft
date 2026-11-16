"""Export the same schema served at /openapi.json without starting any workers."""

import argparse
import json
from pathlib import Path

from .app import create_app


def main():
    parser = argparse.ArgumentParser(description="Export the Render API OpenAPI JSON")
    parser.add_argument("--output", type=Path, default=Path("docs/openapi.json"))
    arguments = parser.parse_args()
    schema = create_app().openapi()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    operations = sum(
        method in {"get", "post", "delete"} for path in schema["paths"].values() for method in path
    )
    print(f"Exported {operations} operations to {arguments.output}")


if __name__ == "__main__":
    main()
