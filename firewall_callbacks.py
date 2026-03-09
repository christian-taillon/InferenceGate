import litellm
from litellm.integrations.custom_guardrail import CustomGuardrail, log_guardrail_information
from litellm.exceptions import BadRequestError
import os
import asyncio
from typing import Any, Dict, List, Optional, Union, Literal

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
    "S14": "Code Interpreter Abuse"
}

class LlamaGuardShield(CustomGuardrail):
    """
    Enterprise Llama Guard 3 Shield.
    Provides granular safety assessment using the Llama Guard 3 taxonomy.
    Supports both sequential (pre_call) and parallel (during_call) execution.
    """
    def __init__(self, **kwargs):
        # Allow overriding the model for local hosting (e.g., ollama/llama-guard3:1b)
        self.guard_model = os.getenv("LLAMA_GUARD_MODEL", "openai/llama-guard3:1b")
        super().__init__(**kwargs)
        print(f"DEBUG: LlamaGuardShield initialized with model: {self.guard_model}")

    async def _run_llama_guard(self, user_content: str, model_name: str) -> None:
        """
        Internal helper to call Llama Guard and raise error if unsafe.
        Maps raw category codes (S1-S14) to human-readable reasons.
        """
        if not user_content or not user_content.strip():
            return

        print(f"DEBUG: LlamaGuard checking prompt: {user_content[:50]}...")
        
        try:
            api_base = os.getenv("LITELLM_API_BASE", "https://api.your-provider.com")
            api_key = os.getenv("LITELLM_API_KEY")
            
            # Request Llama Guard 3 verdict
            response = await litellm.acompletion(
                model=self.guard_model,
                messages=[{"role": "user", "content": user_content}],
                api_base=api_base,
                api_key=api_key,
                temperature=0,
                max_tokens=20
            )
            
            raw_content = response.choices[0].message.content.strip()
            print(f"DEBUG: LlamaGuard Raw Output: {raw_content}")
            
            # Standard Llama Guard output:
            # line 1: safe | unsafe
            # line 2: S1,S2 (if unsafe)
            lines = raw_content.split('\n')
            verdict = lines[0].strip().lower()
            
            if "unsafe" in verdict:
                categories = []
                if len(lines) > 1:
                    codes = lines[1].split(',')
                    for code in codes:
                        code = code.strip()
                        category_name = LLAMA_GUARD_TAXONOMY.get(code, "Policy Violation")
                        categories.append(f"{code}: {category_name}")
                
                reason_str = ", ".join(categories) if categories else "General Safety Violation"
                print(f"DEBUG: BLOCKING via LlamaGuard. Categories: {reason_str}")
                
                raise BadRequestError(
                    message=f"🛡️ Blocked by LlamaGuard (Probabilistic Shield). Categories: {reason_str}",
                    model=model_name,
                    llm_provider="llama-guard"
                )
        except BadRequestError as e:
            raise e
        except Exception as e:
            # Fail-open for infrastructure issues by default, but log the error
            print(f"LlamaGuard execution error (Failing Open): {e}")

    @log_guardrail_information
    async def async_moderation_hook(
        self,
        data: dict,
        user_api_key_dict: Any,
        call_type: Any = None
    ) -> dict:
        """
        Parallel Hook: Runs alongside the main LLM call.
        Triggered when mode: "during_call" is set in config.yaml.
        """
        messages = data.get("messages", [])
        user_content = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_content = m.get("content", "")
                break
        
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
        """
        Sequential Hook: Runs before the main LLM call.
        Triggered when mode: "pre_call" is set in config.yaml.
        """
        if input_type != "request":
            return inputs

        try:
            texts = inputs.get("texts", [])
        except AttributeError:
            texts = getattr(inputs, "texts", [])
            
        user_content = " ".join(texts)
        await self._run_llama_guard(user_content, request_data.get("model", "unknown"))
        return inputs

# Export instance
llama_shield_instance = LlamaGuardShield()
