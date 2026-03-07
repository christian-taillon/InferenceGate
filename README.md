# LiteLLM Firewall Demonstration

A minimal, non-over-engineered LLM firewall built using LiteLLM Proxy.

## Purpose
This project demonstrates how to set up guardrails and filters for sensitive information (PII) and malicious prompts using LiteLLM's built-in content filters and integrated Llama Guard assessment. It acts as a security gateway between users and an underlying AI model.

## Features

### Phase 1: Built-in Content Filters (Regex & Keywords)
Demonstrates LiteLLM's on-device, zero-cost guardrails:
- **PII Blocking**: Automatically blocks prompts containing sensitive information like specific email addresses.
- **Prompt Injection Protection**: Blocks "ignore instructions" style attacks.
- **Brand Protection**: Blocks competitor mentions (e.g., Google, Microsoft) via keyword matching.

### Phase 2: Llama-Guard-3 Content Assessment
Demonstrates leveraging a specialized safety model (`llama-guard3:1b`) to assess user intent, fully integrated into the proxy workflow:
- **Violent Content Detection**: Detects prompts about harmful activities (S9).
- **Criminal Intent Detection**: Detects prompts about theft or crimes (S2).

## Setup

1.  **Prerequisites**: Ensure you have [uv](https://github.com/astral-sh/uv) installed.
2.  **Environment**: Create a `.env` file with your API credentials (see `.env.example`):
    ```env
    LITELLM_API_BASE='https://your-api-endpoint/v1'
    LITELLM_API_KEY='your-api-key'
    ```
3.  **Install Dependencies**:
    ```bash
    uv sync
    ```

## Running the Demonstration
The demonstration script starts a local LiteLLM Proxy instance and runs test cases against it to show the firewall in action:
```bash
uv run demo.py
```

## Configuration
The firewall policies are defined in `config.yaml` using the LiteLLM `guardrails` system. This approach allows for consistent and reproducible safety rules across environments.
