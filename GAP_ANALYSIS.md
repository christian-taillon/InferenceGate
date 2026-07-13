# Gap Analysis: InferenceGate vs. Production Requirements

Assessment of the current LiteLLM-proxy-based firewall against production security and reliability bars. Findings are line-backed against the current codebase.

> **Status update 2026-07-12 (verified against HEAD `784bb21`):** The original
> analysis below predates the Phase 6 hardening commits (`73bc48b`, `f9171fe`).
> Items marked **[FIXED — Phase 6]** inline have been re-verified as resolved.
> Remaining and newly discovered gaps are tracked in `TASKS.yaml` /
> `PLAN.md § Transformation Program (v2)`; the enterprise target state is
> `docs/security/OBJECTIVE.md`. Verified baseline: **78 tests passing**, ruff
> clean, litellm pinned 1.82.0 (`docs/security/reports/legacy-baseline.md`).
>
> Newly discovered gaps (2026-07-12):
> - **Hook-dispatch ambiguity** — custom shields implement
>   `async_moderation_hook`/`apply_guardrail` while config declares
>   `mode: pre_call`; actual dispatch at litellm 1.82.0 unverified (DECISIONS.md D-004).
> - **Streaming bypass** — `ResponseGuardShield` only covers non-streaming
>   responses; streamed chunks are unscanned (D-005).
> - **Residual content logging** — shield `print()` calls emit prompt/response
>   excerpts (`firewall_callbacks.py:274,440,474,711,741`); `demo.py:454`
>   pipes proxy stdout to `proxy_debug.log` (task `p0.scrub-debug-logging`).

Legend: ✅ Mature · ⚠️ Partial / At-risk · ❌ Missing

---

## 1. Shield Coverage (Input & Output)

| Requirement | Status | Gap / Recommendation |
| :--- | :--- | :--- |
| **PII / Secrets / Attack regex** | ✅ Mature | Regex + LlamaGuard cover major PII and attack patterns (`config.yaml:16-46`). |
| **Response-side filtering** | ✅ **[FIXED — Phase 6]** (non-streaming only; streamed chunks still bypass — see status update) | All guardrails are `mode: pre_call` (`config.yaml:20,55,68`). Model output passes through unscanned. **Risk:** data exfiltration via model output, toxic content, leaked secrets echoed back. **Fix:** add `during_call`/`post_call` guardrails and scan completions. |
| **Message-scope coverage** | ✅ **[FIXED — Phase 6]** (`_extract_all_content` scans full stack incl. system/developer/multimodal) | `_extract_latest_user_content` only inspects the latest `user` text message (`firewall_callbacks.py:39-53`). **Bypass vectors:** (a) injection via `system`/`developer` messages, (b) multimodal non-text content (images/audio), (c) prior turns in history. **Fix:** scan full message stack incl. system/developer and non-text parts. |
| **Encrypted / encoded PII** | ⚠️ Partial | Base64/hex PII only caught probabilistically by LlamaGuard. **Fix:** deterministic decode-and-scan middleware (base64, hex, URL-encoding, unicode escapes). |
| **Shield fail-mode** | ⚠️ **[Partially fixed — Phase 6]** (`INFERENCE_GATE_FAIL_MODE` toggle exists; still global, import-time, no failure metric) | Shields fail **open** on any unexpected exception (`firewall_callbacks.py:349-352, 471-474`) with no metric, alert, or config toggle. **Fix:** make fail-open/closed configurable per guardrail and emit a counter on failure. |

## 2. Secrets & Configuration Hygiene

| Requirement | Status | Gap / Recommendation |
| :--- | :--- | :--- |
| **Secret-scanning in CI** | ✅ **[FIXED — Phase 6]** (gitleaks-action@v2 in workflow) | No gitleaks/trufflehog step in `.github/workflows/test.yml:1-36`. `.gitignore:5` blocks `*.env` (verified — no real keys tracked, `.env.example` holds placeholders only). **Fix:** add a secret-scanning CI step as a guardrail to prevent future leaks. |
| **Default master key** | ✅ **[FIXED — Phase 6]** (`serve.py:70-78` refuses unset/default key) | `LITELLM_MASTER_KEY` defaults to the literal `sk-inference-gate-v1` (`serve.py:62-68`, `demo.py:445-453`, `.env.example:20`). Any deployment that forgets the env var ships with a known key. **Fix:** refuse to start without an explicit, high-entropy key. |
| **Key logged at startup** | ✅ **[FIXED — Phase 6]** (masked as `************`) | `serve.py:64-85` prints the master key and startup errors to stdout. **Fix:** redact secrets from logs; never log credentials. |
| **Per-tenant keys / rotation** | ❌ Missing | Single shared master key for all clients (`serve.py:62-74`). No virtual keys, no rotation, no revocation. **Fix:** LiteLLM virtual keys + Postgres, or integrate Vault/OIDC. |
| **Verbose debug logging** | ⚠️ **[Partially fixed]** (`--detailed_debug` removed; shield print() excerpts and proxy_debug.log pipe remain — task p0.scrub-debug-logging) | Demo runs `litellm --detailed_debug` and pipes stdout/stderr to `proxy_debug.log` (`demo.py:444-466`). Full prompts/responses likely captured to disk. **Fix:** gate debug mode behind an explicit flag and scrub PII from debug logs. |

