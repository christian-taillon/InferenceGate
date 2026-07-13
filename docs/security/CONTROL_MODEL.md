# Control Model — P1 Contracts

**Normative source of truth: `inference_gate/contracts.py`** (typed, tested
in `tests/test_contracts.py`). This doc records the decisions the code
encodes and what deliberately isn't in code yet. Prose rationale:
`OBJECTIVE.md`. The original brief's separate STAGES / FINDING_SCHEMA /
DECISION_SCHEMA / ACTION_MODEL / FAILURE_POLICY documents are consolidated
here + in code to avoid drift (per the minimal-code directive); split them
out only if they grow past this file.

## What the code defines

| Contract | Type | Key decisions |
|---|---|---|
| `Stage` | enum, 14 stages | Internal trust boundaries; LiteLLM hooks are adapters onto stages, never the model itself |
| `ControlType` | enum, 10 types | normalizer…sink per OBJECTIVE |
| `Mode` | enum + `parse()` | Canonical rollout modes; guard-spec aliases `shadow`→observe, `review`→alert accepted; **`test` and `enforce` rejected** (offline-only / ambiguous — D-009) |
| `Action` | enum + `resolve()` | Default precedence deny > require_approval > quarantine > drop_field > dehydrate > redact > route_to_alternate > alert > tag > allow; only explicit policy may override |
| `Severity` | enum | critical…info |
| `FailureAction` + `FAILURE_DEFAULTS` | enum + map | detectors/classifiers/reviewers fail `allow_and_alert`; transformers/enforcers fail `deny`; DENY floor for transformer-class failures is a platform invariant |
| `TenantContext` | frozen dataclass + `from_user_api_key_auth()` | Resolved from authenticated LiteLLM identity only (team_id→tenant, org_id, hashed api_key→virtual_key_id, key_alias→application, end_user_id→subject — shapes verified in LITELLM_CAPABILITY_MATRIX.md); **missing tenant raises → fail closed**; never populated from request content |
| `Finding` | frozen dataclass | Facts only, no enforcement semantics; no plaintext — `redacted_excerpt` pre-sanitized, `fingerprint` keyed-HMAC only; span + source_path for dehydration targeting |
| `Decision` | frozen dataclass | `recommended_action` vs `executed_action` always both recorded; `.simulated` derived — makes observe/simulate rollouts auditable (D-006); references `policy_id` + `configuration_id` |

## Deliberately not yet in code (arrives with its consuming phase)

- **Policy model & precedence resolver** — P5 decision engine (the 13-level
  precedence in OBJECTIVE.md is the spec).
- **Effective-configuration record & atomic reload** — P5/P7.
- **Assessment-event envelope** (trace/session ids, detector_version,
  content_hash, redacted_evidence, fail/bypass records — merged research) —
  P1 task notes hold the field list; lands with the audit sink.
- **Manifest / placeholder contracts** — P8 (crypto review first, D-007).
- **Session risk state** — P10 correlator.

## Review gate

P1's phase gate is strict architecture review. Status: contracts implemented
and tested; flagged `review` in TASKS.yaml. P2 normalization may proceed
against these types — they are code and cheap to adjust under review
feedback, but any change to Action precedence, Mode semantics, or
TenantContext fail-closed behavior requires a DECISIONS.md entry.
