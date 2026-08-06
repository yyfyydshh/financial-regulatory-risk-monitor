#!/usr/bin/env python3
"""Build a complete, topic-neutral inventory of normalized regulatory records."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from risk_common import dump_json, load_json


INDEX_FIELDS = (
    "record_id",
    "source_type",
    "source_task_id",
    "title",
    "authority",
    "document_number",
    "published_at",
    "effective_date",
    "effective_status",
    "source_url",
    "official_source",
    "source_text_complete",
)


def make_index(normalized: dict[str, Any], provenance: dict[str, Any]) -> dict[str, Any]:
    records = normalized.get("records", [])
    if not isinstance(records, list):
        raise ValueError("normalized records must be an array")

    indexed_records: list[dict[str, Any]] = []
    reviewed_ids: set[str] = set()
    for position, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise ValueError(f"records[{position - 1}] must be an object")
        record_id = str(record.get("record_id", "")).strip()
        if not record_id:
            raise ValueError(f"records[{position - 1}].record_id is required")
        if record_id in reviewed_ids:
            raise ValueError(f"duplicate record_id: {record_id}")
        reviewed_ids.add(record_id)
        item = {field: record.get(field, "") for field in INDEX_FIELDS}
        body = str(record.get("body", ""))
        item["position"] = position
        item["body_chars"] = len(body)
        item["body_head"] = body[:240]
        item["raw_keys"] = sorted(str(key) for key in record.get("raw", {}) if isinstance(record.get("raw"), dict))
        indexed_records.append(item)

    dates = sorted(
        str(item["published_at"])
        for item in indexed_records
        if str(item.get("published_at", "")).strip()
    )
    return {
        "current_run_provenance": provenance.get("source_tasks", []),
        "generated_from": {
            "raw_count": normalized.get("raw_count", len(records)),
            "normalized_count": normalized.get("normalized_count", len(records)),
            "deduplicated_count": normalized.get("deduplicated_count", len(records)),
            "duplicates_removed": normalized.get("duplicates_removed", 0),
            "sources": normalized.get("sources", []),
        },
        "coverage": {
            "indexed_record_count": len(indexed_records),
            "semantic_review_complete": False,
            "first_published_at": dates[0] if dates else "",
            "last_published_at": dates[-1] if dates else "",
            "source_types": dict(Counter(str(item["source_type"]) for item in indexed_records)),
            "effective_statuses": dict(Counter(str(item["effective_status"]) for item in indexed_records)),
            "official_source_records": sum(bool(item["official_source"]) for item in indexed_records),
            "complete_text_records": sum(bool(item["source_text_complete"]) for item in indexed_records),
            "missing_titles": sum(not str(item["title"]).strip() for item in indexed_records),
            "missing_dates": sum(not str(item["published_at"]).strip() for item in indexed_records),
            "missing_urls": sum(not str(item["source_url"]).strip() for item in indexed_records),
        },
        "records": indexed_records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="normalized-records.json")
    parser.add_argument("--provenance", required=True, help="verified collection-provenance.json")
    parser.add_argument("--output", required=True, help="evidence-index.json")
    args = parser.parse_args()

    source = Path(args.input)
    target = Path(args.output)
    normalized = load_json(source)
    provenance = load_json(Path(args.provenance))
    if not isinstance(normalized, dict):
        raise ValueError("normalized input must be an object")
    if not isinstance(provenance, dict) or not provenance.get("source_tasks"):
        raise ValueError("verified current-run provenance is required")
    index = make_index(normalized, provenance)
    dump_json(target, index)
    print(
        json.dumps(
            {
                "status": "indexed",
                "records": index["coverage"]["indexed_record_count"],
                "output": str(target),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
