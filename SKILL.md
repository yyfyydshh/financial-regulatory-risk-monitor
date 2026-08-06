---
name: financial-regulatory-risk-monitor
description: Guide every required Octoparse API-Key, enterprise-profile, current-run collection-task, and delivery input; read and semantically analyze unpredictable full exports of Chinese government regulations, notices, or financial enforcement data; create an evidence-gated enterprise HTML risk report; and deliver it to fixed Feishu users/groups through lark-cli or directly by SMTP email. Use for first-time onboarding, latest-task-only regulatory monitoring, municipal or financial-policy screening, synthetic-profile demos, and repeatable collection-to-risk-to-delivery workflows.
---

# Financial Regulatory Risk Monitor

Turn official financial-regulatory collection results into an enterprise-specific, traceable HTML risk prompt. Treat the report as compliance decision support, not a legal opinion.

## Required input

Accept the following shape. Preserve unknown profile fields as supplemental context.

```yaml
octoparse_mcp:
  endpoint: https://mcp.bazhuayu.com
  auth_mode: api_key
  api_key_configured: true
profile_mode: provided | synthetic_from_data
enterprise_profile:
  company_name:
  company_type:
  operating_regions: []
  licensed_activities: []
  products_and_services: []
  customer_types: []
  sales_channels: []
  consumer_protection_exposure: []
  data_processing_activities: []
  technology_outsourcing: []
  anti_money_laundering_exposure: []
  governance_features: []
  partner_and_intermediary_types: []
enterprise_profile_confirmed: true
collection_tasks:
  - task_id:
    task_name:
    role: regulatory_notice | enforcement_penalty
collection_tasks_confirmed: true
delivery:
  channel: feishu_cli | direct_email
  auto_send: true
  confirmed: true
  feishu:
    identity: user | bot
    users: []  # ou_xxx
    chats: []  # oc_xxx
  direct_email:
    from_address:
    to: []
    cc: []
    bcc: []
    smtp:
      host:
      port:
      security: ssl | starttls | none
      username:
      password_env: REGULATORY_REPORT_SMTP_PASSWORD
      no_auth: false
```

Use `synthetic_from_data` only for demonstrations and label the resulting enterprise as synthetic throughout the report. For production, require a customer-provided and customer-confirmed profile before treating a finding as enterprise-specific.
Configure only the selected delivery branch. Read [delivery-channels.md](references/delivery-channels.md) before any delivery action. Never store an SMTP password, mailbox authorization code, Feishu token, or Octoparse API key in Skill files, reports, receipts, ledgers, or command output.

## Mandatory onboarding

Read [onboarding.md](references/onboarding.md) and conduct the questionnaire before taking any mutating action. Ask every field; never silently import a previous value, assume an empty list, select a channel, or enable automatic sending on the customer's behalf. Group related questions into short rounds, explain unfamiliar terms, and record an explicit empty list or `false` when that is the customer's answer.

- For a new customer, ask all connection, profile-mode, profile, task, delivery, destination, and auto-send questions.
- For a returning customer, show each saved non-secret value and ask whether it remains valid. Ask changed or unconfirmed fields again.
- Never ask the customer to paste an API key, SMTP authorization code, Feishu app secret, or token into ordinary chat when a secure credential field, hidden terminal prompt, or secret manager is available.
- Store only `api_key_configured: true` and the SMTP environment-variable name. Do not store either secret value.
- Run `scripts/validate_request.py --stage collect` before starting tasks. Ask every returned question and rerun until `status: ready`.
- For `synthetic_from_data`, generate the profile after collection, show every field, ask for explicit confirmation, then run `scripts/validate_request.py --stage publish --check-runtime`.
- For `provided`, require the complete profile and confirmation before collection, then rerun the publish-stage validation before sending.
- Do not run collection, preflight, or delivery while the corresponding validator status is `input_required`.

## Workflow

