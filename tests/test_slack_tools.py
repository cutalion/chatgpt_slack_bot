import json
import logging
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
async def test_read_channel_history_uses_helper(monkeypatch, caplog):
    async def fake_fetch_channel_history(channel_id, **kwargs):
        assert channel_id == "C123"
        assert kwargs["oldest"] == "2024-05-01"
        assert kwargs["limit"] == 30
        assert kwargs["max_thread_messages"] == 10
        assert kwargs["cursor"] == "cursor_123"
        return {
            "channel_id": channel_id,
            "messages": [{"ts": "1", "text": "hello"}],
            "truncated": True,
            "next_cursor": "cursor_124",
            "requested": {
                "oldest": "2024-05-01",
                "latest": None,
                "limit": 30,
                "thread_limit": 10,
                "cursor": "cursor_123",
            },
        }

    monkeypatch.setattr("slack_tools.fetch_channel_history", fake_fetch_channel_history)

    runner = SlackToolRunner(max_calls=1)
    caplog.set_level(logging.INFO)
    call = {
        "id": "call_history",
        "name": "read_channel_history",
        "arguments": {
            "channel_id": "C123",
            "oldest": "2024-05-01",
            "max_messages": 30,
            "max_thread_messages": 10,
            "cursor": "cursor_123",
        },
    }

    outputs = await runner.execute([call])
    payload = json.loads(outputs[0]["output"])

    assert payload["channel_id"] == "C123"
    assert payload["messages"][0]["text"] == "hello"
    assert payload["next_cursor"] == "cursor_124"

    log_messages = [record.getMessage() for record in caplog.records if "Slack tool call" in record.getMessage()]
    assert any("'tool': 'read_channel_history'" in message for message in log_messages)
    assert any("'messages': 1" in message for message in log_messages)


@pytest.mark.asyncio
async def test_read_channel_history_defaults_to_runner_channel(monkeypatch):
    recorded = {}

    async def fake_fetch_channel_history(channel_id, **kwargs):
        recorded['channel_id'] = channel_id
        return {"channel_id": channel_id, "messages": []}

    monkeypatch.setattr("slack_tools.fetch_channel_history", fake_fetch_channel_history)

    runner = SlackToolRunner(max_calls=1, default_channel_id="C555")
    call = {"id": "call_history_default", "name": "read_channel_history", "arguments": {}}

    outputs = await runner.execute([call])
    payload = json.loads(outputs[0]["output"])

    assert recorded['channel_id'] == "C555"
    assert payload["channel_id"] == "C555"
    assert payload.get("messages") == []


@pytest.mark.asyncio
async def test_read_channel_history_without_channel_errors():
    runner = SlackToolRunner(max_calls=1)
    call = {"id": "call_history_missing", "name": "read_channel_history", "arguments": {}}

    outputs = await runner.execute([call])
    payload = json.loads(outputs[0]["output"])

    assert payload["error"] == "channel_id is required"


def test_tool_definition_includes_channel_descriptor_note():
    runner = SlackToolRunner(channel_descriptor="C999 (public channel)")
    definitions = runner.tool_definitions
    history_def = next(defn for defn in definitions if defn["name"] == "read_channel_history")
    channel_prop = history_def["parameters"]["properties"]["channel_id"]
    assert "Current channel: C999 (public channel)." in channel_prop["description"]


