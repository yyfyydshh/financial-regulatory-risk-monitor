#!/usr/bin/env python3
"""Shared validation and serialization helpers for the regulatory-risk Skill."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SEVERITY_ORDER = {
    "not_applicable": 0,
    "watch": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}
SEVERITY_LABELS = {
    "critical": "严重",
    "high": "高",
    "medium": "中",
    "watch": "观察",
    "not_applicable": "不适用",
}
CONFIDENCE_LABELS = {"high": "高", "medium": "中", "low": "低"}
EFFECT_LABELS = {
    "effective": "现行",
    "future": "未来生效",
    "draft": "征求意见/草案",
    "expired": "已失效",
    "general_notice": "一般通知",
    "unknown": "待核实",
}
REQUIRED_PROFILE_FIELDS = (
    "company_name",
    "company_type",
    "operating_regions",
    "licensed_activities",
    "products_and_services",
    "customer_types",
    "sales_channels",
    "consumer_protection_exposure",
    "data_processing_activities",
    "technology_outsourcing",
    "anti_money_laundering_exposure",
    "governance_features",
    "partner_and_intermediary_types",
)


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def dump_json(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def is_official_url(value: str) -> bool:
    try:
        host = (urlparse(value).hostname or "").lower().strip(".")
    except ValueError:
        return False
    return bool(
        host
        and (
            host.endswith(".gov.cn")
            or host == "gov.cn"
            or host.endswith(".nfsa.gov.cn")
            or host == "nfsa.gov.cn"
            or host.endswith(".cbirc.gov.cn")
            or host == "cbirc.gov.cn"
        )
    )


def nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


def validate_analysis(analysis: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    meta = analysis.get("report_meta")
    profile = analysis.get("enterprise_profile")
    findings = analysis.get("findings")
    if not isinstance(meta, dict):
        errors.append("report_meta must be an object")
        meta = {}
    if not isinstance(profile, dict):
        errors.append("enterprise_profile must be an object")
        profile = {}
    if not isinstance(findings, list):
        errors.append("findings must be an array")
        findings = []

    for field in ("title", "report_id", "generated_at", "profile_mode", "source_tasks"):
        if not nonempty(meta.get(field)):
            errors.append(f"report_meta.{field} is required")
    if meta.get("profile_mode") not in {"provided", "synthetic_from_data"}:
        errors.append("report_meta.profile_mode must be provided or synthetic_from_data")
    for field in REQUIRED_PROFILE_FIELDS:
        if field not in profile:
            errors.append(f"enterprise_profile.{field} is required")
    if meta.get("profile_mode") == "synthetic_from_data" and not profile.get("synthetic_basis"):
        errors.append("synthetic profiles require enterprise_profile.synthetic_basis")

    source_tasks = meta.get("source_tasks", [])
    roles = {item.get("role") for item in source_tasks if isinstance(item, dict)}
    if not roles:
        errors.append("source_tasks must include at least one collection task")
    invalid_roles = roles - {"regulatory_notice", "enforcement_penalty"}
    if invalid_roles:
        errors.append(f"source_tasks contains invalid roles: {', '.join(sorted(str(role) for role in invalid_roles))}")
    for index, item in enumerate(source_tasks if isinstance(source_tasks, list) else []):
        if not isinstance(item, dict):
            errors.append(f"source_tasks[{index}] must be an object")
            continue
        for key in ("task_id", "role", "status", "snapshot"):
            if not nonempty(item.get(key)):
                errors.append(f"source_tasks[{index}].{key} is required")
        if str(item.get("status", "")).lower() not in {"completed", "exported", "finished"}:
            errors.append(f"source_tasks[{index}] is not completed/exported")

    seen_ids: set[str] = set()
    for index, finding in enumerate(findings):
        prefix = f"findings[{index}]"
        if not isinstance(finding, dict):
            errors.append(f"{prefix} must be an object")
            continue
        finding_id = str(finding.get("id", "")).strip()
        if not finding_id:
            errors.append(f"{prefix}.id is required")
        elif finding_id in seen_ids:
            errors.append(f"duplicate finding id: {finding_id}")
        seen_ids.add(finding_id)

        severity = finding.get("severity")
        confidence = finding.get("confidence")
        source_type = finding.get("source_type")
        finding_kind = finding.get("finding_kind")
        effect = finding.get("effective_status")
        app = finding.get("applicability")
        if severity not in SEVERITY_ORDER:
            errors.append(f"{prefix}.severity is invalid")
            continue
        if confidence not in CONFIDENCE_LABELS:
            errors.append(f"{prefix}.confidence is invalid")
        if source_type not in {"regulatory_notice", "enforcement_penalty"}:
            errors.append(f"{prefix}.source_type is invalid")
        if finding_kind not in {"regulatory_obligation", "enforcement_signal", "monitoring"}:
            errors.append(f"{prefix}.finding_kind is invalid")
        if effect not in EFFECT_LABELS:
            errors.append(f"{prefix}.effective_status is invalid")
        if not isinstance(app, dict):
            errors.append(f"{prefix}.applicability must be an object")
            app = {}

        if confidence == "low" and SEVERITY_ORDER[severity] > SEVERITY_ORDER["watch"]:
            errors.append(f"{prefix}: low confidence cannot exceed watch severity")
        if effect in {"draft", "expired", "unknown", "general_notice"} and SEVERITY_ORDER[severity] > SEVERITY_ORDER["watch"]:
            errors.append(f"{prefix}: {effect} material cannot exceed watch severity")
        if source_type == "enforcement_penalty":
            if finding_kind != "enforcement_signal":
                errors.append(f"{prefix}: penalties must be enforcement_signal")
            if SEVERITY_ORDER[severity] > SEVERITY_ORDER["watch"]:
                errors.append(f"{prefix}: a penalty signal cannot be presented as direct enterprise risk above watch")
            language = " ".join(
                str(finding.get(key, ""))
                for key in ("title", "applicability_summary", "potential_consequence", "recommended_action")
            )
            if re.search(r"企业(?:已经|已)(?:违法|违规)|画像企业(?:已经|已)(?:违法|违规)", language):
                errors.append(f"{prefix}: penalty language improperly asserts enterprise wrongdoing")
        if source_type == "regulatory_notice" and finding_kind == "enforcement_signal":
            warnings.append(f"{prefix}: notice is classified as an enforcement signal")

        if severity in {"critical", "high"}:
            if source_type != "regulatory_notice" or finding_kind != "regulatory_obligation":
                errors.append(f"{prefix}: critical/high requires a regulatory notice obligation")
            if effect not in {"effective", "future"}:
                errors.append(f"{prefix}: critical/high requires current or future effect")
            if severity == "critical" and confidence != "high":
                errors.append(f"{prefix}: critical requires high confidence")
            if confidence not in {"high", "medium"}:
                errors.append(f"{prefix}: critical/high confidence is insufficient")
            for gate in ("jurisdiction_match", "subject_match", "activity_match", "time_match"):
                if app.get(gate) is not True:
                    errors.append(f"{prefix}.applicability.{gate} must be true for critical/high")
            for field, value in (
                ("risk_point", finding.get("risk_point")),
                ("risk_reason", finding.get("risk_reason")),
                ("authority", finding.get("authority")),
                ("source_url", finding.get("source_url")),
                ("evidence_excerpt", finding.get("evidence_excerpt")),
                ("applicability.logic", app.get("logic")),
                ("applicability.matched_profile_fields", app.get("matched_profile_fields")),
                ("potential_consequence", finding.get("potential_consequence")),
                ("action_plan", finding.get("action_plan")),
            ):
                if not nonempty(value):
                    errors.append(f"{prefix}.{field} is required for critical/high")
            if finding.get("source_text_complete") is not True:
                errors.append(f"{prefix}.source_text_complete must be true for critical/high")
            if not is_official_url(str(finding.get("source_url", ""))):
                errors.append(f"{prefix}.source_url is not recognized as an official government source")

        action_plan = finding.get("action_plan")
        if severity not in {"not_applicable"}:
            if not nonempty(finding.get("risk_point")):
                warnings.append(f"{prefix}: risk_point is missing")
            if not nonempty(finding.get("risk_reason")):
                warnings.append(f"{prefix}: risk_reason is missing")
            minimum_steps = 2 if severity in {"critical", "high"} else 1
            if not isinstance(action_plan, list) or not (minimum_steps <= len(action_plan) <= 4):
                errors.append(f"{prefix}.action_plan must contain {minimum_steps}-4 steps")
            else:
                for step_index, step in enumerate(action_plan):
                    if not isinstance(step, dict):
                        errors.append(f"{prefix}.action_plan[{step_index}] must be an object")
                        continue
                    for field in ("action", "owner", "deadline", "deliverable"):
                        if not nonempty(step.get(field)):
                            errors.append(f"{prefix}.action_plan[{step_index}].{field} is required")
        if len(str(finding.get("risk_point", ""))) > 60:
            warnings.append(f"{prefix}: risk_point should be no more than 60 characters")
        if re.search(r"可能不完整|需关注|存在风险$", str(finding.get("risk_point", ""))):
            warnings.append(f"{prefix}: risk_point is vague; name the specific gap, trigger, or missing evidence")
        if len(str(finding.get("risk_reason", ""))) > 140:
            warnings.append(f"{prefix}: risk_reason should be no more than 140 characters")
        if len(str(finding.get("recommended_action", ""))) > 240:
            warnings.append(f"{prefix}: recommended_action should be no more than 240 characters")

        matched = app.get("matched_profile_fields", [])
        if isinstance(matched, list):
            unknown = [field for field in matched if field.split(".", 1)[0] not in profile]
            if unknown:
                errors.append(f"{prefix}: matched profile fields do not exist: {', '.join(unknown)}")
        else:
            errors.append(f"{prefix}.applicability.matched_profile_fields must be an array")
        if not nonempty(finding.get("source_url")):
            warnings.append(f"{prefix}: source URL is missing; keep this item pending verification")
        if not nonempty(finding.get("evidence_excerpt")):
            warnings.append(f"{prefix}: evidence excerpt is missing")

    if not nonempty(analysis.get("executive_summary")):
        errors.append("executive_summary is required")
    if "enforcement_patterns" not in analysis:
        errors.append("enforcement_patterns is required")
    if "pending_verification" not in analysis:
        errors.append("pending_verification is required")
    if not nonempty(analysis.get("disclaimer")):
        errors.append("disclaimer is required")
    return errors, warnings


def validate_html(html: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    lowered = html.lower()
    for required_id in (
        "management-summary",
        "enterprise-profile",
        "risk-statistics",
        "risk-findings",
        "enforcement-patterns",
        "pending-verification",
        "disclaimer",
    ):
        if f'id="{required_id}"' not in lowered:
            errors.append(f"HTML section missing: {required_id}")
    if "<script" in lowered:
        errors.append("HTML must not contain JavaScript")
    if "<link" in lowered or "@import" in lowered:
        errors.append("HTML must not load external stylesheets")
    if "<style" in lowered:
        errors.append("HTML must use inline CSS only")
    if "```" in html:
        errors.append("HTML contains Markdown code-fence text")
    if not lowered.lstrip().startswith("<!doctype html"):
        warnings.append("HTML should start with a doctype")
    if "严重" not in html or "观察" not in html:
        warnings.append("risk labels may not cover the full textual severity legend")
    return errors, warnings
