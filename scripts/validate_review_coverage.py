#!/usr/bin/env python3
"""Validate that every indexed record received an explicit semantic disposition."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from risk_common import dump_json, load_json


REVIEW_DEPTHS = {"screened", "full_body"}
DISPOSITIONS = {"candidate", "excluded", "pending"}


def validate(index: dict[str, Any], ledger: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    index_records = index.get("records", [])
    ledger_records = ledger.get("records", [])
    if not isinstance(index_records, list):
        return ["evidence index records must be an array"]
    if not isinstance(ledger_records, list):
        return ["review ledger records must be an array"]

    expected = {
        str(item.get("record_id", "")).strip()
        for item in index_records
        if isinstance(item, dict) and str(item.get("record_id", "")).strip()
    }
    seen: set[str] = set()
    for position, item in enumerate(ledger_records):
        prefix = f"records[{position}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        record_id = str(item.get("record_id", "")).strip()
        if not record_id:
            errors.append(f"{prefix}.record_id is required")
        elif record_id in seen:
            errors.append(f"duplicate record_id: {record_id}")
        seen.add(record_id)
        depth = item.get("review_depth")
        disposition = item.get("disposition")
        if depth not in REVIEW_DEPTHS:
            errors.append(f"{prefix}.review_depth must be screened or full_body")
        if disposition not in DISPOSITIONS:
            errors.append(f"{prefix}.disposition is invalid")
        if disposition in {"candidate", "pending"} and depth != "full_body":
            errors.append(f"{prefix}: candidate/pending records require full_body review")
        if not str(item.get("reason", "")).strip():
            errors.append(f"{prefix}.reason is required")

    missing = sorted(expected - seen)
    unexpected = sorted(seen - expected)
    if missing:
        errors.append(f"missing semantic reviews for {len(missing)} record(s): {', '.join(missing[:10])}")
    if unexpected:
        errors.append(f"review ledger contains {len(unexpected)} unknown record(s): {', '.join(unexpected[:10])}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, help="evidence-index.json")
    parser.add_argument("--ledger", required=True, help="semantic-review-ledger.json")
    parser.add_argument("--result", help="optional validation result JSON")
    args = parser.parse_args()

    index = load_json(Path(args.index))
    ledger = load_json(Path(args.ledger))
    if not isinstance(index, dict) or not isinstance(ledger, dict):
        raise ValueError("index and ledger must be JSON objects")
    errors = validate(index, ledger)
    result = {
        "status": "passed" if not errors else "failed",
        "indexed_records": len(index.get("records", [])),
        "reviewed_records": len(ledger.get("records", [])),
        "errors": errors,
    }
    if args.result:
        dump_json(Path(args.result), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