@pytest.mark.asyncio
async def test_read_channel_history_fallbacks_to_latest_when_empty(monkeypatch):
    calls = []

    async def fake_fetch_channel_history(channel_id, **kwargs):
        calls.append(dict(kwargs))
        if kwargs.get("oldest"):
            return {
                "channel_id": channel_id,
                "messages": [],
                "requested": {
                    "oldest": kwargs.get("oldest"),
                    "latest": kwargs.get("latest"),
                    "limit": kwargs.get("limit"),
                    "thread_limit": kwargs.get("max_thread_messages"),
                },
            }
        return {
            "channel_id": channel_id,
            "messages": [{"ts": "2", "text": "fallback"}],
            "requested": {
                "oldest": None,
                "latest": None,
                "limit": kwargs.get("limit"),
                "thread_limit": kwargs.get("max_thread_messages"),
            },
        }

    monkeypatch.setattr("slack_tools.fetch_channel_history", fake_fetch_channel_history)

    runner = SlackToolRunner(max_calls=1, default_channel_id="C888")
    call = {
        "id": "call_history_fallback",
        "name": "read_channel_history",
        "arguments": {"oldest": "2020-01-01"},
    }

    outputs = await runner.execute([call])
    payload = json.loads(outputs[0]["output"])

    assert payload["fallback_applied"] is True
    assert payload["fallback_reason"] == "no_messages_in_range"
    assert payload["messages"][0]["text"] == "fallback"
    assert payload["requested"]["fallback_from"]["oldest"] == "2020-01-01"
    assert len(calls) == 2
    assert calls[0]["oldest"] == "2020-01-01"
    assert calls[1].get("oldest") is None


def test_can_handle_with_none():
    """Test can_handle returns False for None tool_name."""
    runner = SlackToolRunner()
    assert runner.can_handle(None) is False


def test_can_handle_with_empty_string():
    """Test can_handle returns False for empty string tool_name."""
    runner = SlackToolRunner()
    assert runner.can_handle("") is False


def test_can_handle_with_unknown_tool():
    """Test can_handle returns False for unknown tool name."""
    runner = SlackToolRunner()
    assert runner.can_handle("unknown_tool") is False


def test_can_handle_with_valid_tool():
    """Test can_handle returns True for valid tool names."""
    runner = SlackToolRunner()
    assert runner.can_handle("get_user_info") is True
    assert runner.can_handle("read_channel_history") is True


@pytest.mark.asyncio
async def test_get_user_info_missing_user_id():
    """Test _handle_get_user_info returns error when user_id is missing."""
    runner = SlackToolRunner()
    result = await runner._handle_get_user_info({})
    assert result["error"] == "user_id is required"


@pytest.mark.asyncio
async def test_get_user_info_empty_user_id():
    """Test _handle_get_user_info returns error when user_id is empty string."""
    runner = SlackToolRunner()
    result = await runner._handle_get_user_info({"user_id": ""})
    assert result["error"] == "user_id is required"


@pytest.mark.asyncio
async def test_get_user_info_whitespace_user_id():
    """Test _handle_get_user_info returns error when user_id is only whitespace."""
    runner = SlackToolRunner()
    result = await runner._handle_get_user_info({"user_id": "   "})
    assert result["error"] == "user_id is required"


@pytest.mark.asyncio
async def test_get_user_info_non_string_user_id():
    """Test _handle_get_user_info returns error when user_id is not a string."""
    runner = SlackToolRunner()
    result = await runner._handle_get_user_info({"user_id": 123})
    assert result["error"] == "user_id is required"


@pytest.mark.asyncio
async def test_read_channel_history_fallback_missing_requested(monkeypatch):
    """Test fallback when result['requested'] is missing."""
    calls = []

    async def fake_fetch_channel_history(channel_id, **kwargs):
        calls.append(dict(kwargs))
        if kwargs.get("oldest"):
            return {
                "channel_id": channel_id,
                "messages": [],
                # Missing "requested" key
            }
        return {
            "channel_id": channel_id,
            "messages": [{"ts": "2", "text": "fallback"}],
            "requested": {
                "oldest": None,
                "latest": None,
                "limit": kwargs.get("limit"),
                "thread_limit": kwargs.get("max_thread_messages"),
            },
        }

    monkeypatch.setattr("slack_tools.fetch_channel_history", fake_fetch_channel_history)

    runner = SlackToolRunner(max_calls=1, default_channel_id="C888")
    call = {
        "id": "call_fallback_missing",
        "name": "read_channel_history",
        "arguments": {"oldest": "2020-01-01"},
    }

    outputs = await runner.execute([call])
    payload = json.loads(outputs[0]["output"])

    assert payload["fallback_applied"] is True
    assert payload["fallback_reason"] == "no_messages_in_range"
    assert payload["requested"]["fallback_from"]["oldest"] == "2020-01-01"


