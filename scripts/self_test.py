#!/usr/bin/env python3
"""Run deterministic acceptance tests for analysis, rendering, and both delivery channels."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from delivery_common import build_email_message
from risk_common import dump_json, load_json, validate_analysis, validate_html


def run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=str(cwd), text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def valid_analysis() -> dict:
    return {
        "report_meta": {
            "title": "广东金融监管风险提示报告（自动化测试）",
            "report_id": "TEST-001",
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "jurisdiction": "广东",
            "profile_mode": "synthetic_from_data",
            "source_tasks": [
                {"task_id": "notice-task", "role": "regulatory_notice", "status": "completed", "snapshot": "notice-s1", "record_count": 1},
                {"task_id": "penalty-task", "role": "enforcement_penalty", "status": "completed", "snapshot": "penalty-s1", "record_count": 1},
            ],
        },
        "enterprise_profile": {
            "company_name": "演示粤融消费金融服务有限公司",
            "company_type": "消费金融机构（演示）",
            "operating_regions": ["广东省"],
            "licensed_activities": ["消费信贷（演示假设）"],
            "products_and_services": ["线上消费信贷"],
            "customer_types": ["个人消费者"],
            "sales_channels": ["自营App", "合作平台"],
            "consumer_protection_exposure": ["营销披露", "投诉处理"],
            "data_processing_activities": ["个人信息", "信用数据"],
            "technology_outsourcing": ["云服务"],
            "anti_money_laundering_exposure": ["客户尽职调查"],
            "governance_features": ["合规审查", "整改跟踪"],
            "partner_and_intermediary_types": ["助贷平台"],
            "synthetic_basis": ["公告样本包含消费者权益保护要求", "处罚样本涉及贷后管理"],
        },
        "data_quality": {"collected": 3, "deduplicated": 2, "official_sources": 2},
        "executive_summary": {
            "management_conclusion": "一项直接义务命中演示画像；处罚仅作为控制复核信号。",
            "immediate_actions": ["复核消费者告知与投诉闭环"],
            "scope_caveats": ["画像为演示合成"],
        },
        "findings": [
            {
                "id": "F-001",
                "severity": "high",
                "confidence": "high",
                "finding_kind": "regulatory_obligation",
                "source_type": "regulatory_notice",
                "title": "关于加强金融消费者权益保护的通知",
                "risk_point": "消费者保护审查和投诉闭环可能不完整",
                "risk_reason": "演示机构在广东面向个人消费者经营，直接命中通知的机构、地区和活动条件。",
                "authority": "国家金融监督管理总局广东监管局",
                "document_number": "粤金监发〔2026〕1号",
                "published_at": "2026-01-01",
                "effective_status": "effective",
                "source_url": "https://www.nfra.gov.cn/branch/guangdong/test.html",
                "source_text_complete": True,
                "evidence_excerpt": "金融机构应建立消费者权益保护审查和投诉闭环机制。",
                "applicability": {
                    "jurisdiction_match": True,
                    "subject_match": True,
                    "activity_match": True,
                    "time_match": True,
                    "matched_profile_fields": ["operating_regions", "consumer_protection_exposure"],
                    "logic": "演示机构在广东面向个人消费者开展业务，直接命中机构、区域和活动条件。",
                },
                "obligation_type": "consumer_protection",
                "legal_basis": "通知正文",
                "potential_consequence": "可能产生责令整改、监管评价和声誉影响。",
                "recommended_owner": "合规与消保部门",
                "recommended_action": "对照通知建立条款差距清单并验证投诉闭环证据。",
                "action_plan": [
                    {"action": "将通知要求映射到现有消保控制", "owner": "合规部", "deadline": "5个工作日内", "deliverable": "条款控制矩阵"},
                    {"action": "抽样验证投诉闭环", "owner": "消保部", "deadline": "10个工作日内", "deliverable": "抽样底稿与整改清单"},
                ],
                "due_date": "30日内",
                "open_questions": [],
            },
            {
                "id": "F-002",
                "severity": "watch",
                "confidence": "medium",
                "finding_kind": "enforcement_signal",
                "source_type": "enforcement_penalty",
                "title": "某机构行政处罚决定",
                "risk_point": "贷后管理控制需要专项复核",
                "risk_reason": "相似活动形成执法关注信号，但处罚对象不是画像企业。",
                "authority": "国家金融监督管理总局广东监管局",
                "document_number": "粤金罚决字〔2026〕1号",
                "published_at": "2026-02-01",
                "effective_status": "effective",
                "source_url": "https://www.nfra.gov.cn/branch/guangdong/penalty-test.html",
                "source_text_complete": True,
                "evidence_excerpt": "因贷后管理不到位，对该被处罚机构罚款。",
                "applicability": {
                    "jurisdiction_match": True,
                    "subject_match": False,
                    "activity_match": True,
                    "time_match": True,
                    "matched_profile_fields": ["products_and_services"],
                    "logic": "相似活动形成控制复核信号，但处罚对象不是画像企业。",
                },
                "obligation_type": "none",
                "legal_basis": "相关审慎经营规则",
                "potential_consequence": "反映贷后管理可能受到监管执法关注。",
                "recommended_owner": "风险管理部",
                "recommended_action": "抽样复核贷后管理控制，不推定企业存在违法。",
                "action_plan": [
                    {"action": "抽样复核贷后管理控制", "owner": "风险管理部", "deadline": "下次合规检查前", "deliverable": "专项抽样底稿"}
                ],
                "due_date": "下次合规检查前",
                "open_questions": [],
            },
        ],
        "enforcement_patterns": [{"theme": "贷后管理", "summary": "处罚样本提示需验证贷后检查和异常升级控制。"}],
        "pending_verification": ["确认正式企业画像中的金融许可证类型与业务范围。"],
        "disclaimer": "本报告为监管信息筛查和风险决策支持，不构成法律意见、执法结论或对任何企业违法事实的认定。",
    }


def main() -> int:
    root = Path(__file__).resolve().parent
    results: list[dict[str, str]] = []
    with tempfile.TemporaryDirectory(prefix="reg-risk-self-test-") as raw_temp:
        temp = Path(raw_temp)
        notice = [
            {"标题": "关于加强金融消费者权益保护的通知", "发布机关": "国家金融监督管理总局广东监管局", "发布日期": "2026-01-01", "正文": "金融机构应建立消费者权益保护审查和投诉闭环机制。" * 8, "原文链接": "https://www.nfra.gov.cn/branch/guangdong/test.html?utm_source=x"},
            {"标题": "关于加强金融消费者权益保护的通知", "发布机关": "国家金融监督管理总局广东监管局", "发布日期": "2026-01-01", "正文": "金融机构应建立消费者权益保护审查和投诉闭环机制。", "原文链接": "https://www.nfra.gov.cn/branch/guangdong/test.html"},
        ]
        penalty = [{"标题": "某机构行政处罚决定", "处罚机关": "国家金融监督管理总局广东监管局", "处罚日期": "2026-02-01", "主要违法违规事实": "贷后管理不到位", "处罚依据": "相关审慎经营规则", "处罚结果": "罚款", "详情链接": "https://www.nfra.gov.cn/branch/guangdong/penalty-test.html"}]
        notice_path, penalty_path = temp / "notice.json", temp / "penalty.json"
        dump_json(notice_path, notice)
        dump_json(penalty_path, penalty)
        normalized_path = temp / "normalized.json"
        normalized = run(
            [sys.executable, str(root / "normalize_records.py"), "--input", f"regulatory_notice:notice-task={notice_path}", "--input", f"enforcement_penalty:penalty-task={penalty_path}", "--output", str(normalized_path)],
            root,
        )
        require(normalized.returncode == 0, normalized.stderr or normalized.stdout)
        normalized_data = load_json(normalized_path)
        require(normalized_data["raw_count"] == 3, "normalizer raw count mismatch")
        require(normalized_data["deduplicated_count"] == 2, "duplicate notice was not merged")
        results.append({"test": "normalize_and_deduplicate", "status": "passed"})

        run_metadata_path = temp / "current-run-tasks.json"
        provenance_path = temp / "collection-provenance.json"
        dump_json(
            run_metadata_path,
            {
                "source_tasks": [
                    {
                        "task_id": "notice-task",
                        "task_name": "公告任务",
                        "role": "regulatory_notice",
                        "status": "exported",
                        "export_url": "https://example.com/notice-export.json",
                        "export_path": str(notice_path),
                    },
                    {
                        "task_id": "penalty-task",
                        "task_name": "处罚任务",
                        "role": "enforcement_penalty",
                        "status": "exported",
                        "export_url": "https://example.com/penalty-export.json",
                        "export_path": str(penalty_path),
                    },
                ]
            },
        )
        provenance = run(
            [
                sys.executable,
                str(root / "build_run_manifest.py"),
                "--metadata",
                str(run_metadata_path),
                "--output",
                str(provenance_path),
            ],
            root,
        )
        require(provenance.returncode == 0, provenance.stderr or provenance.stdout)
        provenance_data = load_json(provenance_path)
        require(
            all(item.get("snapshot") and item.get("record_count") for item in provenance_data["source_tasks"]),
            "current-run provenance omitted snapshot or record count",
        )
        results.append({"test": "current_run_provenance_verified", "status": "passed"})

        evidence_index_path = temp / "evidence-index.json"
        indexed = run(
            [
                sys.executable,
                str(root / "build_evidence_index.py"),
                "--input",
                str(normalized_path),
                "--provenance",
                str(provenance_path),
                "--output",
                str(evidence_index_path),
            ],
            root,
        )
        require(indexed.returncode == 0, indexed.stderr or indexed.stdout)
        evidence_index = load_json(evidence_index_path)
        require(
            evidence_index["coverage"]["indexed_record_count"] == normalized_data["deduplicated_count"],
            "evidence index did not cover every normalized record",
        )
        require(
            all(item.get("record_id") and "body_chars" in item for item in evidence_index["records"]),
            "evidence index omitted traceability fields",
        )
        require(
            len(evidence_index.get("current_run_provenance", [])) == 2,
            "evidence index omitted current-run provenance",
        )
        results.append({"test": "complete_topic_neutral_evidence_index", "status": "passed"})

        review_ledger_path = temp / "semantic-review-ledger.json"
        dump_json(
            review_ledger_path,
            {
                "records": [
                    {
                        "record_id": item["record_id"],
                        "review_depth": "full_body" if item["source_type"] == "regulatory_notice" else "screened",
                        "disposition": "candidate" if item["source_type"] == "regulatory_notice" else "excluded",
                        "reason": "self-test semantic disposition",
                    }
                    for item in evidence_index["records"]
                ]
            },
        )
        review_validation = run(
            [
                sys.executable,
                str(root / "validate_review_coverage.py"),
                "--index",
                str(evidence_index_path),
                "--ledger",
                str(review_ledger_path),
            ],
            root,
        )
        require(review_validation.returncode == 0, review_validation.stderr or review_validation.stdout)
        results.append({"test": "semantic_review_coverage_required", "status": "passed"})

        analysis = valid_analysis()
        errors, _ = validate_analysis(analysis)
        require(not errors, "valid analysis rejected: " + "; ".join(errors))
        results.append({"test": "valid_evidence_gates", "status": "passed"})

        latest_notice_only = copy.deepcopy(analysis)
        latest_notice_only["report_meta"]["source_tasks"] = [
            item
            for item in latest_notice_only["report_meta"]["source_tasks"]
            if item.get("role") == "regulatory_notice"
        ]
        latest_notice_only["findings"] = [
            item
            for item in latest_notice_only["findings"]
            if item.get("source_type") == "regulatory_notice"
        ]
        latest_notice_only["enforcement_patterns"] = []
        latest_notice_errors, _ = validate_analysis(latest_notice_only)
        require(
            not latest_notice_errors,
            "latest notice-only analysis rejected: " + "; ".join(latest_notice_errors),
        )
        results.append({"test": "latest_task_notice_only_supported", "status": "passed"})

        request_manifest = {
            "octoparse_mcp": {
                "endpoint": "https://mcp.bazhuayu.com",
                "auth_mode": "api_key",
                "api_key_configured": True,
            },
            "profile_mode": "provided",
            "enterprise_profile": analysis["enterprise_profile"],
            "enterprise_profile_confirmed": True,
            "collection_tasks": [
                {"task_id": "notice-task", "role": "regulatory_notice"},
                {"task_name": "处罚任务", "role": "enforcement_penalty"},
            ],
            "collection_tasks_confirmed": True,
            "delivery": {
                "channel": "direct_email",
                "auto_send": True,
                "confirmed": True,
                "direct_email": {
                    "from_address": "sender@example.com",
                    "to": ["recipient@example.com"],
                    "cc": [],
                    "bcc": [],
                    "smtp": {
                        "host": "smtp.example.com",
                        "port": 587,
                        "security": "starttls",
                        "username": "sender@example.com",
                        "password_env": "REG_RISK_TEST_SMTP_PASSWORD",
                        "no_auth": False,
                    },
                },
            },
        }
        request_path = temp / "request.json"
        dump_json(request_path, request_manifest)
        for stage in ("collect", "publish"):
            request_check = run(
                [
                    sys.executable,
                    str(root / "validate_request.py"),
                    "--request",
                    str(request_path),
                    "--stage",
                    stage,
                ],
                root,
            )
            require(request_check.returncode == 0, request_check.stderr or request_check.stdout)
            require(json.loads(request_check.stdout)["status"] == "ready", f"{stage} request validation did not pass")
        results.append({"test": "complete_onboarding_ready", "status": "passed"})

        incomplete_request_path = temp / "incomplete-request.json"
        dump_json(incomplete_request_path, {})
        incomplete_request = run(
            [
                sys.executable,
                str(root / "validate_request.py"),
                "--request",
                str(incomplete_request_path),
                "--stage",
                "collect",
            ],
            root,
        )
        incomplete_result = json.loads(incomplete_request.stdout)
        require(incomplete_request.returncode != 0, "empty onboarding request was not blocked")
        require(incomplete_result.get("status") == "input_required", "empty request status mismatch")
        require(incomplete_result.get("missing_count", 0) >= 8, "empty request did not list all question groups")
        results.append({"test": "missing_inputs_return_questions", "status": "passed"})

        synthetic_request = copy.deepcopy(request_manifest)
        synthetic_request["profile_mode"] = "synthetic_from_data"
        synthetic_request.pop("enterprise_profile")
        synthetic_request.pop("enterprise_profile_confirmed")
        synthetic_request_path = temp / "synthetic-request.json"
        dump_json(synthetic_request_path, synthetic_request)
        synthetic_collect = run(
            [
                sys.executable,
                str(root / "validate_request.py"),
                "--request",
                str(synthetic_request_path),
                "--stage",
                "collect",
            ],
            root,
        )
        synthetic_publish = run(
            [
                sys.executable,
                str(root / "validate_request.py"),
                "--request",
                str(synthetic_request_path),
                "--stage",
                "publish",
            ],
            root,
        )
        require(synthetic_collect.returncode == 0, "synthetic collection was blocked before profile derivation")
        require(synthetic_publish.returncode != 0, "unconfirmed synthetic profile was allowed to publish")
        results.append({"test": "synthetic_profile_confirmation_staged", "status": "passed"})

        for name, mutate in (
            ("low_confidence_high_blocked", lambda item: item.update(confidence="low")),
            ("draft_high_blocked", lambda item: item.update(effective_status="draft")),
        ):
            invalid = copy.deepcopy(analysis)
            mutate(invalid["findings"][0])
            invalid_errors, _ = validate_analysis(invalid)
            require(invalid_errors, f"{name} was not blocked")
            results.append({"test": name, "status": "passed"})
        cross_region = copy.deepcopy(analysis)
        cross_region["findings"][0]["applicability"]["jurisdiction_match"] = False
        cross_region_errors, _ = validate_analysis(cross_region)
        require(cross_region_errors, "cross-region high finding was not blocked")
        results.append({"test": "cross_region_high_blocked", "status": "passed"})
        missing_plan = copy.deepcopy(analysis)
        missing_plan["findings"][0]["action_plan"] = []
        missing_plan_errors, _ = validate_analysis(missing_plan)
        require(missing_plan_errors, "high finding without an actionable plan was not blocked")
        results.append({"test": "high_action_plan_required", "status": "passed"})
        invalid_penalty = copy.deepcopy(analysis)
        invalid_penalty["findings"][1]["severity"] = "critical"
        invalid_errors, _ = validate_analysis(invalid_penalty)
        require(invalid_errors, "critical penalty signal was not blocked")
        results.append({"test": "penalty_not_presented_as_direct_risk", "status": "passed"})

        analysis_path = temp / "analysis.json"
        report_path = temp / "regulatory-risk-report.html"
        validation_path = temp / "validation.json"
        dump_json(analysis_path, analysis)
        rendered = run([sys.executable, str(root / "render_report.py"), "--analysis", str(analysis_path), "--output", str(report_path)], root)
        require(rendered.returncode == 0, rendered.stderr or rendered.stdout)
        html_text = report_path.read_text(encoding="utf-8")
        html_errors, _ = validate_html(html_text)
        require(not html_errors, "; ".join(html_errors))
        require("```" not in html_text and "<script" not in html_text.lower(), "report contains unsafe/Markdown content")
        validated = run([sys.executable, str(root / "validate_report.py"), "--analysis", str(analysis_path), "--html", str(report_path), "--result", str(validation_path)], root)
        require(validated.returncode == 0, validated.stderr or validated.stdout)
        results.append({"test": "render_and_validate_html", "status": "passed"})

        dry_run = run([sys.executable, str(root / "send_feishu_mail.py"), "--analysis", str(analysis_path), "--report", str(report_path), "--to", "test@example.com", "--dry-run"], root)
        receipt_file = temp / "internal" / "delivery-receipt.json"
        receipt = load_json(receipt_file) if receipt_file.is_file() else {}
        require(
            dry_run.returncode == 0,
            "\n".join([dry_run.stdout, dry_run.stderr, json.dumps(receipt, ensure_ascii=False)]),
        )
        require(receipt.get("status") == "dry_run_passed", "mail dry-run did not pass")
        results.append({"test": "legacy_feishu_mail_dry_run", "status": "passed"})

        dump_json(temp / "internal" / "send-ledger.json", {"sent": [{"fingerprint": receipt["fingerprint"], "sent_at": "test"}]})
        duplicate = run([sys.executable, str(root / "send_feishu_mail.py"), "--analysis", str(analysis_path), "--report", str(report_path), "--to", "test@example.com", "--dry-run"], root)
        require(duplicate.returncode != 0, "duplicate fingerprint was not blocked")
        duplicate_receipt = load_json(receipt_file)
        require(duplicate_receipt.get("status") == "duplicate_blocked", "duplicate receipt status mismatch")
        results.append({"test": "duplicate_send_blocked", "status": "passed"})

        invalid_recipient = run([sys.executable, str(root / "send_feishu_mail.py"), "--analysis", str(analysis_path), "--report", str(report_path), "--to", "not-an-email", "--dry-run"], root)
        require(invalid_recipient.returncode != 0, "invalid recipient was not blocked")
        results.append({"test": "invalid_recipient_blocked", "status": "passed"})

        missing_recipient = run([sys.executable, str(root / "send_feishu_mail.py"), "--analysis", str(analysis_path), "--report", str(report_path)], root)
        require(missing_recipient.returncode != 0, "missing recipient was not blocked")
        results.append({"test": "missing_recipient_blocked", "status": "passed"})

        direct_receipt_path = temp / "internal" / "direct-email-test-receipt.json"
        direct_ledger_path = temp / "internal" / "direct-email-test-ledger.json"
        direct_dry_run = run(
            [
                sys.executable,
                str(root / "send_direct_email.py"),
                "--analysis",
                str(analysis_path),
                "--report",
                str(report_path),
                "--from-address",
                "sender@example.com",
                "--to",
                "recipient@example.com",
                "--bcc",
                "audit@example.com",
                "--smtp-host",
                "smtp.example.com",
                "--security",
                "starttls",
                "--prompt-password",
                "--ledger",
                str(direct_ledger_path),
                "--receipt",
                str(direct_receipt_path),
                "--dry-run",
            ],
            root,
        )
        direct_receipt = load_json(direct_receipt_path)
        require(direct_dry_run.returncode == 0, direct_dry_run.stderr or direct_dry_run.stdout)
        require(direct_receipt.get("status") == "dry_run_passed", "direct email dry-run did not pass")
        email_message = build_email_message(
            "sender@example.com",
            ["recipient@example.com"],
            [],
            "测试报告",
            report_path,
            html_text,
        )
        require(email_message.get("Bcc") is None, "Bcc leaked into MIME headers")
        results.append({"test": "direct_email_dry_run_and_bcc_privacy", "status": "passed"})

        dump_json(
            direct_ledger_path,
            {
                "sent": [
                    {
                        "fingerprint": direct_receipt["fingerprint"],
                        "sent_at": "test",
                        "channel": "direct_email",
                    }
                ]
            },
        )
        direct_duplicate = run(
            [
                sys.executable,
                str(root / "send_direct_email.py"),
                "--analysis",
                str(analysis_path),
                "--report",
                str(report_path),
                "--from-address",
                "sender@example.com",
                "--to",
                "recipient@example.com",
                "--bcc",
                "audit@example.com",
                "--smtp-host",
                "smtp.example.com",
                "--security",
                "starttls",
                "--ledger",
                str(direct_ledger_path),
                "--receipt",
                str(direct_receipt_path),
                "--dry-run",
            ],
            root,
        )
        require(direct_duplicate.returncode != 0, "direct email duplicate was not blocked")
        require(load_json(direct_receipt_path).get("status") == "duplicate_blocked", "direct email duplicate status mismatch")
        results.append({"test": "direct_email_duplicate_blocked", "status": "passed"})

        missing_password = run(
            [
                sys.executable,
                str(root / "send_direct_email.py"),
                "--analysis",
                str(analysis_path),
                "--report",
                str(report_path),
                "--from-address",
                "sender@example.com",
                "--to",
                "recipient@example.com",
                "--smtp-host",
                "smtp.example.com",
                "--password-env",
                "REG_RISK_SELF_TEST_MISSING_PASSWORD",
                "--ledger",
                str(temp / "internal" / "direct-email-auth-test-ledger.json"),
                "--receipt",
                str(direct_receipt_path),
                "--preflight",
            ],
            root,
        )
        require(missing_password.returncode != 0, "missing SMTP secret was not blocked")
        require(load_json(direct_receipt_path).get("status") == "auth_required", "missing SMTP secret status mismatch")
        results.append({"test": "direct_email_missing_secret_blocked", "status": "passed"})

        feishu_receipt_path = temp / "internal" / "feishu-message-test-receipt.json"
        feishu_dry_run = run(
            [
                sys.executable,
                str(root / "send_feishu_message.py"),
                "--analysis",
                str(analysis_path),
                "--report",
                str(report_path),
                "--user-id",
                "ou_selftestuser",
                "--chat-id",
                "oc_selftestchat",
                "--lark-cli",
                sys.executable,
                "--ledger",
                str(temp / "internal" / "feishu-message-test-ledger.json"),
                "--receipt",
                str(feishu_receipt_path),
                "--dry-run",
            ],
            root,
        )
        feishu_receipt = load_json(feishu_receipt_path)
        require(feishu_dry_run.returncode == 0, feishu_dry_run.stderr or feishu_dry_run.stdout)
        require(feishu_receipt.get("status") == "dry_run_passed", "Feishu message dry-run did not pass")
        require(len(feishu_receipt.get("planned", [])) == 2, "Feishu fixed targets were not planned")
        require(
            feishu_receipt.get("fingerprint") != direct_receipt.get("fingerprint"),
            "channel-specific fingerprints collided",
        )
        results.append({"test": "feishu_user_and_group_dry_run", "status": "passed"})

        invalid_feishu = run(
            [
                sys.executable,
                str(root / "send_feishu_message.py"),
                "--analysis",
                str(analysis_path),
                "--report",
                str(report_path),
                "--chat-id",
                "not-a-chat-id",
                "--lark-cli",
                sys.executable,
                "--dry-run",
            ],
            root,
        )
        require(invalid_feishu.returncode != 0, "invalid Feishu target was not blocked")
        results.append({"test": "invalid_feishu_target_blocked", "status": "passed"})

        missing_cli_receipt = temp / "internal" / "feishu-cli-missing-receipt.json"
        missing_cli = run(
            [
                sys.executable,
                str(root / "send_feishu_message.py"),
                "--analysis",
                str(analysis_path),
                "--report",
                str(report_path),
                "--chat-id",
                "oc_selftestchat",
                "--lark-cli",
                str(temp / "missing-lark-cli"),
                "--ledger",
                str(temp / "internal" / "feishu-cli-missing-ledger.json"),
                "--receipt",
                str(missing_cli_receipt),
                "--preflight",
            ],
            root,
        )
        require(missing_cli.returncode != 0, "missing Feishu CLI was not blocked")
        require(load_json(missing_cli_receipt).get("status") == "lark_cli_missing", "missing Feishu CLI status mismatch")
        results.append({"test": "missing_feishu_cli_guided_block", "status": "passed"})

    print(json.dumps({"status": "passed", "tests": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
