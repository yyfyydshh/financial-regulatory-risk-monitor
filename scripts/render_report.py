#!/usr/bin/env python3
"""Render a validated analysis manifest as self-contained, email-safe HTML."""

from __future__ import annotations

import argparse
import html
import json
from collections import Counter
from pathlib import Path
from typing import Any

from risk_common import CONFIDENCE_LABELS, EFFECT_LABELS, SEVERITY_LABELS, load_json, validate_analysis, validate_html

COLORS = {
    "critical": ("#8f1d1d", "#fff1f0", "#fecaca"),
    "high": ("#9a4d00", "#fff7ed", "#fed7aa"),
    "medium": ("#7c5c00", "#fffbea", "#fde68a"),
    "watch": ("#1856a8", "#eff6ff", "#bfdbfe"),
    "not_applicable": ("#536070", "#f8fafc", "#d9e0e8"),
}
PROFILE_FIELD_LABELS = {
    "company_name": "企业名称",
    "company_type": "机构类型",
    "operating_regions": "经营区域",
    "licensed_activities": "持牌/许可活动",
    "products_and_services": "产品与服务",
    "customer_types": "客户类型",
    "sales_channels": "销售渠道",
    "consumer_protection_exposure": "消费者保护暴露",
    "data_processing_activities": "数据处理活动",
    "technology_outsourcing": "科技外包",
    "anti_money_laundering_exposure": "反洗钱暴露",
    "governance_features": "治理特征",
    "partner_and_intermediary_types": "合作方/中介",
}
OBLIGATION_LABELS = {
    "prohibition": "禁止性要求",
    "mandatory": "强制要求",
    "reporting": "报送/报告",
    "remediation": "整改",
    "internal_control": "内控治理",
    "consumer_protection": "消费者保护",
    "guidance": "倡导/指导",
    "none": "无直接义务",
}


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def clip_text(value: Any, limit: int = 180) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def render_value(value: Any) -> str:
    if value in (None, "", []):
        return '<span style="color:#98a2b3;">未提供</span>'
    if isinstance(value, list):
        return "、".join(esc(item) for item in value) if value else '<span style="color:#98a2b3;">未提供</span>'
    if isinstance(value, dict):
        return "；".join(f"{esc(key)}：{render_value(val)}" for key, val in value.items())
    return esc(value)


def section_title(title: str, subtitle: str = "") -> str:
    sub = f'<div style="font-size:12px;color:#667085;margin-top:3px;">{esc(subtitle)}</div>' if subtitle else ""
    return (
        '<div style="margin:30px 0 14px;border-left:4px solid #2f6fab;padding-left:12px;">'
        f'<div style="font-size:19px;font-weight:700;color:#102a43;">{esc(title)}</div>{sub}</div>'
    )


def render_list(items: Any, empty: str = "无") -> str:
    if isinstance(items, str):
        items = [items]
    if not items:
        return f'<div style="color:#667085;font-size:13px;">{esc(empty)}</div>'
    rows = []
    for item in items:
        if isinstance(item, dict):
            title = item.get("title") or item.get("question") or item.get("theme") or "待办项"
            detail = item.get("detail") or item.get("reason") or item.get("action") or item.get("summary") or ""
            rows.append(
                '<tr><td style="width:18px;vertical-align:top;color:#2f6fab;padding:4px 0;">•</td>'
                f'<td style="padding:4px 0;color:#344054;"><strong>{esc(title)}</strong>'
                f'{("<br><span style=\"font-size:13px;color:#667085;\">" + esc(detail) + "</span>") if detail else ""}</td></tr>'
            )
        else:
            rows.append(
                '<tr><td style="width:18px;vertical-align:top;color:#2f6fab;padding:4px 0;">•</td>'
                f'<td style="padding:4px 0;color:#344054;">{esc(item)}</td></tr>'
            )
    return '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;">' + "".join(rows) + "</table>"


