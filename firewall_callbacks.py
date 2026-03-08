import litellm
from litellm.integrations.custom_guardrail import CustomGuardrail
from litellm.exceptions import BadRequestError
import os
import asyncio
from typing import Any, Dict, List, Optional, Union, Literal

class LlamaGuardShield(CustomGuardrail):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        print("DEBUG: LlamaGuardShield (CustomGuardrail) initialized")

    async def apply_guardrail(
        self,
        inputs: Any,
        request_data: dict,
        input_type: Literal["request", "response"],
        logging_obj: Optional[Any] = None,
    ) -> Any:
        """
        Custom guardrail to run Llama Guard 3 before any inference.
        Raise BadRequestError to block the request.
        """
        if input_type != "request":
            return inputs
        
        # Get texts from GenericGuardrailAPIInputs
        try:
            texts = inputs.get("texts", [])
        except AttributeError:
            texts = getattr(inputs, "texts", [])

        if not texts:
            return inputs
            
        user_content = " ".join(texts)
        if not user_content.strip():
            return inputs

        print(f"DEBUG: LlamaGuard checking prompt: {user_content[:50]}...")
        
        try:
            api_base = os.getenv("LITELLM_API_BASE", "https://ai.christiant.io/api")
            api_key = os.getenv("LITELLM_API_KEY")
            
            response = await litellm.acompletion(
                model="openai/llama-guard3:1b",
                messages=[{"role": "user", "content": user_content}],
                api_base=api_base,
                api_key=api_key,
                temperature=0,
                max_tokens=10
            )
            
            verdict = response.choices[0].message.content.strip().lower()
            print(f"DEBUG: LlamaGuard Result: {verdict}")
            
            if "unsafe" in verdict:
                print("DEBUG: BLOCKING via CustomGuardrail")
                raise BadRequestError(
                    message=f"🛡️ Blocked by LlamaGuard (Probabilistic Shield). Verdict: {verdict.upper()}",
                    model=request_data.get("model", "unknown"),
                    llm_provider="llama-guard"
                )
            
            return inputs # Allow
        except BadRequestError as e:
            raise e
        except Exception as e:
            print(f"LlamaGuard Guardrail Error: {e}")
            return inputs

# Export instance
llama_shield_instance = LlamaGuardShield()