@pytest.mark.asyncio
async def test_read_channel_history_fallback_non_dict_requested(monkeypatch):
    """Test fallback when result['requested'] is not a dict."""
    calls = []

    async def fake_fetch_channel_history(channel_id, **kwargs):
        calls.append(dict(kwargs))
        if kwargs.get("oldest"):
            return {
                "channel_id": channel_id,
                "messages": [],
                "requested": "not_a_dict",  # Not a dict
            }
        return {
            "channel_id": channel_id,
            "messages": [{"ts": "2", "text": "fallback"}],
            "requested": {
                "oldest": None,
                "latest": None,
                "limit": kwargs.get("limit"),
                "thread_limit": kwargs.get("max_thread_messages"),
            },
        }

    monkeypatch.setattr("slack_tools.fetch_channel_history", fake_fetch_channel_history)

    runner = SlackToolRunner(max_calls=1, default_channel_id="C888")
    call = {
        "id": "call_fallback_non_dict",
        "name": "read_channel_history",
        "arguments": {"oldest": "2020-01-01"},
    }

    outputs = await runner.execute([call])
    payload = json.loads(outputs[0]["output"])

    assert payload["fallback_applied"] is True
    assert payload["fallback_reason"] == "no_messages_in_range"
    assert payload["requested"]["fallback_from"]["oldest"] == "2020-01-01"


@pytest.mark.asyncio
async def test_read_channel_history_fallback_non_dict_fallback_requested(monkeypatch):
    """Test fallback when fallback_result['requested'] is not a dict."""
    calls = []

    async def fake_fetch_channel_history(channel_id, **kwargs):
        calls.append(dict(kwargs))
        if kwargs.get("oldest"):
            return {
                "channel_id": channel_id,
                "messages": [],
                "requested": {
                    "oldest": kwargs.get("oldest"),
                    "latest": kwargs.get("latest"),
                    "limit": kwargs.get("limit"),
                    "thread_limit": kwargs.get("max_thread_messages"),
                },
            }
        return {
            "channel_id": channel_id,
            "messages": [{"ts": "2", "text": "fallback"}],
            "requested": "not_a_dict",  # Not a dict
        }

    monkeypatch.setattr("slack_tools.fetch_channel_history", fake_fetch_channel_history)

    runner = SlackToolRunner(max_calls=1, default_channel_id="C888")
    call = {
        "id": "call_fallback_non_dict_fallback",
        "name": "read_channel_history",
        "arguments": {"oldest": "2020-01-01"},
    }

    outputs = await runner.execute([call])
    payload = json.loads(outputs[0]["output"])

    assert payload["fallback_applied"] is True
    assert payload["fallback_reason"] == "no_messages_in_range"
    assert payload["requested"]["fallback_from"]["oldest"] == "2020-01-01"


def test_summarise_arguments_with_non_dict():
    """Test _summarise_arguments with non-dict arguments."""
    result = SlackToolRunner._summarise_arguments("get_user_info", "not_a_dict")
    assert result == {}


def test_summarise_arguments_with_unknown_tool():
    """Test _summarise_arguments with unknown tool name."""
    args = {"user_id": "U123", "_private": "hidden", "public": "visible"}
    result = SlackToolRunner._summarise_arguments("unknown_tool", args)
    # Should filter out keys starting with "_" but include others
    assert result == {"user_id": "U123", "public": "visible"}


def test_summarise_result_with_non_dict_payload():
    """Test _summarise_result with non-dict payload."""
    result = SlackToolRunner._summarise_result("get_user_info", "not_a_dict")
    assert result == {}


def test_summarise_result_with_unknown_tool():
    """Test _summarise_result with unknown tool name and dict payload without error."""
    payload = {"some_key": "some_value"}
    result = SlackToolRunner._summarise_result("unknown_tool", payload)
    assert result == {}


