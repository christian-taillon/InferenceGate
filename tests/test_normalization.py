"""Normalization tests (P2): exact source paths, role→trust mapping,
first-class tool calls, and the legacy full-stack coverage invariants."""

import types

from inference_gate.normalization import (
    TrustLevel,
    normalize_request,
    normalize_response,
)


class TestNormalizeRequest:
    def test_string_content_with_exact_path(self):
        req = normalize_request(
            {"model": "m", "messages": [{"role": "user", "content": "hello"}]}
        )
        (seg,) = req.segments
        assert seg.text == "hello"
        assert seg.source_path == "messages[0].content"
        assert seg.role == "user"
        assert seg.trust == TrustLevel.USER

    def test_full_stack_roles_and_trust(self):
        req = normalize_request(
            {
                "messages": [
                    {"role": "system", "content": "be helpful"},
                    {"role": "developer", "content": "use JSON"},
                    {"role": "user", "content": "hi"},
                    {"role": "assistant", "content": "prior turn"},
                    {"role": "tool", "content": "external result"},
                ]
            }
        )
        trusts = [s.trust for s in req.segments]
        assert trusts == [
            TrustLevel.SYSTEM,
            TrustLevel.SYSTEM,
            TrustLevel.USER,
            TrustLevel.ASSISTANT,
            TrustLevel.EXTERNAL,
        ]

    def test_unknown_role_is_external(self):
        req = normalize_request(
            {"messages": [{"role": "narrator", "content": "x"}]}
        )
        assert req.segments[0].trust == TrustLevel.EXTERNAL

    def test_multimodal_text_and_image_url_paths(self):
        req = normalize_request(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "describe"},
                            {"type": "image_url", "image_url": {"url": "https://x/i.png"}},
                        ],
                    }
                ]
            }
        )
        paths = [s.source_path for s in req.segments]
        assert paths == [
            "messages[0].content[0].text",
            "messages[0].content[1].image_url.url",
        ]

    def test_history_tool_calls_are_first_class(self):
        req = normalize_request(
            {
                "messages": [
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "function": {
                                    "name": "http_request",
                                    "arguments": '{"url": "https://e.com"}',
                                },
                            }
                        ],
                    }
                ]
            }
        )
        (call,) = req.tool_calls
        assert call.name == "http_request"
        assert call.arguments == '{"url": "https://e.com"}'
        assert call.call_id == "call_1"
        assert call.source_path == "messages[0].tool_calls[0]"
        # not flattened into text segments
        assert req.segments == ()

    def test_malformed_input_tolerated(self):
        req = normalize_request(
            {
                "messages": [
                    "not-a-dict",
                    {"role": "user"},
                    {"role": "user", "content": ["bare-string", {"type": "text"}]},
                    {"role": "assistant", "tool_calls": [{"function": {}}, 7]},
                ]
            }
        )
        assert req.segments == ()
        assert req.tool_calls == ()
        assert req.model == "unknown"


class TestNormalizeResponse:
    def _response(self, **message_attrs):
        attrs = {"content": None, "reasoning_content": None, "tool_calls": None}
        attrs.update(message_attrs)
        message = types.SimpleNamespace(**attrs)
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=message)]
        )

    def test_content_and_reasoning_paths(self):
        resp = normalize_response(
            self._response(content="answer", reasoning_content="because")
        )
        assert [(s.source_path, s.text) for s in resp.segments] == [
            ("choices[0].message.content", "answer"),
            ("choices[0].message.reasoning_content", "because"),
        ]
        assert all(s.trust == TrustLevel.ASSISTANT for s in resp.segments)

    def test_tool_calls_extracted_with_paths(self):
        call = types.SimpleNamespace(
            id="c9",
            function=types.SimpleNamespace(
                name="execute_shell", arguments='{"command": "ls"}'
            ),
        )
        resp = normalize_response(self._response(tool_calls=[call]))
        (tool_call,) = resp.tool_calls
        assert tool_call.name == "execute_shell"
        assert tool_call.arguments == '{"command": "ls"}'
        assert tool_call.source_path == "choices[0].message.tool_calls[0]"

    def test_empty_response(self):
        resp = normalize_response(types.SimpleNamespace(choices=[]))
        assert resp.segments == () and resp.tool_calls == ()
