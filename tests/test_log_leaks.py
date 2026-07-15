"""Log-leak guard tests.

Security invariant: shield logging must never contain message or response
content — even truncated — and never exception text (which may embed request
payloads). See AGENTS.md and docs/security/reports/legacy-baseline.md.
"""

import asyncio
import logging
import types
from pathlib import Path

import pytest

from tests.test_firewall import FIREWALL_CALLBACKS

# Canary that must never appear in any captured log output.
CANARY = "sk-canary-XYZSECRET123"

LOGGER_NAME = "inference_gate.shields"


def _guard_response(content: str):
    """Minimal stand-in for a litellm completion response."""
    message = types.SimpleNamespace(content=content, reasoning_content=None)
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


@pytest.fixture
def guard_env(monkeypatch):
    monkeypatch.setenv("LITELLM_API_BASE", "https://api.openai.com/v1")
    monkeypatch.setenv("LITELLM_API_KEY", "test-key")
    monkeypatch.delenv("LLAMA_GUARD_API_BASE", raising=False)
    monkeypatch.delenv("LLAMA_GUARD_API_KEY", raising=False)


class TestNoContentInLogs:
    def test_no_print_statements_in_shield_module(self):
        source = Path(FIREWALL_CALLBACKS.__file__).read_text(encoding="utf-8")
        assert "print(" not in source, (
            "firewall_callbacks.py must use the module logger, not print()"
        )

    def test_fail_open_omits_exception_message(self, caplog, capsys, monkeypatch):
        monkeypatch.setattr(FIREWALL_CALLBACKS, "FAIL_MODE", "open")
        with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
            FIREWALL_CALLBACKS._handle_shield_error(
                RuntimeError(f"upstream said: {CANARY}"), "TestShield"
            )
        assert "TestShield" in caplog.text
        assert "RuntimeError" in caplog.text
        assert CANARY not in caplog.text
        assert CANARY not in capsys.readouterr().out

    def test_llama_guard_block_logs_no_prompt_content(
        self, caplog, monkeypatch, guard_env
    ):
        shield = FIREWALL_CALLBACKS.LlamaGuardShield()

        async def fake_acompletion(*args, **kwargs):
            return _guard_response("unsafe\nS7")

        monkeypatch.setattr(FIREWALL_CALLBACKS.litellm, "acompletion", fake_acompletion)
        with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
            with pytest.raises(FIREWALL_CALLBACKS.HTTPException) as exc_info:
                asyncio.run(shield._scan_text(f"my key is {CANARY}"))
        assert CANARY not in caplog.text
        assert CANARY not in str(exc_info.value)

    def test_llama_guard_log_drops_non_taxonomy_codes(
        self, caplog, monkeypatch, guard_env
    ):
        """Guard-model output is untrusted; only known S-codes may be logged."""
        shield = FIREWALL_CALLBACKS.LlamaGuardShield()

        async def fake_acompletion(*args, **kwargs):
            return _guard_response(f"unsafe\nS7, {CANARY}")

        monkeypatch.setattr(FIREWALL_CALLBACKS.litellm, "acompletion", fake_acompletion)
        with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
            with pytest.raises(FIREWALL_CALLBACKS.HTTPException):
                asyncio.run(shield._scan_text("hello"))
        assert "S7" in caplog.text
        assert CANARY not in caplog.text

    def test_response_guard_block_logs_no_response_content(
        self, caplog, monkeypatch, guard_env
    ):
        shield = FIREWALL_CALLBACKS.ResponseGuardShield()

        async def fake_acompletion(*args, **kwargs):
            return _guard_response("unsafe\nS2")

        monkeypatch.setattr(FIREWALL_CALLBACKS.litellm, "acompletion", fake_acompletion)
        with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
            with pytest.raises(FIREWALL_CALLBACKS.HTTPException):
                asyncio.run(
                    shield._scan_text(f"the secret is {CANARY}")
                )
        assert CANARY not in caplog.text
