#!/usr/bin/env python3
"""Validate, fingerprint, and send the HTML report through Feishu Mail."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formatdate, make_msgid
from pathlib import Path
from typing import Any

from risk_common import canonical_json, dump_json, load_json, validate_analysis, validate_html

EMAIL_RE = re.compile(r"^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$")


def expand_recipients(values: list[str] | None) -> list[str]:
    result: list[str] = []
    for value in values or []:
        for part in re.split(r"[,;]", value):
            address = part.strip()
            if address and address not in result:
                result.append(address)
    return result


def locate_lark(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    found = shutil.which("lark-cli") or shutil.which("lark-cli.cmd") or shutil.which("lark-cli.ps1")
    if found:
        return found
    candidate = Path(os.environ.get("APPDATA", "")) / "QClaw" / "npm-global" / "lark-cli.ps1"
    return str(candidate) if candidate.is_file() else None


def command_prefix(lark: str) -> list[str]:
    if lark.lower().endswith(".ps1"):
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if not powershell:
            raise RuntimeError("PowerShell is required to run lark-cli.ps1")
        return [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", lark]
    return [lark]


def run_lark(prefix: list[str], args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        prefix + args,
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


def parse_json_output(output: str) -> Any:
    output = output.strip()
    if not output:
        return {}
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        start = output.find("{")
        end = output.rfind("}")
        if start >= 0 and end > start:
            return json.loads(output[start : end + 1])
        raise


def find_value(value: Any, keys: set[str]) -> Any:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in keys and item not in (None, ""):
                return item
        for item in value.values():
            found = find_value(item, keys)
            if found not in (None, ""):
                return found
    elif isinstance(value, list):
        for item in value:
            found = find_value(item, keys)
            if found not in (None, ""):
                return found
    return None


def build_message(from_address: str, to: list[str], cc: list[str], bcc: list[str], subject: str, report_path: Path, html_text: str) -> bytes:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = from_address
    message["To"] = ", ".join(to)
    if cc:
        message["Cc"] = ", ".join(cc)
    if bcc:
        message["Bcc"] = ", ".join(bcc)
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain=from_address.rsplit("@", 1)[-1])
    message.set_content("请使用支持 HTML 的邮件客户端查看《广东金融监管风险提示报告》，完整报告同时见附件。", charset="utf-8")
    message.add_alternative(html_text, subtype="html", charset="utf-8")
    message.add_attachment(
        report_path.read_bytes(),
        maintype="text",
        subtype="html",
        filename="regulatory-risk-report.html",
    )
    return message.as_bytes(policy=SMTP)


def write_receipt(path: Path, status: str, **extra: Any) -> None:
    receipt = {"status": status, "at": datetime.now().astimezone().isoformat(timespec="seconds"), **extra}
    dump_json(path, receipt)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--to", action="append")
    parser.add_argument("--cc", action="append")
    parser.add_argument("--bcc", action="append")
    parser.add_argument("--subject")
    parser.add_argument("--lark-cli")
    parser.add_argument("--ledger")
    parser.add_argument("--receipt")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--preflight", action="store_true", help="check all gates including live authentication without creating or sending a draft")
    args = parser.parse_args()

    analysis_path = Path(args.analysis).resolve()
    report_path = Path(args.report).resolve()
    internal_dir = report_path.parent / "internal"
    ledger_path = Path(args.ledger).resolve() if args.ledger else internal_dir / "send-ledger.json"
    receipt_path = Path(args.receipt).resolve() if args.receipt else internal_dir / "delivery-receipt.json"
    to, cc, bcc = expand_recipients(args.to), expand_recipients(args.cc), expand_recipients(args.bcc)

    if not to:
        write_receipt(receipt_path, "awaiting_recipient", reason="delivery.to is empty")
        print(json.dumps({"status": "awaiting_recipient", "receipt": str(receipt_path)}, ensure_ascii=False))
        return 3
    invalid = [address for address in to + cc + bcc if not EMAIL_RE.fullmatch(address)]
    if invalid:
        write_receipt(receipt_path, "invalid_recipient", invalid=invalid)
        print(json.dumps({"status": "invalid_recipient", "invalid": invalid}, ensure_ascii=False))
        return 4
    if not analysis_path.is_file() or not report_path.is_file():
        write_receipt(receipt_path, "artifact_missing", analysis=str(analysis_path), report=str(report_path))
        print(json.dumps({"status": "artifact_missing"}, ensure_ascii=False))
        return 5

    analysis = load_json(analysis_path)
    report_bytes = report_path.read_bytes()
    try:
        report_html = report_bytes.decode("utf-8")
    except UnicodeDecodeError:
        write_receipt(receipt_path, "validation_failed", errors=["report HTML must be UTF-8"])
        return 6
    errors, warnings = validate_analysis(analysis)
    html_errors, html_warnings = validate_html(report_html)
    errors.extend(html_errors)
    warnings.extend(html_warnings)
    if errors:
        write_receipt(receipt_path, "validation_failed", errors=errors, warnings=warnings)
        print(json.dumps({"status": "validation_failed", "errors": errors}, ensure_ascii=False, indent=2))
        return 6

    fingerprint_payload = {
        "report_sha256": hashlib.sha256(report_bytes).hexdigest(),
        "profile": analysis.get("enterprise_profile"),
        "task_snapshots": [
            {key: task.get(key) for key in ("task_id", "role", "snapshot", "record_count")}
            for task in analysis.get("report_meta", {}).get("source_tasks", [])
        ],
        "recipients": {"to": sorted(to), "cc": sorted(cc), "bcc": sorted(bcc)},
    }
    fingerprint = hashlib.sha256(canonical_json(fingerprint_payload).encode("utf-8")).hexdigest()
    ledger: dict[str, Any] = {"sent": []}
    if ledger_path.is_file():
        try:
            ledger = load_json(ledger_path)
        except (OSError, ValueError, json.JSONDecodeError):
            write_receipt(receipt_path, "ledger_unreadable", ledger=str(ledger_path))
            return 7
    prior = [item for item in ledger.get("sent", []) if item.get("fingerprint") == fingerprint]
    if prior:
        write_receipt(receipt_path, "duplicate_blocked", fingerprint=fingerprint, prior=prior[-1])
        print(json.dumps({"status": "duplicate_blocked", "fingerprint": fingerprint}, ensure_ascii=False))
        return 8

    lark = locate_lark(args.lark_cli)
    if not lark:
        write_receipt(receipt_path, "lark_cli_missing", fingerprint=fingerprint)
        return 9
    try:
        prefix = command_prefix(lark)
    except RuntimeError as exc:
        write_receipt(receipt_path, "lark_cli_missing", fingerprint=fingerprint, reason=str(exc))
        return 9

    subject = args.subject or str(analysis.get("report_meta", {}).get("title") or "广东金融监管风险提示报告")
    with tempfile.TemporaryDirectory(prefix="reg-risk-mail-") as temporary:
        temp = Path(temporary)
        create_params = temp / "create-params.json"
        create_data = temp / "create-data.json"
        send_params = temp / "send-params.json"
        send_data = temp / "send-data.json"
        create_params.write_text(json.dumps({"user_mailbox_id": "me"}), encoding="utf-8")
        send_data.write_text("{}", encoding="utf-8")

        if args.dry_run:
            from_address = "dry-run@example.com"
        else:
            doctor = run_lark(prefix, ["doctor"], temp)
            doctor_text = (doctor.stdout + "\n" + doctor.stderr).strip()
            doctor_lower = doctor_text.lower().replace(" ", "")
            if doctor.returncode != 0 or "expired" in doctor_lower or '"ok":false' in doctor_lower or "ok:false" in doctor_lower:
                write_receipt(
                    receipt_path,
                    "auth_required",
                    fingerprint=fingerprint,
                    reason="lark-cli doctor did not confirm valid authentication",
                    doctor_excerpt=doctor_text[-1500:],
                )
                print(json.dumps({"status": "auth_required", "receipt": str(receipt_path)}, ensure_ascii=False))
                return 10
            profile = run_lark(
                prefix,
                ["mail", "user_mailboxes", "profile", "--params", "@create-params.json", "--as", "user", "--format", "json"],
                temp,
            )
            if profile.returncode != 0:
                write_receipt(receipt_path, "auth_required", fingerprint=fingerprint, reason=profile.stderr or profile.stdout)
                return 10
            try:
                profile_data = parse_json_output(profile.stdout)
            except json.JSONDecodeError:
                write_receipt(receipt_path, "auth_required", fingerprint=fingerprint, reason="mailbox profile response was not JSON")
                return 10
            from_address = str(find_value(profile_data, {"primary_email_address"}) or "")
            if not EMAIL_RE.fullmatch(from_address):
                write_receipt(receipt_path, "auth_required", fingerprint=fingerprint, reason="current mailbox address unavailable")
                return 10

        if args.preflight:
            write_receipt(
                receipt_path,
                "ready_to_send",
                fingerprint=fingerprint,
                from_address=from_address,
                recipients={"to": to, "cc": cc, "bcc": bcc},
                report_sha256=fingerprint_payload["report_sha256"],
                warnings=warnings,
            )
            print(json.dumps({"status": "ready_to_send", "fingerprint": fingerprint}, ensure_ascii=False))
            return 0

        raw_message = build_message(from_address, to, cc, bcc, subject, report_path, report_html)
        raw_base64url = base64.urlsafe_b64encode(raw_message).decode("ascii").rstrip("=")
        create_data.write_text(json.dumps({"raw": raw_base64url}, ensure_ascii=False), encoding="utf-8")

        create_args = [
            "mail", "user_mailbox.drafts", "create",
            "--params", "@create-params.json",
            "--data", "@create-data.json",
            "--as", "user", "--format", "json",
        ]
        if args.dry_run:
            create_result = run_lark(prefix, create_args + ["--dry-run"], temp)
            send_params.write_text(json.dumps({"user_mailbox_id": "me", "draft_id": "dry-run-draft-id"}), encoding="utf-8")
            send_args = [
                "mail", "user_mailbox.drafts", "send",
                "--params", "@send-params.json",
                "--data", "@send-data.json",
                "--as", "user", "--format", "json", "--yes", "--dry-run",
            ]
            send_result = run_lark(prefix, send_args, temp)
            if create_result.returncode != 0 or send_result.returncode != 0:
                write_receipt(receipt_path, "dry_run_failed", fingerprint=fingerprint, create_error=create_result.stderr, send_error=send_result.stderr)
                return 11
            write_receipt(
                receipt_path,
                "dry_run_passed",
                fingerprint=fingerprint,
                recipients={"to": to, "cc": cc, "bcc": bcc},
                mime_bytes=len(raw_message),
                report_sha256=fingerprint_payload["report_sha256"],
                warnings=warnings,
            )
            print(json.dumps({"status": "dry_run_passed", "fingerprint": fingerprint, "mime_bytes": len(raw_message)}, ensure_ascii=False))
            return 0

        create_result = run_lark(prefix, create_args, temp)
        if create_result.returncode != 0:
            write_receipt(receipt_path, "draft_create_failed", fingerprint=fingerprint, error=create_result.stderr or create_result.stdout)
            return 12
        try:
            create_response = parse_json_output(create_result.stdout)
            draft_id = str(find_value(create_response, {"draft_id", "id"}) or "")
        except json.JSONDecodeError:
            draft_id = ""
        if not draft_id:
            write_receipt(receipt_path, "draft_create_failed", fingerprint=fingerprint, error="draft id missing", response=create_result.stdout[-2000:])
            return 12

        send_params.write_text(json.dumps({"user_mailbox_id": "me", "draft_id": draft_id}), encoding="utf-8")
        send_result = run_lark(
            prefix,
            [
                "mail", "user_mailbox.drafts", "send",
                "--params", "@send-params.json",
                "--data", "@send-data.json",
                "--as", "user", "--format", "json", "--yes",
            ],
            temp,
        )
        if send_result.returncode != 0:
            write_receipt(receipt_path, "send_failed", fingerprint=fingerprint, draft_id=draft_id, error=send_result.stderr or send_result.stdout)
            return 13
        try:
            send_response = parse_json_output(send_result.stdout)
        except json.JSONDecodeError:
            send_response = {"raw_output": send_result.stdout[-2000:]}
        message_id = find_value(send_response, {"message_id"})
        entry = {
            "fingerprint": fingerprint,
            "sent_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "draft_id": draft_id,
            "message_id": message_id,
            "to": to,
            "cc": cc,
            "bcc": bcc,
            "report_sha256": fingerprint_payload["report_sha256"],
        }
        ledger.setdefault("sent", []).append(entry)
        dump_json(ledger_path, ledger)
        write_receipt(receipt_path, "sent", **entry, warnings=warnings)
        print(json.dumps({"status": "sent", "message_id": message_id, "fingerprint": fingerprint}, ensure_ascii=False))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
