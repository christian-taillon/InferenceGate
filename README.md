# LiteLLM Firewall Demonstration

A minimal, non-over-engineered LLM firewall built using LiteLLM Proxy.

## Purpose
This project demonstrates how to set up guardrails and filters for sensitive information (PII) and malicious prompts using LiteLLM's built-in content filters and Llama Guard assessment. It acts as a security gateway between users and an underlying AI model.

## Features

### Phase 1: Built-in Content Filters (Regex & Keywords)
Demonstrates LiteLLM's on-device, zero-cost guardrails:
- **PII Blocking**: Automatically blocks prompts containing sensitive information like specific email addresses.
- **Prompt Injection Protection**: Blocks "ignore all previous instructions" style attacks.
- **Brand Protection**: Blocks competitor mentions (e.g., Google, Microsoft) via keyword matching.

### Phase 2: Llama-Guard-3 Content Assessment
Demonstrates leveraging a specialized safety model (`llama-guard3:1b`) to assess user intent:
- **Violent Content Detection**: Detects prompts about harmful activities (S9).
- **Illegal Activity Detection**: Detects prompts about theft or crimes (S2).

## Setup

1.  **Prerequisites**: Ensure you have [uv](https://github.com/astral-sh/uv) installed.
2.  **Environment**: Create a `.env` file with your API credentials:
    ```env
    baseURL='https://ai.christiant.io/api'
    OPENAI_API_KEY='your-sk-...'
    MODEL='qwen3.5:35b-ctx100k'
    ```
3.  **Install Dependencies**:
    ```bash
    uv sync
    ```

## Running the Demonstration
The demonstration orchestrates a LiteLLM Proxy instance and runs test cases against it:
```bash
uv run demo.py
```

## Configuration
The firewall policies are defined in `config.yaml` using the LiteLLM `guardrails` system. This allows for easy replication and modification of safety rules across different environments.
