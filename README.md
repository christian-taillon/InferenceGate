# LiteLLM Firewall

A minimal, non-over-engineered LLM firewall built using LiteLLM Proxy.

## Purpose
This project demonstrates how to set up guardrails and filters for sensitive information (PII) and malicious prompts using LiteLLM's built-in content filters and Llama Guard assessment. It acts as a gateway between users and the underlying AI model.

## Demonstration Phases

### Phase 1: Built-in Content Filters (Regex)
Demonstrates LiteLLM's on-device, zero-cost guardrails:
- **PII Masking**: Automatically redacts emails and credit cards.
- **Prompt Injection Protection**: Blocks "ignore all previous instructions" style attacks.
- **Brand Protection**: Blocks competitor mentions (e.g., Google, Microsoft).

### Phase 2: Llama-Guard-3 Content Assessment
Demonstrates leveraging a specialized safety model (`llama-guard3:1b`) to assess intent:
- **Violent Content Detection**: Detects prompts about building weapons (S9).
- **Illegal Activity Detection**: Detects prompts about theft or crime (S2).

## Setup
1.  Ensure you have `uv` installed.
2.  Configure your `.env` file with:
    ```env
    baseURL='https://ai.christiant.io/api'
    OPENAI_API_KEY='your-key'
    MODEL='qwen3.5:35b-ctx100k'
    ```
3.  Install dependencies:
    ```bash
    uv sync
    ```

## Running the Demonstration
Execute the demonstration script:
```bash
uv run demo.py
```

The script will:
1.  Start the LiteLLM Proxy in the background using `config.yaml`.
2.  Run tests for Phase 1 (Built-in filters).
3.  Run tests for Phase 2 (Llama Guard assessment).
4.  Cleanly shut down the proxy.

## Configuration
The guardrails are defined in `config.yaml` using `litellm_content_filter`. 

## Logs
Detailed logs of the firewall activity can be found in `firewall.log` during execution.
