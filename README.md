# InferenceGate
 
A reference implementation for an enterprise-ready LLM security gateway built using LiteLLM Proxy.

## Purpose
This project provides a secure AI gateway architecture. It demonstrates how to intercept, assess, and filter LLM requests and responses using **deterministic regex/keyword rules**, **local and remote prompt-attack classification** (Llama Prompt Guard 2), and **probabilistic safety assessment** (Llama Guard 3).

## Architecture
```text
[ User / App ]
      |
      v
[ InferenceGate Proxy ] <--- [ config.yaml ]
      |
      +-- Shield 1: Built-in Filters (Regex/PII/Secrets)     pre_call
      +-- Shield 2: Llama Prompt Guard 2 (remote classify)   pre_call
      +-- Shield 2b: Prompt Guard Local (HF transformers)   pre_call
      +-- Shield 3: Llama Guard 3 content safety (S1-S14)   pre_call
      +-- Shield 4: Response Guard (post-call output scan)   post_call
      |
      v
[ Backend AI Model ] (e.g., Qwen, GPT-4, etc.)
```

## Features

### Shield 1: Built-in Content Filters (Regex & Prebuilt Detection)
Zero-latency, on-device guardrails:
- **PII and Secret Blocking**: Automatically prevents leakage of emails, SSNs, IBANs, API keys, JWTs, and similar sensitive values.
- **Prompt Injection Protection**: Blocks common jailbreak and instruction-override attempts.
- **Attack Pattern Detection**: Blocks common SQL injection payloads before they reach the upstream model.

### Shield 2: Prompt Attack Assessment (Llama Prompt Guard 2, remote)
Focused detection for prompt manipulation attempts, served via a vLLM-style `/classify` endpoint or Groq chat completions:
- **Jailbreak / Injection Classification**: Catches prompts trying to override hidden or developer instructions.
- **Configurable threshold and timeout**: Tunable per-shield via `litellm_params` in `config.yaml`.

### Shield 2b: Prompt Guard Local (on-device)
Same classifier run locally via HuggingFace `transformers` — no network dependency:
- **Preload**: Set `preload: true` to load the model at startup rather than on the first request.
- Requires `uv sync --extra local-prompt-guard`.

### Shield 3: Llama Guard 3 Content Assessment
Advanced intent analysis using a specialized safety model:
- **Taxonomy-based Blocking**: Detects and blocks prompts based on the full Llama Guard 3 taxonomy (S1-S14), including violent content, criminal intent, and privacy violations.
- **Category scoping**: Set `blocked_categories: [S1, S4, "Privacy"]` to block only specific categories. An unsafe verdict without a recognizable category always blocks (deny by default).
- **Strict output parsing**: Guard output is parsed strictly — a degraded guard model answering prose is a fail-policy event, never a silent allow.

### Shield 4: Response Content Filtering
Security doesn't stop at the request:
- **Output Scanning**: Scans LLM completions (including proposed tool calls) for data exfiltration, toxic content, or secret echo, blocking the response before it reaches the client.
- Non-streaming responses only (see DECISIONS.md D-005).

### Per-shield configuration
Every shield knob is a `litellm_params` key in `config.yaml` with an environment-variable fallback:

| Key | Shields | Default | Purpose |
|-----|---------|---------|---------|
| `api_base` | 2, 2b, 3, 4 | from env | Guard model endpoint |
| `api_key` | 2, 2b, 3, 4 | from env | Guard model auth |
| `model` | 2, 2b, 3, 4 | per shield | Guard model identifier |
| `fail_mode` | all | `open` | `open` (log + allow) or `closed` (deny) |
| `threshold` | 2, 2b | `0.5` | Malicious-score cutoff |
| `blocked_categories` | 3, 4 | all | S-codes or taxonomy names to block |
| `timeout` | 2 | `30s` | Classify endpoint timeout |
| `preload` | 2b | `false` | Load model at startup |

Invalid config (bad `fail_mode`, out-of-range `threshold`, unknown category) fails at proxy startup instead of at request time.

## Setup

1.  **Prerequisites**: Ensure you have [uv](https://github.com/astral-sh/uv) or `pip` installed.
2.  **Environment**: Create a `.env` file based on `.env.example`:
    ```env
    LITELLM_API_BASE='https://your-api-endpoint/v1'
    LITELLM_API_KEY='your-api-key'
    LITELLM_MASTER_KEY='sk-your-secure-random-key'
    ```
3.  **Install Dependencies**:
    ```bash
    uv sync  # or: pip install -r requirements.txt
    ```

## Running the Service (for Open WebUI)
To run the firewall as a persistent service for Open WebUI or other apps:
```bash
uv run serve.py
```
This will start the proxy on port 8001 and print connection instructions.

## Running the Demonstration
Run the automated test suite to see the firewall in action:
```bash
uv run demo.py
```

Or use the helper script to pick a `.env`, start the demo, or launch the server:
```bash
./scripts/run-demo-stack.sh
./scripts/run-demo-stack.sh serve
```

For an auto-advancing version of the demo, pass a delay in seconds:
```bash
uv run demo.py --delay 2
```

## Management UI

With PostgreSQL configured (`DATABASE_URL` in `.env`), the LiteLLM management UI at `http://<host>:8001/ui/` gives you:

- **Guardrails page**: all five configured shields are listed with their modes.
- **Add Guardrail**: the four InferenceGate shields register as first-class providers ("InferenceGate: …") with typed config forms — thresholds, fail mode, and a Llama Guard category multiselect (S1–S14) — so additional shield instances can be created and managed from the UI.

Division of authority: `config.yaml` is the source of truth for the default pipeline (version it, review it, deploy it); UI-created guardrails are DB-managed *additions* and never modify the config-file pipeline. At least one `firewall_callbacks.*` reference must remain in `config.yaml` — importing that module is what registers the UI providers.

## Customization
Modify `config.yaml` to add your own regex or prebuilt detection rules, or adjust the per-shield knobs (model, threshold, `blocked_categories`, `fail_mode`, `timeout`, `preload`). Every knob is a `litellm_params` key with an env-var fallback; invalid config fails at startup. The full config surface is documented inline in `config.yaml` and in the `firewall_callbacks.py` module docstring.

## License
MIT License. See [LICENSE](LICENSE) for details.

