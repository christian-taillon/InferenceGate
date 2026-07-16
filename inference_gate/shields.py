"""InferenceGate shields — custom guardrails for LiteLLM Proxy.

Canonical import path: ``inference_gate.shields`` (pip package
``inference-gate``). The repo-root ``firewall_callbacks.py`` is a
compatibility shim for config-file references, which LiteLLM loads from
.py files relative to the config directory.

Four config-driven shields complement LiteLLM's native content filter:

- ``LlamaPromptGuardShield`` (pre_call): prompt-attack classifier served
  remotely — a vLLM-style ``/classify`` endpoint or Groq chat completions.
- ``PromptGuardLocalShield`` (pre_call): the same classifier run on-device
  via HuggingFace transformers; no network dependency.
- ``LlamaGuardShield`` (pre_call): Llama Guard 3 safety taxonomy (S1–S14)
  over the full request message stack.
- ``ResponseGuardShield`` (post_call): Llama Guard over the model response,
  including proposed tool calls. Non-streaming responses only (D-005).

Configuration — every knob is a ``litellm_params`` key in config.yaml, with
an environment-variable fallback so existing deployments keep working:

    key                  env fallback(s)                            default
    api_base             <SHIELD>_API_BASE, LITELLM_API_BASE        —
    api_key              <SHIELD>_API_KEY, LITELLM_API_KEY          —
    model                LLAMA_PROMPT_GUARD_MODEL /                 per shield
                         PROMPT_GUARD_LOCAL_MODEL / LLAMA_GUARD_MODEL
    fail_mode            INFERENCE_GATE_FAIL_MODE                   open
    threshold            LLAMA_PROMPT_GUARD_THRESHOLD /             0.5
                         PROMPT_GUARD_LOCAL_THRESHOLD
    blocked_categories   —                            all unsafe categories
    timeout              —                                          30s
    preload              —                                          false

``blocked_categories`` (LlamaGuardShield / ResponseGuardShield) accepts
S-codes or taxonomy names (["S1", "Child Sexual Exploitation"]); when set,
only those categories block. An unsafe verdict without a recognizable
category always blocks (deny by default). Values of the form
``os.environ/VAR`` are resolved from the environment.

Security invariants (AGENTS.md):
- Log records never contain message/response content or raw guard-model
  output — only exception types, taxonomy codes, scores, and latencies.
- Client-facing block errors carry only ``BLOCKED_MESSAGE``; shield detail
  stays in server logs.
- Blocks raise ``fastapi.HTTPException(status_code=400)`` — the convention
  LiteLLM recognizes as a guardrail *intervention* (not a guardrail
  failure) in ``StandardLoggingGuardrailInformation`` and metrics.
- Shield malfunctions (network errors, malformed guard output, missing
  configuration) go through the fail policy: ``fail_mode: open`` logs and
  allows, ``fail_mode: closed`` re-raises and denies.
"""

import asyncio
import logging
import os
import re
import time
from typing import Any, Literal, Optional

import litellm
from litellm.integrations.custom_guardrail import (
    CustomGuardrail,
    log_guardrail_information,
)

try:
    import httpx
except ImportError:  # pragma: no cover - httpx ships with litellm
    httpx = None  # type: ignore[assignment]

try:
    from fastapi import HTTPException
except ImportError:  # pragma: no cover - fastapi ships with litellm[proxy]

    class HTTPException(Exception):  # type: ignore[no-redef]
        def __init__(self, status_code: int, detail: Any = None):
            self.status_code = status_code
            self.detail = detail
            super().__init__(f"{status_code}: {detail}")


try:  # UI config models — optional, only needed for the management UI
    from pydantic import Field
    from litellm.types.proxy.guardrails.guardrail_hooks.base import (
        GuardrailConfigModel,
    )
except ImportError:  # pragma: no cover - ships with litellm[proxy]
    GuardrailConfigModel = None  # type: ignore[assignment,misc]


# Llama Guard 3 Taxonomy (S1-S14)
# Note: S14 (Code Interpreter Abuse) is specific to the 8B model but included for future-proofing.
LLAMA_GUARD_TAXONOMY = {
    "S1": "Violent Crimes",
    "S2": "Non-Violent Crimes",
    "S3": "Sex-Related Crimes",
    "S4": "Child Sexual Exploitation",
    "S5": "Defamation",
    "S6": "Specialized Advice",
    "S7": "Privacy",
    "S8": "Intellectual Property",
    "S9": "Indiscriminate Weapons",
    "S10": "Hate",
    "S11": "Suicide & Self-Harm",
    "S12": "Sexual Content",
    "S13": "Elections",
    "S14": "Code Interpreter Abuse",
}

PROMPT_GUARD_MAX_TOKENS = 512
PROMPT_GUARD_MAX_WORDS = 350
PROMPT_GUARD_WORD_OVERLAP = 50

DEFAULT_LLAMA_GUARD_MODEL = "openai/llama-guard3:1b"
DEFAULT_PROMPT_GUARD_MODEL = "meta-llama/llama-prompt-guard-2-86m"
DEFAULT_LOCAL_PROMPT_GUARD_MODEL = "meta-llama/Llama-Prompt-Guard-2-86M"
DEFAULT_REMOTE_TIMEOUT_SECONDS = 30.0

