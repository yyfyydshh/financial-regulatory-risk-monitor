# Evidence-gated risk standard

Use ISO 37301:2021 and ISO 31000:2018 as management-system and risk-process references, not as substitutes for Chinese law. The State-owned Assets Supervision and Administration Commission's compliance measures may inform workflow design but directly govern central state-owned enterprises; do not present them as universally applicable law.

Primary references:

- ISO 37301: https://www.iso.org/standard/75080.html
- ISO 31000: https://www.iso.org/standard/65694.html
- SASAC Order No. 42: https://www.sasac.gov.cn/n2588035/n2588320/n2588335/c26018430/content.html

## Required assessment sequence

1. `source_authenticity`: regulator identity, official link, and text completeness.
2. `effect_status`: `effective`, `future`, `draft`, `expired`, `general_notice`, or `unknown`.
3. `applicability`: jurisdiction, subject type, licensed activity, product/activity, and time.
4. `obligation_type`: `prohibition`, `mandatory`, `reporting`, `remediation`, `internal_control`, `consumer_protection`, `guidance`, or `none`.
5. `potential_consequence`: operating restriction, license effect, administrative penalty, economic loss, remediation burden, and reputation.
6. `enterprise_exposure`: exact enterprise-profile facts that trigger or negate applicability.

## Analysis manifest

The root JSON object contains:

- `report_meta`: title, report id, generated time, jurisdiction, coverage dates, source tasks, and profile mode.
- `enterprise_profile`: standard fields from `enterprise-profile.md`; add `synthetic_basis` for demos.
- `data_quality`: collected, normalized, deduplicated, official-source, complete-text, and unresolved counts.
- `executive_summary`: management conclusion, immediate actions, and scope caveats.
- `findings`: assessed source items.
- `enforcement_patterns`: aggregated conduct, legal-basis, consequence, and control themes. Describe them as signals, not proof against the enterprise.
- `pending_verification`: unanswered facts that could change severity or applicability.
- `disclaimer`: a specific statement that the report is risk decision support and not a legal opinion.

Each finding contains:

```json
{
  "id": "F-001",
  "severity": "critical|high|medium|watch|not_applicable",
  "confidence": "high|medium|low",
  "finding_kind": "regulatory_obligation|enforcement_signal|monitoring",
  "source_type": "regulatory_notice|enforcement_penalty",
  "title": "",
  "risk_point": "one-sentence management risk",
  "risk_reason": "decisive applicability match and consequence",
  "authority": "",
  "document_number": "",
  "published_at": "YYYY-MM-DD",
  "effective_status": "effective|future|draft|expired|general_notice|unknown",
  "source_url": "https://official.example/path",
  "source_text_complete": true,
  "evidence_excerpt": "",
  "applicability": {
    "jurisdiction_match": true,
    "subject_match": true,
    "activity_match": true,
    "time_match": true,
    "matched_profile_fields": ["licensed_activities"],
    "logic": ""
  },
  "obligation_type": "mandatory",
  "legal_basis": "",
  "potential_consequence": "",
  "recommended_owner": "",
  "recommended_action": "",
  "action_plan": [
    {
      "action": "",
      "owner": "",
      "deadline": "",
      "deliverable": ""
    }
  ],
  "due_date": "",
  "open_questions": []
}
```

## Hard gates

- `critical`: confidence high; regulatory obligation; current/future effect; all four applicability booleans true; complete source text; official source; matched profile fields; explicit logic, consequence, and action.
- `high`: confidence high or medium; regulatory obligation; current/future effect; all four applicability booleans true; the same evidence fields as critical.
- Every `critical` or `high` finding requires 2–4 complete `action_plan` steps. Missing owner, deadline, or deliverable fails publication validation.
- `medium`: may be conditional, but confidence cannot be low. Missing trigger facts must be stated.
- Low confidence, drafts, expired material, and unknown effect status are at most `watch`.
- Penalties are `enforcement_signal`, never `critical`, and never worded as a finding that the enterprise has violated a rule. A high penalty signal still requires an official source, complete text, matched profile facts, and a legal basis.
- `not_applicable` items stay traceable but do not count as active risk.

## Management presentation

- `risk_point`: use “specific object/process + concrete gap or trigger + direct outcome.” Name the exact reporting period, system route, fee type, control, or regulated activity where possible. Target no more than 60 Chinese characters.
- Do not write generic points such as “合规管理可能不完整”“需关注监管要求” or “存在风险”. When facts are unverified, say that the required control evidence or closed loop is unverified instead of asserting a violation.
- `risk_reason`: state the decisive rule, enterprise-profile match, and plausible consequence only. Target no more than 140 Chinese characters.
- `action_plan`: provide 2–4 steps. Each step must be executable and auditable: an action verb, one accountable owner, a relative or calendar deadline, and a named deliverable/evidence item.
- Use progressive control design where appropriate: immediate inventory/containment → process or system remediation → test/monitoring. Do not make “review”, “strengthen”, or “pay attention” the only action.
- Keep legal quotations and detailed applicability reasoning in the evidence fields. The HTML main card must read `风险点` → `为什么有风险` → `落地策略`.
