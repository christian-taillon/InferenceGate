# InferenceGate

An LLM firewall for [LiteLLM Proxy](https://docs.litellm.ai/docs/simple_proxy). InferenceGate inspects every request and response crossing your AI gateway and blocks prompt injection, jailbreaks, PII/secret leakage, and unsafe content — deterministic filters first, then specialized guard models (Llama Prompt Guard 2, Llama Guard 3), with response-side scanning on the way out. Blocked requests get a generic error; detection detail stays in server logs; every shield's behavior is configurable per-instance from `config.yaml` or the LiteLLM management UI.

Use it either way:

- **Bring your own LiteLLM** — pip-install the shields into the proxy you already run. Five lines of config per shield.
- **Reference deployment** — clone this repo for a complete, hardened gateway: pinned LiteLLM, secure-by-default settings, management UI, demo battery, and CI.

## Quick start — add to your existing LiteLLM proxy

```bash
pip install git+https://github.com/christian-taillon/InferenceGate.git
```

LiteLLM loads custom guardrail classes from `.py` files **relative to the config directory** (verified at 1.82.0 — there is no installed-package fallback), so create a one-line adapter next to your `config.yaml`:

```python
# firewall_callbacks.py — lets LiteLLM find the installed package
from inference_gate.shields import *  # noqa: F401,F403
```

Attach shields in `config.yaml` and restart the proxy:

```yaml
guardrails:
  - guardrail_name: llama-guard
    litellm_params:
      guardrail: firewall_callbacks.LlamaGuardShield
      mode: pre_call
      default_on: true
      model: openai/llama-guard3:1b
      api_base: os.environ/GUARD_API_BASE
      api_key: os.environ/GUARD_API_KEY
      blocked_categories: [S1, S4, S9]   # omit to block every unsafe category
      fail_mode: closed

  - guardrail_name: response-guard
    litellm_params:
      guardrail: firewall_callbacks.ResponseGuardShield
      mode: post_call
      default_on: true
```

Available shield classes:

| Class | Mode | What it does |
|-------|------|--------------|
| `LlamaPromptGuardShield` | `pre_call` | Jailbreak / prompt-injection classifier — vLLM-style `/classify` endpoint or Groq chat completions |
| `PromptGuardLocalShield` | `pre_call` | Same classifier on-device via HuggingFace transformers — no network dependency |
| `LlamaGuardShield` | `pre_call` | Llama Guard 3 content safety (S1–S14) over the full message stack |
| `ResponseGuardShield` | `post_call` | Llama Guard over model output, including proposed tool calls |

For the on-device classifier, install the extra: `pip install "inference-gate[local-prompt-guard] @ git+https://github.com/christian-taillon/InferenceGate.git"`.

Pair them with LiteLLM's native `litellm_content_filter` for zero-latency regex/PII/secret blocking — this repo's [`config.yaml`](config.yaml) is a working five-shield pipeline you can copy.

**Version compatibility:** tested against `litellm==1.97.0` (the version this repo pins). The package declares `litellm>=1.82.0`; guardrail hook dispatch is litellm-internal behavior, so after changing LiteLLM versions run the credential-free compatibility suite from this repo: `uv run pytest tests/ -m integration`.

## Quick start — run the full gateway

```bash
git clone https://github.com/christian-taillon/InferenceGate.git && cd InferenceGate
cp .env.example .env   # set LITELLM_MASTER_KEY, LITELLM_API_BASE, LITELLM_API_KEY, MODEL
uv sync                # installs the package plus dev + deployment dependency groups
uv run serve.py        # proxy on :8001 with all five shields active
```

`serve.py` refuses to start with an unset or default `LITELLM_MASTER_KEY`. Point any OpenAI-compatible client (Open WebUI, IDE assistants, SDKs) at:

| Field | Value |
|-------|-------|
| Base URL | `http://<host>:8001/v1` |
| API key | your `LITELLM_MASTER_KEY` |
| Model | `firewall-model` |

## Architecture

```text
[ User / App ]
      |
      v
[ InferenceGate Proxy ] <--- [ config.yaml ]
      |
      +-- Shield 1: Built-in Filters (Regex/PII/Secrets)     pre_call
      +-- Shield 2: Llama Prompt Guard 2 (remote classify)   pre_call
      +-- Shield 2b: Prompt Guard Local (HF transformers)    pre_call
      +-- Shield 3: Llama Guard 3 content safety (S1-S14)    pre_call
      +-- Shield 4: Response Guard (post-call output scan)   post_call
      |
      v
[ Backend AI Model ] (e.g., Qwen, GPT-4, etc.)
```

The firewalling logic lives in the pip package (`inference_gate.shields`); the repo-root `firewall_callbacks.py` is a compatibility shim so config-file references resolve to the packaged classes. Everything else in this repo — `serve.py`, `config.yaml`, the Postgres-backed UI, the demo — is the reference deployment.

## Shields in detail

### Shield 1: Built-in Content Filters (Regex & Prebuilt Detection)
Zero-latency, on-device guardrails via LiteLLM's native content filter:
- **PII and Secret Blocking**: emails, SSNs, IBANs, credit cards, API keys, JWTs, and similar sensitive values.
- **Prompt Injection Protection**: common jailbreak and instruction-override phrasings.
- **Attack Pattern Detection**: SQL injection payloads blocked before they reach the upstream model.

### Shield 2: Prompt Attack Assessment (Llama Prompt Guard 2, remote)
Focused detection for prompt manipulation, served via a vLLM-style `/classify` endpoint or Groq chat completions:
- **Jailbreak / Injection Classification** with a configurable `threshold` (default 0.5) and endpoint `timeout`.
- Long inputs are chunked (350 words, 50-word overlap) so attacks can't hide past a truncation boundary.

### Shield 2b: Prompt Guard Local (on-device)
The same classifier run locally via HuggingFace `transformers` — no API calls, no network dependency:
- Set `preload: true` to load the model at startup rather than on the first request.
- Repo install: `uv sync --extra local-prompt-guard`; pip install: the `local-prompt-guard` extra.

### Shield 3: Llama Guard 3 Content Assessment
Intent analysis using a specialized safety model:
- **Taxonomy-based Blocking** across the full Llama Guard 3 taxonomy (S1–S14): violent crimes, CSE, weapons, privacy, self-harm, and more.
- **Category scoping**: `blocked_categories: [S1, S4, "Privacy"]` (S-codes or taxonomy names) blocks only those categories. An unsafe verdict without a recognizable category always blocks — deny by default.
- **Strict output parsing**: guard output must be exactly `safe` or `unsafe` + S-codes. A degraded guard model answering prose is a fail-policy event, never a silent allow.

### Shield 4: Response Content Filtering
Security doesn't stop at the request:
- **Output Scanning**: completions — including reasoning content and proposed tool calls — are scanned for data exfiltration, toxic content, and secret echo before they reach the client.
- Supports both the classic post-call hook and LiteLLM's unified `apply_guardrail` response path.
- Non-streaming responses only (see [DECISIONS.md](DECISIONS.md) D-005); disable streaming for sensitive profiles.

## Configuration reference

Every knob is a `litellm_params` key with an environment-variable fallback, so shields work with zero config beyond the class reference:

| Key | Shields | Default | Env fallback | Purpose |
|-----|---------|---------|--------------|---------|
| `api_base` | 2, 2b, 3, 4 | — | `<SHIELD>_API_BASE`, `LITELLM_API_BASE` | Guard model endpoint |
| `api_key` | 2, 2b, 3, 4 | — | `<SHIELD>_API_KEY`, `LITELLM_API_KEY` | Guard model auth (accepts `os.environ/VAR`) |
| `model` | 2, 2b, 3, 4 | per shield | `LLAMA_PROMPT_GUARD_MODEL` / `PROMPT_GUARD_LOCAL_MODEL` / `LLAMA_GUARD_MODEL` | Guard model identifier |
| `fail_mode` | all | `open` | `INFERENCE_GATE_FAIL_MODE` | `open` (log + allow) or `closed` (deny) on shield malfunction |
| `threshold` | 2, 2b | `0.5` | `LLAMA_PROMPT_GUARD_THRESHOLD` / `PROMPT_GUARD_LOCAL_THRESHOLD` | Malicious-score cutoff |
| `blocked_categories` | 3, 4 | all | — | S-codes or taxonomy names that block |
| `timeout` | 2 | `30` | — | Classify-endpoint timeout (seconds) |
| `preload` | 2b | `false` | — | Load model at startup |

Invalid config (bad `fail_mode`, out-of-range `threshold`, unknown category) fails at proxy startup instead of at request time. The full surface is documented inline in [`config.yaml`](config.yaml) and the `inference_gate/shields.py` module docstring.

### Security behavior

- **Generic block errors**: clients receive HTTP 400 with `Request blocked by content safety shield.` — no shield names, labels, scores, or taxonomy codes. Detection detail (categories, scores, latency) goes to server logs only, and logs never contain message or response content.
- **Proper guardrail telemetry**: blocks raise the exception form LiteLLM records as a guardrail *intervention* in `StandardLoggingGuardrailInformation` and per-guardrail Prometheus metrics — not as a guardrail failure.
- **Fail policy**: a shield malfunction (guard endpoint down, malformed guard output, missing config) is routed through `fail_mode` — never silently ignored.

## Management UI

With PostgreSQL configured (`DATABASE_URL` in `.env`), the LiteLLM management UI at `http://<host>:8001/ui/` gives you:

- **Guardrails page**: all configured shields listed with their modes.
- **Add Guardrail**: the four InferenceGate shields register as first-class providers ("InferenceGate: …") with typed config forms — thresholds, fail mode, and a Llama Guard category multiselect (S1–S14) — so additional shield instances can be created and managed from the UI.

Division of authority: `config.yaml` is the source of truth for the default pipeline (version it, review it, deploy it); UI-created guardrails are DB-managed *additions* and never modify the config-file pipeline. At least one `firewall_callbacks.*` reference must remain in `config.yaml` — importing that module is what registers the UI providers.

## Demo

Run the automated battery of safe and malicious prompts against a live proxy:

```bash
uv run demo.py             # interactive
uv run demo.py --delay 2   # auto-advancing
```

Or use the helper script to pick a `.env`, start the demo, or launch the server:

```bash
./scripts/run-demo-stack.sh
./scripts/run-demo-stack.sh serve
```

## Development

```bash
uv sync                               # package + dev/deployment groups
uv run pytest tests/ -q               # unit tests (153)
uv run pytest tests/ -m integration   # live proxy vs stub upstream (6) — no creds needed
uv run ruff check .
uv build                              # build the pip package
```

The integration suite boots the real proxy against a stub upstream and doubles as the LiteLLM compatibility battery: it verifies hook dispatch order, that blocked requests never reach the provider, generic error responses, and the management-UI provider registration. Project conventions and operational detail live in [AGENTS.md](AGENTS.md); architecture decisions in [DECISIONS.md](DECISIONS.md).

## License

MIT License. See [LICENSE](LICENSE) for details.