def render_summary(summary: Any) -> str:
    if isinstance(summary, str):
        conclusion, actions, caveats = summary, [], []
    else:
        summary = summary or {}
        conclusion = summary.get("management_conclusion") or summary.get("summary") or ""
        actions = summary.get("immediate_actions", [])
        caveats = summary.get("scope_caveats", [])
    return (
        '<div style="background:#f0f6fb;border:1px solid #c8dced;border-radius:14px;overflow:hidden;">'
        '<div style="padding:11px 18px;background:#dfeefa;color:#174a73;font-size:12px;font-weight:800;letter-spacing:1px;">本期管理判断</div>'
        f'<div style="padding:18px 20px 16px;font-size:15px;line-height:1.8;color:#19324a;font-weight:600;">{esc(conclusion)}</div>'
        + ('<div style="padding:11px 20px;background:#f8fafc;border-top:1px solid #dce6ef;font-size:11px;color:#667085;">范围说明：' + '；'.join(esc(item) for item in caveats) + '</div>' if caveats else "")
        + "</div>"
    )


def render_profile(profile: dict[str, Any], synthetic: bool) -> str:
    groups = (
        ("企业定位", ("company_name", "company_type", "operating_regions", "licensed_activities")),
        ("业务与渠道", ("products_and_services", "customer_types", "sales_channels", "partner_and_intermediary_types")),
        ("重点控制暴露", ("consumer_protection_exposure", "data_processing_activities", "technology_outsourcing", "anti_money_laundering_exposure", "governance_features")),
    )
    group_blocks = []
    for group_name, fields in groups:
        rows = []
        for key in fields:
            rows.append(
                '<tr>'
                f'<td style="width:170px;padding:9px 12px;background:#f8fafc;border:1px solid #e7ebf0;font-size:12px;font-weight:700;color:#475467;vertical-align:top;">{esc(PROFILE_FIELD_LABELS[key])}</td>'
                f'<td style="padding:9px 12px;border:1px solid #e7ebf0;font-size:12px;color:#253b53;vertical-align:top;">{render_value(profile.get(key))}</td>'
                '</tr>'
            )
        group_blocks.append(
            '<div style="margin-top:12px;border:1px solid #dde5ed;border-radius:10px;overflow:hidden;">'
            f'<div style="padding:9px 12px;background:#edf3f8;color:#244761;font-size:12px;font-weight:800;letter-spacing:.5px;">{esc(group_name)}</div>'
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;">' + "".join(rows) + '</table></div>'
        )
    banner = ""
    if synthetic:
        banner = (
            '<div style="margin-bottom:12px;padding:10px 12px;border-radius:8px;background:#fff7ed;border:1px solid #fed7aa;color:#9a4d00;font-size:13px;font-weight:700;">'
            '演示合成画像：仅用于说明能力，不代表任何真实企业。</div>'
        )
    basis = ""
    if synthetic and profile.get("synthetic_basis"):
        basis = '<div style="margin-top:12px;font-size:13px;font-weight:700;color:#475467;">合成依据</div>' + render_list(profile["synthetic_basis"])
    return banner + "".join(group_blocks) + basis


def render_stats(findings: list[dict[str, Any]]) -> str:
    counts = Counter(item.get("severity", "watch") for item in findings)
    cards = []
    for severity in ("critical", "high", "medium", "watch", "not_applicable"):
        fg, bg, border = COLORS[severity]
        cards.append(
            '<td width="20%" style="padding:0 4px;vertical-align:top;">'
            f'<div style="border:1px solid {border};background:{bg};border-radius:10px;padding:13px 8px;text-align:center;">'
            f'<div style="font-size:22px;font-weight:800;color:{fg};">{counts.get(severity, 0)}</div>'
            f'<div style="font-size:12px;font-weight:700;color:{fg};">{SEVERITY_LABELS[severity]}</div></div></td>'
        )
    return (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;"><tr>'
        + "".join(cards)
        + '</tr></table><div style="font-size:11px;color:#667085;margin-top:8px;">等级以文字和颜色同时标识：严重 / 高 / 中 / 观察 / 不适用。</div>'
    )


