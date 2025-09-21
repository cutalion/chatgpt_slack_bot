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

import slack_utils


@pytest.mark.asyncio
async def test_fetch_channel_history_includes_threads(monkeypatch):
    class DummyClient:
        def __init__(self):
            self.history_calls = []
            self.reply_calls = []

        async def conversations_history(self, **kwargs):
            self.history_calls.append(kwargs)
            return {
                "ok": True,
                "messages": [
                    {
                        "ts": "1.0",
                        "user": "U1",
                        "text": "parent message",
                        "thread_ts": "1.0",
                        "reply_count": 2,
                        "reactions": [{"name": "+1", "count": 3, "users": ["U2"]}],
                        "files": [
                            {
                                "id": "F1",
                                "name": "log.txt",
                                "mimetype": "text/plain",
                                "filetype": "text",
                                "permalink": "https://files.slack.com/F1",
                            }
                        ],
                    },
                    {
                        "ts": "2.0",
                        "user": "U3",
                        "text": "second message",
                    },
                ],
                "has_more": False,
                "response_metadata": {"next_cursor": ""},
            }

        async def conversations_replies(self, **kwargs):
            self.reply_calls.append(kwargs)
            return {
                "ok": True,
                "messages": [
                    {"ts": "1.0", "thread_ts": "1.0", "user": "U1", "text": "parent message"},
                    {"ts": "1.1", "thread_ts": "1.0", "user": "U4", "text": "reply one"},
                    {"ts": "1.2", "thread_ts": "1.0", "user": "U5", "text": "reply two"},
                ],
                "has_more": False,
                "response_metadata": {"next_cursor": ""},
            }

    dummy_client = DummyClient()
    monkeypatch.setattr(slack_utils, "slack_client", dummy_client)
    monkeypatch.setattr(slack_utils.config, "SLACK_TOOL_HISTORY_TEXT_CHAR_CAP", 10)

    result = await slack_utils.fetch_channel_history(
        "CBUGS",
        oldest="2024-05-01T00:00:00Z",
        limit=5,
        max_thread_messages=1,
    )

    assert result["channel_id"] == "CBUGS"
    assert result["messages"][0]["is_thread_root"] is True
    assert result["messages"][0]["text"].endswith("…")
    assert len(result["messages"][0]["replies"]) == 1
    assert result["messages"][0]["replies_truncated"] is True
    assert result["messages"][0]["replies"][0]["text"] == "reply one"
    assert "files" in result["messages"][0]
    assert result["messages"][1]["text"].startswith("second")

    assert dummy_client.history_calls[0]["channel"] == "CBUGS"
    assert "oldest" in dummy_client.history_calls[0]
    assert dummy_client.reply_calls[0]["limit"] == 1

    requested = result["requested"]
    assert requested["oldest"]
    assert requested["limit"] == 5
    assert requested["thread_limit"] == 1
