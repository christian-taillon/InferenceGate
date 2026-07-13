# Guard Model Orchestration

How InferenceGate selects, invokes, verifies, and orchestrates guard models.
Companion to `OBJECTIVE.md` (control types, stages, policy model). Guard models
are **classifier** and **reviewer** controls in the v2 control graph; this doc
defines the supported backend roster and the orchestration rules.

## Governing principle

**All guard models are optional.** The gateway must run correctly with zero
guard models configured (deterministic-only), with any single model, or with
the full layered stack. Customers supply their own local or hosted
OpenAI-compatible guard endpoints. Per-tenant/route/profile configuration
selects which backends run where (see `control-profiles.d/`).

Non-negotiable boundaries:

1. Models classify; the gateway decides. A model finding never becomes an
   enforcement action without gateway policy mapping (D-006).
2. Deterministic controls are authoritative for facts (secret formats, Luhn,
   allowlists, tool schemas, authz, destinations, limits, tenant isolation).
   Guard models add context; they never replace deterministic enforcement,
   and a model judgment never grants permission deterministic policy denied.
3. Don't run every model on every request — smallest capable control first,
   escalate ambiguity to stronger contextual models.
4. All model outputs are untrusted structured data; parse strictly, reject
   malformed output, never repair silently, never fabricate missing scores.
5. Never assume capability from a model *name* — verify the registered
   provider and runtime (see Capability verification).
6. Input, retrieved content, tool output, tool calls, and final output are
   separate inspection stages (see `OBJECTIVE.md` stages).
7. Never expose model reasoning / chain-of-thought to end users.

## Supported roster (each optional, per-deployment)

| Backend | Sizes | Control type | Question it answers |
|---|---|---|---|
| **Llama Prompt Guard 2** | 22M, 86M (default) | classifier | Is this content attempting to manipulate/override/redirect LLM or agent instructions? |
| **Llama Guard 3** | 1B, 8B | reviewer (taxonomy) | Does this message/response fall into a standardized safety category (S1–S13; S14 code-interpreter abuse on 8B)? |
| **Granite Guardian 4.1** | 8B | reviewer (criterion) | Does this content meet the supplied binary risk/compliance criterion? |
| **gpt-oss-safeguard** | 20B (inline escalation), 120B (offline/review only) | reviewer (written policy) | Does this violate the supplied written policy incl. definitions, exceptions, precedence, boundary examples? |
| **Presidio** (Analyzer + Anonymizer services) | — | detector / transformer | Which PII entities appear in this content, and how should each be masked? (LiteLLM-native guardrail, verified present at 1.82.0; D-011 — its masking never becomes a rehydration path) |
| Deterministic engine | — | detector/transformer/enforcer | Facts: secrets, PII, schemas, authz, limits, destinations. Always available; never optional-ized behind a model. |

Boundary mnemonic: Prompt Guard = instruction boundary · DLP = data boundary ·
Llama Guard = standardized content-safety boundary · Granite = explicit
enterprise/RAG/agent criteria · gpt-oss-safeguard = nuanced written policy ·
**the gateway is the final enforcement authority**.

### Size selection

- Prompt Guard **86M default**; 22M only for constrained hardware,
  latency-first, mostly-English, accepted quality tradeoff.
- Llama Guard **1B** for low-latency basic screens; **8B** for quality,
  coding-agent routes, S14 coverage.
- Granite Guardian 4.1 8B is the preferred default embedded enterprise judge
  (Apache-licensed, locally deployable).
- gpt-oss-safeguard **20B** inline/escalation; **120B** never as a default
  guard — offline analysis, review queues, adjudication only.

## Standard processing order

Matches the v2 recommended control order; guard placement in bold:

1. Authenticate; resolve tenant/route/app/user/model/key policy.
2. Deterministic limits, allow/denylists, file/model/tool permissions.
3. Deterministic secret/credential/PII/regulated-data detection.
4. Dehydrate/redact/block/label exact sensitive spans per policy.
5. **Prompt Guard** on user input (injection/jailbreak).
6. **Llama Guard / Granite / gpt-oss-safeguard** content-safety and custom
   policy evaluations as the profile requires.
