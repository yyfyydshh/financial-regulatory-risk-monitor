#!/usr/bin/env python3
"""List every unanswered onboarding input before collection or publication."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from delivery_common import EMAIL_RE, FEISHU_CHAT_RE, FEISHU_USER_RE
from risk_common import load_json


PROFILE_FIELDS = {
    "company_name": "企业全称是什么？",
    "company_type": "企业主体类型和持牌机构层级是什么？",
    "operating_regions": "实际经营地区有哪些？没有覆盖的地区也请明确说明。",
    "licensed_activities": "现有牌照及获准业务活动有哪些？",
    "products_and_services": "主要产品和服务有哪些？",
    "customer_types": "主要客户类型有哪些？",
    "sales_channels": "销售和获客渠道有哪些？",
    "consumer_protection_exposure": "涉及哪些消费者权益保护场景？",
    "data_processing_activities": "处理哪些个人信息、业务数据或敏感数据？",
    "technology_outsourcing": "有哪些云服务、系统或技术外包？",
    "anti_money_laundering_exposure": "涉及哪些反洗钱或客户尽职调查活动？",
    "governance_features": "现有合规治理、内控、审计和整改机制有哪些？",
    "partner_and_intermediary_types": "合作平台、中介、渠道或第三方类型有哪些？",
}


def nested_value(data: dict[str, Any], path: str) -> tuple[bool, Any]:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def add_missing(
    missing: list[dict[str, str]],
    path: str,
    question: str,
    reason: str = "required_input",
) -> None:
    if not any(item["path"] == path for item in missing):
        missing.append({"path": path, "question": question, "reason": reason})


def require_value(
    data: dict[str, Any],
    missing: list[dict[str, str]],
    path: str,
    question: str,
    *,
    allow_empty_list: bool = False,
) -> Any:
    present, value = nested_value(data, path)
    empty = value is None or value == ""
    if isinstance(value, list) and not value and not allow_empty_list:
        empty = True
    if not present or empty:
        add_missing(missing, path, question)
        return None
    return value


def validate_request(
    data: dict[str, Any],
    stage: str,
    check_runtime: bool,
) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []

    endpoint = require_value(
        data,
        missing,
        "octoparse_mcp.endpoint",
        "八爪鱼 MCP 地址是什么？默认可填写 https://mcp.bazhuayu.com。",
    )
    if endpoint and str(endpoint).rstrip("/") != "https://mcp.bazhuayu.com":
        add_missing(
            missing,
            "octoparse_mcp.endpoint",
            "请确认八爪鱼 MCP 地址；当前 Skill 的标准地址是 https://mcp.bazhuayu.com。",
            "invalid_value",
        )
    auth_mode = require_value(
        data,
        missing,
        "octoparse_mcp.auth_mode",
        "请选择八爪鱼 MCP 鉴权方式；本服务只能选择 api_key。",
    )
    if auth_mode and auth_mode != "api_key":
        add_missing(
            missing,
            "octoparse_mcp.auth_mode",
            "八爪鱼 MCP 仅支持 API-Key；请勿选择 OAuth 或 Bearer Token。",
            "invalid_value",
        )
    configured_present, configured = nested_value(
        data,
        "octoparse_mcp.api_key_configured",
    )
    if not configured_present or configured is not True:
        add_missing(
            missing,
            "octoparse_mcp.api_key_configured",
            "请在 MCP 客户端的安全凭据字段填写 API-Key，完成后仅确认“已配置”；不要把密钥写入配置文件或报告。",
            "secret_setup_required",
        )

    profile_mode = require_value(
        data,
        missing,
        "profile_mode",
        "本次使用客户提供画像还是采集后生成演示画像？请选择 provided 或 synthetic_from_data。",
    )
    if profile_mode not in (None, "provided", "synthetic_from_data"):
        add_missing(
            missing,
            "profile_mode",
            "画像模式只能选择 provided 或 synthetic_from_data。",
            "invalid_value",
        )
    profile_required = profile_mode == "provided" or stage == "publish"
    if profile_required:
        for field, question in PROFILE_FIELDS.items():
            require_value(
                data,
                missing,
                f"enterprise_profile.{field}",
                question,
                allow_empty_list=field not in {"company_name", "company_type"},
            )
        confirmed_present, confirmed = nested_value(
            data,
            "enterprise_profile_confirmed",
        )
        if not confirmed_present or confirmed is not True:
            add_missing(
                missing,
                "enterprise_profile_confirmed",
                "请查看完整企业画像并确认其可用于本次适用性判断。",
                "confirmation_required",
            )

    tasks = require_value(
        data,
        missing,
        "collection_tasks",
        "请提供至少一个要执行的采集任务名称或 taskId，并说明其角色。",
    )
    if isinstance(tasks, list):
        for index, task in enumerate(tasks):
            base = f"collection_tasks[{index}]"
            if not isinstance(task, dict):
                add_missing(
                    missing,
                    base,
                    f"第 {index + 1} 个采集任务需要名称或 taskId 以及 role。",
                )
                continue
            if not task.get("task_id") and not task.get("task_name"):
                add_missing(
                    missing,
                    f"{base}.task_id_or_name",
                    f"第 {index + 1} 个采集任务的准确名称或 taskId 是什么？",
                )
            if task.get("role") not in (
                "regulatory_notice",
                "enforcement_penalty",
            ):
                add_missing(
                    missing,
                    f"{base}.role",
                    f"第 {index + 1} 个任务属于监管公告还是行政处罚？",
                )
    elif tasks is not None:
        add_missing(
            missing,
            "collection_tasks",
            "采集任务必须是列表；请逐项提供准确名称或 taskId 及其角色。",
            "invalid_value",
        )
    tasks_confirmed_present, tasks_confirmed = nested_value(
        data,
        "collection_tasks_confirmed",
    )
    if not tasks_confirmed_present or tasks_confirmed is not True:
        add_missing(
            missing,
            "collection_tasks_confirmed",
            "请确认任务清单和每个任务的角色，确认后才启动采集。",
            "confirmation_required",
        )

    channel = require_value(
        data,
        missing,
        "delivery.channel",
        "报告采用哪种送达方式：feishu_cli 还是 direct_email？",
    )
    auto_send_present, auto_send = nested_value(data, "delivery.auto_send")
    if not auto_send_present or not isinstance(auto_send, bool):
        add_missing(
            missing,
            "delivery.auto_send",
            "通过发布门槛后是否自动发送？请选择 true 或 false。",
        )

    if channel == "feishu_cli":
        identity = require_value(
            data,
            missing,
            "delivery.feishu.identity",
            "飞书以当前用户还是机器人身份发布？请选择 user 或 bot。",
        )
        if identity not in (None, "user", "bot"):
            add_missing(
                missing,
                "delivery.feishu.identity",
                "飞书身份只能选择 user 或 bot。",
                "invalid_value",
            )
        _, users = nested_value(data, "delivery.feishu.users")
        _, chats = nested_value(data, "delivery.feishu.chats")
        if not users and not chats:
            add_missing(
                missing,
                "delivery.feishu.targets",
                "请提供固定接收人的 ou_... open_id 或固定群组的 oc_... chat_id；若只有名称，先提供准确名称用于解析。",
            )
        if users and (
            not isinstance(users, list)
            or any(not FEISHU_USER_RE.fullmatch(str(item)) for item in users)
        ):
            add_missing(
                missing,
                "delivery.feishu.users",
                "固定个人必须使用 ou_... open_id 列表；若只有姓名，请先授权查询并确认唯一匹配。",
                "invalid_value",
            )
        if chats and (
            not isinstance(chats, list)
            or any(not FEISHU_CHAT_RE.fullmatch(str(item)) for item in chats)
        ):
            add_missing(
                missing,
                "delivery.feishu.chats",
                "固定群组必须使用 oc_... chat_id 列表；若只有群名，请先搜索并确认唯一匹配。",
                "invalid_value",
            )
    elif channel == "direct_email":
        from_address = require_value(
            data,
            missing,
            "delivery.direct_email.from_address",
            "发件邮箱地址是什么？",
        )
        to = require_value(
            data,
            missing,
            "delivery.direct_email.to",
            "主收件人邮箱有哪些？",
        )
        for path, question in (
            ("delivery.direct_email.cc", "抄送邮箱有哪些？没有请明确填写空列表。"),
            ("delivery.direct_email.bcc", "密送邮箱有哪些？没有请明确填写空列表。"),
            ("delivery.direct_email.smtp.host", "SMTP 服务器地址是什么？"),
            ("delivery.direct_email.smtp.port", "SMTP 端口是多少？"),
            (
                "delivery.direct_email.smtp.security",
                "SMTP 加密方式是什么：ssl、starttls 还是 none？",
            ),
            ("delivery.direct_email.smtp.username", "SMTP 登录用户名是什么？"),
            (
                "delivery.direct_email.smtp.password_env",
                "用于保存 SMTP 授权码的环境变量名是什么？",
            ),
        ):
            require_value(
                data,
                missing,
                path,
                question,
                allow_empty_list=path.endswith((".cc", ".bcc")),
            )
        if from_address and not EMAIL_RE.fullmatch(str(from_address)):
            add_missing(
                missing,
                "delivery.direct_email.from_address",
                "发件邮箱格式无效，请重新填写。",
                "invalid_value",
            )
        for field, values in (
            ("to", to),
            ("cc", nested_value(data, "delivery.direct_email.cc")[1]),
            ("bcc", nested_value(data, "delivery.direct_email.bcc")[1]),
        ):
            if values is not None and (
                not isinstance(values, list)
                or any(not EMAIL_RE.fullmatch(str(item)) for item in values)
            ):
                add_missing(
                    missing,
                    f"delivery.direct_email.{field}",
                    f"{field.upper()} 必须是有效邮箱地址列表；没有时请明确填写空列表。",
                    "invalid_value",
                )
        _, port = nested_value(data, "delivery.direct_email.smtp.port")
        if port is not None and (
            not isinstance(port, int)
            or isinstance(port, bool)
            or not 1 <= port <= 65535
        ):
            add_missing(
                missing,
                "delivery.direct_email.smtp.port",
                "SMTP 端口必须是 1–65535 的整数。",
                "invalid_value",
            )
        _, security = nested_value(
            data,
            "delivery.direct_email.smtp.security",
        )
        if security not in (None, "ssl", "starttls", "none"):
            add_missing(
                missing,
                "delivery.direct_email.smtp.security",
                "SMTP 加密方式只能选择 ssl、starttls 或 none。",
                "invalid_value",
            )
        no_auth_present, no_auth = nested_value(
            data,
            "delivery.direct_email.smtp.no_auth",
        )
        if not no_auth_present or not isinstance(no_auth, bool):
            add_missing(
                missing,
                "delivery.direct_email.smtp.no_auth",
                "SMTP 是否为明确允许免登录的可信内部中继？请选择 true 或 false。",
            )
        if stage == "publish" and check_runtime and no_auth is False:
            _, password_env = nested_value(
                data,
                "delivery.direct_email.smtp.password_env",
            )
            if password_env and not os.environ.get(str(password_env)):
                add_missing(
                    missing,
                    "delivery.direct_email.smtp.authorization_code",
                    "请按邮箱服务商指引生成 SMTP 授权码，并用隐藏输入或秘密管理器写入配置的环境变量；完成后只需确认已设置。",
                    "secret_setup_required",
                )
    elif channel not in (None, "feishu_cli", "direct_email"):
        add_missing(
            missing,
            "delivery.channel",
            "送达方式只能选择 feishu_cli 或 direct_email。",
            "invalid_value",
        )

    delivery_confirmed_present, delivery_confirmed = nested_value(
        data,
        "delivery.confirmed",
    )
    if not delivery_confirmed_present or delivery_confirmed is not True:
        add_missing(
            missing,
            "delivery.confirmed",
            "请确认送达通道、固定接收目标和自动发送选择。",
            "confirmation_required",
        )
    return missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True)
    parser.add_argument(
        "--stage",
        choices=("collect", "publish"),
        default="collect",
    )
    parser.add_argument(
        "--check-runtime",
        action="store_true",
        help="also verify that the selected SMTP secret environment variable is populated",
    )
    args = parser.parse_args()

    request_path = Path(args.request).resolve()
    if not request_path.is_file():
        print(
            json.dumps(
                {
                    "status": "input_required",
                    "missing": [
                        {
                            "path": "request",
                            "question": "请先创建本次运行的非秘密输入清单。",
                            "reason": "artifact_missing",
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 3
    data = load_json(request_path)
    missing = validate_request(data, args.stage, args.check_runtime)
    status = "ready" if not missing else "input_required"
    print(
        json.dumps(
            {
                "status": status,
                "stage": args.stage,
                "missing_count": len(missing),
                "missing": missing,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if not missing else 2


if __name__ == "__main__":
    raise SystemExit(main())