1. Read [onboarding.md](references/onboarding.md), [enterprise-profile.md](references/enterprise-profile.md), [dynamic-data-analysis.md](references/dynamic-data-analysis.md), [risk-standard.md](references/risk-standard.md), [applicability-rules.md](references/applicability-rules.md), and—when delivery is requested—[delivery-channels.md](references/delivery-channels.md).
2. Complete the mandatory questionnaire and pass the collect-stage request validation.
3. Verify the configured `bazhuayu` MCP with a read-only task search. Use Streamable HTTP with API-Key authentication only. Never switch to OAuth or Bearer authorization and never write the API key into Skill files or artifacts.
4. Resolve every current-run collection task exactly by task id or exact task name. Show the resolved list and obtain `collection_tasks_confirmed: true`. Treat this list as an isolation boundary: exclude every earlier task and report unless the customer explicitly includes it again.
5. Start independent tasks in parallel with `start_or_stop_task(action="start")`. Poll every 10–30 seconds. After each task has completed, call `export_data` with `exportFileType="JSON"`, download the full export when a file URL is returned, and preserve the task id, role, run state, export count, export URL, and snapshot identity. Never base a final report on MCP sample rows.
6. Record the current MCP results and local export paths in non-secret `current-run-tasks.json`, then run `scripts/build_run_manifest.py`. Require completed/exported state and a recomputed snapshot for every current-run file.
7. Normalize every full export with `scripts/normalize_records.py`, then build a topic-neutral complete inventory with `scripts/build_evidence_index.py --provenance collection-provenance.json`. Merge duplicates without dropping distinct documents. A penalty record remains an `enforcement_penalty`; it is never converted into a generally applicable obligation. Adapt field aliases or extraction logic when a new source schema leaves required fields empty; preserve unknown raw fields.
8. Build the enterprise profile:
   - `provided`: retain the customer's exact facts and identify unanswered trigger fields.
   - `synthetic_from_data`: infer a plausible demonstration profile that intentionally intersects multiple collected themes, but do not invent licenses or operations unsupported by the demo label. Explain which data themes drove each synthetic attribute, show every field to the customer, and obtain `enterprise_profile_confirmed: true`.
9. Complete the publish-stage request validation. Do not continue while any input, destination, confirmation, CLI setup, or SMTP secret is unresolved.
10. Read the complete evidence index and semantically review the current-run records as required by `references/dynamic-data-analysis.md`. Do not use a fixed topic list, inherited conclusions, or keyword scores as risk decisions. Create `semantic-review-ledger.json`, deep-read full bodies for candidate obligations, amendments, repeals, exceptions, and contradictory effect signals, then require `scripts/validate_review_coverage.py` to pass.
11. Create an analysis JSON manifest using the schema in `references/risk-standard.md`. Apply source, effect, applicability, obligation, consequence, and enterprise-exposure gates in that order.
   - Write every active finding for management consumption as `risk_point`, `risk_reason`, and `action_plan`.
   - Form `risk_point` as: specific process/object + concrete gap or trigger + direct risk outcome. Avoid vague phrases such as “需关注”“可能不完整” or a rewritten document title.
   - If the enterprise has not provided control evidence, state “缺少可验证证据” or “需核验是否形成闭环”; do not assert that a production enterprise lacks the control.
   - Keep `risk_reason` to the decisive regulatory requirement, profile match, and consequence.
   - For every critical/high finding, provide 2–4 `action_plan` steps with action, owner, deadline, and deliverable. Prefer policy, workflow, system-control, monitoring, sampling, or drill measures over generic “加强管理”.
12. Verify semantic review coverage, not merely index coverage, and ensure every finding cites a record from a current-run snapshot. Run `scripts/validate_report.py --analysis <analysis.json>`. Correct all errors before rendering. Warnings may remain only in the report's “待核实” area.
13. Render `regulatory-risk-report.html` with `scripts/render_report.py`. Do not create a Markdown report. Use the same HTML bytes as the email HTML body and as the attached `regulatory-risk-report.html`.
14. If delivery is requested, select exactly one adapter:
   - `feishu_cli`: call `scripts/send_feishu_message.py` to post a concise management summary and the exact HTML report attachment to every configured `ou_...` user and `oc_...` chat. Resolve names to ids before publication; store fixed ids in customer configuration, not in the Skill itself.
   - `direct_email`: call `scripts/send_direct_email.py` to send the exact HTML as both email body and `regulatory-risk-report.html` attachment through the configured SMTP server. Read the password or mailbox authorization code only from `password_env`.
15. Run the selected adapter with `--dry-run`, then `--preflight`, before the first live send for a new channel configuration. When the customer has explicitly answered `auto_send: true` and confirmed the destinations, valid inputs authorize immediate sending after all automatic gates pass; do not ask for a second send confirmation. If destinations are missing or malformed, authentication fails, evidence fails, a target rejects delivery, or the channel-specific fingerprint already exists, do not claim complete delivery and return the exact receipt status.

## Professional judgment gates

Keep severity and confidence separate. Apply these non-negotiable rules:

- `critical`: direct, current, mandatory obligation; all applicability gates true; high confidence; credible license, operating-restriction, or major-penalty consequence.
- `high`: direct, current obligation with explicit remediation, reporting, internal-control, or consumer-protection requirements; evidence complete; confidence high or medium.
- `medium`: conditional applicability needing additional product, scale, license, or control facts.
- `watch`: regulatory direction, draft/expired material, indirect enforcement signal, or low-confidence item.
- `not_applicable`: jurisdiction, subject, activity, or time condition does not match.

Low-confidence information cannot be `critical`, `high`, or `medium`. Every `critical` or `high` finding must contain an official source URL, complete source text or a sufficient evidence excerpt, explicit applicability logic, and at least one matched enterprise-profile field. A penalty may reveal enforcement focus and consequences but must not claim that the profiled enterprise violated the law.

## Output contract

User-visible artifacts are only:

- `regulatory-risk-report.html`
- for `feishu_cli`: a management-summary post and the HTML report attachment in each configured personal chat or group
- for `direct_email`: the HTML email body and the same HTML report attachment

Internal JSON may include normalized records, the analysis manifest, validation result, report fingerprint, send ledger, and delivery receipt. The HTML must be self-contained and email-safe: inline CSS and table layout only; no JavaScript, external fonts, remote stylesheets, or color-only risk encoding.

Use a channel-specific fingerprint containing the report bytes, enterprise profile, task snapshots, channel, and normalized destinations. A successful send blocks an identical repeat for that channel and destination set. Feishu partial failures must preserve component-level results; retry with the same idempotency keys so an already delivered summary or attachment is not duplicated. Direct email must omit Bcc recipients from message headers while retaining them in the SMTP envelope and internal receipt.

Lead the HTML with management decisions, not legal analysis. For each active item show, in this order: `风险点` → `为什么有风险` → `落地策略`. Render the strategy as numbered, independently assignable steps with owner, deadline, and deliverable. Keep the official source, date, short evidence excerpt, matched profile fields, and confidence in a compact evidence footer. Move `not_applicable` items into a concise exclusion list rather than rendering them as full risk cards.

## Commands

Check which onboarding inputs still require questions:

```powershell
python scripts/validate_request.py --request request.json --stage collect
python scripts/validate_request.py --request request.json --stage publish --check-runtime
```

Normalize and index one or more current-run exports:

```powershell
python scripts/build_run_manifest.py --metadata current-run-tasks.json --output collection-provenance.json
python scripts/normalize_records.py --input regulatory_notice:task-id=notice.json --output normalized-records.json
python scripts/build_evidence_index.py --input normalized-records.json --provenance collection-provenance.json --output evidence-index.json
python scripts/validate_review_coverage.py --index evidence-index.json --ledger semantic-review-ledger.json
```

Validate and render:

```powershell
python scripts/validate_report.py --analysis analysis.json --result validation.json
python scripts/render_report.py --analysis analysis.json --output regulatory-risk-report.html
```

Exercise a Feishu personal/group publication without sending:

```powershell
python scripts/send_feishu_message.py --analysis analysis.json --report regulatory-risk-report.html --user-id ou_xxx --chat-id oc_xxx --dry-run
```

Check Feishu authentication without posting:

```powershell
python scripts/send_feishu_message.py --analysis analysis.json --report regulatory-risk-report.html --chat-id oc_xxx --preflight
```

Exercise direct SMTP email without connecting:

```powershell
python scripts/send_direct_email.py --analysis analysis.json --report regulatory-risk-report.html --from-address sender@example.com --to recipient@example.com --smtp-host smtp.example.com --security starttls --password-env REGULATORY_REPORT_SMTP_PASSWORD --dry-run
```

Check SMTP connection and authentication without sending:

```powershell
python scripts/send_direct_email.py --analysis analysis.json --report regulatory-risk-report.html --from-address sender@example.com --to recipient@example.com --smtp-host smtp.example.com --security starttls --password-env REGULATORY_REPORT_SMTP_PASSWORD --preflight
```

When a customer cannot use a secret manager or session environment variable, let them enter the SMTP authorization code in a hidden terminal prompt:

```powershell
python scripts/send_direct_email.py --analysis analysis.json --report regulatory-risk-report.html --from-address sender@example.com --to recipient@example.com --smtp-host smtp.example.com --security starttls --prompt-password --preflight
```

Feishu user-identity publication requires a valid `lark-cli` user login; bot publication requires an approved bot application with access to each target. Direct email requires a reachable SMTP service and, unless an explicitly trusted relay is selected with `no_auth`, a password or mailbox authorization code in the configured environment variable. The legacy `send_feishu_mail.py` remains available only for backward compatibility and is not one of the two primary delivery modes.