def finding_badge(severity: str) -> str:
    fg, bg, border = COLORS.get(severity, COLORS["watch"])
    return f'<span style="display:inline-block;padding:3px 9px;border-radius:12px;background:{bg};border:1px solid {border};color:{fg};font-size:12px;font-weight:800;">{SEVERITY_LABELS.get(severity, esc(severity))}</span>'


def render_action_plan(finding: dict[str, Any]) -> str:
    plan = finding.get("action_plan") or []
    if not plan:
        return f'<strong>{esc(finding.get("recommended_action"))}</strong><br><span style="color:#667085;">责任人：{esc(finding.get("recommended_owner")) or "待指定"}　完成时点：{esc(finding.get("due_date")) or "尽快"}</span>'
    rows = []
    for index, step in enumerate(plan, 1):
        rows.append(
            '<tr>'
            f'<td style="width:30px;padding:9px 7px 9px 0;vertical-align:top;"><span style="display:inline-block;width:22px;height:22px;line-height:22px;text-align:center;border-radius:11px;background:#17633a;color:#ffffff;font-size:11px;font-weight:800;">{index}</span></td>'
            f'<td style="padding:8px 10px 8px 0;border-bottom:1px solid #dcebe2;vertical-align:top;"><div style="font-size:13px;font-weight:700;color:#173b2a;">{esc(step.get("action"))}</div><div style="margin-top:3px;font-size:11px;color:#567065;">交付物：{esc(step.get("deliverable"))}</div></td>'
            f'<td style="width:180px;padding:8px 0 8px 10px;border-bottom:1px solid #dcebe2;vertical-align:top;font-size:11px;color:#567065;">责任人：{esc(step.get("owner"))}<br>期限：{esc(step.get("deadline"))}</td>'
            '</tr>'
        )
    return '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;">' + "".join(rows) + '</table>'


def render_findings(findings: list[dict[str, Any]]) -> str:
    findings = [item for item in findings if item.get("severity") != "not_applicable"]
    if not findings:
        return '<div style="padding:18px;border:1px solid #e7ebf0;border-radius:10px;color:#667085;">本期未形成可报告判断。</div>'
    blocks = []
    for finding in findings:
        severity = finding.get("severity", "watch")
        app = finding.get("applicability") or {}
        source_url = str(finding.get("source_url", ""))
        source_link = (
            f'<a href="{esc(source_url)}" style="color:#1d5f9a;text-decoration:underline;">查看监管原文</a>'
            if source_url.startswith(("http://", "https://"))
            else '<span style="color:#b54708;">原文链接待核实</span>'
        )
        matched = app.get("matched_profile_fields", [])
        matched_labels = [PROFILE_FIELD_LABELS.get(str(item), str(item)) for item in matched]
        kind_label = {"regulatory_obligation": "合规义务", "enforcement_signal": "执法信号", "monitoring": "监管观察"}.get(finding.get("finding_kind"), "监管观察")
        risk_point = finding.get("risk_point") or finding.get("title")
        risk_reason = finding.get("risk_reason") or f'{app.get("logic", "")} {finding.get("potential_consequence", "")}'
        blocks.append(
            '<div style="margin:0 0 16px;border:1px solid #dfe5ec;border-radius:12px;overflow:hidden;">'
            '<div style="padding:14px 16px;background:#f8fafc;border-bottom:1px solid #e7ebf0;">'
            f'{finding_badge(severity)} <span style="font-size:12px;color:#667085;margin-left:6px;">{esc(kind_label)} · 置信度{CONFIDENCE_LABELS.get(finding.get("confidence"), "待核实")}</span>'
            f'<div style="font-size:16px;font-weight:700;color:#172033;margin-top:7px;">{esc(finding.get("id"))} · {esc(finding.get("title"))}</div></div>'
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;">'
            f'<tr><td style="width:118px;padding:12px 14px;border-bottom:1px solid #edf0f4;background:#fff7ed;color:#9a4d00;font-size:13px;font-weight:800;vertical-align:top;">风险点</td><td style="padding:12px 14px;border-bottom:1px solid #edf0f4;font-size:14px;font-weight:700;color:#172033;">{esc(risk_point)}</td></tr>'
            f'<tr><td style="padding:12px 14px;border-bottom:1px solid #edf0f4;background:#f8fafc;color:#475467;font-size:13px;font-weight:800;vertical-align:top;">为什么有风险</td><td style="padding:12px 14px;border-bottom:1px solid #edf0f4;font-size:13px;color:#344054;">{esc(risk_reason)}</td></tr>'
            f'<tr><td style="padding:12px 14px;background:#eef7f1;color:#17633a;font-size:13px;font-weight:800;vertical-align:top;">落地策略</td><td style="padding:4px 14px 8px;font-size:13px;color:#173b2a;">{render_action_plan(finding)}</td></tr>'
            '</table>'
            f'<div style="padding:10px 14px;background:#fbfcfd;border-top:1px solid #edf0f4;font-size:11px;line-height:1.65;color:#667085;">证据：{esc(finding.get("authority"))} · {esc(finding.get("document_number"))} · {esc(finding.get("published_at"))} · {source_link}<br>命中画像：{render_value(matched_labels)}<br>依据摘要：{esc(clip_text(finding.get("evidence_excerpt"), 180))}</div>'
            '</div>'
        )
    return "".join(blocks)


