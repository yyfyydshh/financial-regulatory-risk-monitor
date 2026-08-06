#!/usr/bin/env python3
"""Publish a report summary and HTML attachment to fixed Feishu users or chats."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from delivery_common import (
    FEISHU_CHAT_RE,
    FEISHU_USER_RE,
    DeliveryBlocked,
    build_feishu_summary,
    expand_values,
    prepare_delivery,
    record_sent,
    write_receipt,
)


def locate_lark(explicit: str | None) -> Path | None:
    if explicit:
        candidate = Path(explicit).expanduser().resolve()
        return candidate if candidate.is_file() else None
    located = shutil.which("lark-cli") or shutil.which("lark-cli.ps1")
    return Path(located).resolve() if located else None


def command_prefix(lark: Path) -> list[str]:
    suffix = lark.suffix.lower()
    if suffix == ".ps1":
        return [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(lark),
        ]
    if suffix == ".py":
        return [sys.executable, str(lark)]
    return [str(lark)]


def run_lark(prefix: list[str], args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        prefix + args,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


def parse_json_output(output: str) -> Any:
    stripped = output.strip()
    if not stripped:
        return {}
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            return json.loads(stripped[start : end + 1])
        raise


def find_message_id(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("message_id", "messageId"):
            if value.get(key):
                return str(value[key])
        for nested in value.values():
            found = find_message_id(nested)
            if found:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = find_message_id(nested)
            if found:
                return found
    return ""


def target_args(kind: str, target_id: str) -> list[str]:
    return ["--user-id", target_id] if kind == "user" else ["--chat-id", target_id]


def idempotency_key(fingerprint: str, kind: str, target_id: str, part: str) -> str:
    target_hash = hashlib.sha256(f"{kind}:{target_id}".encode("utf-8")).hexdigest()
    return f"reg-risk-{fingerprint[:20]}-{target_hash[:10]}-{part}"


def output_status(status: str, **details: Any) -> None:
    print(json.dumps({"status": status, **details}, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--user-id", action="append")
    parser.add_argument("--chat-id", action="append")
    parser.add_argument("--as", dest="identity", choices=("user", "bot"), default="user")
    parser.add_argument("--lark-cli")
    parser.add_argument("--ledger")
    parser.add_argument("--receipt")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument(
        "--preflight",
        action="store_true",
        help="check CLI authentication without posting",
    )
    args = parser.parse_args()

    analysis_path = Path(args.analysis).resolve()
    report_path = Path(args.report).resolve()
    internal_dir = report_path.parent / "internal"
    ledger_path = (
        Path(args.ledger).resolve()
        if args.ledger
        else internal_dir / "send-ledger.json"
    )
    receipt_path = (
        Path(args.receipt).resolve()
        if args.receipt
        else internal_dir / "feishu-message-receipt.json"
    )

    users = expand_values(args.user_id)
    chats = expand_values(args.chat_id)
    if not users and not chats:
        write_receipt(
            receipt_path,
            "awaiting_recipient",
            reason="delivery.feishu.users and delivery.feishu.chats are empty",
        )
        output_status("awaiting_recipient", receipt=str(receipt_path))
        return 3
    invalid_users = [value for value in users if not FEISHU_USER_RE.fullmatch(value)]
    invalid_chats = [value for value in chats if not FEISHU_CHAT_RE.fullmatch(value)]
    if invalid_users or invalid_chats:
        write_receipt(
            receipt_path,
            "invalid_recipient",
            invalid_users=invalid_users,
            invalid_chats=invalid_chats,
        )
        output_status(
            "invalid_recipient",
            invalid_users=invalid_users,
            invalid_chats=invalid_chats,
        )
        return 4

    destination = {
        "identity": args.identity,
        "users": sorted(users),
        "chats": sorted(chats),
    }
    try:
        context = prepare_delivery(
            analysis_path,
            report_path,
            "feishu_cli",
            destination,
            ledger_path,
        )
    except DeliveryBlocked as exc:
        write_receipt(receipt_path, exc.status, **exc.details)
        output_status(exc.status, **{key: value for key, value in exc.details.items() if key != "prior"})
        return exc.exit_code

    lark = locate_lark(args.lark_cli)
    if not lark:
        write_receipt(
            receipt_path,
            "lark_cli_missing",
            channel="feishu_cli",
            fingerprint=context.fingerprint,
        )
        output_status("lark_cli_missing", receipt=str(receipt_path))
        return 9
    prefix = command_prefix(lark)
    summary = build_feishu_summary(context.analysis)
    targets = [("user", value) for value in users] + [
        ("chat", value) for value in chats
    ]

    if args.dry_run:
        planned = [
            {
                "target_type": kind,
                "target_id": target_id,
                "messages": ["management_summary", "html_attachment"],
            }
            for kind, target_id in targets
        ]
        write_receipt(
            receipt_path,
            "dry_run_passed",
            channel="feishu_cli",
            fingerprint=context.fingerprint,
            identity=args.identity,
            planned=planned,
            report_sha256=context.report_sha256,
            warnings=context.warnings,
        )
        output_status(
            "dry_run_passed",
            fingerprint=context.fingerprint,
            targets=len(targets),
        )
        return 0

    if args.identity == "user":
        auth_check = run_lark(prefix, ["doctor"])
        auth_text = (auth_check.stdout + "\n" + auth_check.stderr).strip()
        normalized = auth_text.lower().replace(" ", "")
        auth_ok = (
            auth_check.returncode == 0
            and '"ok":false' not in normalized
            and "expired" not in normalized
            and "pendingapproval" not in normalized
        )
    else:
        auth_check = run_lark(
            prefix,
            [
                "im",
                "+chat-list",
                "--as",
                "bot",
                "--page-size",
                "1",
                "--format",
                "json",
            ],
        )
        auth_text = (auth_check.stdout + "\n" + auth_check.stderr).strip()
        auth_ok = auth_check.returncode == 0
    if not auth_ok:
        write_receipt(
            receipt_path,
            "auth_required",
            channel="feishu_cli",
            fingerprint=context.fingerprint,
            reason="Feishu CLI authentication or app authorization is unavailable",
            auth_excerpt=auth_text[-1500:],
        )
        output_status("auth_required", receipt=str(receipt_path))
        return 10

    if args.preflight:
        write_receipt(
            receipt_path,
            "ready_to_send",
            channel="feishu_cli",
            fingerprint=context.fingerprint,
            identity=args.identity,
            targets=destination,
            report_sha256=context.report_sha256,
            warnings=context.warnings,
        )
        output_status("ready_to_send", fingerprint=context.fingerprint)
        return 0

    delivered: list[dict[str, str]] = []
    failures: list[dict[str, str]] = []
    for kind, target_id in targets:
        common = [
            "im",
            "+messages-send",
            "--as",
            args.identity,
            *target_args(kind, target_id),
        ]
        summary_result = run_lark(
            prefix,
            [
                *common,
                "--markdown",
                summary,
                "--idempotency-key",
                idempotency_key(
                    context.fingerprint,
                    kind,
                    target_id,
                    "summary",
                ),
            ],
        )
        if summary_result.returncode != 0:
            failures.append(
                {
                    "target_type": kind,
                    "target_id": target_id,
                    "part": "management_summary",
                    "error": (summary_result.stderr or summary_result.stdout)[-1000:],
                }
            )
            continue
        try:
            summary_id = find_message_id(parse_json_output(summary_result.stdout))
        except json.JSONDecodeError:
            summary_id = ""
        delivered.append(
            {
                "target_type": kind,
                "target_id": target_id,
                "part": "management_summary",
                "message_id": summary_id,
            }
        )

        file_result = run_lark(
            prefix,
            [
                *common,
                "--file",
                str(report_path),
                "--idempotency-key",
                idempotency_key(
                    context.fingerprint,
                    kind,
                    target_id,
                    "report",
                ),
            ],
        )
        if file_result.returncode != 0:
            failures.append(
                {
                    "target_type": kind,
                    "target_id": target_id,
                    "part": "html_attachment",
                    "error": (file_result.stderr or file_result.stdout)[-1000:],
                }
            )
            continue
        try:
            file_id = find_message_id(parse_json_output(file_result.stdout))
        except json.JSONDecodeError:
            file_id = ""
        delivered.append(
            {
                "target_type": kind,
                "target_id": target_id,
                "part": "html_attachment",
                "message_id": file_id,
            }
        )

    if failures:
        write_receipt(
            receipt_path,
            "partial_send_failed",
            channel="feishu_cli",
            fingerprint=context.fingerprint,
            delivered=delivered,
            failures=failures,
        )
        output_status(
            "partial_send_failed",
            delivered=len(delivered),
            failures=len(failures),
            receipt=str(receipt_path),
        )
        return 13

    entry = {
        "channel": "feishu_cli",
        "identity": args.identity,
        "users": users,
        "chats": chats,
        "messages": delivered,
    }
    record_sent(context, entry)
    write_receipt(
        receipt_path,
        "sent",
        fingerprint=context.fingerprint,
        report_sha256=context.report_sha256,
        warnings=context.warnings,
        **entry,
    )
    output_status(
        "sent",
        fingerprint=context.fingerprint,
        targets=len(targets),
        messages=len(delivered),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
