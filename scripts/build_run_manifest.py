#!/usr/bin/env python3
"""Create a verified current-run provenance manifest for full collection exports."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from normalize_records import load_rows
from risk_common import dump_json, load_json


ALLOWED_ROLES = {"regulatory_notice", "enforcement_penalty"}
COMPLETED_STATES = {"completed", "exported", "finished"}


def build_manifest(metadata: dict[str, Any]) -> dict[str, Any]:
    tasks = metadata.get("source_tasks", [])
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("source_tasks must be a non-empty array")

    verified: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for position, task in enumerate(tasks):
        prefix = f"source_tasks[{position}]"
        if not isinstance(task, dict):
            raise ValueError(f"{prefix} must be an object")
        task_id = str(task.get("task_id", "")).strip()
        task_name = str(task.get("task_name", "")).strip()
        role = str(task.get("role", "")).strip()
        status = str(task.get("status", "")).strip().lower()
        export_url = str(task.get("export_url", "")).strip()
        export_path = Path(str(task.get("export_path", "")).strip())
        if not task_id or task_id in seen_ids:
            raise ValueError(f"{prefix}.task_id is missing or duplicated")
        seen_ids.add(task_id)
        if not task_name:
            raise ValueError(f"{prefix}.task_name is required")
        if role not in ALLOWED_ROLES:
            raise ValueError(f"{prefix}.role is invalid")
        if status not in COMPLETED_STATES:
            raise ValueError(f"{prefix}.status is not completed/exported")
        if not export_url.startswith("https://"):
            raise ValueError(f"{prefix}.export_url must be an HTTPS URL")
        if not export_path.is_file():
            raise ValueError(f"{prefix}.export_path does not exist: {export_path}")

        payload = export_path.read_bytes()
        rows = load_rows(export_path)
        verified.append(
            {
                "task_id": task_id,
                "task_name": task_name,
                "role": role,
                "status": status,
                "export_url": export_url,
                "export_path": str(export_path.resolve()),
                "record_count": len(rows),
                "bytes": len(payload),
                "snapshot": hashlib.sha256(payload).hexdigest(),
            }
        )
    return {"source_tasks": verified}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", required=True, help="current-run task metadata JSON")
    parser.add_argument("--output", required=True, help="collection-provenance.json")
    args = parser.parse_args()

    metadata = load_json(Path(args.metadata))
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be a JSON object")
    manifest = build_manifest(metadata)
    output = Path(args.output)
    dump_json(output, manifest)
    print(
        json.dumps(
            {
                "status": "verified",
                "tasks": len(manifest["source_tasks"]),
                "records": sum(item["record_count"] for item in manifest["source_tasks"]),
                "output": str(output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
