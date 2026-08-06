# Customer onboarding

Ask every input before execution. Use short rounds so the customer can answer accurately. Do not silently fill fields from examples or prior demonstrations.

## Round 1: connection and usage mode

Ask:

1. Is the Octoparse MCP already connected?
2. Confirm the endpoint: `https://mcp.bazhuayu.com`.
3. Has the API-Key been entered in the MCP client's secure credential field?
4. Confirm that authentication is `api_key`, never OAuth or Bearer Token.
5. Is this a production customer profile (`provided`) or a post-collection demonstration profile (`synthetic_from_data`)?

Do not request the API key in ordinary chat when a secure credential field is available. Record only `api_key_configured: true`. Verify the connection with a read-only task search.

## Round 2: enterprise profile

For `provided`, ask every field in [enterprise-profile.md](enterprise-profile.md), including explicit empty answers. Summarize the completed profile and ask the customer to confirm it before collection.

For `synthetic_from_data`, explain that collection runs first. After deriving the profile, display every field, its synthetic label, and the data theme supporting it. Ask the customer to confirm the complete profile before risk analysis or delivery.

Never interpret a missing answer as “none”. Record an empty list only after the customer says there is no exposure.

## Round 3: collection tasks

Ask for:

- each exact task name or task id;
- whether it is a `regulatory_notice` or `enforcement_penalty`;
- whether all listed tasks may be started now.

Resolve task names read-only, show the exact matched names and ids, then ask for one list-level confirmation. Do not start a partially resolved or unconfirmed list.

## Round 4: delivery selection

Ask:

1. `feishu_cli` or `direct_email`;
2. whether passing all automatic gates should trigger immediate sending (`auto_send`);
3. all channel-specific destinations and settings;
4. whether the displayed channel, destinations, and auto-send setting are confirmed.

### Feishu CLI setup

First check whether `lark-cli --version` or `lark-cli doctor --offline` is available.

If it is missing:

1. Explain that Node.js and npm are required.
2. Ask whether the customer wants to install the official CLI.
3. After approval, install with:

   ```powershell
   npm install -g @larksuite/cli
   ```

4. Verify with `lark-cli --version`.
5. Guide application setup with `lark-cli config init`. If the customer already has an approved application, bind or initialize that application instead of silently creating another.
6. Start user authorization with `lark-cli auth login --domain im`. Show the verification URL exactly as returned and wait for the customer to authorize it.
7. Run `lark-cli doctor`.

If the application is pending administrator approval, stop setup and explain that an administrator must approve the application and IM permissions. Offer `direct_email` as an alternative; never silently switch channels.

Then ask:

- publish as `user` or `bot`;
- fixed user open ids (`ou_...`);
- fixed chat ids (`oc_...`).

When the customer provides names instead of ids, resolve groups with `lark-cli im +chat-search` and users with an authorized directory lookup. Require one exact intended match before recording an id.

### Direct SMTP email setup

Ask:

- sender address;
- To, Cc, and Bcc lists, including explicit empty Cc/Bcc lists;
- SMTP host, port, and `ssl`/`starttls`/`none`;
- SMTP username;
- whether this is an explicitly trusted no-auth relay;
- the environment-variable name that will hold the SMTP authorization code;
- whether automatic sending is allowed after preflight.

Explain how to obtain the secret:

1. Open the sender mailbox provider's security or POP/IMAP/SMTP settings.
2. Enable SMTP if required.
3. Create a dedicated application password or SMTP authorization code. Do not use the normal mailbox login password when the provider offers an authorization code.
4. Put the code in the deployment secret manager or the agreed environment variable.
5. If neither is available, use `send_direct_email.py --prompt-password --preflight` and type the code into the hidden terminal prompt.
6. Confirm only that the secret is configured; never copy the value into request JSON, chat transcripts, reports, receipts, or ledgers.

Run `--dry-run`, then `--preflight`. If either fails, explain the exact setting that must be corrected and ask only for that field again.

## Validation checkpoints

Create a non-secret request JSON and run:

```powershell
python scripts/validate_request.py --request request.json --stage collect
```

Ask every question in `missing[]` and rerun until `status` is `ready`.

Before analysis and delivery, run:

```powershell
python scripts/validate_request.py --request request.json --stage publish --check-runtime
```

Do not start a task or send a report while the relevant validation stage returns `input_required`.