def render_exclusions(findings: list[dict[str, Any]]) -> str:
    excluded = [item for item in findings if item.get("severity") == "not_applicable"]
    if not excluded:
        return '<div style="font-size:13px;color:#667085;">本期无明确排除项。</div>'
    rows = []
    for finding in excluded:
        source_url = str(finding.get("source_url", ""))
        source_link = (
            f'<a href="{esc(source_url)}" style="color:#1d5f9a;text-decoration:underline;">原文</a>'
            if source_url.startswith(("http://", "https://"))
            else "原文待核实"
        )
        rows.append(
            '<tr>'
            f'<td style="padding:9px 10px;border:1px solid #e7ebf0;font-size:12px;font-weight:700;color:#344054;">{esc(finding.get("title"))}</td>'
            f'<td style="padding:9px 10px;border:1px solid #e7ebf0;font-size:12px;color:#667085;">{esc(clip_text((finding.get("applicability") or {}).get("logic"), 140))}</td>'
            f'<td style="padding:9px 10px;border:1px solid #e7ebf0;font-size:12px;white-space:nowrap;">{source_link}</td>'
            '</tr>'
        )
    return '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;">' + "".join(rows) + "</table>"


def render_patterns(patterns: Any) -> str:
    if not patterns:
        return render_list([], "本期处罚样本不足，暂不形成模式判断。")
    if isinstance(patterns, dict):
        patterns = [dict(theme=key, summary=value) for key, value in patterns.items()]
    return render_list(patterns)


