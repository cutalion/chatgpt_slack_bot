import pytest
import os
from types import SimpleNamespace

os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_APP_TOKEN", "xapp-test")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

def _load_module():
    from bot import llm  # noqa: WPS433
    return llm

def test_extract_tool_calls_from_output_function_call():
    llm = _load_module()
    resp = {
        "output": [
            {
                "type": "function_call",
                "name": "get_user_info",
                "arguments": '{"user_id":"U123"}',
                "id": "fc_123",
                "call_id": "call_123",
            }
        ]
    }

    calls = llm._extract_tool_calls(resp)

    assert len(calls) == 1
    assert calls[0]["name"] == "get_user_info"
    assert calls[0]["arguments"] == '{"user_id":"U123"}'
    assert calls[0]["id"] == 'fc_123'
    assert calls[0]["call_id"] == 'call_123'

def test_extract_tool_calls_from_required_action_function_block():
    llm = _load_module()
    resp = SimpleNamespace(
        required_action={
            "submit_tool_outputs": {
                "tool_calls": [
                    {
                        "id": "call_abc",
                        "type": "function",
                        "function": {
                            "name": "get_user_info",
                            "arguments": '{"user_id":"U456"}',
                        },
                    }
                ]
            }
        }
    )

    calls = llm._extract_tool_calls(resp)

    assert len(calls) == 1
    assert calls[0]["name"] == "get_user_info"
    assert calls[0]["arguments"] == '{"user_id":"U456"}'
    assert calls[0]["id"] == 'call_abc'
    assert calls[0]["call_id"] == 'call_abc'



@pytest.mark.asyncio
async def test_run_slack_tools_submits_function_outputs(monkeypatch):
    llm = _load_module()

    class StubRunner:
        max_calls = 1

        def can_handle(self, name):
            return name == "get_user_info"

        async def execute(self, calls):
            assert calls[0]["name"] == "get_user_info"
            assert calls[0]["call_id"] == 'call_123'
            return [
                {
                    "tool_call_id": calls[0]["call_id"],
                    "output": '{"display_name": "Test"}',
                }
            ]

    captured = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id="resp_next", output=[])

    monkeypatch.setattr(llm.aclient.responses, "create", fake_create)

    resp = SimpleNamespace(
        id="resp_initial",
        output=[
            {
                "type": "function_call",
                "name": "get_user_info",
                "arguments": '{"user_id":"U1"}',
                "id": "call_123",
            }
        ],
    )

    runner = StubRunner()
    _, handled, pending = await llm._run_slack_tools(
        resp,
        runner,
        instructions="sys",
        max_output_tokens=123,
        tool_definitions=[{"type": "function", "function": {"name": "get_user_info"}}],
    )

    assert handled is True
    assert pending == []
    assert captured["previous_response_id"] == "resp_initial"
    assert captured["input"] == [
        {
            "type": "function_call_output",
            "call_id": "call_123",
            "output": '{"display_name": "Test"}',
        }
    ]
    assert captured["instructions"] == "sys"
    assert captured["max_output_tokens"] == 123