def test_summarise_result_with_unknown_tool_and_error():
    """Test _summarise_result with unknown tool name and dict payload with error."""
    payload = {"error": "some_error", "other": "data"}
    result = SlackToolRunner._summarise_result("unknown_tool", payload)
    assert result == {"error": "some_error"}


def test_parse_arguments_with_invalid_json():
    """Test _parse_arguments with invalid JSON string."""
    result = SlackToolRunner._parse_arguments('{"invalid": json}')
    assert result == {}


def test_parse_arguments_with_empty_string():
    """Test _parse_arguments with empty string."""
    result = SlackToolRunner._parse_arguments("")
    assert result == {}


def test_parse_arguments_with_whitespace_string():
    """Test _parse_arguments with whitespace-only string."""
    result = SlackToolRunner._parse_arguments("   ")
    assert result == {}


def test_serialise_payload_with_string():
    """Test _serialise_payload with string payload."""
    result = SlackToolRunner._serialise_payload("already_a_string")
    assert result == "already_a_string"


def test_serialise_payload_with_non_serializable():
    """Test _serialise_payload with non-serializable payload."""
    class NonSerializable:
        def __init__(self):
            self.circular = self  # Create circular reference
    
    result = SlackToolRunner._serialise_payload(NonSerializable())
    assert result == '{"error": "non_serialisable_payload"}'


# ============================================================================
# Private Channel Access Control Tests
# ============================================================================

@pytest.mark.asyncio
async def test_private_channel_access_denied_for_non_member(monkeypatch):
    """Test that non-members cannot access private channel history."""
    async def fake_is_private_channel(channel_id):
        return channel_id == "C_PRIVATE"
    
    async def fake_is_user_member(channel_id, user_id, *, bypass_cache=False):
        # User U123 is NOT a member of C_PRIVATE
        return False
    
    monkeypatch.setattr("slack_tools.is_private_channel", fake_is_private_channel)
    monkeypatch.setattr("slack_tools.is_user_member_of_channel", fake_is_user_member)
    
    runner = SlackToolRunner(max_calls=1, requesting_user_id="U123")
    call = {
        "id": "call_access_denied",
        "name": "read_channel_history",
        "arguments": {"channel_id": "C_PRIVATE"},
    }
    
    outputs = await runner.execute([call])
    payload = json.loads(outputs[0]["output"])
    
    assert payload["error"] == "access_denied"
    assert "don't have access" in payload["message"]
    assert payload["channel_id"] == "C_PRIVATE"


@pytest.mark.asyncio
async def test_private_channel_access_allowed_for_member(monkeypatch):
    """Test that members can access private channel history."""
    async def fake_is_private_channel(channel_id):
        return channel_id == "C_PRIVATE"
    
    async def fake_is_user_member(channel_id, user_id, *, bypass_cache=False):
        # User U123 IS a member of C_PRIVATE
        return True
    
    async def fake_fetch_channel_history(channel_id, **kwargs):
        return {"channel_id": channel_id, "messages": [{"ts": "1", "text": "hello"}]}
    
    monkeypatch.setattr("slack_tools.is_private_channel", fake_is_private_channel)
    monkeypatch.setattr("slack_tools.is_user_member_of_channel", fake_is_user_member)
    monkeypatch.setattr("slack_tools.fetch_channel_history", fake_fetch_channel_history)
    
    runner = SlackToolRunner(max_calls=1, requesting_user_id="U123")
    call = {
        "id": "call_access_allowed",
        "name": "read_channel_history",
        "arguments": {"channel_id": "C_PRIVATE"},
    }
    
    outputs = await runner.execute([call])
    payload = json.loads(outputs[0]["output"])
    
    assert "error" not in payload
    assert payload["channel_id"] == "C_PRIVATE"
    assert len(payload["messages"]) == 1


