import asyncio
import json
import os
import urllib.error
import urllib.request
from typing import Any, Literal, Optional

import litellm
from litellm.exceptions import BadRequestError
from litellm.integrations.custom_guardrail import (
    CustomGuardrail,
    log_guardrail_information,
)

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

FAIL_MODE = os.getenv("INFERENCE_GATE_FAIL_MODE", "open").lower()
BLOCKED_MESSAGE = "Request blocked by content safety shield."


def _handle_shield_error(exc: Exception, shield_name: str) -> None:
    """Handle shield execution errors based on configured fail mode."""
    if FAIL_MODE == "closed":
        raise exc
    print(f"{shield_name} execution error (Failing Open): {exc}")


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
    """Extract text content from an LLM response object."""
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


class LlamaPromptGuardShield(CustomGuardrail):
    """
    Prompt attack shield powered by Llama Prompt Guard 2.
    Blocks prompts classified as malicious jailbreak or prompt-injection attempts.
    """

    def __init__(self, **kwargs):
        self.guard_model = os.getenv(
            "LLAMA_PROMPT_GUARD_MODEL", "meta-llama/llama-prompt-guard-2-86m"
        )
        super().__init__(**kwargs)
        print(
            f"DEBUG: LlamaPromptGuardShield initialized with model: {self.guard_model}"
        )

    def _build_classify_urls(self, api_base: str) -> list[str]:
        base = api_base.rstrip("/")
        candidates = []
        if base.endswith("/v1"):
            candidates.append(f"{base[:-3]}/classify")
            candidates.append(f"{base}/classify")
        else:
            candidates.append(f"{base}/classify")
            candidates.append(f"{base}/v1/classify")

        deduped = []
        for candidate in candidates:
            if candidate not in deduped:
                deduped.append(candidate)
        return deduped

    def _is_groq_api_base(self, api_base: str | None) -> bool:
        return bool(api_base and "groq.com" in api_base)

    def _resolved_guard_model(self, api_base: str | None) -> str:
        model = self.guard_model
        if "/" in model:
            provider = model.split("/", 1)[0]
            if provider in {"openai", "groq", "ollama", "anthropic", "vertex_ai"}:
                return model

        if self._is_groq_api_base(api_base):
            return f"groq/{model}"

        return model

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
        label = result.get("label", "").strip().lower()
        if label in {"malicious", "jailbreak", "prompt_injection", "injection"}:
            return True
        if label in {"benign", "safe", "default"}:
            return False

        try:
            score = result.get("malicious_score")
            return score is not None and float(score) >= 0.5
        except (TypeError, ValueError):
            return False

    def _parse_chat_classification_text(self, text: str) -> dict[str, Any]:
        normalized = (text or "").strip()
        upper_text = normalized.upper()

        try:
            numeric_score = float(normalized)
            return {
                "label": "MALICIOUS" if numeric_score >= 0.5 else "BENIGN",
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
        self, texts: list[str], api_base: str, api_key: str | None
    ) -> list[dict[str, Any]]:
        results = []

        for text in texts:
            response = await litellm.acompletion(
                model=self._resolved_guard_model(api_base),
                messages=[
                    {
                        "role": "user",
                        "content": text,
                    }
                ],
                api_base=api_base,
                api_key=api_key,
                temperature=0,
                max_tokens=4,
            )

            choices = getattr(response, "choices", None) or []
            if not choices:
                print("DEBUG: Llama Prompt Guard returned no choices.")
                continue

            message = getattr(choices[0], "message", None)
            raw_content = (getattr(message, "content", "") or "").strip()
            print(f"DEBUG: Llama Prompt Guard Raw Output: {raw_content}")
            if not raw_content:
                continue

            results.append(self._parse_chat_classification_text(raw_content))

        return results

    def _classify_sync(self, texts: list[str]) -> list[dict[str, Any]]:
        api_base = os.getenv("LLAMA_PROMPT_GUARD_API_BASE") or os.getenv(
            "LITELLM_API_BASE"
        )
        api_key = os.getenv("LLAMA_PROMPT_GUARD_API_KEY") or os.getenv(
            "LITELLM_API_KEY"
        )

        if not api_base:
            print(
                "DEBUG: Llama Prompt Guard error - LLAMA_PROMPT_GUARD_API_BASE or LITELLM_API_BASE not set."
            )
            return []

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = json.dumps(
            {
                "model": self.guard_model,
                "input": texts,
                "truncate_prompt_tokens": PROMPT_GUARD_MAX_TOKENS,
            }
        ).encode("utf-8")

        last_error = None
        for url in self._build_classify_urls(api_base):
            request = urllib.request.Request(url, data=payload, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    body = response.read().decode("utf-8")
                parsed = self._parse_classify_response(json.loads(body))
                if parsed:
                    return parsed
                print("DEBUG: Llama Prompt Guard returned no classification data.")
                return []
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="ignore")
                if exc.code == 404:
                    last_error = RuntimeError(
                        f"Prompt Guard classify endpoint not found at {url}: {detail or exc.reason}"
                    )
                    continue
                raise RuntimeError(
                    f"Prompt Guard request failed ({exc.code}): {detail or exc.reason}"
                ) from exc
            except urllib.error.URLError as exc:
                raise RuntimeError(
                    f"Prompt Guard connection failed: {exc.reason}"
                ) from exc

        if last_error is not None:
            raise last_error
        return []

    async def _run_prompt_guard(self, user_content: str, model_name: str) -> None:
        if not user_content or not user_content.strip():
            return

        text_chunks = _chunk_text_for_prompt_guard(user_content)
        if not text_chunks:
            return

        print(f"DEBUG: Llama Prompt Guard checking {len(text_chunks)} chunk(s).")

        try:
            api_base = os.getenv("LLAMA_PROMPT_GUARD_API_BASE") or os.getenv(
                "LITELLM_API_BASE"
            )
            api_key = os.getenv("LLAMA_PROMPT_GUARD_API_KEY") or os.getenv(
                "LITELLM_API_KEY"
            )

            if api_base and self._is_groq_api_base(api_base):
                results = await self._classify_via_chat(text_chunks, api_base, api_key)
            else:
                results = await asyncio.to_thread(self._classify_sync, text_chunks)

            malicious_results = [
                result for result in results if self._is_malicious_result(result)
            ]
            if not malicious_results:
                return

            top_result = max(
                malicious_results,
                key=lambda item: float(item.get("malicious_score") or 0.0),
            )
            _ = top_result.get("label") or "MALICIOUS"

            raise BadRequestError(
                message=BLOCKED_MESSAGE,
                model=model_name,
                llm_provider="llama-prompt-guard",
            )
        except BadRequestError as exc:
            raise exc
        except Exception as exc:
            _handle_shield_error(exc, "Llama Prompt Guard")

    @log_guardrail_information
    async def async_moderation_hook(
        self, data: dict, user_api_key_dict: Any, call_type: Any = None
    ) -> dict:
        user_content = _extract_all_content(data.get("messages", []))
        await self._run_prompt_guard(user_content, data.get("model", "unknown"))
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

        try:
            texts = inputs.get("texts", [])
        except AttributeError:
            texts = getattr(inputs, "texts", [])

        user_content = " ".join(text for text in texts if isinstance(text, str))
        await self._run_prompt_guard(user_content, request_data.get("model", "unknown"))
        return inputs