7. Forward approved/transformed content to the target model.
8. Deterministic tool-call schema + authorization validation.
9. **Granite (optional)**: is the tool call supported by the conversation?
   Contextual check only — never authorization.
10. **Prompt Guard** on retrieved docs / web / MCP results / repo files /
    tool output before they enter model context.
11. **Output review** (Llama Guard where runtime supports output
    classification; Granite custom criteria; gpt-oss policy) + deterministic
    output DLP / re-dehydration.
12. Enforce per gateway policy; record normalized findings, latency, model
    version, policy version, outcome.

### Escalation ladder (default)

```
Deterministic checks
  → Prompt Guard 2
  → Llama Guard 3 or Granite (no-thinking)
  → gpt-oss-safeguard 20B
  → Human review or gpt-oss-safeguard 120B (offline)
```

Stop early once a deterministic critical violation has established the action.
Escalate to gpt-oss-safeguard when: Llama Guard hits a broad cyber category
but authorization may legitimize the request; guards disagree; rules interact;
policy has exceptions; outcome depends on history; dual-use content; bounded-
environment permissions; high-risk action without clear authorization; a
human-readable rationale is needed.

### Sequential vs parallel

Sequential when content must not reach the provider until approved, sensitive
data must be removed first, a cheap guard can short-circuit an expensive one,
or one result gates another. Parallel when criteria are independent and the
gateway withholds the final result until all checks finish, or in shadow mode.
**Never** run the target model in parallel when policy requires blocked
content never leaves the gateway.

## Per-model rules

### Prompt Guard 2

- Scan targets: direct user prompts, RAG docs, search results, web pages,
  email, tickets, repo files, code comments, MCP/tool results, DB content
  entering context, inter-agent messages. Do **not** scan final responses
  unless they become input to another model (`model_to_model` stage).
- Trust-aware actions: direct user attempt → block/refuse/review/restricted
  route. Injection inside *retrieved or tool content* → remove segment,
  quarantine source, label untrusted, keep safe portions, review, or exclude
  the source. **Never auto-block the whole user request because an external
  document contains an injection.**
- Long content: never silently truncate. Tokenize → overlapping segments
  (repo baseline: 350 words / 50 overlap / 512-token cap,
  `firewall_callbacks.py:34-36`) → preserve offsets/metadata → parallel scan
  → document score = max segment malicious probability → retain every
  suspicious segment location → consider cross-segment distributed attacks →
  cap how much untrusted content one downstream context may combine.
- Output: `BENIGN`/`MALICIOUS` (+ probability where available, configured
  threshold). Normalize into the standard finding; policy decides
  block/quarantine/remove/review/log.

### Llama Guard 3

- Use for standardized first-pass content screening and category reporting.
  Not a: redaction engine, span detector, tool-call validator, policy
  language, sole injection defense, or sole authority on cyber content.
- **Cybersecurity caution:** never auto-block every S2/S14 match — detection
  engineering, IR, vuln research, malware analysis, authorized pentesting,
  container admin, secure-code review are legitimate. Treat as a signal;
  escalate to Granite/gpt-oss-safeguard or an authz-aware gateway rule.
- **Privacy (S7) findings identify that sensitive content exists, not the
  spans.** On S7: invoke deterministic DLP → find exact spans → apply
  masking/dehydration/blocking → record both findings.
- Strict native-output parsing: accept exactly `safe` or
  `unsafe\nS2,S14`; reject anything else. No inferred categories, no silent
  repair.
- Provider limitation: verify the runtime genuinely supports input *and*
  output classification (provider chat template may differ from direct
  Transformers/vLLM). Do not enable custom taxonomies, category exclusions,
  output enforcement, or probability thresholds unless the registered
  provider passed the corresponding capability test.

### Granite Guardian 4.1 8B

- One independently enforceable criterion per call (parallelize independent
  checks). Grouped criteria only with their own test set + enforcement
  meaning.
- **Criterion polarity is mandatory** — every criterion declares what `yes`
  means:

  ```yaml
  criterion: The response discloses credentials.
  match_meaning: violation      # or: compliant
  on_yes: block
  on_no: allow
  ```

