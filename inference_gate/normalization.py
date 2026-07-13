"""Canonical records for request/response content (P2).

Detectors and transformers consume these records — never raw LiteLLM
objects. Every text segment carries its exact ``source_path`` (so
transformers can write modified values back and dehydration can target
spans) plus the ``role`` and ``TrustLevel`` of its origin (so policy can
treat user input, assistant history, and external/tool content differently).

Tool calls are first-class records, never flattened into text: a harmful
tool invocation must remain attributable to tool name and arguments.

Supersedes the semantics of ``_extract_all_content`` /
``_extract_response_content`` in firewall_callbacks.py; those remain until
P4 parity migration removes them.
"""

from __future__ import annotations

import enum
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any


class TrustLevel(enum.StrEnum):
    """Origin-based trust of a piece of content (OBJECTIVE.md stages).

    EXTERNAL marks content that crossed a trust boundary (tool results,
    retrieved documents, MCP output) — prompt-injection findings there
    quarantine the segment, never the requesting user (GUARD_MODELS.md).
    """

    SYSTEM = "system"        # system/developer-authored instructions
    USER = "user"            # direct end-user input
    ASSISTANT = "assistant"  # model-authored (prior turns or response)
    EXTERNAL = "external"    # tool/function results, retrieval, MCP


_ROLE_TRUST: dict[str, TrustLevel] = {
    "system": TrustLevel.SYSTEM,
    "developer": TrustLevel.SYSTEM,
    "user": TrustLevel.USER,
    "assistant": TrustLevel.ASSISTANT,
    "tool": TrustLevel.EXTERNAL,
    "function": TrustLevel.EXTERNAL,
}


def _trust_for_role(role: str) -> TrustLevel:
    # Unknown roles are treated as external: least trusted.
    return _ROLE_TRUST.get(role, TrustLevel.EXTERNAL)


@dataclass(frozen=True, slots=True)
class TextSegment:
    """One scannable text with its exact origin."""

    text: str
    source_path: str
    role: str
    trust: TrustLevel


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A proposed or historical tool invocation. ``arguments`` is kept as
    the raw provider string (usually JSON) — parsing/validation is a
    detector concern, and byte-exact preservation matters for spans."""

    name: str
    arguments: str
    call_id: str | None
    source_path: str


@dataclass(frozen=True, slots=True)
class CanonicalRequest:
    model: str
    segments: tuple[TextSegment, ...]
    tool_calls: tuple[ToolCall, ...]

    def texts(self) -> Iterator[TextSegment]:
        return iter(self.segments)


@dataclass(frozen=True, slots=True)
class CanonicalResponse:
    segments: tuple[TextSegment, ...]
    tool_calls: tuple[ToolCall, ...]

    def texts(self) -> Iterator[TextSegment]:
        return iter(self.segments)


def _segment(
    parts: list[TextSegment], text: Any, path: str, role: str
) -> None:
    if isinstance(text, str) and text:
        parts.append(
            TextSegment(text=text, source_path=path, role=role, trust=_trust_for_role(role))
        )


def _tool_calls_from_message(
    raw_calls: Any, base_path: str
) -> Iterator[ToolCall]:
    if not isinstance(raw_calls, list):
        return
    for k, call in enumerate(raw_calls):
        if not isinstance(call, Mapping):
            continue
        function = call.get("function")
        if not isinstance(function, Mapping):
            continue
        name = function.get("name")
        arguments = function.get("arguments")
        if not isinstance(name, str) or not name:
            continue
        yield ToolCall(
            name=name,
            arguments=arguments if isinstance(arguments, str) else "",
            call_id=call.get("id") if isinstance(call.get("id"), str) else None,
            source_path=f"{base_path}.tool_calls[{k}]",
        )


def normalize_request(data: Mapping[str, Any]) -> CanonicalRequest:
    """Build a canonical record from a LiteLLM request dict.

    Scans the full message stack (all roles, prior turns), multimodal text
    parts and image URLs, and assistant-history tool calls — the coverage
    invariants pinned by the legacy baseline.
    """
    segments: list[TextSegment] = []
    tool_calls: list[ToolCall] = []

    messages = data.get("messages")
    if isinstance(messages, list):
        for i, message in enumerate(messages):
            if not isinstance(message, Mapping):
                continue
            role = message.get("role") if isinstance(message.get("role"), str) else ""
            base = f"messages[{i}]"
            content = message.get("content")
            if isinstance(content, str):
                _segment(segments, content, f"{base}.content", role)
            elif isinstance(content, list):
                for j, item in enumerate(content):
                    if not isinstance(item, Mapping):
                        continue
                    if item.get("type") == "text":
                        _segment(
                            segments, item.get("text"), f"{base}.content[{j}].text", role
                        )
                    elif item.get("type") == "image_url":
                        url_obj = item.get("image_url")
                        if isinstance(url_obj, Mapping):
                            _segment(
                                segments,
                                url_obj.get("url"),
                                f"{base}.content[{j}].image_url.url",
                                role,
                            )
            tool_calls.extend(_tool_calls_from_message(message.get("tool_calls"), base))

    model = data.get("model")
    return CanonicalRequest(
        model=model if isinstance(model, str) else "unknown",
        segments=tuple(segments),
        tool_calls=tuple(tool_calls),
    )


def normalize_response(response: Any) -> CanonicalResponse:
    """Build a canonical record from a LiteLLM/OpenAI response object.

    Attribute-based (works for pydantic response objects and test stubs):
    message content, reasoning content, and proposed tool calls per choice.
    """
    segments: list[TextSegment] = []
    tool_calls: list[ToolCall] = []

    for i, choice in enumerate(getattr(response, "choices", None) or []):
        message = getattr(choice, "message", None)
        if message is None:
            continue
        base = f"choices[{i}].message"
        _segment(segments, getattr(message, "content", None), f"{base}.content", "assistant")
        _segment(
            segments,
            getattr(message, "reasoning_content", None),
            f"{base}.reasoning_content",
            "assistant",
        )
        for k, call in enumerate(getattr(message, "tool_calls", None) or []):
            function = getattr(call, "function", None)
            if function is None:
                continue
            name = getattr(function, "name", None)
            if not isinstance(name, str) or not name:
                continue
            arguments = getattr(function, "arguments", None)
            call_id = getattr(call, "id", None)
            tool_calls.append(
                ToolCall(
                    name=name,
                    arguments=arguments if isinstance(arguments, str) else "",
                    call_id=call_id if isinstance(call_id, str) else None,
                    source_path=f"{base}.tool_calls[{k}]",
                )
            )

    return CanonicalResponse(segments=tuple(segments), tool_calls=tuple(tool_calls))
