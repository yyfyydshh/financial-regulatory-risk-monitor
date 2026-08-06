#!/usr/bin/env python3
"""Send the validated HTML report directly through an SMTP server."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import smtplib
import ssl
from pathlib import Path
from typing import Any

from delivery_common import (
    EMAIL_RE,
    DeliveryBlocked,
    build_email_message,
    expand_values,
    message_bytes,
    prepare_delivery,
    record_sent,
    write_receipt,
)


def open_smtp(
    host: str,
    port: int,
    security: str,
    timeout: float,
) -> smtplib.SMTP:
    if security == "ssl":
        client: smtplib.SMTP = smtplib.SMTP_SSL(
            host,
            port,
            timeout=timeout,
            context=ssl.create_default_context(),
        )
        client.ehlo()
        return client
    client = smtplib.SMTP(host, port, timeout=timeout)
    client.ehlo()
    if security == "starttls":
        client.starttls(context=ssl.create_default_context())
        client.ehlo()
    return client


def output_status(status: str, **details: Any) -> None:
    print(json.dumps({"status": status, **details}, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--to", action="append")
    parser.add_argument("--cc", action="append")
    parser.add_argument("--bcc", action="append")
    parser.add_argument("--from-address", required=True)
    parser.add_argument("--subject")
    parser.add_argument("--smtp-host", required=True)
    parser.add_argument("--smtp-port", type=int)
    parser.add_argument(
        "--security",
        choices=("ssl", "starttls", "none"),
        default="starttls",
    )
    parser.add_argument("--username")
    parser.add_argument(
        "--password-env",
        default="REGULATORY_REPORT_SMTP_PASSWORD",
        help="environment variable containing the SMTP password or mailbox authorization code",
    )
    parser.add_argument(
        "--no-auth",
        action="store_true",
        help="use only for an explicitly trusted SMTP relay that does not require login",
    )
    parser.add_argument(
        "--prompt-password",
        action="store_true",
        help="read the SMTP authorization code from a hidden terminal prompt instead of an environment variable",
    )
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--ledger")
    parser.add_argument("--receipt")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument(
        "--preflight",
        action="store_true",
        help="connect and authenticate without sending",
    )
    args = parser.parse_args()
    if args.no_auth and args.prompt_password:
        parser.error("--no-auth and --prompt-password cannot be used together")

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
        else internal_dir / "direct-email-receipt.json"
    )

    to = expand_values(args.to)
    cc = expand_values(args.cc)
    bcc = expand_values(args.bcc)
    if not to:
        write_receipt(receipt_path, "awaiting_recipient", reason="delivery.email.to is empty")
        output_status("awaiting_recipient", receipt=str(receipt_path))
        return 3
    invalid = [
        address
        for address in to + cc + bcc + [args.from_address]
        if not EMAIL_RE.fullmatch(address)
    ]
    if invalid:
        write_receipt(receipt_path, "invalid_recipient", invalid=invalid)
        output_status("invalid_recipient", invalid=invalid)
        return 4
    if args.smtp_port is not None and not (1 <= args.smtp_port <= 65535):
        write_receipt(receipt_path, "invalid_smtp_config", reason="smtp port must be 1-65535")
        return 4
    if not args.smtp_host.strip():
        write_receipt(receipt_path, "invalid_smtp_config", reason="smtp host is empty")
        return 4
    if args.timeout <= 0:
        write_receipt(receipt_path, "invalid_smtp_config", reason="timeout must be positive")
        return 4

    port = args.smtp_port or {"ssl": 465, "starttls": 587, "none": 25}[args.security]
    destination = {
        "from": args.from_address.lower(),
        "to": sorted(address.lower() for address in to),
        "cc": sorted(address.lower() for address in cc),
        "bcc": sorted(address.lower() for address in bcc),
        "smtp_host": args.smtp_host.lower(),
        "smtp_port": port,
        "security": args.security,
    }
    try:
        context = prepare_delivery(
            analysis_path,
            report_path,
            "direct_email",
            destination,
            ledger_path,
        )
    except DeliveryBlocked as exc:
        write_receipt(receipt_path, exc.status, **exc.details)
        output_status(exc.status, **{key: value for key, value in exc.details.items() if key != "prior"})
        return exc.exit_code

    subject = args.subject or str(
        context.analysis.get("report_meta", {}).get("title")
        or "金融监管风险提示报告"
    )
    message = build_email_message(
        args.from_address,
        to,
        cc,
        subject,
        report_path,
        context.report_html,
    )
    raw_message = message_bytes(message)

    if args.dry_run:
        write_receipt(
            receipt_path,
            "dry_run_passed",
            channel="direct_email",
            fingerprint=context.fingerprint,
            recipients={"to": to, "cc": cc, "bcc": bcc},
            smtp={
                "host": args.smtp_host,
                "port": port,
                "security": args.security,
                "authenticated": not args.no_auth,
                "password_env": None if args.no_auth else args.password_env,
            },
            mime_bytes=len(raw_message),
            report_sha256=context.report_sha256,
            warnings=context.warnings,
        )
        output_status(
            "dry_run_passed",
            fingerprint=context.fingerprint,
            mime_bytes=len(raw_message),
        )
        return 0

    password = ""
    username = args.username or args.from_address
    if not args.no_auth:
        password = (
            getpass.getpass("SMTP password or authorization code: ")
            if args.prompt_password
            else os.environ.get(args.password_env, "")
        )
        if not password:
            write_receipt(
                receipt_path,
                "auth_required",
                channel="direct_email",
                fingerprint=context.fingerprint,
                reason=(
                    "hidden SMTP authorization-code input was empty"
                    if args.prompt_password
                    else f"environment variable {args.password_env} is empty"
                ),
            )
            output_status("auth_required", receipt=str(receipt_path))
            return 10

    client: smtplib.SMTP | None = None
    try:
        client = open_smtp(args.smtp_host, port, args.security, args.timeout)
        if not args.no_auth:
            client.login(username, password)
        if args.preflight:
            write_receipt(
                receipt_path,
                "ready_to_send",
                channel="direct_email",
                fingerprint=context.fingerprint,
                from_address=args.from_address,
                recipients={"to": to, "cc": cc, "bcc": bcc},
                report_sha256=context.report_sha256,
                warnings=context.warnings,
            )
            output_status("ready_to_send", fingerprint=context.fingerprint)
            return 0

        refused = client.send_message(
            message,
            from_addr=args.from_address,
            to_addrs=to + cc + bcc,
        )
        if refused:
            write_receipt(
                receipt_path,
                "recipient_refused",
                channel="direct_email",
                fingerprint=context.fingerprint,
                refused=sorted(refused),
            )
            output_status("recipient_refused", refused=sorted(refused))
            return 12
    except smtplib.SMTPAuthenticationError as exc:
        write_receipt(
            receipt_path,
            "auth_required",
            channel="direct_email",
            fingerprint=context.fingerprint,
            reason=f"SMTP authentication failed ({exc.smtp_code})",
        )
        output_status("auth_required", receipt=str(receipt_path))
        return 10
    except (smtplib.SMTPException, OSError, TimeoutError) as exc:
        write_receipt(
            receipt_path,
            "send_failed" if not args.preflight else "preflight_failed",
            channel="direct_email",
            fingerprint=context.fingerprint,
            error=str(exc),
        )
        output_status(
            "send_failed" if not args.preflight else "preflight_failed",
            receipt=str(receipt_path),
        )
        return 13
    finally:
        if client is not None:
            try:
                client.quit()
            except (smtplib.SMTPException, OSError):
                client.close()

    message_id = str(message.get("Message-ID") or "")
    entry = {
        "channel": "direct_email",
        "message_id": message_id,
        "from": args.from_address,
        "to": to,
        "cc": cc,
        "bcc": bcc,
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
        message_id=message_id,
        fingerprint=context.fingerprint,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