class LlamaGuardShield(CustomGuardrail):
    """
    Enterprise Llama Guard 3 Shield.
    Provides granular safety assessment using the Llama Guard 3 taxonomy.
    Supports both sequential (pre_call) and parallel (during_call) execution.
    """

    def __init__(self, **kwargs):
        self.guard_model = os.getenv("LLAMA_GUARD_MODEL", "openai/llama-guard3:1b")
        super().__init__(**kwargs)
        print(f"DEBUG: LlamaGuardShield initialized with model: {self.guard_model}")

    def _resolved_guard_model(self, api_base: str | None) -> str:
        model = self.guard_model
        if "/" in model:
            provider = model.split("/", 1)[0]
            if provider in {"openai", "groq", "ollama", "anthropic", "vertex_ai"}:
                return model

        if api_base and "groq.com" in api_base:
            return f"groq/{model}"

        return model

    async def _run_llama_guard(self, user_content: str, model_name: str) -> None:
        if not user_content or not user_content.strip():
            return

        print(f"DEBUG: LlamaGuard checking prompt: {user_content[:50]}...")

        try:
            api_base = os.getenv("LLAMA_GUARD_API_BASE") or os.getenv(
                "LITELLM_API_BASE"
            )
            api_key = os.getenv("LLAMA_GUARD_API_KEY") or os.getenv("LITELLM_API_KEY")

            if not api_base:
                print(
                    "DEBUG: LlamaGuard error - LITELLM_API_BASE not set in environment."
                )
                return

            response = await litellm.acompletion(
                model=self._resolved_guard_model(api_base),
                messages=[{"role": "user", "content": user_content}],
                api_base=api_base,
                api_key=api_key,
                temperature=0,
                max_tokens=20,
            )

            choices = getattr(response, "choices", None) or []
            if not choices:
                print("DEBUG: LlamaGuard returned no choices.")
                return

            message = getattr(choices[0], "message", None)
            raw_content = (getattr(message, "content", "") or "").strip()
            if not raw_content:
                print("DEBUG: LlamaGuard returned empty content.")
                return

            print(f"DEBUG: LlamaGuard Raw Output: {raw_content}")

            lines = raw_content.split("\n")
            verdict = lines[0].strip().lower()

            if "unsafe" in verdict:
                categories = []
                if len(lines) > 1:
                    codes = lines[1].split(",")
                    for code in codes:
                        code = code.strip()
                        category_name = LLAMA_GUARD_TAXONOMY.get(
                            code, "Policy Violation"
                        )
                        categories.append(f"{code}: {category_name}")

                reason_str = (
                    ", ".join(categories) if categories else "General Safety Violation"
                )
                print(f"DEBUG: BLOCKING via LlamaGuard. Categories: {reason_str}")

                raise BadRequestError(
                    message=BLOCKED_MESSAGE,
                    model=model_name,
                    llm_provider="llama-guard",
                )
        except BadRequestError as exc:
            raise exc
        except Exception as exc:
            _handle_shield_error(exc, "LlamaGuard")

    @log_guardrail_information
    async def async_moderation_hook(
        self, data: dict, user_api_key_dict: Any, call_type: Any = None
    ) -> dict:
        user_content = _extract_all_content(data.get("messages", []))
        await self._run_llama_guard(user_content, data.get("model", "unknown"))
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

        try:
            texts = inputs.get("texts", [])
        except AttributeError:
            texts = getattr(inputs, "texts", [])

        user_content = " ".join(texts)
        await self._run_llama_guard(user_content, request_data.get("model", "unknown"))
        return inputs