# Providers litellm can route to when the model carries an explicit prefix.
_PROVIDER_PREFIXES = {
    "openai",
    "groq",
    "ollama",
    "ollama_chat",
    "anthropic",
    "vertex_ai",
    "azure",
    "bedrock",
    "hosted_vllm",
}

VALID_FAIL_MODES = {"open", "closed"}
FAIL_MODE = os.getenv("INFERENCE_GATE_FAIL_MODE", "open").lower()
BLOCKED_MESSAGE = "Request blocked by content safety shield."

# Security invariant: log records must never contain message or response
# content, even truncated — exception text may embed request payloads, so
# only exception types are logged (ShieldConfigError excepted: its message
# is authored here and content-free by construction).
logger = logging.getLogger("inference_gate.shields")


class ShieldConfigError(RuntimeError):
    """A shield is enabled but not usable (e.g. no API base configured)."""


class GuardOutputError(ValueError):
    """The guard model returned output outside its documented format.

    Message text must stay content-free: the guard model's raw output is
    untrusted and may echo request content.
    """


def _blocked_error() -> HTTPException:
    """The only exception clients ever see for a policy block: generic
    message, no shield names, labels, scores, or taxonomy codes."""
    return HTTPException(status_code=400, detail={"error": BLOCKED_MESSAGE})


def _handle_shield_error(
    exc: Exception, shield_name: str, fail_mode: Optional[str] = None
) -> None:
    """Route a shield malfunction through the fail policy."""
    mode = (fail_mode or FAIL_MODE or "open").lower()
    detail = str(exc) if isinstance(exc, ShieldConfigError) else type(exc).__name__
    if mode == "closed":
        logger.error("%s shield error (%s); failing closed", shield_name, detail)
        raise exc
    logger.warning("%s shield error (%s); failing open", shield_name, detail)


def _resolve_secret_ref(value: Any) -> Optional[str]:
    """Resolve config values of the form ``os.environ/VAR`` (LiteLLM
    convention); pass plain values through."""
    if isinstance(value, str) and value.startswith("os.environ/"):
        return os.getenv(value.split("/", 1)[1]) or None
    return value or None


def _resolve_threshold(value: Any, env_var: str, shield_name: str) -> float:
    if value is None:
        value = os.getenv(env_var) or 0.5
    try:
        threshold = float(value)
    except (TypeError, ValueError):
        raise ValueError(
            f"{shield_name}: threshold must be a number in [0, 1], got {value!r}"
        ) from None
    if not 0.0 <= threshold <= 1.0:
        raise ValueError(
            f"{shield_name}: threshold must be in [0, 1], got {threshold}"
        )
    return threshold


def _normalize_blocked_categories(
    value: Any, shield_name: str
) -> Optional[frozenset[str]]:
    """Normalize a category policy to S-codes; None means every unsafe
    category blocks. Unknown entries are a startup configuration error."""
    if value is None:
        return None
    if isinstance(value, str):
        value = [item for item in re.split(r"[\s,]+", value) if item]
    if not value:
        raise ValueError(
            f"{shield_name}: blocked_categories cannot be empty; "
            "omit it to block every unsafe category"
        )
    by_name = {name.lower(): code for code, name in LLAMA_GUARD_TAXONOMY.items()}
    codes = set()
    for item in value:
        text = str(item).strip()
        if text.upper() in LLAMA_GUARD_TAXONOMY:
            codes.add(text.upper())
        elif text.lower() in by_name:
            codes.add(by_name[text.lower()])
        else:
            raise ValueError(
                f"{shield_name}: unknown Llama Guard category {text!r}; "
                f"expected S1–S14 or a taxonomy name"
            )
    return frozenset(codes)


def _parse_llama_guard_output(raw: str) -> tuple[str, list[str]]:
    """Strictly parse Llama Guard output into (verdict, taxonomy codes).

    Accepted format: first token ``safe`` or ``unsafe``; category codes on
    the same or following lines. Only codes present in the known taxonomy
    are kept — the guard model's raw output is untrusted and must never be
    logged or echoed. Anything else raises GuardOutputError so a degraded
    guard model becomes a fail-policy event instead of a silent allow.
    """
    lines = [line.strip() for line in (raw or "").strip().splitlines() if line.strip()]
    if not lines:
        raise GuardOutputError("empty guard-model output")
    first, _, remainder = lines[0].partition(" ")
    verdict = first.strip().lower()
    if verdict not in {"safe", "unsafe"}:
        raise GuardOutputError("unrecognized guard-model verdict")
    code_text = " ".join([remainder, *lines[1:]])
    codes = [
        code
        for code in dict.fromkeys(re.split(r"[\s,]+", code_text))
        if code in LLAMA_GUARD_TAXONOMY
    ]
    return verdict, codes