def render_source_footer(meta: dict[str, Any], quality: Any) -> str:
    tasks = meta.get("source_tasks", [])
    rows = []
    for task in tasks:
        rows.append(
            '<tr>'
            f'<td style="padding:7px 9px;border:1px solid #e7ebf0;font-size:12px;">{esc(task.get("role"))}</td>'
            f'<td style="padding:7px 9px;border:1px solid #e7ebf0;font-size:12px;word-break:break-all;">{esc(task.get("task_id"))}</td>'
            f'<td style="padding:7px 9px;border:1px solid #e7ebf0;font-size:12px;">{esc(task.get("status"))}</td>'
            f'<td style="padding:7px 9px;border:1px solid #e7ebf0;font-size:12px;">{esc(task.get("record_count", ""))}</td>'
            '</tr>'
        )
    quality_text = render_value(quality) if quality else "未提供"
    return (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;">'
        '<tr><td style="padding:7px 9px;background:#f8fafc;border:1px solid #e7ebf0;font-size:12px;font-weight:700;">角色</td><td style="padding:7px 9px;background:#f8fafc;border:1px solid #e7ebf0;font-size:12px;font-weight:700;">任务 ID</td><td style="padding:7px 9px;background:#f8fafc;border:1px solid #e7ebf0;font-size:12px;font-weight:700;">状态</td><td style="padding:7px 9px;background:#f8fafc;border:1px solid #e7ebf0;font-size:12px;font-weight:700;">记录</td></tr>'
        + "".join(rows)
        + f'</table><div style="font-size:12px;color:#667085;margin-top:9px;">数据质量：{quality_text}</div>'
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--template", default=str(Path(__file__).resolve().parent.parent / "assets" / "report-template.html"))
    args = parser.parse_args()

    analysis = load_json(args.analysis)
    errors, warnings = validate_analysis(analysis)
    if errors:
        print(json.dumps({"status": "invalid_analysis", "errors": errors, "warnings": warnings}, ensure_ascii=False, indent=2))
        return 2

    meta = analysis["report_meta"]
    profile = analysis["enterprise_profile"]
    findings = analysis.get("findings", [])
    synthetic = meta.get("profile_mode") == "synthetic_from_data"
    content = []
    content.append(f'<section id="management-summary">{render_summary(analysis.get("executive_summary"))}</section>')
    content.append(section_title("风险概览", "优先处理高风险；观察项进入专项核查"))
    content.append(f'<section id="risk-statistics">{render_stats(findings)}</section>')
    content.append(section_title("风险与行动", "先看风险点、原因和举措；监管证据保留在每项底部"))
    content.append(f'<section id="risk-findings">{render_findings(findings)}</section>')
    content.append(section_title("企业画像", "以下画像决定监管信息是否与企业形成实际暴露"))
    content.append(f'<section id="enterprise-profile">{render_profile(profile, synthetic)}</section>')
    content.append(section_title("已排除信息", "地区、机构类型或业务活动不匹配，不进入整改清单"))
    content.append(f'<section id="excluded-items">{render_exclusions(findings)}</section>')
    content.append(section_title("行政处罚模式", "仅作为监管关注点和后果信号，不代表画像企业已经违法"))
    content.append(f'<section id="enforcement-patterns">{render_patterns(analysis.get("enforcement_patterns"))}</section>')
    content.append(section_title("待确认信息", "补充这些事实可能改变适用性或风险等级"))
    content.append(f'<section id="pending-verification">{render_list(analysis.get("pending_verification"), "当前无待确认项。")}</section>')
    content.append(section_title("数据范围", "采集任务与数据质量记录"))
    content.append(render_source_footer(meta, analysis.get("data_quality")))
    content.append(f'<section id="disclaimer" style="margin-top:28px;padding-top:18px;border-top:1px solid #e7ebf0;font-size:12px;color:#667085;">{esc(analysis.get("disclaimer"))}</section>')

    template = Path(args.template).read_text(encoding="utf-8")
    title = str(meta.get("title", "广东金融监管风险提示报告"))
    report_html = (
        template.replace("{{TITLE}}", esc(title))
        .replace("{{PREHEADER}}", esc((analysis.get("executive_summary") or {}).get("management_conclusion", title) if isinstance(analysis.get("executive_summary"), dict) else title))
        .replace("{{REPORT_ID}}", esc(meta.get("report_id")))
        .replace("{{GENERATED_AT}}", esc(meta.get("generated_at")))
        .replace("{{CONTENT}}", "".join(content))
        .replace("{{DISCLAIMER}}", esc(analysis.get("disclaimer")))
    )
    html_errors, html_warnings = validate_html(report_html)
    if html_errors:
        print(json.dumps({"status": "invalid_html", "errors": html_errors, "warnings": html_warnings}, ensure_ascii=False, indent=2))
        return 3
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report_html, encoding="utf-8")
    print(json.dumps({"status": "rendered", "output": str(output), "bytes": output.stat().st_size, "warnings": warnings + html_warnings}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
