# Dynamic collection analysis

Treat every collection run as a new, unpredictable dataset. Keep the risk standard stable; never keep a fixed list of expected documents, topics, or conclusions.

## Run isolation

- Define the current-run task set from the customer's latest confirmed `collection_tasks`.
- Include only those task ids and their newest completed exports in `report_meta.source_tasks`.
- Never merge an earlier task, export, finding, profile inference, or enforcement pattern unless the customer explicitly includes it in the current run.
- Create non-secret `current-run-tasks.json` from MCP results with task id, exact name, role, completed/exported status, export URL, and local full-export path.
- Run `scripts/build_run_manifest.py` to recompute record count, byte size, and SHA-256 snapshot from each downloaded file. A changed snapshot requires a new analysis.
- Pass the verified `collection-provenance.json` to `scripts/build_evidence_index.py`. Do not analyze an orphan export that lacks current-run status and snapshot proof.

## Full-data rule

- Download and parse the full export. MCP samples are for connectivity checks only and cannot support the final report.
- Normalize every record, preserve `raw`, and run `scripts/build_evidence_index.py`.
- Read the complete evidence index, not only the first page or top-ranked records. Index coverage proves ingestion only; it does not prove semantic review.
- Deep-read the full body of every record that may match the enterprise, alter another document's effect, supply a legal basis, or contradict a candidate finding.
- Maintain an internal `semantic-review-ledger.json` with exactly one row per indexed `record_id`:

```json
{
  "records": [
    {
      "record_id": "",
      "review_depth": "screened|full_body",
      "disposition": "candidate|excluded|pending",
      "reason": ""
    }
  ]
}
```

- Use `full_body` for every `candidate` or `pending` record. A clearly irrelevant item may be `screened` and `excluded` only after its title, authority, effect, scope, and body head have been reviewed.
- If the dataset is too large for one context window, process deterministic batches and append to the ledger. Do not stop after finding the first few risks.
- Run `scripts/validate_review_coverage.py` and block rendering until it passes.

## Schema adaptation

- Discover source keys before assuming a schema. Common fields may appear as `文件名`, `标题`, `正文`, `文号`, `来源`, `页面网址`, or new provider-specific names.
- Use `scripts/normalize_records.py` first. It preserves unknown fields under `raw`.
- If a required normalized field is still empty, inspect the raw keys and body. Extend aliases or extraction logic for the new source, rerun normalization, and report the adaptation in internal validation.
- Reject mojibake, source text truncation, dates that contain authority text, and URLs that are not official before analysis.
- Distinguish publication date, effective date, validity end date, and the date of an event or attachment.

## Semantic review

Use the evidence index as a complete inventory, not as a keyword scoring model.

1. Review every title, authority, document number, date, effect label, source type, and body length.
2. Identify candidate documents from meaning and enterprise activities. Keywords may help locate passages but cannot decide applicability or severity.
3. For each candidate, read the full body and identify the regulated subject, jurisdiction, activity, obligation verb, trigger, deadline, effect, consequence, and exceptions.
4. Trace each candidate to exact enterprise-profile fields and values.
5. Search the rest of the current-run dataset for amendments, extensions, repeals, implementing rules, overlapping notices, and contradictory effect signals.
6. Put uncertain or incomplete items in `pending_verification`; do not force them into active risk.
7. Record `not_applicable` examples when they demonstrate that profile filtering prevented a plausible false positive.

## Action design

Derive measures from the concrete gap or trigger in the current source:

- name the process, system, product, report, vendor, or evidence item;
- assign one accountable owner;
- set a deadline tied to the urgency of the obligation;
- name the deliverable that proves completion;
- use containment, remediation, and testing/monitoring steps when the risk warrants a sequence.

Do not reuse action text merely because a previous report had the same broad theme.

## Completion check

Before rendering, verify:

- `validate_review_coverage.py` passes with exactly one semantic disposition for every indexed current-run record;
- evidence-index provenance contains the exact latest confirmed tasks, completed/exported states, full-export URLs, and recomputed snapshots;
- every active finding cites a current-run record;
- every source task and snapshot belongs to the latest confirmed task set;
- no finding or enforcement pattern was inherited from an excluded run;
- the report's counts, date range, authorities, and scope caveat match the actual current-run data.