llama_prompt_guard_instance = LlamaPromptGuardShield()
llama_shield_instance = LlamaGuardShield()


class PromptGuardLocalShield(CustomGuardrail):
    """Local prompt-attack shield using HuggingFace Prompt Guard models.

    Loads a DeBERTa-based text-classification model (e.g.
    meta-llama/Prompt-Guard-86M or meta-llama/Llama-Prompt-Guard-2-86M)
    directly via the transformers library. Runs entirely on-device —
    no API calls, no network dependency.

    Activated when PROMPT_GUARD_LOCAL_MODEL is set. If transformers/torch
    are not installed, the shield prints a warning and fails open.
    """

    _model_cache: dict[str, Any] = {}

    def __init__(self, **kwargs):
        self.model_id = os.getenv(
            "PROMPT_GUARD_LOCAL_MODEL", "meta-llama/Llama-Prompt-Guard-2-86M"
        )
        self.threshold = float(os.getenv("PROMPT_GUARD_LOCAL_THRESHOLD", "0.5"))
        super().__init__(**kwargs)
        print(
            f"DEBUG: PromptGuardLocalShield initialized with model: {self.model_id}"
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

            print(f"DEBUG: PromptGuardLocal loading model: {model_id}")
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

        if label in {"LABEL_0"}:
            label = "BENIGN"
        elif label in {"LABEL_1"}:
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
            if score is not None and float(score) < self.threshold:
                return False
            return True
        if label in {"benign", "safe"}:
            return False
        return False

    async def _run_local_prompt_guard(self, user_content: str, model_name: str) -> None:
        if not user_content or not user_content.strip():
            return

        text_chunks = _chunk_text_for_prompt_guard(user_content)
        if not text_chunks:
            return

        print(
            f"DEBUG: PromptGuardLocal checking {len(text_chunks)} chunk(s)."
        )

        try:
            results = await asyncio.to_thread(
                lambda: [self._classify_chunk(chunk) for chunk in text_chunks]
            )

            malicious_results = [
                result for result in results if self._is_malicious_result(result)
            ]
            if not malicious_results:
                return

            raise BadRequestError(
                message=BLOCKED_MESSAGE,
                model=model_name,
                llm_provider="prompt-guard-local",
            )
        except BadRequestError as exc:
            raise exc
        except ImportError as exc:
            _handle_shield_error(exc, "PromptGuardLocal")
        except Exception as exc:
            _handle_shield_error(exc, "PromptGuardLocal")

    @log_guardrail_information
    async def async_moderation_hook(
        self, data: dict, user_api_key_dict: Any, call_type: Any = None
    ) -> dict:
        user_content = _extract_all_content(data.get("messages", []))
        await self._run_local_prompt_guard(user_content, data.get("model", "unknown"))
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

        try:
            texts = inputs.get("texts", [])
        except AttributeError:
            texts = getattr(inputs, "texts", [])

        user_content = " ".join(text for text in texts if isinstance(text, str))
        await self._run_local_prompt_guard(
            user_content, request_data.get("model", "unknown")
        )
        return inputs


prompt_guard_local_instance = PromptGuardLocalShield()


class ResponseGuardShield(CustomGuardrail):
    """Response-side shield that scans model output for unsafe content.

    Runs as a post_call guardrail to catch data exfiltration, toxic content,
    and secret echo that pre_call shields cannot detect.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        print("DEBUG: ResponseGuardShield initialized")

    async def _scan_response(self, response_content: str, model_name: str) -> None:
        if not response_content or not response_content.strip():
            return
        await self._run_llama_guard_response(response_content, model_name)

    async def _run_llama_guard_response(
        self, response_content: str, model_name: str
    ) -> None:
        print(f"DEBUG: ResponseGuard scanning output: {response_content[:50]}...")

        try:
            api_base = os.getenv("LLAMA_GUARD_API_BASE") or os.getenv(
                "LITELLM_API_BASE"
            )
            api_key = os.getenv("LLAMA_GUARD_API_KEY") or os.getenv("LITELLM_API_KEY")

            if not api_base:
                print("DEBUG: ResponseGuard error - no API base configured.")
                return

            response = await litellm.acompletion(
                model=LlamaGuardShield().guard_model,
                messages=[{"role": "user", "content": response_content}],
                api_base=api_base,
                api_key=api_key,
                temperature=0,
                max_tokens=20,
            )

            choices = getattr(response, "choices", None) or []
            if not choices:
                return

            message = getattr(choices[0], "message", None)
            raw_content = (getattr(message, "content", "") or "").strip()
            if not raw_content:
                return

            print(f"DEBUG: ResponseGuard Raw Output: {raw_content}")
            verdict = raw_content.split("\n")[0].strip().lower()

            if "unsafe" in verdict:
                print(f"DEBUG: BLOCKING via ResponseGuard. Verdict: {verdict}")
                raise BadRequestError(
                    message=BLOCKED_MESSAGE,
                    model=model_name,
                    llm_provider="response-guard",
                )
        except BadRequestError as exc:
            raise exc
        except Exception as exc:
            _handle_shield_error(exc, "ResponseGuard")

    @log_guardrail_information
    async def async_post_call_success_hook(
        self,
        data: dict,
        user_api_key_dict: Any,
        response: Any,
    ) -> Any:
        response_content = _extract_response_content(response)
        await self._scan_response(response_content, data.get("model", "unknown"))
        return response


response_guard_instance = ResponseGuardShield()