## 3. Transport & Network

| Requirement | Status | Gap / Recommendation |
| :--- | :--- | :--- |
| **TLS termination** | ⚠️ **[Documented 2026-07-12]** (`docs/security/OPERATIONS.md`: ingress termination required; native `--ssl_certfile_path` flags verified; enforcement/runbooks in P12) | Proxy listens plain HTTP on `:8001` (`serve.py:55,77-80`). No TLS in app or config. **Fix:** terminate TLS at proxy or a fronting ingress; reject plaintext. |
| **CORS / origin policy** | ❌ **[Verified worse than assumed]** litellm 1.82.0 hardcodes `origins=["*"]` + `allow_credentials=True` (`proxy_server.py:1076`) with no config knob — must be enforced at ingress (`docs/security/OPERATIONS.md`) | No CORS configuration found in code or config. **Fix:** explicit allow-list of origins; deny by default. |
| **Health/readiness exposure** | ⚠️ Partial | `/health/readiness` used in docs (`DOCKER_DEPLOYMENT.md:68-74`); no liveness/readiness split or auth on health endpoints. **Fix:** unauthenticated `/healthz` (liveness) vs. authenticated `/readyz` (readiness). |
| **High availability** | ❌ Missing | Single process, single point of failure. **Fix:** K8s Deployment + LB, stateless replicas, external Redis/Postgres. |

## 4. Error Handling & Information Disclosure

| Requirement | Status | Gap / Recommendation |
| :--- | :--- | :--- |
| **Error detail to client** | ✅ **[FIXED — Phase 6]** (generic `BLOCKED_MESSAGE`; detail server-side only) | Blocked requests raise `BadRequestError` with shield labels/categories (`firewall_callbacks.py:341-348, 466-470`), parsed into user-facing phase/reason in `demo.py:235-294`. **Risk:** tells attackers which shield tripped and why, enabling evasion tuning. **Fix:** return generic `request rejected` to client; keep detail in server logs only. |
| **Stack-trace leakage** | ⚠️ Unknown | No global exception handler seen; default LiteLLM behavior may surface tracebacks. **Fix:** explicit `except Exception` handler returning generic 5xx. |
| **Upstream failure mode** | ⚠️ Partial | No explicit handling for upstream LLM downtime/timeout. **Fix:** circuit breaker, timeout budget, fallback model, and fail-closed option for high-sensitivity tenants. |

## 5. Rate Limiting & Abuse

| Requirement | Status | Gap / Recommendation |
| :--- | :--- | :--- |
| **Static rate limits** | ⚠️ Basic | Only static limits documented. **Fix:** LiteLLM Redis `tpm_limit`/`rpm_limit` per virtual key for multi-tenant isolation. |
| **Prompt-injection storm alerting** | ❌ Missing | No burst detection or alert when block-rate spikes (e.g., coordinated injection attempt). **Fix:** Prometheus counter on blocks + alert on rate threshold. |
| **Cost / token-blowout protection** | ❌ Missing | No per-request max_tokens cap or per-tenant spend ceiling. **Fix:** enforce `max_tokens` upper bound and budget guards. |

## 6. Observability