def _extract_all_content(messages: list[dict[str, Any]]) -> str:
    """Extract all text content from the full message stack.

    Scans system, developer, user, and assistant messages including
    non-text content items (image URLs, audio), to prevent bypass via
    system prompts, prior turns, or multimodal content.
    """
    parts: list[str] = []
    for message in messages:
        content = message.get("content", "")
        if isinstance(content, str):
            if content:
                parts.append(content)
        elif isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text":
                    text = item.get("text", "")
                    if text:
                        parts.append(text)
                elif item.get("type") == "image_url":
                    url_obj = item.get("image_url", {})
                    if isinstance(url_obj, dict):
                        url = url_obj.get("url", "")
                        if url:
                            parts.append(url)
    return " ".join(parts)


def _extract_response_content(response: Any) -> str:
    """Extract text content from an LLM response object.

    Covers message content, reasoning content, and proposed tool calls —
    a harmful tool invocation may accompany perfectly benign text.
    """
    parts: list[str] = []
    choices = getattr(response, "choices", None) or []
    for choice in choices:
        message = getattr(choice, "message", None)
        if message is None:
            continue
        content = getattr(message, "content", None)
        if content:
            parts.append(content)
        reasoning = getattr(message, "reasoning_content", None)
        if reasoning:
            parts.append(reasoning)
        for tool_call in getattr(message, "tool_calls", None) or []:
            function = getattr(tool_call, "function", None)
            if function is None:
                continue
            name = getattr(function, "name", None)
            if name:
                parts.append(name)
            arguments = getattr(function, "arguments", None)
            if arguments:
                parts.append(arguments)
    return " ".join(parts)


def _texts_from_guardrail_inputs(inputs: Any) -> str:
    """Flatten LiteLLM's unified guardrail inputs (texts, tool calls, image
    URLs) into one scannable string. Data-URI images are skipped — base64
    blobs are noise to text classifiers and can exceed guard context."""

    def _get(name: str) -> list[Any]:
        try:
            value = inputs.get(name)
        except AttributeError:
            value = getattr(inputs, name, None)
        return list(value) if value else []

    parts = [text for text in _get("texts") if isinstance(text, str) and text]
    for tool_call in _get("tool_calls"):
        if isinstance(tool_call, dict):
            function = tool_call.get("function") or {}
        else:
            function = getattr(tool_call, "function", None)
        if isinstance(function, dict):
            name, arguments = function.get("name"), function.get("arguments")
        else:
            name = getattr(function, "name", None)
            arguments = getattr(function, "arguments", None)
        parts.extend(str(value) for value in (name, arguments) if value)
    for image in _get("images"):
        if isinstance(image, str) and image.startswith(("http://", "https://")):
            parts.append(image)
    return " ".join(parts)


def _chunk_text_for_prompt_guard(text: str) -> list[str]:
    normalized = " ".join((text or "").split())
    if not normalized:
        return []

    words = normalized.split(" ")
    if len(words) <= PROMPT_GUARD_MAX_WORDS:
        return [normalized]

    chunks = []
    step = max(1, PROMPT_GUARD_MAX_WORDS - PROMPT_GUARD_WORD_OVERLAP)
    for start in range(0, len(words), step):
        chunk = " ".join(words[start : start + PROMPT_GUARD_MAX_WORDS]).strip()
        if chunk:
            chunks.append(chunk)
        if start + PROMPT_GUARD_MAX_WORDS >= len(words):
            break

    return chunks


# ---------------------------------------------------------------------------
# LiteLLM management-UI config models
#
# These pydantic models drive the guardrail forms in the LiteLLM UI: the
# /guardrails/ui/add_guardrail_settings endpoint renders each field
# (descriptions, selects, multiselects) for every provider registered in
# litellm's guardrail_class_registry — see register_with_litellm_ui() below.
# config.yaml remains the source of truth for the default pipeline; the UI
# creates additional DB-managed instances of the same shields.
# ---------------------------------------------------------------------------

