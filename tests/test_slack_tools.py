import json
import os
import sys
import types

import pytest

os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")

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

    async_client_module.AsyncWebClient = DummyAsyncWebClient
    web_module.async_client = async_client_module
    slack_sdk_module.web = web_module

    sys.modules["slack_sdk"] = slack_sdk_module
    sys.modules["slack_sdk.web"] = web_module
    sys.modules["slack_sdk.web.async_client"] = async_client_module

from slack_tools import SlackToolRunner


@pytest.mark.asyncio
async def test_get_user_info_returns_profile(monkeypatch):
    async def fake_get_user_profile(user_id: str):
        assert user_id == "U123456"
        return {
            "user_id": "U123456",
            "display_name": "Test User",
            "real_name": "Test User",
            "tz": "America/Los_Angeles",
            "is_bot": False,
        }

    monkeypatch.setattr("slack_tools.get_user_profile", fake_get_user_profile)

    runner = SlackToolRunner(max_calls=1)
    call = {"id": "call_1", "name": "get_user_info", "arguments": {"user_id": "U123456"}}

    outputs = await runner.execute([call])
    assert len(outputs) == 1
    assert outputs[0]["tool_call_id"] == "call_1"

    payload = json.loads(outputs[0]["output"])
    assert payload["display_name"] == "Test User"
    assert payload["tz"] == "America/Los_Angeles"


@pytest.mark.asyncio
async def test_get_user_info_accepts_string_arguments(monkeypatch):
    async def fake_get_user_profile(user_id: str):
        return {"user_id": user_id, "display_name": "Another"}

    monkeypatch.setattr("slack_tools.get_user_profile", fake_get_user_profile)

    runner = SlackToolRunner(max_calls=1)
    call = {"id": "call_2", "name": "get_user_info", "arguments": "{\"user_id\": \"U999\"}"}
    outputs = await runner.execute([call])

    payload = json.loads(outputs[0]["output"])
    assert payload["user_id"] == "U999"
    assert payload["display_name"] == "Another"


@pytest.mark.asyncio
async def test_unknown_tool_returns_error():
    runner = SlackToolRunner(max_calls=1)
    call = {"id": "call_3", "name": "not_a_tool", "arguments": {}}

    outputs = await runner.execute([call])
    payload = json.loads(outputs[0]["output"])
    assert payload["error"].startswith("Unsupported tool")



@pytest.mark.asyncio
async def test_execute_prefers_call_id(monkeypatch):
    async def fake_get_user_profile(user_id: str):
        return {"user_id": user_id, "display_name": "Name"}

    monkeypatch.setattr("slack_tools.get_user_profile", fake_get_user_profile)

    runner = SlackToolRunner(max_calls=1)
    call = {"id": "fc_1", "call_id": "call_real", "name": "get_user_info", "arguments": {"user_id": "U1"}}
    outputs = await runner.execute([call])

    assert outputs[0]["tool_call_id"] == "call_real"


def test_tool_definition_exposes_user_id_parameter():
    runner = SlackToolRunner()
    definitions = runner.tool_definitions
    names = {definition["name"] for definition in definitions}
    assert "get_user_info" in names
    assert "read_channel_history" in names

    user_info_definition = next(defn for defn in definitions if defn["name"] == "get_user_info")
    params = user_info_definition["parameters"]

    assert params["type"] == "object"
    assert params["required"] == ["user_id"]
    assert "user_id" in params["properties"]


@pytest.mark.asyncio
async def test_read_channel_history_uses_helper(monkeypatch):
    async def fake_fetch_channel_history(channel_id, **kwargs):
        assert channel_id == "C123"
        assert kwargs["oldest"] == "2024-05-01"
        assert kwargs["limit"] == 30
        assert kwargs["max_thread_messages"] == 10
        return {"channel_id": channel_id, "messages": [{"ts": "1", "text": "hello"}]}

    monkeypatch.setattr("slack_tools.fetch_channel_history", fake_fetch_channel_history)

    runner = SlackToolRunner(max_calls=1)
    call = {
        "id": "call_history",
        "name": "read_channel_history",
        "arguments": {
            "channel_id": "C123",
            "oldest": "2024-05-01",
            "max_messages": 30,
            "max_thread_messages": 10,
        },
    }

    outputs = await runner.execute([call])
    payload = json.loads(outputs[0]["output"])

    assert payload["channel_id"] == "C123"
    assert payload["messages"][0]["text"] == "hello"
