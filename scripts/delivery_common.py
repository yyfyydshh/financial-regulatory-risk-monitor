#!/usr/bin/env python3
"""Shared publication gates, fingerprints, receipts, and message builders."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formatdate, make_msgid
from pathlib import Path
from typing import Any

from risk_common import canonical_json, dump_json, load_json, validate_analysis, validate_html


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
FEISHU_USER_RE = re.compile(r"^ou_[A-Za-z0-9_-]+$")
FEISHU_CHAT_RE = re.compile(r"^oc_[A-Za-z0-9_-]+$")


class DeliveryBlocked(RuntimeError):
    """A publication gate failed before a complete delivery."""

    def __init__(self, status: str, exit_code: int, **details: Any) -> None:
        super().__init__(status)
        self.status = status
        self.exit_code = exit_code
        self.details = details


@dataclass
class DeliveryContext:
    analysis: dict[str, Any]
    analysis_path: Path
    report_path: Path
    report_html: str
    report_bytes: bytes
    report_sha256: str
    fingerprint: str
    warnings: list[str]
    ledger_path: Path
    ledger: dict[str, Any]


def expand_values(groups: list[str] | None) -> list[str]:
    values: list[str] = []
    for group in groups or []:
        values.extend(item.strip() for item in group.split(",") if item.strip())
    return values


def write_receipt(path: Path, status: str, **details: Any) -> None:
    dump_json(
        path,
        {
            "status": status,
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            **details,
        },
    )


def prepare_delivery(
    analysis_path: Path,
    report_path: Path,
    channel: str,
    destination: dict[str, Any],
    ledger_path: Path,
) -> DeliveryContext:
    if not analysis_path.is_file() or not report_path.is_file():
        raise DeliveryBlocked(
            "artifact_missing",
            5,
            analysis=str(analysis_path),
            report=str(report_path),
        )

    analysis = load_json(analysis_path)
    report_bytes = report_path.read_bytes()
    try:
        report_html = report_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DeliveryBlocked(
            "validation_failed",
            6,
            errors=["report HTML must be UTF-8"],
        ) from exc

    errors, warnings = validate_analysis(analysis)
    html_errors, html_warnings = validate_html(report_html)
    errors.extend(html_errors)
    warnings.extend(html_warnings)
    if errors:
        raise DeliveryBlocked(
            "validation_failed",
            6,
            errors=errors,
            warnings=warnings,
        )

    report_sha256 = hashlib.sha256(report_bytes).hexdigest()
    fingerprint_payload = {
        "channel": channel,
        "report_sha256": report_sha256,
        "profile": analysis.get("enterprise_profile"),
        "task_snapshots": [
            {
                key: task.get(key)
                for key in ("task_id", "role", "snapshot", "record_count")
            }
            for task in analysis.get("report_meta", {}).get("source_tasks", [])
        ],
        "destination": destination,
    }
    fingerprint = hashlib.sha256(
        canonical_json(fingerprint_payload).encode("utf-8")
    ).hexdigest()

    ledger: dict[str, Any] = {"sent": []}
    if ledger_path.is_file():
        try:
            ledger = load_json(ledger_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise DeliveryBlocked(
                "ledger_unreadable",
                7,
                ledger=str(ledger_path),
            ) from exc
    prior = [
        item
        for item in ledger.get("sent", [])
        if item.get("fingerprint") == fingerprint
    ]
    if prior:
        raise DeliveryBlocked(
            "duplicate_blocked",
            8,
            fingerprint=fingerprint,
            prior=prior[-1],
        )

    return DeliveryContext(
        analysis=analysis,
        analysis_path=analysis_path,
        report_path=report_path,
        report_html=report_html,
        report_bytes=report_bytes,
        report_sha256=report_sha256,
        fingerprint=fingerprint,
        warnings=warnings,
        ledger_path=ledger_path,
        ledger=ledger,
    )


def record_sent(context: DeliveryContext, entry: dict[str, Any]) -> None:
    context.ledger.setdefault("sent", []).append(
        {
            "fingerprint": context.fingerprint,
            "sent_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "report_sha256": context.report_sha256,
            **entry,
        }
    )
    dump_json(context.ledger_path, context.ledger)


def build_email_message(
    from_address: str,
    to: list[str],
    cc: list[str],
    subject: str,
    report_path: Path,
    html_text: str,
) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = from_address
    message["To"] = ", ".join(to)
    if cc:
        message["Cc"] = ", ".join(cc)
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain=from_address.rsplit("@", 1)[-1])
    message.set_content(
        "请使用支持 HTML 的邮件客户端查看《金融监管风险提示报告》，完整报告同时见附件。",
        charset="utf-8",
    )
    message.add_alternative(html_text, subtype="html", charset="utf-8")
    message.add_attachment(
        report_path.read_bytes(),
        maintype="text",
        subtype="html",
        filename="regulatory-risk-report.html",
    )
    return message


def message_bytes(message: EmailMessage) -> bytes:
    return message.as_bytes(policy=SMTP)


def build_feishu_summary(analysis: dict[str, Any]) -> str:
    meta = analysis.get("report_meta", {})
    profile = analysis.get("enterprise_profile", {})
    summary = analysis.get("executive_summary", {})
    findings = [
        item
        for item in analysis.get("findings", [])
        if item.get("severity") != "not_applicable"
    ]
    levels = {"critical": 0, "high": 0, "medium": 0, "watch": 0}
    for finding in findings:
        severity = str(finding.get("severity") or "")
        if severity in levels:
            levels[severity] += 1

    lines = [
        f"**{meta.get('title') or '金融监管风险提示报告'}**",
        "",
        f"企业：{profile.get('company_name') or '未命名企业'}",
        (
            "风险概览："
            f"严重 {levels['critical']}｜高 {levels['high']}｜"
            f"中 {levels['medium']}｜观察 {levels['watch']}"
        ),
        "",
        str(summary.get("management_conclusion") or "请查看完整报告。")[:800],
    ]
    risk_points = [
        str(item.get("risk_point") or "").strip()
        for item in findings
        if str(item.get("risk_point") or "").strip()
    ][:3]
    if risk_points:
        lines.extend(["", "**优先风险点**"])
        lines.extend(f"{index}. {point}" for index, point in enumerate(risk_points, 1))
    actions = [
        str(item).strip()
        for item in summary.get("immediate_actions", [])
        if str(item).strip()
    ][:3]
    if actions:
        lines.extend(["", "**立即举措**"])
        lines.extend(f"{index}. {action}" for index, action in enumerate(actions, 1))
    lines.extend(["", "完整证据、适用逻辑与落地策略见随附 HTML 报告。"])
    return "\n".join(lines)[:3800]