if GuardrailConfigModel is not None:
    _CategoryCode = Literal[
        "S1", "S2", "S3", "S4", "S5", "S6", "S7",
        "S8", "S9", "S10", "S11", "S12", "S13", "S14",
    ]

    class _ShieldConfigModel(GuardrailConfigModel):
        """Fields shared by every InferenceGate shield."""

        api_base: Optional[str] = Field(
            default=None,
            description="Guard model endpoint. Falls back to the shield's "
            "*_API_BASE env var, then LITELLM_API_BASE.",
        )
        api_key: Optional[str] = Field(
            default=None,
            description="Guard model API key (accepts os.environ/VAR). Falls "
            "back to the shield's *_API_KEY env var, then LITELLM_API_KEY.",
        )
        fail_mode: Optional[Literal["open", "closed"]] = Field(
            default=None,
            description="open: log and allow on shield malfunction; closed: "
            "deny. Default from INFERENCE_GATE_FAIL_MODE (open).",
        )

        @staticmethod
        def ui_friendly_name() -> str:
            return "InferenceGate Shield"

    class LlamaPromptGuardConfigModel(_ShieldConfigModel):
        model: Optional[str] = Field(
            default=None,
            description="Prompt Guard model id "
            "(default meta-llama/llama-prompt-guard-2-86m; "
            "env LLAMA_PROMPT_GUARD_MODEL).",
        )
        threshold: Optional[float] = Field(
            default=None,
            description="Malicious-score cutoff in [0, 1]; default 0.5 "
            "(env LLAMA_PROMPT_GUARD_THRESHOLD).",
        )
        timeout: Optional[float] = Field(
            default=None,
            description="Classify-endpoint timeout in seconds (default 30).",
        )

        @staticmethod
        def ui_friendly_name() -> str:
            return "InferenceGate: Llama Prompt Guard (remote)"

    class PromptGuardLocalConfigModel(_ShieldConfigModel):
        model: Optional[str] = Field(
            default=None,
            description="HuggingFace model id run on-device "
            "(default meta-llama/Llama-Prompt-Guard-2-86M; "
            "env PROMPT_GUARD_LOCAL_MODEL). Requires the "
            "local-prompt-guard extra.",
        )
        threshold: Optional[float] = Field(
            default=None,
            description="Malicious-score cutoff in [0, 1]; default 0.5 "
            "(env PROMPT_GUARD_LOCAL_THRESHOLD).",
        )
        preload: Optional[bool] = Field(
            default=None,
            description="Load the model at startup instead of on the first "
            "request.",
        )

        @staticmethod
        def ui_friendly_name() -> str:
            return "InferenceGate: Prompt Guard (local)"

    class LlamaGuardConfigModel(_ShieldConfigModel):
        model: Optional[str] = Field(
            default=None,
            description="Llama Guard model id "
            "(default openai/llama-guard3:1b; env LLAMA_GUARD_MODEL).",
        )
        blocked_categories: Optional[list[_CategoryCode]] = Field(
            default=None,
            description="Llama Guard 3 categories that block "
            "(S1 Violent Crimes … S14 Code Interpreter Abuse). "
            "Leave empty to block every unsafe category.",
        )

        @staticmethod
        def ui_friendly_name() -> str:
            return "InferenceGate: Llama Guard (requests)"

    class ResponseGuardConfigModel(LlamaGuardConfigModel):
        @staticmethod
        def ui_friendly_name() -> str:
            return "InferenceGate: Response Guard (output scan)"

else:  # pragma: no cover - litellm UI types unavailable
    LlamaPromptGuardConfigModel = None  # type: ignore[assignment,misc]
    PromptGuardLocalConfigModel = None  # type: ignore[assignment,misc]
    LlamaGuardConfigModel = None  # type: ignore[assignment,misc]
    ResponseGuardConfigModel = None  # type: ignore[assignment,misc]


class _InferenceGateShield(CustomGuardrail):
    """Shared shield plumbing: config resolution, fail policy, blocking.

    Subclasses implement ``_scan_text`` — classify the given text and raise
    ``_blocked_error()`` when policy blocks it; anything else that goes
    wrong inside the scan must go through ``self._handle_error``.
    """

    shield_name: str = "InferenceGateShield"
    api_base_env: tuple[str, ...] = ("LITELLM_API_BASE",)
    api_key_env: tuple[str, ...] = ("LITELLM_API_KEY",)

    def __init__(
        self,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        fail_mode: Optional[str] = None,
        **kwargs,
    ):
        self._api_base = _resolve_secret_ref(api_base)
        self._api_key = _resolve_secret_ref(api_key)
        if fail_mode is not None:
            fail_mode = str(fail_mode).strip().lower()
            if fail_mode not in VALID_FAIL_MODES:
                raise ValueError(
                    f"{self.shield_name}: fail_mode must be one of "
                    f"{sorted(VALID_FAIL_MODES)}, got {fail_mode!r}"
                )
        self.fail_mode = fail_mode
        super().__init__(**kwargs)

    def _resolve_api_base(self) -> Optional[str]:
        if self._api_base:
            return self._api_base
        for var in self.api_base_env:
            value = os.getenv(var)
            if value:
                return value
        return None

    def _resolve_api_key(self) -> Optional[str]:
        if self._api_key:
            return self._api_key
        for var in self.api_key_env:
            value = os.getenv(var)
            if value:
                return value
        return None

    def _handle_error(self, exc: Exception) -> None:
        _handle_shield_error(exc, self.shield_name, self.fail_mode)

    @staticmethod
    def _is_groq_api_base(api_base: Optional[str]) -> bool:
        return bool(api_base and "groq.com" in api_base)

    def _resolved_guard_model(self, api_base: Optional[str] = None) -> str:
        model = self.guard_model
        if "/" in model and model.split("/", 1)[0] in _PROVIDER_PREFIXES:
            return model
        if self._is_groq_api_base(api_base):
            return f"groq/{model}"
        return model

    async def _scan_text(self, content: str) -> None:
        raise NotImplementedError


# LiteLLM routes a guardrail through the unified apply_guardrail path only
# when apply_guardrail appears in type(callback).__dict__ — inherited hook
# methods are invisible to that check and the shield silently never runs.
# Every concrete shield must therefore define its hooks on the class itself.
# apply_guardrail is the live dispatch path at litellm 1.82.0 (see
# docs/security/LITELLM_INTEGRATION.md); async_moderation_hook keeps the
# request shields usable on older proxies and in during_call mode.


