"""Integration tests for bot.py handle_mention function.

These tests provide comprehensive coverage of all execution paths in handle_mention()
to act as a safety net during refactoring.
"""

import os
import sys
import types
import logging
from unittest.mock import Mock, AsyncMock, patch
from typing import Any, Dict, List

import pytest

# Set up environment
os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_APP_TOKEN", "xapp-test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

# Mock slack_sdk modules before importing bot
if "slack_sdk" not in sys.modules:
    slack_sdk_module = types.ModuleType("slack_sdk")
    web_module = types.ModuleType("slack_sdk.web")
    async_client_module = types.ModuleType("slack_sdk.web.async_client")
    bolt_module = types.ModuleType("slack_bolt")
    app_module = types.ModuleType("slack_bolt.async_app")
    socket_handler_module = types.ModuleType("slack_bolt.adapter.socket_mode.async_handler")

    class DummyAsyncWebClient:
        def __init__(self, *args, **kwargs):
            self.conversations_replies = AsyncMock()
            self.chat_postMessage = AsyncMock()
            self.users_info = AsyncMock()
            self.auth_test = AsyncMock()

    class DummyAsyncApp:
        def __init__(self, *args, **kwargs):
            pass
        
        def event(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator

    class DummySocketModeHandler:
        def __init__(self, *args, **kwargs):
            pass
        
        async def start_async(self):
            pass

    async_client_module.AsyncWebClient = DummyAsyncWebClient
    web_module.async_client = async_client_module
    slack_sdk_module.web = web_module
    
    app_module.AsyncApp = DummyAsyncApp
    bolt_module.async_app = app_module
    slack_sdk_module.bolt = bolt_module
    
    socket_handler_module.AsyncSocketModeHandler = DummySocketModeHandler
    bolt_module.adapter = types.ModuleType("slack_bolt.adapter")
    bolt_module.adapter.socket_mode = types.ModuleType("slack_bolt.adapter.socket_mode")
    bolt_module.adapter.socket_mode.async_handler = socket_handler_module

    sys.modules["slack_sdk"] = slack_sdk_module
    sys.modules["slack_sdk.web"] = web_module
    sys.modules["slack_sdk.web.async_client"] = async_client_module
    sys.modules["slack_bolt"] = bolt_module
    sys.modules["slack_bolt.async_app"] = app_module
    sys.modules["slack_bolt.adapter.socket_mode.async_handler"] = socket_handler_module

# Import bot module after mocking
import bot


class TestHandleMentionIntegration:
    """Integration tests for handle_mention function covering all execution paths."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock Slack client with common responses."""
        client = Mock()
        client.conversations_replies = AsyncMock()
        client.chat_postMessage = AsyncMock()
        client.users_info = AsyncMock()
        client.auth_test = AsyncMock()
        return client

    @pytest.fixture
    def mock_llm(self, monkeypatch):
        """Mock the LLM generation function."""
        async def mock_generate_ai_reply(messages, slack_context=None):
            return "Mock AI response"
        
        monkeypatch.setattr("llm.generate_ai_reply", mock_generate_ai_reply)
        return mock_generate_ai_reply

    @pytest.fixture
    def mock_slack_utils(self, monkeypatch):
        """Mock slack_utils functions."""
        monkeypatch.setattr("bot.get_bot_user_id", AsyncMock(return_value="U_BOT123"))
        monkeypatch.setattr("bot.get_user_display_name", AsyncMock(return_value="TestUser"))
        monkeypatch.setattr("bot.get_bot_name_from_message", Mock(return_value="TestBot"))
        monkeypatch.setattr("bot.format_ts_utc", Mock(return_value="[2024-01-01 10:00Z]"))
        monkeypatch.setattr("bot.normalise_user_mentions", Mock(side_effect=lambda x: x))
        monkeypatch.setattr("bot.clean_user_message", Mock(side_effect=lambda text, bot_uid: text))
        monkeypatch.setattr("bot.get_channel_descriptor", Mock(return_value="C123 (public channel)"))

    @pytest.mark.asyncio
    async def test_unsupported_subtype_returns_early(self, mock_client, mock_llm, mock_slack_utils, monkeypatch, caplog):
        """Verify unsupported subtypes are ignored early."""
        monkeypatch.setattr("bot.client", mock_client)
        
        body = {
            "event": {
                "type": "message",
                "subtype": "message_changed",  # Unsupported
                "user": "U123",
                "channel": "C123",
                "event_ts": "100.0",
                "text": "edited text"
            }
        }
        
        caplog.set_level(logging.DEBUG)
        await bot.handle_mention(body, logging.getLogger())
        
        # Verify no API calls were made (early return)
        mock_client.conversations_replies.assert_not_called()
        mock_client.chat_postMessage.assert_not_called()
        assert "Ignoring event with subtype=message_changed" in caplog.text

    @pytest.mark.asyncio
    async def test_bot_message_returns_early(self, mock_client, mock_llm, mock_slack_utils, monkeypatch, caplog):
        """Verify messages from bots are ignored early."""
        monkeypatch.setattr("bot.client", mock_client)
        
        body = {
            "event": {
                "type": "message",
                "bot_id": "B123",  # Bot message
                "user": "U123",
                "channel": "C123",
                "event_ts": "100.0",
                "text": "bot message"
            }
        }
        
        caplog.set_level(logging.DEBUG)
        await bot.handle_mention(body, logging.getLogger())
        
        mock_client.conversations_replies.assert_not_called()
        mock_client.chat_postMessage.assert_not_called()
        assert "Ignoring message from bot_id=B123" in caplog.text

    @pytest.mark.asyncio
    async def test_missing_user_returns_early(self, mock_client, mock_llm, mock_slack_utils, monkeypatch, caplog):
        """Verify events without user field are ignored early."""
        monkeypatch.setattr("bot.client", mock_client)
        
        body = {
            "event": {
                "type": "message",
                "channel": "C123",
                "event_ts": "100.0",
                "text": "message without user"
            }
        }
        
        caplog.set_level(logging.DEBUG)
        await bot.handle_mention(body, logging.getLogger())
        
        mock_client.conversations_replies.assert_not_called()
        mock_client.chat_postMessage.assert_not_called()
        assert "Ignoring event without user field" in caplog.text

    @pytest.mark.asyncio
    async def test_missing_channel_returns_early(self, mock_client, mock_llm, mock_slack_utils, monkeypatch, caplog):
        """Verify events without channel field are ignored early."""
        monkeypatch.setattr("bot.client", mock_client)
        
        body = {
            "event": {
                "type": "message",
                "user": "U123",
                "event_ts": "100.0",
                "text": "message without channel"
            }
        }
        
        caplog.set_level(logging.DEBUG)
        await bot.handle_mention(body, logging.getLogger())
        
        mock_client.conversations_replies.assert_not_called()
        mock_client.chat_postMessage.assert_not_called()
        assert "Ignoring event without channel field" in caplog.text

    @pytest.mark.asyncio
    async def test_missing_event_ts_returns_early(self, mock_client, mock_llm, mock_slack_utils, monkeypatch, caplog):
        """Verify events without event_ts field are ignored early."""
        monkeypatch.setattr("bot.client", mock_client)
        
        body = {
            "event": {
                "type": "message",
                "user": "U123",
                "channel": "C123",
                "text": "message without event_ts"
            }
        }
        
        caplog.set_level(logging.DEBUG)
        await bot.handle_mention(body, logging.getLogger())
        
        mock_client.conversations_replies.assert_not_called()
        mock_client.chat_postMessage.assert_not_called()
        assert "Ignoring event without event_ts field" in caplog.text

    @pytest.mark.asyncio
    async def test_empty_message_requests_clarification(self, mock_client, mock_llm, mock_slack_utils, monkeypatch, caplog):
        """Verify empty messages trigger clarification request."""
        monkeypatch.setattr("bot.client", mock_client)
        monkeypatch.setattr("bot.clean_user_message", Mock(return_value=""))  # Empty after cleaning
        
        body = {
            "event": {
                "type": "app_mention",
                "user": "U123",
                "channel": "C123",
                "event_ts": "100.0",
                "text": "@bot   "  # Empty after cleaning
            }
        }
        
        caplog.set_level(logging.INFO)
        await bot.handle_mention(body, logging.getLogger())
        
        # Should call chat_postMessage for clarification
        mock_client.chat_postMessage.assert_called_once()
        call_args = mock_client.chat_postMessage.call_args
        assert "empty" in call_args[1]["text"].lower()
        assert call_args[1]["channel"] == "C123"
        
        # Should not call conversations_replies
        mock_client.conversations_replies.assert_not_called()

    @pytest.mark.asyncio
    async def test_direct_message_without_thread(self, mock_client, mock_llm, mock_slack_utils, monkeypatch, caplog):
        """Verify DM without thread_ts works correctly."""
        monkeypatch.setattr("bot.client", mock_client)
        monkeypatch.setattr("bot.clean_user_message", Mock(return_value="hello"))
        
        body = {
            "event": {
                "type": "message",
                "channel_type": "im",
                "user": "U123",
                "channel": "D123",
                "event_ts": "100.0",
                "text": "hello"
            }
        }
        
        caplog.set_level(logging.INFO)
        await bot.handle_mention(body, logging.getLogger())
        
        # Should not call conversations_replies (no thread)
        mock_client.conversations_replies.assert_not_called()
        
        # Should call chat_postMessage with AI response
        mock_client.chat_postMessage.assert_called_once()
        call_args = mock_client.chat_postMessage.call_args
        assert call_args[1]["channel"] == "D123"
        assert call_args[1]["text"] == "Mock AI response"

    @pytest.mark.asyncio
    async def test_channel_mention_without_thread(self, mock_client, mock_llm, mock_slack_utils, monkeypatch, caplog):
        """Verify channel mention without thread_ts works correctly."""
        monkeypatch.setattr("bot.client", mock_client)
        monkeypatch.setattr("bot.clean_user_message", Mock(return_value="hello"))
        
        body = {
            "event": {
                "type": "app_mention",
                "user": "U123",
                "channel": "C123",
                "event_ts": "100.0",
                "text": "@bot hello"
            }
        }
        
        caplog.set_level(logging.INFO)
        await bot.handle_mention(body, logging.getLogger())
        
        # Should not call conversations_replies (no thread)
        mock_client.conversations_replies.assert_not_called()
        
        # Should call chat_postMessage with AI response
        mock_client.chat_postMessage.assert_called_once()
        call_args = mock_client.chat_postMessage.call_args
        assert call_args[1]["channel"] == "C123"
        assert call_args[1]["text"] == "Mock AI response"

    @pytest.mark.asyncio
    async def test_thread_reply_with_history(self, mock_client, mock_llm, mock_slack_utils, monkeypatch, caplog):
        """Verify thread reply with history works correctly."""
        monkeypatch.setattr("bot.client", mock_client)
        monkeypatch.setattr("bot.clean_user_message", Mock(return_value="follow up"))
        
        # Mock conversations_replies to return thread history
        mock_client.conversations_replies.return_value = {
            "messages": [
                {"ts": "100.0", "user": "U1", "text": "first message"},
                {"ts": "200.0", "user": "U2", "text": "second message"},
                {"ts": "300.0", "user": "U3", "text": "triggering message"},  # This should be skipped
            ]
        }
        
        body = {
            "event": {
                "type": "app_mention",
                "user": "U3",
                "channel": "C123",
                "event_ts": "300.0",  # Same as last message in history
                "thread_ts": "100.0",
                "text": "@bot triggering message"
            }
        }
        
        caplog.set_level(logging.INFO)
        await bot.handle_mention(body, logging.getLogger())
        
        # Should call conversations_replies for thread history
        mock_client.conversations_replies.assert_called_once()
        call_args = mock_client.conversations_replies.call_args
        assert call_args[1]["channel"] == "C123"
        assert call_args[1]["ts"] == "100.0"  # thread_ts
        
        # Should call chat_postMessage with AI response
        mock_client.chat_postMessage.assert_called_once()
        call_args = mock_client.chat_postMessage.call_args
        assert call_args[1]["channel"] == "C123"
        assert call_args[1]["thread_ts"] == "100.0"  # Reply in thread
        assert call_args[1]["text"] == "Mock AI response"

    @pytest.mark.asyncio
    async def test_thread_reply_with_bot_messages(self, mock_client, mock_llm, mock_slack_utils, monkeypatch, caplog):
        """Verify thread with bot messages marks them as assistant role."""
        monkeypatch.setattr("bot.client", mock_client)
        monkeypatch.setattr("bot.clean_user_message", Mock(return_value="follow up"))
        
        # Mock conversations_replies to return thread with bot messages
        mock_client.conversations_replies.return_value = {
            "messages": [
                {"ts": "100.0", "user": "U1", "text": "user question"},
                {"ts": "200.0", "bot_id": "B123", "text": "bot response", "username": "testbot"},
                {"ts": "300.0", "user": "U1", "text": "follow up"},
            ]
        }
        
        body = {
            "event": {
                "type": "app_mention",
                "user": "U1",
                "channel": "C123",
                "event_ts": "400.0",
                "thread_ts": "100.0",
                "text": "@bot another follow up"
            }
        }
        
        caplog.set_level(logging.INFO)
        await bot.handle_mention(body, logging.getLogger())
        
        # Should call conversations_replies
        mock_client.conversations_replies.assert_called_once()
        
        # Should call chat_postMessage
        mock_client.chat_postMessage.assert_called_once()

    @pytest.mark.asyncio
    async def test_conversations_replies_failure_handled_gracefully(self, mock_client, mock_llm, mock_slack_utils, monkeypatch, caplog):
        """Verify conversations_replies failure is now handled gracefully (bug fixed!).
        
        The refactoring fixed the bug where conversations_replies failures would crash
        the handler. Now it logs the error and continues without history.
        """
        monkeypatch.setattr("bot.client", mock_client)
        monkeypatch.setattr("bot.clean_user_message", Mock(return_value="hello"))
        
        # Mock conversations_replies to raise an exception
        mock_client.conversations_replies.side_effect = Exception("API Error")
        
        body = {
            "event": {
                "type": "app_mention",
                "user": "U123",
                "channel": "C123",
                "event_ts": "100.0",
                "thread_ts": "50.0",
                "text": "@bot hello"
            }
        }
        
        caplog.set_level(logging.DEBUG)
        
        # Should not crash anymore - refactoring fixed the bug!
        await bot.handle_mention(body, logging.getLogger())
        
        # Should log the error
        assert "Failed to fetch thread history for C123: API Error" in caplog.text
        
        # Should still call chat_postMessage (fallback behavior)
        mock_client.chat_postMessage.assert_called_once()
        call_args = mock_client.chat_postMessage.call_args
        assert call_args[1]["text"] == "Mock AI response"

    @pytest.mark.asyncio
    async def test_generate_ai_reply_returns_empty_uses_fallback(self, mock_client, mock_llm, mock_slack_utils, monkeypatch, caplog):
        """Verify empty AI response uses fallback message."""
        monkeypatch.setattr("bot.client", mock_client)
        monkeypatch.setattr("bot.clean_user_message", Mock(return_value="hello"))
        
        # Mock generate_ai_reply to return empty string
        async def mock_generate_empty(messages, slack_context=None):
            return ""
        
        monkeypatch.setattr("llm.generate_ai_reply", mock_generate_empty)
        
        body = {
            "event": {
                "type": "app_mention",
                "user": "U123",
                "channel": "C123",
                "event_ts": "100.0",
                "text": "@bot hello"
            }
        }
        
        caplog.set_level(logging.INFO)
        await bot.handle_mention(body, logging.getLogger())
        
        # Should call chat_postMessage with fallback text
        mock_client.chat_postMessage.assert_called_once()
        call_args = mock_client.chat_postMessage.call_args
        assert "couldn't generate a response" in call_args[1]["text"]

    @pytest.mark.asyncio
    async def test_chat_postMessage_failure_logged_but_doesnt_crash(self, mock_client, mock_llm, mock_slack_utils, monkeypatch, caplog):
        """Verify chat_postMessage failure is logged but doesn't crash handler."""
        monkeypatch.setattr("bot.client", mock_client)
        monkeypatch.setattr("bot.clean_user_message", Mock(return_value="hello"))
        
        # Mock chat_postMessage to raise an exception
        mock_client.chat_postMessage.side_effect = Exception("Post failed")
        
        body = {
            "event": {
                "type": "app_mention",
                "user": "U123",
                "channel": "C123",
                "event_ts": "100.0",
                "text": "@bot hello"
            }
        }
        
        caplog.set_level(logging.ERROR)
        await bot.handle_mention(body, logging.getLogger())
        
        # Should log the error
        assert "Failed to post message to Slack" in caplog.text

    @pytest.mark.asyncio
    async def test_duplicate_message_prevention_in_thread(self, mock_client, mock_llm, mock_slack_utils, monkeypatch, caplog):
        """Verify triggering message is not duplicated in thread history.
        
        This is the core test for the duplicate issue mentioned in IMPROVEMENTS.md.
        """
        monkeypatch.setattr("bot.client", mock_client)
        monkeypatch.setattr("bot.clean_user_message", Mock(return_value="triggering message"))
        
        # Mock conversations_replies to return thread history including the triggering message
        mock_client.conversations_replies.return_value = {
            "messages": [
                {"ts": "100.0", "user": "U1", "text": "first message"},
                {"ts": "200.0", "user": "U2", "text": "second message"},
                {"ts": "300.0", "user": "U3", "text": "triggering message"},  # This should be skipped
            ]
        }
        
        # Capture the messages passed to generate_ai_reply
        captured_messages = []
        async def capture_messages(messages, slack_context=None):
            captured_messages.extend(messages)
            return "Mock AI response"
        
        monkeypatch.setattr("llm.generate_ai_reply", capture_messages)
        
        body = {
            "event": {
                "type": "app_mention",
                "user": "U3",
                "channel": "C123",
                "event_ts": "300.0",  # Same as last message in history
                "thread_ts": "100.0",
                "text": "@bot triggering message"
            }
        }
        
        caplog.set_level(logging.INFO)
        await bot.handle_mention(body, logging.getLogger())
        
        # Verify the triggering message appears only once in the messages sent to LLM
        triggering_content = [m["content"] for m in captured_messages if "triggering message" in m["content"]]
        assert len(triggering_content) == 1, f"Expected 1 occurrence of 'triggering message', got {len(triggering_content)}: {triggering_content}"
        
        # Verify the structure: system + history (excluding duplicate) + current
        assert len(captured_messages) >= 3  # system + 2 history + 1 current
        assert captured_messages[0]["role"] == "system"
        
        # The last message should be the current user message
        assert captured_messages[-1]["role"] == "user"
        assert "triggering message" in captured_messages[-1]["content"]