@pytest.mark.asyncio
async def test_public_channel_always_allowed(monkeypatch):
    """Test that public channels bypass membership check."""
    async def fake_is_private_channel(channel_id):
        return False  # Public channel
    
    async def fake_fetch_channel_history(channel_id, **kwargs):
        return {"channel_id": channel_id, "messages": []}
    
    monkeypatch.setattr("slack_tools.is_private_channel", fake_is_private_channel)
    monkeypatch.setattr("slack_tools.fetch_channel_history", fake_fetch_channel_history)
    
    # Even without membership check mocked, this should work
    runner = SlackToolRunner(max_calls=1, requesting_user_id="U123")
    call = {
        "id": "call_public",
        "name": "read_channel_history",
        "arguments": {"channel_id": "C_PUBLIC"},
    }
    
    outputs = await runner.execute([call])
    payload = json.loads(outputs[0]["output"])
    
    assert "error" not in payload
    assert payload["channel_id"] == "C_PUBLIC"


@pytest.mark.asyncio
async def test_access_check_without_requesting_user(monkeypatch):
    """Test that access check is skipped when no requesting_user_id is set."""
    async def fake_fetch_channel_history(channel_id, **kwargs):
        return {"channel_id": channel_id, "messages": []}
    
    monkeypatch.setattr("slack_tools.fetch_channel_history", fake_fetch_channel_history)
    
    # No requesting_user_id set - should skip access control
    runner = SlackToolRunner(max_calls=1)  # No requesting_user_id
    call = {
        "id": "call_no_user",
        "name": "read_channel_history",
        "arguments": {"channel_id": "C_ANY"},
    }
    
    outputs = await runner.execute([call])
    payload = json.loads(outputs[0]["output"])
    
    assert "error" not in payload
    assert payload["channel_id"] == "C_ANY"


@pytest.mark.asyncio
async def test_refresh_channel_access_invalidates_cache(monkeypatch):
    """Test that refresh_channel_access invalidates cache and re-checks."""
    invalidate_calls = []
    
    def fake_invalidate_cache(user_id):
        invalidate_calls.append(user_id)
    
    async def fake_is_user_member(channel_id, user_id, *, bypass_cache=False):
        # Return True after cache is bypassed
        return bypass_cache
    
    monkeypatch.setattr("slack_tools.invalidate_user_channel_cache", fake_invalidate_cache)
    monkeypatch.setattr("slack_tools.is_user_member_of_channel", fake_is_user_member)
    
    runner = SlackToolRunner(max_calls=1, requesting_user_id="U123")
    call = {
        "id": "call_refresh",
        "name": "refresh_channel_access",
        "arguments": {"channel_id": "C_PRIVATE"},
    }
    
    outputs = await runner.execute([call])
    payload = json.loads(outputs[0]["output"])
    
    assert payload["refreshed"] is True
    assert payload["access"] is True  # bypass_cache=True returns True in our mock
    assert payload["channel_id"] == "C_PRIVATE"
    assert "U123" in invalidate_calls


@pytest.mark.asyncio
async def test_refresh_channel_access_without_user_context():
    """Test that refresh_channel_access fails gracefully without user context."""
    runner = SlackToolRunner(max_calls=1)  # No requesting_user_id
    call = {
        "id": "call_refresh_no_user",
        "name": "refresh_channel_access",
        "arguments": {"channel_id": "C_PRIVATE"},
    }
    
    outputs = await runner.execute([call])
    payload = json.loads(outputs[0]["output"])
    
    assert payload["error"] == "no_user_context"


def test_tool_definitions_includes_refresh_channel_access():
    """Test that tool_definitions includes the refresh_channel_access tool."""
    runner = SlackToolRunner()
    definitions = runner.tool_definitions
    names = {definition["name"] for definition in definitions}
    
    assert "refresh_channel_access" in names
    
    refresh_def = next(d for d in definitions if d["name"] == "refresh_channel_access")
    assert "channel_id" in refresh_def["parameters"]["properties"]
    assert refresh_def["parameters"]["required"] == ["channel_id"]