class LlamaPromptGuardShield(_InferenceGateShield):
    """Prompt attack shield powered by Llama Prompt Guard 2 (remote).

    Blocks prompts classified as jailbreak or prompt-injection attempts.
    Talks to a vLLM-style ``/classify`` endpoint, or falls back to chat
    completions on Groq API bases.
    """

    shield_name = "Llama Prompt Guard"
    api_base_env = ("LLAMA_PROMPT_GUARD_API_BASE", "LITELLM_API_BASE")
    api_key_env = ("LLAMA_PROMPT_GUARD_API_KEY", "LITELLM_API_KEY")

    @staticmethod
    def get_config_model():
        return LlamaPromptGuardConfigModel

    def __init__(
        self,
        model: Optional[str] = None,
        threshold: Any = None,
        timeout: Any = None,
        **kwargs,
    ):
        self.guard_model = _resolve_secret_ref(model) or os.getenv(
            "LLAMA_PROMPT_GUARD_MODEL", DEFAULT_PROMPT_GUARD_MODEL
        )
        self.threshold = _resolve_threshold(
            threshold, "LLAMA_PROMPT_GUARD_THRESHOLD", self.shield_name
        )
        self.timeout = float(timeout or DEFAULT_REMOTE_TIMEOUT_SECONDS)
        super().__init__(**kwargs)
        logger.info(
            "%s initialized (model=%s, threshold=%.2f)",
            self.shield_name,
            self.guard_model,
            self.threshold,
        )

    def _build_classify_urls(self, api_base: str) -> list[str]:
        base = api_base.rstrip("/")
        if base.endswith("/v1"):
            candidates = [f"{base[:-3]}/classify", f"{base}/classify"]
        else:
            candidates = [f"{base}/classify", f"{base}/v1/classify"]
        return list(dict.fromkeys(candidates))

    def _parse_classify_result(self, item: dict[str, Any]) -> dict[str, Any]:
        label = str(item.get("label") or item.get("classification") or "").strip()
        probs = item.get("probs") or item.get("scores") or item.get("probabilities")

        malicious_score = item.get("malicious_score")
        if malicious_score is None and isinstance(probs, list) and len(probs) > 1:
            malicious_score = probs[1]
        elif malicious_score is None and isinstance(probs, dict):
            for key in ("MALICIOUS", "malicious", "LABEL_1", "1"):
                if key in probs:
                    malicious_score = probs[key]
                    break
        elif malicious_score is None and "score" in item:
            malicious_score = item.get("score")

        return {
            "label": label,
            "malicious_score": malicious_score,
            "raw": item,
        }

    def _parse_classify_response(self, response_json: Any) -> list[dict[str, Any]]:
        if isinstance(response_json, dict) and isinstance(
            response_json.get("data"), list
        ):
            return [
                self._parse_classify_result(item)
                for item in response_json["data"]
                if isinstance(item, dict)
            ]
        if isinstance(response_json, list):
            return [
                self._parse_classify_result(item)
                for item in response_json
                if isinstance(item, dict)
            ]
        if isinstance(response_json, dict):
            return [self._parse_classify_result(response_json)]
        return []

    def _is_malicious_result(self, result: dict[str, Any]) -> bool:
        label = str(result.get("label", "")).strip().lower()
        try:
            score = result.get("malicious_score")
            score = float(score) if score is not None else None
        except (TypeError, ValueError):
            score = None

        if label in {"malicious", "jailbreak", "prompt_injection", "injection"}:
            return score is None or score >= self.threshold
        if label in {"benign", "safe", "default"}:
            return False
        return score is not None and score >= self.threshold

    def _parse_chat_classification_text(self, text: str) -> dict[str, Any]:
        normalized = (text or "").strip()
        upper_text = normalized.upper()

        try:
            numeric_score = float(normalized)
            return {
                "label": "MALICIOUS" if numeric_score >= self.threshold else "BENIGN",
                "malicious_score": numeric_score,
                "raw": {"content": normalized},
            }
        except ValueError:
            pass

        if "MALICIOUS" in upper_text and "BENIGN" not in upper_text:
            label = "MALICIOUS"
        elif "BENIGN" in upper_text and "MALICIOUS" not in upper_text:
            label = "BENIGN"
        elif upper_text.startswith("MALICIOUS"):
            label = "MALICIOUS"
        elif upper_text.startswith("BENIGN"):
            label = "BENIGN"
        else:
            label = normalized.splitlines()[0].strip() if normalized else ""

        return {
            "label": label,
            "malicious_score": 1.0 if label.upper() == "MALICIOUS" else 0.0,
            "raw": {"content": normalized},
        }

    async def _classify_via_chat(
        self, texts: list[str], api_base: str, api_key: Optional[str]
    ) -> list[dict[str, Any]]:
        results = []
        for text in texts:
            response = await litellm.acompletion(
                model=self._resolved_guard_model(api_base),
                messages=[{"role": "user", "content": text}],
                api_base=api_base,
                api_key=api_key,
                temperature=0,
                max_tokens=4,
            )
            choices = getattr(response, "choices", None) or []
            if not choices:
                logger.debug("%s returned no choices", self.shield_name)
                continue
            message = getattr(choices[0], "message", None)
            raw_content = (getattr(message, "content", "") or "").strip()
            if not raw_content:
                continue
            results.append(self._parse_chat_classification_text(raw_content))
        return results

    async def _classify_remote(self, texts: list[str]) -> list[dict[str, Any]]:
        api_base = self._resolve_api_base()
        api_key = self._resolve_api_key()
        if not api_base:
            raise ShieldConfigError(
                "no API base configured: set litellm_params.api_base, "
                "LLAMA_PROMPT_GUARD_API_BASE, or LITELLM_API_BASE"
            )
        if self._is_groq_api_base(api_base):
            return await self._classify_via_chat(texts, api_base, api_key)
        if httpx is None:  # pragma: no cover - httpx ships with litellm
            raise ShieldConfigError("httpx is required for the classify endpoint")

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": self.guard_model,
            "input": texts,
            "truncate_prompt_tokens": PROMPT_GUARD_MAX_TOKENS,
        }

        last_error: Optional[Exception] = None
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for url in self._build_classify_urls(api_base):
                response = await client.post(url, json=payload, headers=headers)
                if response.status_code == 404:
                    last_error = ShieldConfigError(
                        f"classify endpoint not found at {url}"
                    )
                    continue
                response.raise_for_status()
                parsed = self._parse_classify_response(response.json())
                if not parsed:
                    logger.debug("%s returned no classification data", self.shield_name)
                return parsed
        raise last_error or ShieldConfigError("no classify endpoint candidates")

    async def _scan_text(self, content: str) -> None:
        text_chunks = _chunk_text_for_prompt_guard(content)
        if not text_chunks:
            return

        started = time.perf_counter()
        try:
            results = await self._classify_remote(text_chunks)
        except Exception as exc:
            self._handle_error(exc)
            return
        latency_ms = (time.perf_counter() - started) * 1000

        malicious_results = [
            result for result in results if self._is_malicious_result(result)
        ]
        if not malicious_results:
            logger.debug(
                "%s allow (chunks=%d, latency_ms=%.0f)",
                self.shield_name,
                len(text_chunks),
                latency_ms,
            )
            return

        top_score = max(
            float(result.get("malicious_score") or 0.0)
            for result in malicious_results
        )
        logger.info(
            "%s blocking request (score=%.3f, chunks_flagged=%d/%d, latency_ms=%.0f)",
            self.shield_name,
            top_score,
            len(malicious_results),
            len(text_chunks),
            latency_ms,
        )
        raise _blocked_error()

    @log_guardrail_information
    async def async_moderation_hook(
        self, data: dict, user_api_key_dict: Any, call_type: Any = None
    ) -> dict:
        await self._scan_text(_extract_all_content(data.get("messages", [])))
        return data

    @log_guardrail_information
    async def apply_guardrail(
        self,
        inputs: Any,
        request_data: dict,
        input_type: Literal["request", "response"],
        logging_obj: Optional[Any] = None,
    ) -> Any:
        if input_type != "request":
            return inputs
        await self._scan_text(_texts_from_guardrail_inputs(inputs))
        return inputs