| Requirement | Status | Gap / Recommendation |
| :--- | :--- | :--- |
| **Structured logging** | ⚠️ Partial | Shields use `print(...)` not structured logging (`firewall_callbacks.py:235,307-352,411-474`). **Fix:** stdlib `logging` with JSON formatter, correlation IDs, redaction. |
| **Metrics & tracing** | ❌ Missing | No Prometheus metrics, no OpenTelemetry traces. **Fix:** emit counters (blocks by category, shield latency, failures, p50/p95 latency). |
| **Audit log of prompts/responses** | ⚠️ Partial | Debug file logging exists but no durable, queryable audit trail with retention/redaction. **Fix:** append-only audit store (Postgres/SIEM) with PII redaction and retention policy. |
| **Security dashboard** | ❌ Missing | No UI for security teams to review blocked prompts. **Fix:** Grafana dashboard or LiteLLM Enterprise UI. |
| **Alerting** | ❌ Missing | No Slack/Email/webhook on shield triggers or anomalies. **Fix:** LiteLLM success/failure callbacks + Alertmanager. |

## 7. Latency

| Requirement | Status | Gap / Recommendation |
| :--- | :--- | :--- |
| **Shield execution model** | ⚠️ Sub-optimal | Sequential `pre_call` adds ~200–400ms. **Fix:** run deterministic regex in-process and probabilistic shields in parallel `during_call`; cache LlamaGuard verdicts by prompt hash. |

## 8. Testing & CI

| Requirement | Status | Gap / Recommendation |
| :--- | :--- | :--- |
| **Unit tests for shields** | ✅ Functional | Regex, taxonomy, parsing covered (`tests/test_firewall.py:84-406`). |
| **Integration through proxy** | ✅ **[FIXED 2026-07-12]** (`tests/test_integration_proxy.py`: live proxy + stub upstream; block/pass/ordering/output-scan asserted; runs in CI) | No end-to-end test that a malicious prompt through the running proxy is actually blocked. **Fix:** integration test spinning the proxy and asserting block behavior. |
| **Bypass tests** | ❌ Missing | No tests asserting system/developer messages, multimodal content, and response-side output are (or are not) scanned. **Fix:** explicit tests pinning the intended scope. |
| **Secret-leak tests** | ✅ **[FIXED 2026-07-12]** (`tests/test_log_leaks.py`: canary assertions on fail-open, block paths, taxonomy filtering) | No test asserting secrets are absent from logs/errors. **Fix:** add assertions that fail-open path does not echo payloads. |
| **Secret scanning in CI** | ❌ Missing | `.github/workflows/test.yml:1-36` runs pytest+ruff only. **Fix:** add gitleaks/trufflehog step. |

## 9. Supply Chain

| Requirement | Status | Gap / Recommendation |
| :--- | :--- | :--- |
| **Runtime pinning** | ⚠️ Mixed | `requirements.txt` pins with hashes (lines 439-1990), but `pyproject.toml:7-15` uses ranges and `serve.py` runs `.venv/bin/litellm` directly — drift risk between dev and prod. **Fix:** single source of truth for pinned versions used by the running service. |
| **Unsafe loader audit** | ✅ OK | YAML uses `safe_load` (`demo.py:172-184`, `tests/test_firewall.py:84-87`, `scripts/run-demo-stack.sh:163-171`). No `eval`/`pickle`/`subprocess`-with-input patterns in app code (one `subprocess.Popen` for the proxy itself in `serve.py:67-77`). |

---

## Reference Architecture (Proposed)

1. **Gateway:** LiteLLM Proxy (stateless), 2+ replicas behind LB.
2. **Auth:** Virtual keys backed by Postgres; OIDC for admin; Vault for provider keys.
3. **Cache/Limits:** Redis for rate limits and LlamaGuard verdict cache.
4. **Audit:** Postgres/SIEM with redaction and retention.
5. **Transport:** TLS at ingress; unauthenticated `/healthz`, authenticated `/readyz`.
6. **Shields (layered, parallel):**
   - **L1 Deterministic (pre_call):** regex for secrets/PII/SQLi/prompt-injection.
   - **L2 Probabilistic (during_call):** LlamaGuard 3 + Prompt Guard, parallel + cached.
   - **L3 Response (post_call):** scan completions for exfil/toxic/secret echo.
7. **Observability:** structured JSON logs (redacted) → SIEM; Prometheus metrics; Grafana dashboard; Alertmanager webhooks.

---

**Top-priority remediations (ship blockers):**
1. Remove plaintext secrets from repo and rotate keys.
2. Make master key mandatory (no insecure default).
3. Add response-side scanning (post_call).
4. Expand shield scope to full message stack incl. system/developer and non-text.
5. Redact secrets from logs and client-facing errors.
6. Add TLS termination.

**Secondary (hardening):**
Configurable fail-mode + failure counters, integration tests, secret-scanning CI, structured logging, metrics/tracing, per-tenant rate limits and budgets, generic error messages to clients.