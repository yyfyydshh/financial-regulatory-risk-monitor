#!/usr/bin/env python3
"""Normalize JSON/CSV Octoparse exports into a stable regulatory record schema."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from risk_common import dump_json, is_official_url

FIELD_ALIASES = {
    "title": ["标题", "公告标题", "文件名", "名称", "title", "Title", "政策名称", "行政处罚标题"],
    "authority": ["发布机关", "处罚机关", "发文机关", "监管机构", "来源", "authority", "机构"],
    "document_number": ["文号", "发文字号", "处罚决定书文号", "行政处罚决定书文号", "document_number"],
    "published_at": ["发布日期", "发布时间", "公示日期", "处罚日期", "决定日期", "published_at", "date"],
    "effective_date": ["生效日期", "施行日期", "effective_date"],
    "body": ["正文", "公告正文", "内容", "详情", "政策内容", "处罚内容", "body", "content", "Content"],
    "legal_basis": ["处罚依据", "法律依据", "主要违法违规事实（案由）", "主要违法违规事实", "legal_basis"],
    "penalized_party": ["处罚对象", "被处罚当事人", "当事人名称", "行政处罚决定书文号", "penalized_party"],
    "conduct": ["处罚行为", "主要违法违规事实", "违法违规行为", "案由", "conduct"],
    "result": ["处罚结果", "行政处罚内容", "处罚决定", "result"],
    "source_url": ["原文链接", "详情链接", "网页链接", "正文url", "页面网址", "链接", "URL", "url", "source_url", "Url"],
}


def scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value).strip()


def pick(record: dict[str, Any], aliases: list[str]) -> str:
    lowered = {str(key).strip().lower(): value for key, value in record.items()}
    for alias in aliases:
        if alias in record and scalar(record[alias]):
            return scalar(record[alias])
        value = lowered.get(alias.lower())
        if scalar(value):
            return scalar(value)
    for key, value in record.items():
        normalized = str(key).replace(" ", "").lower()
        if any(alias.replace(" ", "").lower() in normalized for alias in aliases):
            if scalar(value):
                return scalar(value)
    return ""


def normalize_space(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[\t \u3000]+", " ", line).strip() for line in value.split("\n")]
    return "\n".join(line for line in lines if line)


def normalize_date(value: str) -> str:
    if not value:
        return ""
    value = value.strip()
    for pattern in (r"(20\d{2})[年/.-](\d{1,2})[月/.-](\d{1,2})", r"(20\d{2})(\d{2})(\d{2})"):
        match = re.search(pattern, value)
        if match:
            try:
                return date(int(match.group(1)), int(match.group(2)), int(match.group(3))).isoformat()
            except ValueError:
                pass
    return ""


def extract_published_date(body: str, authority: str) -> str:
    date_pattern = r"(20\d{2})年(\d{1,2})月(\d{1,2})日"
    if authority:
        authority_pattern = rf"{re.escape(authority)}.{{0,300}}?{date_pattern}"
        matches = list(re.finditer(authority_pattern, body, flags=re.DOTALL))
        if matches:
            return normalize_date(matches[-1].group(0))
    matches = list(re.finditer(date_pattern, body))
    return normalize_date(matches[-1].group(0)) if matches else ""


def extract_effective_date(body: str) -> str:
    patterns = (
        r"自\s*((?:20\d{2})年\d{1,2}月\d{1,2}日)\s*起?(?:施行|实施|执行|生效)",
        r"((?:20\d{2})年\d{1,2}月\d{1,2}日)\s*起(?:施行|实施|执行|生效)",
    )
    for pattern in patterns:
        match = re.search(pattern, body)
        if match:
            return normalize_date(match.group(1))
    return ""


def clean_url(value: str) -> str:
    if not value:
        return ""
    value = value.strip()
    try:
        split = urlsplit(value)
        query = [(key, val) for key, val in parse_qsl(split.query, keep_blank_values=True) if not key.lower().startswith("utm_")]
        return urlunsplit((split.scheme.lower(), split.netloc.lower(), split.path, urlencode(query), ""))
    except ValueError:
        return value


def classify_effect(title: str, body: str, effective_date: str) -> str:
    head = f"{title}\n{body[:1000]}"
    if re.search(r"征求意见|意见稿|草案", head):
        return "draft"
    if re.search(r"(?:行政处罚决定书|催告书|监管强制措施.{0,8}(?:决定书|告知书)).{0,8}送达公告", title):
        return "general_notice"
    if re.search(r"规范性文件.{0,12}废止|废止.{0,12}(?:公告|通知)", title) or re.search(
        r"(?:本|该)(?:办法|规定|通知|文件)(?:自.{0,24})?(?:废止|失效)|已废止|停止执行",
        body[:1200],
    ):
        return "expired"
    if re.search(r"风险提示|适当性管理的提示|指导意见|工作方案|若干措施|政策指引", title):
        return "general_notice"
    if effective_date:
        try:
            if date.fromisoformat(effective_date) > date.today():
                return "future"
            return "effective"
        except ValueError:
            pass
    if re.search(r"自.{0,40}(?:起施行|起实施|开始实施|开始按|施行)|自印发之日|现予发布|印发给你们|请(?:认真)?遵照执行|贯彻落实", head):
        return "effective"
    if re.search(r"公示|名单|会议|招聘|采购|考试|一般通知", title):
        return "general_notice"
    return "unknown"


def load_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    with path.open("r", encoding="utf-8-sig") as handle:
        value = json.load(handle)
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in ("data", "records", "items", "list", "sampleData"):
            rows = value.get(key)
            if isinstance(rows, list):
                return [item for item in rows if isinstance(item, dict)]
    raise ValueError(f"Unsupported export structure: {path}")


def normalize_record(record: dict[str, Any], role: str, task_id: str, source_file: str) -> dict[str, Any]:
    values = {field: normalize_space(pick(record, aliases)) for field, aliases in FIELD_ALIASES.items()}
    values["source_url"] = clean_url(values["source_url"])
    values["published_at"] = normalize_date(values["published_at"])
    values["effective_date"] = normalize_date(values["effective_date"])
    if not values["published_at"]:
        values["published_at"] = extract_published_date(values["body"], values["authority"])
    if not values["effective_date"]:
        values["effective_date"] = extract_effective_date(values["body"])
    if role == "enforcement_penalty" and not values["body"]:
        values["body"] = "\n".join(
            part for part in (values["conduct"], values["legal_basis"], values["result"]) if part
        )
    if not values["document_number"]:
        number_match = re.search(r"[\u4e00-\u9fff]{0,10}(?:发|办发|规|罚决字)〔20\d{2}〕\d+号", values["body"][:500])
        if number_match:
            values["document_number"] = number_match.group(0)
    fingerprint_source = values["source_url"] or values["document_number"] or f'{values["title"]}|{values["published_at"]}'
    record_id = hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()[:20]
    return {
        "record_id": record_id,
        "source_type": role,
        "title": values["title"],
        "authority": values["authority"],
        "document_number": values["document_number"],
        "published_at": values["published_at"],
        "effective_date": values["effective_date"],
        "effective_status": classify_effect(values["title"], values["body"], values["effective_date"]),
        "body": values["body"],
        "source_text_complete": len(values["body"]) >= 120,
        "legal_basis": values["legal_basis"],
        "penalized_party": values["penalized_party"],
        "conduct": values["conduct"],
        "result": values["result"],
        "source_url": values["source_url"],
        "official_source": is_official_url(values["source_url"]),
        "source_task_id": task_id,
        "source_file": source_file,
        "raw": record,
    }


def parse_input(value: str) -> tuple[str, str, Path]:
    try:
        role_and_task, raw_path = value.split("=", 1)
        if ":" in role_and_task:
            role, task_id = role_and_task.split(":", 1)
        else:
            role, task_id = role_and_task, ""
    except ValueError as exc:
        raise argparse.ArgumentTypeError("input must be role[:task_id]=path") from exc
    if role not in {"regulatory_notice", "enforcement_penalty"}:
        raise argparse.ArgumentTypeError(f"invalid role: {role}")
    return role, task_id, Path(raw_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True, help="role[:task_id]=path")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    normalized: list[dict[str, Any]] = []
    raw_count = 0
    sources = []
    for spec in args.input:
        role, task_id, path = parse_input(spec)
        rows = load_rows(path)
        raw_count += len(rows)
        sources.append({"role": role, "task_id": task_id, "path": str(path), "rows": len(rows)})
        normalized.extend(normalize_record(row, role, task_id, str(path)) for row in rows)

    deduplicated: dict[tuple[str, str], dict[str, Any]] = {}
    for row in normalized:
        key = (row["source_type"], row["record_id"])
        current = deduplicated.get(key)
        if current is None or len(row["body"]) > len(current["body"]):
            deduplicated[key] = row
    records = sorted(
        deduplicated.values(),
        key=lambda item: (item.get("published_at", ""), item.get("title", "")),
        reverse=True,
    )
    output = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "sources": sources,
        "raw_count": raw_count,
        "normalized_count": len(normalized),
        "deduplicated_count": len(records),
        "duplicates_removed": len(normalized) - len(records),
        "records": records,
    }
    dump_json(args.output, output)
    print(json.dumps({key: output[key] for key in ("raw_count", "deduplicated_count", "duplicates_removed")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