class PromptGuardLocalShield(_InferenceGateShield):
    """Local prompt-attack shield using HuggingFace Prompt Guard models.

    Loads a DeBERTa-based text-classification model (e.g.
    meta-llama/Llama-Prompt-Guard-2-86M) directly via transformers. Runs
    entirely on-device — no API calls, no network dependency. Set
    ``preload: true`` to load the model at startup instead of adding the
    load time to the first request.
    """

    shield_name = "Prompt Guard Local"

    _model_cache: dict[str, Any] = {}

    @staticmethod
    def get_config_model():
        return PromptGuardLocalConfigModel

    def __init__(
        self,
        model: Optional[str] = None,
        threshold: Any = None,
        preload: bool = False,
        **kwargs,
    ):
        self.model_id = _resolve_secret_ref(model) or os.getenv(
            "PROMPT_GUARD_LOCAL_MODEL", DEFAULT_LOCAL_PROMPT_GUARD_MODEL
        )
        self.threshold = _resolve_threshold(
            threshold, "PROMPT_GUARD_LOCAL_THRESHOLD", self.shield_name
        )
        super().__init__(**kwargs)
        logger.info(
            "%s initialized (model=%s, threshold=%.2f)",
            self.shield_name,
            self.model_id,
            self.threshold,
        )
        if preload:
            try:
                self._load_pipeline(self.model_id)
            except Exception as exc:
                logger.warning(
                    "%s preload failed (%s); will retry at first request",
                    self.shield_name,
                    type(exc).__name__,
                )

    @classmethod
    def _load_pipeline(cls, model_id: str):
        if model_id not in cls._model_cache:
            try:
                from transformers import pipeline
            except ImportError as exc:
                raise ImportError(
                    "transformers is required for PromptGuardLocalShield. "
                    "Install with: uv sync --extra local-prompt-guard"
                ) from exc

            logger.info("Prompt Guard Local loading model %s", model_id)
            cls._model_cache[model_id] = pipeline(
                "text-classification",
                model=model_id,
                truncation=True,
                max_length=PROMPT_GUARD_MAX_TOKENS,
            )
        return cls._model_cache[model_id]

    def _classify_chunk(self, text: str) -> dict[str, Any]:
        pipe = self._load_pipeline(self.model_id)
        results = pipe(text)

        if isinstance(results, list):
            results = results[0] if results else {}
        if not isinstance(results, dict):
            return {"label": "", "malicious_score": None, "raw": results}

        label = str(results.get("label", "")).strip().upper()
        score = results.get("score")

        if label == "LABEL_0":
            label = "BENIGN"
        elif label == "LABEL_1":
            label = "MALICIOUS"

        if label in {"MALICIOUS", "JAILBREAK", "INJECTION", "INJECT"}:
            malicious_score = float(score) if score is not None else 1.0
        elif label in {"BENIGN", "SAFE"}:
            malicious_score = 0.0
        else:
            malicious_score = float(score) if score is not None else 0.0

        return {
            "label": label,
            "malicious_score": malicious_score,
            "raw": results,
        }

    def _is_malicious_result(self, result: dict[str, Any]) -> bool:
        label = result.get("label", "").strip().lower()
        if label in {"malicious", "jailbreak", "injection", "inject"}:
            score = result.get("malicious_score")
            return score is None or float(score) >= self.threshold
        return False

    async def _scan_text(self, content: str) -> None:
        text_chunks = _chunk_text_for_prompt_guard(content)
        if not text_chunks:
            return

        started = time.perf_counter()
        try:
            results = await asyncio.to_thread(
                lambda: [self._classify_chunk(chunk) for chunk in text_chunks]
            )
        except Exception as exc:
            self._handle_error(exc)
            return
        latency_ms = (time.perf_counter() - started) * 1000

        malicious_results = [
            result for result in results if self._is_malicious_result(result)
        ]
        if not malicious_results:
            logger.debug(
                "%s allow (chunks=%d, latency_ms=%.0f)",
                self.shield_name,
                len(text_chunks),
                latency_ms,
            )
            return

        logger.info(
            "%s blocking request (chunks_flagged=%d/%d, latency_ms=%.0f)",
            self.shield_name,
            len(malicious_results),
            len(text_chunks),
            latency_ms,
        )
        raise _blocked_error()

    @log_guardrail_information
    async def async_moderation_hook(
        self, data: dict, user_api_key_dict: Any, call_type: Any = None
    ) -> dict:
        await self._scan_text(_extract_all_content(data.get("messages", [])))
        return data

    @log_guardrail_information
    async def apply_guardrail(
        self,
        inputs: Any,
        request_data: dict,
        input_type: Literal["request", "response"],
        logging_obj: Optional[Any] = None,
    ) -> Any:
        if input_type != "request":
            return inputs
        await self._scan_text(_texts_from_guardrail_inputs(inputs))
        return inputs