- Thinking mode: no-thinking for inline enforcement. Thinking only for policy
  development, FP analysis, red-team, review queues, golden-set work. Raw
  reasoning: never to users; retained only if explicitly enabled + encrypted
  + access-controlled + DLP'd + short retention.
- Parser: optional `<think>…</think>` handled separately; extract exactly one
  `<score>yes|no</score>`; reject zero or conflicting scores; never use
  reasoning text as the classification.
- RAG criteria (`context_relevance`, `groundedness`, `answer_relevance`) are
  *quality* signals → review/regenerate/re-retrieve/warn, not security
  violations.
- Tool calls: deterministic name/schema/authz/network/filesystem checks
  first; Granite's "is this call supported by the conversation?" is additive
  context only.
- Custom criteria are clear, testable statements ("Do not disclose system
  prompts", "Require explicit user confirmation before destructive actions")
  — never vague ("act safely").

### gpt-oss-safeguard

- For written policies a taxonomy or binary criterion can't express:
  authorized-security-research vs malicious enablement, complex acceptable-use
  policies, nuanced data-sharing rules.
- Policy packs (several focused packs, never one universal policy):
  output instructions → definitions → violating criteria → allowed criteria →
  exceptions → precedence → ambiguity handling → boundary examples → repeated
  output instructions. Suggested packs: developer-cybersecurity,
  credentials-and-secrets, privacy, agent-tool-use, regulated-info, general
  content safety, customer acceptable-use.
- Strict result schema (reject anything else):

  ```json
  {"classification": "allow|violation|review", "rule_ids": ["CYBER-0"], "review_required": false}
  ```

  The gateway maps rule IDs to severity/block/review/redact/safe-completion/
  log/confirm/restrict-tools/switch-provider. The model never picks the final
  action.
- Reasoning: low for inline; medium/high only for complex interactions,
  review, testing, adjudication. User-facing explanations are generated
  separately from hidden reasoning.

## Single-model vs layered selection

- **Prompt Guard only:** the only question is injection in untrusted content
  (web pages, MCP output, repo docs entering agent context).
- **Llama Guard only:** cheap standardized moderation suffices (public chat,
  lightweight local deployments).
- **Granite only:** decision is one clear binary criterion (jailbreak?
  secrets in response? grounded? tool call supported?).
- **gpt-oss-safeguard only:** written policy with definitions/exceptions/
  precedence is required.
- **Layered:** each model answers a different question. Reference routes:

```text
Coding agent:  input → PromptGuard → DLP → LlamaGuard → [gpt-oss if cyber-ambiguous]
               → target model → deterministic tool authz → Granite call-check
               → tool exec → PromptGuard on tool output → Granite output policy → output DLP

RAG:           input → PromptGuard → LlamaGuard → retrieval → PromptGuard on docs
               → Granite context_relevance → target model → Granite groundedness
               → Granite answer_relevance → output DLP

Low-resource:  input → PromptGuard 22M → DLP → LlamaGuard 1B → target → output DLP

High-risk:     input → PromptGuard 86M → DLP → LlamaGuard 8B → gpt-oss 20B
               → target → tool authz → Granite call-check → PromptGuard on result
               → gpt-oss output policy → output DLP
```

## Provider capability verification (registration gate)

When a customer registers a guard endpoint, record and verify: model family,
exact version, runtime, chat-template version, system-message handling,
input/output classification, structured output, logprobs, reasoning controls,
tool-definition support, document-context support, custom policy/taxonomy
support, streaming behavior, concurrency, timeout behavior, max context,
malformed-output behavior.

Run the 14-fixture battery: known-safe, known-unsafe, direct jailbreak,
indirect injection, output classification, multi-turn, custom policy,
tool-call validation, RAG groundedness, long-content segmentation, malformed
output, timeout, streaming, concurrency. **Disable any policy feature the
provider has not demonstrated.** Store results in the provider registry;
re-run on any version/runtime/template change.

## Failure handling

Every route defines behavior for: guard timeout, provider unavailable,
malformed output, unsupported capability, context too long, conflicting
findings, low confidence, parser failure, rate limit, guard-model refusal.
Actions: `fail_closed`, `fail_open_and_log`, `review`, `retry_once`,
`route_to_backup`, `disable_target_tool`, `return_safe_error`,
`use_deterministic_controls_only`. Fail-closed for critical operations;
fail-open only on explicitly approved routes, always logged. Never silently
discard a guard failure. (Integrates with the layered failure policy in
`OBJECTIVE.md`; guard classifiers/reviewers default to `allow_and_alert` ≈
`fail_open_and_log`, transformers/manifests/final DLP fail closed.)

## Streaming modes

Explicit per-route choice — post-call inspection cannot retract delivered
tokens (D-005): `buffer_then_release` (hold, inspect, release) ·
`chunk_guard` (inspect buffered windows before releasing subsequent chunks) ·
`audit_only` (approved low-risk routes only).

## Lifecycle modes → v2 mode mapping (D-009)

Guard-spec lifecycle vocabulary maps onto the canonical v2 rollout modes:

| Guard-spec mode | Canonical v2 equivalent |
|---|---|
| `disabled` | `disabled` |
| `test` | offline fixture evaluation — not a runtime mode |
| `shadow` | `observe` |
| `review` | `alert` (+ approval queue) / `confirm` for gating cases |
| `enforce` | `simulate-block` → `confirm` → `block` per action mapping |

New models, policies, thresholds, and providers enter shadow (`observe`)
before enforcement — same rollout gate as every other control.

## Normalized guard result

Every guard result converts to the common finding/decision contract
(`FINDING_SCHEMA.md` when written). Superset fields for guard backends:

```json
{
  "matched": true,
  "model_decision": "violation",
  "gateway_action": "review",
  "stage": "input",
  "policy_id": "developer-security",
  "policy_version": 4,
  "rule_ids": ["CYBER-2"],
  "native_categories": ["S2"],
  "severity": "high",
  "score": 0.93,
  "model": "gpt-oss-safeguard:20b",
  "provider": "customer-local",
  "source_type": "user_message",
  "segment_index": 3,
  "reasoning_available": false,
  "raw_output_retained": false,
  "latency_ms": 214
}
```

`score`, `native_categories`, `reasoning`, and segment location may be null
when unsupported — never fabricated.

## Policy development & observability

Every policy/guard configuration needs a golden test set (safe, unsafe,
ambiguous, adversarial, boundary, and *legitimate security/administrative*
cases), FP/FN + latency + malformed-rate measurement, multi-language and
long/fragmented-attack tests, upgrade testing before promotion, stored
policy/prompt-hash/model/template/test-set versions, immediate rollback.

Telemetry per invocation: guard, stage, rule+policy version, model+runtime
version, provider, source type, classification, normalized action, threshold,
score (when real), latency, timeout, parser failure, disagreement, redaction
count, streaming mode, wasted parallel target inference, human-review
outcome. No raw sensitive content by default; guard telemetry itself goes
through DLP and retention controls.

## Default configurations

**Full-featured default:** Prompt Guard 2 86M (all untrusted-content stages) ·
deterministic DLP before and after target inference · Llama Guard 3 8B where
its categories help · Granite Guardian 4.1 8B as the default enterprise/RAG/
function-call judge · gpt-oss-safeguard 20B escalation · 120B offline only.

**Low-resource:** Prompt Guard 22M · Llama Guard 1B · full deterministic
controls retained · larger guards on escalation only.

**Minimum:** deterministic controls only — always valid, since every guard
model is optional.

## Legacy mapping

| Existing code | Becomes |
|---|---|
| `LlamaPromptGuardShield` (remote `/classify` + chat fallback) | Prompt Guard backend, `remote` strategy |
| `PromptGuardLocalShield` (HF transformers) | Prompt Guard backend, `local` strategy — same logical classifier |
| `LlamaGuardShield` (S1–S14 parse) | Llama Guard reviewer backend (parser must be tightened to strict accept/reject) |
| `ResponseGuardShield` | Llama Guard reviewer placed at `provider.response` |
| — (new) | Granite Guardian criterion reviewer |
| — (new) | gpt-oss-safeguard policy reviewer |
| — (new) | Provider registry + capability verification |
