# Delivery channels

Select exactly one channel for each publication request. Rendering and evidence validation are channel-independent.

## Feishu CLI

Use `channel: feishu_cli` when the report must be posted to fixed Feishu people or groups.
Before collecting channel inputs, follow the Feishu installation and authorization flow in [onboarding.md](onboarding.md). Never assume the customer already has the CLI.

Required configuration:

```yaml
delivery:
  channel: feishu_cli
  auto_send: true
  feishu:
    identity: user | bot
    users: [ou_xxx]
    chats: [oc_xxx]
```

- `users` accepts Feishu user `open_id` values beginning with `ou_`.
- `chats` accepts Feishu chat ids beginning with `oc_`.
- Resolve a group name with `lark-cli im +chat-search`; require one exact intended match before persisting its id in customer configuration.
- Publish two components to every target: a short management summary and the exact `regulatory-risk-report.html` file.
- Use a deterministic idempotency key for each target and component.
- `identity: user` requires a valid user device login. `identity: bot` requires an approved bot application and target access.
- Treat any missing component as `partial_send_failed`; never report full success merely because the summary or one target succeeded.

Commands:

```powershell
python scripts/send_feishu_message.py --analysis analysis.json --report regulatory-risk-report.html --user-id ou_xxx --chat-id oc_xxx --dry-run
python scripts/send_feishu_message.py --analysis analysis.json --report regulatory-risk-report.html --chat-id oc_xxx --preflight
python scripts/send_feishu_message.py --analysis analysis.json --report regulatory-risk-report.html --chat-id oc_xxx
```

## Direct email

Use `channel: direct_email` when the report must be sent without Feishu.
Ask every SMTP setting and guide the customer to create a dedicated authorization code as described in [onboarding.md](onboarding.md). Never place the code in this configuration.

Required configuration:

```yaml
delivery:
  channel: direct_email
  auto_send: true
  direct_email:
    from_address: compliance@example.com
    to: [recipient@example.com]
    cc: []
    bcc: []
    smtp:
      host: smtp.example.com
      port: 587
      security: starttls
      username: compliance@example.com
      password_env: REGULATORY_REPORT_SMTP_PASSWORD
      no_auth: false
```

- Accept `ssl`, `starttls`, or `none`; default ports are 465, 587, and 25 respectively.
- Read the password or mailbox authorization code from `password_env` only. Never accept it as a command-line argument and never write it to an artifact.
- Use `no_auth: true` only for an explicitly trusted internal relay.
- Send the exact HTML bytes as the email HTML body and as `regulatory-risk-report.html`.
- Keep Bcc recipients out of MIME headers; include them only in the SMTP envelope and protected delivery receipt.
- Treat SMTP authentication, connectivity, and recipient refusal as hard publication failures.

Commands:

```powershell
python scripts/send_direct_email.py --analysis analysis.json --report regulatory-risk-report.html --from-address compliance@example.com --to recipient@example.com --smtp-host smtp.example.com --security starttls --password-env REGULATORY_REPORT_SMTP_PASSWORD --dry-run
python scripts/send_direct_email.py --analysis analysis.json --report regulatory-risk-report.html --from-address compliance@example.com --to recipient@example.com --smtp-host smtp.example.com --security starttls --password-env REGULATORY_REPORT_SMTP_PASSWORD --preflight
python scripts/send_direct_email.py --analysis analysis.json --report regulatory-risk-report.html --from-address compliance@example.com --to recipient@example.com --smtp-host smtp.example.com --security starttls --password-env REGULATORY_REPORT_SMTP_PASSWORD
```

For a hidden one-time terminal prompt, replace `--password-env ...` with `--prompt-password`.

## Shared release gates

Before either channel sends:

1. Require all source tasks to be completed and exported.
2. Validate analysis evidence and rendered HTML.
3. Validate every fixed destination.
4. Run the channel authentication preflight.
5. Block a previously sent channel-specific fingerprint.
6. Preserve a receipt containing status, report hash, fingerprint, destinations, and provider message ids without secrets.