class _LlamaGuardCore(_InferenceGateShield):
    """Llama Guard 3 classification with a per-category block policy."""

    api_base_env = ("LLAMA_GUARD_API_BASE", "LITELLM_API_BASE")
    api_key_env = ("LLAMA_GUARD_API_KEY", "LITELLM_API_KEY")
    scan_target = "request"

    def __init__(
        self,
        model: Optional[str] = None,
        blocked_categories: Any = None,
        **kwargs,
    ):
        self.guard_model = _resolve_secret_ref(model) or os.getenv(
            "LLAMA_GUARD_MODEL", DEFAULT_LLAMA_GUARD_MODEL
        )
        self.blocked_categories = _normalize_blocked_categories(
            blocked_categories, self.shield_name
        )
        super().__init__(**kwargs)
        logger.info(
            "%s initialized (model=%s, blocked_categories=%s)",
            self.shield_name,
            self.guard_model,
            ",".join(sorted(self.blocked_categories))
            if self.blocked_categories
            else "all",
        )

    async def _classify(self, content: str) -> tuple[str, list[str]]:
        api_base = self._resolve_api_base()
        if not api_base:
            raise ShieldConfigError(
                "no API base configured: set litellm_params.api_base, "
                "LLAMA_GUARD_API_BASE, or LITELLM_API_BASE"
            )
        response = await litellm.acompletion(
            model=self._resolved_guard_model(api_base),
            messages=[{"role": "user", "content": content}],
            api_base=api_base,
            api_key=self._resolve_api_key(),
            temperature=0,
            max_tokens=20,
        )
        choices = getattr(response, "choices", None) or []
        raw_content = ""
        if choices:
            message = getattr(choices[0], "message", None)
            raw_content = (getattr(message, "content", "") or "").strip()
        return _parse_llama_guard_output(raw_content)

    def _policy_blocks(self, codes: list[str]) -> bool:
        if self.blocked_categories is None:
            return True
        if not codes:
            # Unsafe with no recognizable category: deny by default rather
            # than let malformed codes slip past a scoped policy.
            return True
        return any(code in self.blocked_categories for code in codes)

    async def _scan_text(self, content: str) -> None:
        if not content or not content.strip():
            return

        started = time.perf_counter()
        try:
            verdict, codes = await self._classify(content)
        except Exception as exc:
            self._handle_error(exc)
            return
        latency_ms = (time.perf_counter() - started) * 1000

        if verdict == "safe":
            logger.debug(
                "%s allow (latency_ms=%.0f)", self.shield_name, latency_ms
            )
            return

        category_list = ",".join(codes) or "unspecified"
        if not self._policy_blocks(codes):
            logger.info(
                "%s unsafe verdict allowed by category policy "
                "(categories=%s, latency_ms=%.0f)",
                self.shield_name,
                category_list,
                latency_ms,
            )
            return

        logger.info(
            "%s blocking %s (categories=%s, latency_ms=%.0f)",
            self.shield_name,
            self.scan_target,
            category_list,
            latency_ms,
        )
        raise _blocked_error()


