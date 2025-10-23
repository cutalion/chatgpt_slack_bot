import pytest
import os
import sys
import types
from types import SimpleNamespace

os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_APP_TOKEN", "xapp-test")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

if "slack_bolt" not in sys.modules:
    slack_bolt_module = types.ModuleType("slack_bolt")
    adapter_module = types.ModuleType("slack_bolt.adapter")
    socket_mode_module = types.ModuleType("slack_bolt.adapter.socket_mode")
    async_handler_module = types.ModuleType("slack_bolt.adapter.socket_mode.async_handler")

    class DummyAsyncSocketModeHandler:
        def __init__(self, *args, **kwargs):
            pass

    async_handler_module.AsyncSocketModeHandler = DummyAsyncSocketModeHandler

    async_app_module = types.ModuleType("slack_bolt.async_app")

    class DummyAsyncApp:
        def __init__(self, *args, **kwargs):
            pass

        def event(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator

    async_app_module.AsyncApp = DummyAsyncApp

    sys.modules["slack_bolt"] = slack_bolt_module
    sys.modules["slack_bolt.adapter"] = adapter_module
    sys.modules["slack_bolt.adapter.socket_mode"] = socket_mode_module
    sys.modules["slack_bolt.adapter.socket_mode.async_handler"] = async_handler_module
    sys.modules["slack_bolt.async_app"] = async_app_module

if "slack_sdk" not in sys.modules:
    slack_sdk_module = types.ModuleType("slack_sdk")
    web_module = types.ModuleType("slack_sdk.web")
    async_client_module = types.ModuleType("slack_sdk.web.async_client")

    class DummyAsyncWebClient:
        def __init__(self, *args, **kwargs):
            pass

        async def users_info(self, *args, **kwargs):
            return {}

        async def auth_test(self, *args, **kwargs):
            return {}

        async def conversations_history(self, *args, **kwargs):
            return {}

        async def conversations_replies(self, *args, **kwargs):
            return {}

    async_client_module.AsyncWebClient = DummyAsyncWebClient
    web_module.async_client = async_client_module
    slack_sdk_module.web = web_module

    sys.modules["slack_sdk"] = slack_sdk_module
    sys.modules["slack_sdk.web"] = web_module
    sys.modules["slack_sdk.web.async_client"] = async_client_module

def _load_agent():
    from bot.llm_openai_direct import OpenAIDirectAgent  # noqa: WPS433
    return OpenAIDirectAgent()

def test_extract_tool_calls_from_output_function_call():
    agent = _load_agent()
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

    calls = agent._extract_tool_calls(resp)

    assert len(calls) == 1
    assert calls[0]["name"] == "get_user_info"
    assert calls[0]["arguments"] == '{"user_id":"U123"}'
    assert calls[0]["id"] == 'fc_123'
    assert calls[0]["call_id"] == 'call_123'

def test_extract_tool_calls_from_required_action_function_block():
    agent = _load_agent()
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

    calls = agent._extract_tool_calls(resp)

    assert len(calls) == 1
    assert calls[0]["name"] == "get_user_info"
    assert calls[0]["arguments"] == '{"user_id":"U456"}'
    assert calls[0]["id"] == 'call_abc'
    assert calls[0]["call_id"] == 'call_abc'



@pytest.mark.asyncio
async def test_run_slack_tools_submits_function_outputs(monkeypatch):
    agent = _load_agent()

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

    monkeypatch.setattr(agent.aclient.responses, "create", fake_create)

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
    _, handled, pending = await agent._run_slack_tools(
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


@pytest.mark.asyncio
async def test_run_slack_tools_enforces_limit(monkeypatch):
    agent = _load_agent()

    class StubRunner:
        max_calls = 0

        def can_handle(self, name):
            return name == "read_channel_history"

        async def execute(self, calls):
            raise AssertionError("execute should not be called when limit is zero")

    captured_calls = []

    async def fake_create(**kwargs):
        captured_calls.append(kwargs)
        return SimpleNamespace(id="resp_after_limit", output=[])

    monkeypatch.setattr(agent.aclient.responses, "create", fake_create)

    resp = SimpleNamespace(
        id="resp_initial",
        output=[
            {
                "type": "function_call",
                "name": "read_channel_history",
                "arguments": '{"channel_id":"C123"}',
                "id": "call_hist",
            }
        ],
    )

    runner = StubRunner()
    _, handled, pending = await agent._run_slack_tools(
        resp,
        runner,
        instructions="sys",
        max_output_tokens=256,
        tool_definitions=[],
    )

    assert handled is True
    assert pending == []
    assert len(captured_calls) == 2
    first_request, second_request = captured_calls

    assert first_request["previous_response_id"] == "resp_initial"
    assert first_request["input"][0]["type"] == "function_call_output"
    assert first_request["input"][0]["call_id"] == "call_hist"
    assert '{"error": "slack_tool_limit_reached"}' in first_request["input"][0]["output"]

    assert second_request["tool_choice"] == "none"
    assert second_request["instructions"].startswith("sys\n\nSlack tool call limit was reached")
    assert second_request["input"][0]["role"] == "user"
    assert "limit reached" in second_request["input"][0]["content"][0]["text"]
