#!/usr/bin/env python3
"""Validate evidence gates and optional rendered HTML before publication."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from risk_common import canonical_json, dump_json, load_json, validate_analysis, validate_html


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--html")
    parser.add_argument("--result")
    args = parser.parse_args()

    analysis = load_json(args.analysis)
    errors, warnings = validate_analysis(analysis)
    html_sha256 = None
    if args.html:
        report_path = Path(args.html)
        if not report_path.is_file():
            errors.append(f"HTML report not found: {report_path}")
        else:
            raw = report_path.read_bytes()
            html_sha256 = hashlib.sha256(raw).hexdigest()
            try:
                report_html = raw.decode("utf-8")
            except UnicodeDecodeError:
                errors.append("HTML report must be UTF-8")
            else:
                html_errors, html_warnings = validate_html(report_html)
                errors.extend(html_errors)
                warnings.extend(html_warnings)
                for placeholder in ("{{TITLE}}", "{{CONTENT}}", "{{DISCLAIMER}}"):
                    if placeholder in report_html:
                        errors.append(f"unresolved HTML placeholder: {placeholder}")

    result = {
        "status": "passed" if not errors else "failed",
        "analysis_sha256": hashlib.sha256(canonical_json(analysis).encode("utf-8")).hexdigest(),
        "html_sha256": html_sha256,
        "errors": errors,
        "warnings": warnings,
        "finding_count": len(analysis.get("findings", [])) if isinstance(analysis, dict) else 0,
    }
    if args.result:
        dump_json(args.result, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