class LlamaGuardShield(_LlamaGuardCore):
    """Request-side Llama Guard 3 shield.

    Classifies the full message stack against the S1–S14 taxonomy; use
    ``blocked_categories`` to scope which categories block.
    """

    shield_name = "LlamaGuard"
    scan_target = "request"

    @staticmethod
    def get_config_model():
        return LlamaGuardConfigModel

    @log_guardrail_information
    async def async_moderation_hook(
        self, data: dict, user_api_key_dict: Any, call_type: Any = None
    ) -> dict:
        await self._scan_text(_extract_all_content(data.get("messages", [])))
        return data

    @log_guardrail_information
    async def apply_guardrail(
        self,
        inputs: Any,
        request_data: dict,
        input_type: Literal["request", "response"],
        logging_obj: Optional[Any] = None,
    ) -> Any:
        if input_type != "request":
            return inputs
        await self._scan_text(_texts_from_guardrail_inputs(inputs))
        return inputs


class ResponseGuardShield(_LlamaGuardCore):
    """Response-side shield that scans model output for unsafe content.

    Runs as a post_call guardrail to catch data exfiltration, toxic
    content, and secret echo that pre_call shields cannot detect. Scans
    message content, reasoning content, and proposed tool calls.
    Non-streaming responses only (DECISIONS.md D-005).
    """

    shield_name = "ResponseGuard"
    scan_target = "response"

    @staticmethod
    def get_config_model():
        return ResponseGuardConfigModel

    @log_guardrail_information
    async def async_post_call_success_hook(
        self,
        data: dict,
        user_api_key_dict: Any,
        response: Any,
    ) -> Any:
        await self._scan_text(_extract_response_content(response))
        return response

    @log_guardrail_information
    async def apply_guardrail(
        self,
        inputs: Any,
        request_data: dict,
        input_type: Literal["request", "response"],
        logging_obj: Optional[Any] = None,
    ) -> Any:
        if input_type != "response":
            return inputs
        await self._scan_text(_texts_from_guardrail_inputs(inputs))
        return inputs


# ---------------------------------------------------------------------------
# LiteLLM management-UI provider registration
# ---------------------------------------------------------------------------

UI_PROVIDER_NAMES = (
    "inference_gate_prompt_guard",
    "inference_gate_prompt_guard_local",
    "inference_gate_llama_guard",
    "inference_gate_response_guard",
)


def register_with_litellm_ui() -> bool:
    """Register the shields as first-class guardrail providers in litellm's
    registries so the management UI can list them in the Add Guardrail flow
    (with typed config forms from get_config_model) and create DB-managed
    instances alongside the config.yaml pipeline.

    Registration requires this module to be imported, which the config.yaml
    dotted-path guardrail references guarantee. Best-effort: if litellm's
    internal registry layout changes, the config.yaml pipeline is unaffected
    and this becomes a logged no-op.
    """
    try:
        from litellm.proxy.guardrails.guardrail_registry import (
            guardrail_class_registry,
            guardrail_initializer_registry,
        )
    except Exception as exc:  # pragma: no cover - depends on litellm internals
        logger.warning(
            "LiteLLM UI provider registration skipped (%s)", type(exc).__name__
        )
        return False

    def _make_initializer(shield_cls, config_keys):
        def _initialize(litellm_params: Any, guardrail: dict):
            kwargs = {}
            for key in config_keys:
                value = litellm_params.get(key)
                if value is not None:
                    kwargs[key] = value
            callback = shield_cls(
                guardrail_name=guardrail.get("guardrail_name", ""),
                event_hook=litellm_params.mode,
                default_on=litellm_params.get("default_on") or False,
                **kwargs,
            )
            litellm.logging_callback_manager.add_litellm_callback(callback)
            return callback

        return _initialize

    common = ("api_base", "api_key", "model", "fail_mode")
    providers = (
        ("inference_gate_prompt_guard", LlamaPromptGuardShield, ("threshold", "timeout")),
        ("inference_gate_prompt_guard_local", PromptGuardLocalShield, ("threshold", "preload")),
        ("inference_gate_llama_guard", LlamaGuardShield, ("blocked_categories",)),
        ("inference_gate_response_guard", ResponseGuardShield, ("blocked_categories",)),
    )
    for name, shield_cls, extra_keys in providers:
        guardrail_class_registry.setdefault(name, shield_cls)
        guardrail_initializer_registry.setdefault(
            name, _make_initializer(shield_cls, common + extra_keys)
        )
    logger.debug("InferenceGate shields registered with the LiteLLM UI")
    return True


UI_REGISTERED = register_with_litellm_ui()

llama_prompt_guard_instance = LlamaPromptGuardShield()
prompt_guard_local_instance = PromptGuardLocalShield()
llama_shield_instance = LlamaGuardShield()
response_guard_instance = ResponseGuardShield()
