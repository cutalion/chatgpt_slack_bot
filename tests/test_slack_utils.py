"""Comprehensive tests for slack_utils.py methods."""

import os
import sys
import types
import logging
from datetime import datetime, timezone

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


class TestTimestampFunctions:
    """Test timestamp normalization and formatting functions."""

    def test_normalise_ts_float_positive(self):
        """Test _normalise_ts with positive float input."""
        result = slack_utils._normalise_ts(1234567890.123456)
        assert result == "1234567890.123456"

    def test_normalise_ts_int_positive(self):
        """Test _normalise_ts with positive int input."""
        result = slack_utils._normalise_ts(1234567890)
        assert result == "1234567890.000000"

    def test_normalise_ts_float_zero(self):
        """Test _normalise_ts with zero float input."""
        result = slack_utils._normalise_ts(0.0)
        assert result is None

    def test_normalise_ts_int_zero(self):
        """Test _normalise_ts with zero int input."""
        result = slack_utils._normalise_ts(0)
        assert result is None

    def test_normalise_ts_float_negative(self):
        """Test _normalise_ts with negative float input."""
        result = slack_utils._normalise_ts(-1.5)
        assert result is None

    def test_normalise_ts_string_numeric(self):
        """Test _normalise_ts with numeric string input."""
        result = slack_utils._normalise_ts("1234567890.123456")
        assert result == "1234567890.123456"

    def test_normalise_ts_string_numeric_with_whitespace(self):
        """Test _normalise_ts with numeric string with whitespace."""
        result = slack_utils._normalise_ts("  1234567890.123456  ")
        assert result == "1234567890.123456"

    def test_normalise_ts_string_empty(self):
        """Test _normalise_ts with empty string input."""
        result = slack_utils._normalise_ts("")
        assert result is None

    def test_normalise_ts_string_whitespace_only(self):
        """Test _normalise_ts with whitespace-only string."""
        result = slack_utils._normalise_ts("   ")
        assert result is None

    def test_normalise_ts_iso_string_with_z(self):
        """Test _normalise_ts with ISO 8601 string ending in Z."""
        result = slack_utils._normalise_ts("2024-01-01T12:00:00Z")
        expected_ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp()
        assert result == f"{expected_ts:.6f}"

    def test_normalise_ts_iso_string_with_timezone(self):
        """Test _normalise_ts with ISO 8601 string with timezone."""
        result = slack_utils._normalise_ts("2024-01-01T12:00:00+05:00")
        expected_ts = datetime(2024, 1, 1, 7, 0, 0, tzinfo=timezone.utc).timestamp()
        assert result == f"{expected_ts:.6f}"

    def test_normalise_ts_iso_string_naive(self):
        """Test _normalise_ts with naive ISO 8601 string (assumes UTC)."""
        result = slack_utils._normalise_ts("2024-01-01T12:00:00")
        expected_ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp()
        assert result == f"{expected_ts:.6f}"

    def test_normalise_ts_invalid_string(self):
        """Test _normalise_ts with invalid string input."""
        result = slack_utils._normalise_ts("not a timestamp")
        assert result is None

    def test_normalise_ts_malformed_iso(self):
        """Test _normalise_ts with malformed ISO string."""
        result = slack_utils._normalise_ts("2024-13-45T25:70:90Z")
        assert result is None

    def test_normalise_ts_none(self):
        """Test _normalise_ts with None input."""
        result = slack_utils._normalise_ts(None)
        assert result is None

    def test_normalise_ts_non_numeric_non_iso(self):
        """Test _normalise_ts with non-numeric, non-ISO string."""
        result = slack_utils._normalise_ts("hello world")
        assert result is None

    def test_format_ts_utc_valid_timestamp(self):
        """Test format_ts_utc with valid Slack timestamp."""
        result = slack_utils.format_ts_utc("1234567890.123456")
        assert result == "[2009-02-13 23:31Z]"

    def test_format_ts_utc_none(self):
        """Test format_ts_utc with None input."""
        result = slack_utils.format_ts_utc(None)
        assert result == "[1970-01-01 00:00Z]"

    def test_format_ts_utc_empty_string(self):
        """Test format_ts_utc with empty string."""
        result = slack_utils.format_ts_utc("")
        assert result == "[1970-01-01 00:00Z]"

    def test_format_ts_utc_zero_timestamp(self):
        """Test format_ts_utc with zero timestamp."""
        result = slack_utils.format_ts_utc("0")
        assert result == "[1970-01-01 00:00Z]"

    def test_format_ts_utc_invalid_timestamp(self):
        """Test format_ts_utc with invalid timestamp string."""
        result = slack_utils.format_ts_utc("invalid")
        assert result == "[0000-00-00 00:00Z]"

    def test_format_ts_utc_negative_timestamp(self):
        """Test format_ts_utc with negative timestamp."""
        result = slack_utils.format_ts_utc("-1")
        assert result == "[1969-12-31 23:59Z]"


class TestUserResolutionFunctions:
    """Test user name resolution and profile functions."""

    def setup_method(self):
        """Clear caches before each test."""
        slack_utils._USER_NAME_CACHE.clear()
        slack_utils._USER_INFO_CACHE.clear()

    def test_extract_display_name_from_user_full_profile(self):
        """Test _extract_display_name_from_user with complete user object."""
        user_obj = {
            "id": "U1234567890",
            "profile": {
                "display_name_normalized": "John Doe",
                "display_name": "Johnny",
                "real_name_normalized": "John Smith",
                "real_name": "John",
                "name": "john.doe"
            }
        }
        result = slack_utils._extract_display_name_from_user(user_obj)
        assert result == "John Doe"  # Should prioritize display_name_normalized

    def test_extract_display_name_from_user_partial_profile(self):
        """Test _extract_display_name_from_user with missing higher priority fields."""
        user_obj = {
            "id": "U1234567890",
            "profile": {
                "real_name": "John Smith",
                "name": "john.doe"
            }
        }
        result = slack_utils._extract_display_name_from_user(user_obj)
        assert result == "John Smith"  # Should fall back to real_name

    def test_extract_display_name_from_user_name_only(self):
        """Test _extract_display_name_from_user with only name field."""
        user_obj = {
            "id": "U1234567890",
            "profile": {
                "name": "john.doe"
            }
        }
        result = slack_utils._extract_display_name_from_user(user_obj)
        assert result == "john.doe"

    def test_extract_display_name_from_user_fallback_to_id(self):
        """Test _extract_display_name_from_user fallback to user ID."""
        user_obj = {
            "id": "U1234567890",
            "profile": {}
        }
        result = slack_utils._extract_display_name_from_user(user_obj)
        assert result == "U1234567890"

    def test_extract_display_name_from_user_none_input(self):
        """Test _extract_display_name_from_user with None input."""
        result = slack_utils._extract_display_name_from_user(None)
        assert result is None

    def test_extract_display_name_from_user_non_dict(self):
        """Test _extract_display_name_from_user with non-dict input."""
        result = slack_utils._extract_display_name_from_user("not a dict")
        assert result is None

    def test_extract_display_name_from_user_empty_profile(self):
        """Test _extract_display_name_from_user with empty profile."""
        user_obj = {
            "id": "U1234567890",
            "profile": {}
        }
        result = slack_utils._extract_display_name_from_user(user_obj)
        assert result == "U1234567890"

    def test_extract_display_name_from_user_no_profile(self):
        """Test _extract_display_name_from_user with no profile key."""
        user_obj = {
            "id": "U1234567890"
        }
        result = slack_utils._extract_display_name_from_user(user_obj)
        assert result == "U1234567890"

    def test_extract_display_name_from_user_empty_strings(self):
        """Test _extract_display_name_from_user with empty string values."""
        user_obj = {
            "id": "U1234567890",
            "profile": {
                "display_name_normalized": "",
                "display_name": "   ",
                "real_name_normalized": None,
                "real_name": "",
                "name": ""
            }
        }
        result = slack_utils._extract_display_name_from_user(user_obj)
        assert result == "U1234567890"

    @pytest.mark.asyncio
    async def test_get_user_display_name_success(self, monkeypatch):
        """Test get_user_display_name with successful API response."""
        class DummyClient:
            async def users_info(self, user):
                return {
                    "ok": True,
                    "user": {
                        "id": "U1234567890",
                        "profile": {
                            "display_name_normalized": "John Doe"
                        }
                    }
                }

        dummy_client = DummyClient()
        monkeypatch.setattr(slack_utils, "slack_client", dummy_client)
        
        result = await slack_utils.get_user_display_name("U1234567890")
        assert result == "John Doe"

    @pytest.mark.asyncio
    async def test_get_user_display_name_cached(self, monkeypatch):
        """Test get_user_display_name with cached result."""
        # Pre-populate cache
        slack_utils._USER_NAME_CACHE["U1234567890"] = "Cached Name"
        
        class DummyClient:
            call_count = 0
            async def users_info(self, user):
                self.call_count += 1
                return {"ok": True, "user": {"id": user}}

        dummy_client = DummyClient()
        monkeypatch.setattr(slack_utils, "slack_client", dummy_client)
        
        result = await slack_utils.get_user_display_name("U1234567890")
        assert result == "Cached Name"
        assert dummy_client.call_count == 0  # Should not call API

    @pytest.mark.asyncio
    async def test_get_user_display_name_api_failure(self, monkeypatch):
        """Test get_user_display_name with API failure."""
        class DummyClient:
            async def users_info(self, user):
                raise Exception("API Error")

        dummy_client = DummyClient()
        monkeypatch.setattr(slack_utils, "slack_client", dummy_client)
        
        result = await slack_utils.get_user_display_name("U1234567890")
        assert result == "<@U1234567890>"

    @pytest.mark.asyncio
    async def test_get_user_display_name_invalid_user_id(self):
        """Test get_user_display_name with invalid user ID."""
        result = await slack_utils.get_user_display_name(None)
        assert result == "Unknown"
        
        result = await slack_utils.get_user_display_name("")
        assert result == "Unknown"
        
        result = await slack_utils.get_user_display_name(123)
        assert result == "Unknown"

    @pytest.mark.asyncio
    async def test_get_user_display_name_response_with_data_attribute(self, monkeypatch):
        """Test get_user_display_name with response object having .data attribute."""
        class ResponseWithData:
            def __init__(self):
                self.data = {
                    "user": {
                        "id": "U1234567890",
                        "profile": {
                            "display_name_normalized": "John Doe"
                        }
                    }
                }

        class DummyClient:
            async def users_info(self, user):
                return ResponseWithData()

        dummy_client = DummyClient()
        monkeypatch.setattr(slack_utils, "slack_client", dummy_client)
        
        result = await slack_utils.get_user_display_name("U1234567890")
        assert result == "John Doe"

    @pytest.mark.asyncio
    async def test_get_user_profile_success(self, monkeypatch):
        """Test get_user_profile with successful API response."""
        class DummyClient:
            async def users_info(self, user):
                return {
                    "ok": True,
                    "user": {
                        "id": "U1234567890",
                        "profile": {
                            "display_name_normalized": "John Doe",
                            "real_name_normalized": "John Smith",
                            "title": "Software Engineer",
                            "status_text": "Working",
                            "status_emoji": ":computer:"
                        },
                        "tz": "America/New_York",
                        "tz_label": "Eastern Time",
                        "is_bot": False
                    }
                }

        dummy_client = DummyClient()
        monkeypatch.setattr(slack_utils, "slack_client", dummy_client)
        
        result = await slack_utils.get_user_profile("U1234567890")
        
        assert result["user_id"] == "U1234567890"
        assert result["display_name"] == "John Doe"
        assert result["real_name"] == "John Smith"
        assert result["title"] == "Software Engineer"
        assert result["tz"] == "America/New_York"
        assert result["tz_label"] == "Eastern Time"
        assert result["status_text"] == "Working"
        assert result["status_emoji"] == ":computer:"
        assert result["is_bot"] is False

    @pytest.mark.asyncio
    async def test_get_user_profile_cached(self, monkeypatch):
        """Test get_user_profile with cached result."""
        # Pre-populate cache
        cached_profile = {
            "user_id": "U1234567890",
            "display_name": "Cached Name",
            "real_name": "Cached Real Name"
        }
        slack_utils._USER_INFO_CACHE["U1234567890"] = cached_profile
        
        class DummyClient:
            call_count = 0
            async def users_info(self, user):
                self.call_count += 1
                return {"ok": True, "user": {"id": user}}

        dummy_client = DummyClient()
        monkeypatch.setattr(slack_utils, "slack_client", dummy_client)
        
        result = await slack_utils.get_user_profile("U1234567890")
        assert result == cached_profile
        assert dummy_client.call_count == 0  # Should not call API

    @pytest.mark.asyncio
    async def test_get_user_profile_api_failure(self, monkeypatch):
        """Test get_user_profile with API failure."""
        class DummyClient:
            async def users_info(self, user):
                raise Exception("API Error")

        dummy_client = DummyClient()
        monkeypatch.setattr(slack_utils, "slack_client", dummy_client)
        
        result = await slack_utils.get_user_profile("U1234567890")
        assert result["user_id"] == "U1234567890"
        assert result["error"] == "lookup_failed"

    @pytest.mark.asyncio
    async def test_get_user_profile_invalid_user_id(self):
        """Test get_user_profile with invalid user ID."""
        result = await slack_utils.get_user_profile(None)
        assert result["user_id"] == ""
        assert result["error"] == "invalid_user_id"
        
        result = await slack_utils.get_user_profile("")
        assert result["user_id"] == ""
        assert result["error"] == "invalid_user_id"
        
        result = await slack_utils.get_user_profile(123)
        assert result["user_id"] == 123  # Non-string user_id is passed through as-is
        assert result["error"] == "invalid_user_id"

    @pytest.mark.asyncio
    async def test_get_user_profile_cache_priming(self, monkeypatch):
        """Test get_user_profile primes the display name cache."""
        class DummyClient:
            async def users_info(self, user):
                return {
                    "ok": True,
                    "user": {
                        "id": "U1234567890",
                        "profile": {
                            "display_name_normalized": "John Doe"
                        }
                    }
                }

        dummy_client = DummyClient()
        monkeypatch.setattr(slack_utils, "slack_client", dummy_client)
        
        # Clear caches
        slack_utils._USER_NAME_CACHE.clear()
        slack_utils._USER_INFO_CACHE.clear()
        
        result = await slack_utils.get_user_profile("U1234567890")
        
        # Check that display name cache was primed
        assert slack_utils._USER_NAME_CACHE["U1234567890"] == "John Doe"
        assert result["display_name"] == "John Doe"


class TestBotFunctions:
    """Test bot name and ID resolution functions."""

    def setup_method(self):
        """Clear caches before each test."""
        slack_utils._USER_NAME_CACHE.clear()
        slack_utils._USER_INFO_CACHE.clear()
        # Reset global bot user ID
        slack_utils._BOT_USER_ID = None

    def test_get_bot_name_from_message_bot_profile_name(self):
        """Test get_bot_name_from_message with bot_profile.name."""
        message = {
            "bot_profile": {
                "name": "MyBot"
            }
        }
        result = slack_utils.get_bot_name_from_message(message)
        assert result == "MyBot"

    def test_get_bot_name_from_message_bot_profile_username(self):
        """Test get_bot_name_from_message with bot_profile.username fallback."""
        message = {
            "bot_profile": {
                "username": "mybot"
            }
        }
        result = slack_utils.get_bot_name_from_message(message)
        assert result == "mybot"

    def test_get_bot_name_from_message_bot_profile_app_id(self):
        """Test get_bot_name_from_message with bot_profile.app_id fallback."""
        message = {
            "bot_profile": {
                "app_id": "A1234567890"
            }
        }
        result = slack_utils.get_bot_name_from_message(message)
        assert result == "A1234567890"

    def test_get_bot_name_from_message_bot_profile_id(self):
        """Test get_bot_name_from_message with bot_profile.id fallback."""
        message = {
            "bot_profile": {
                "id": "B1234567890"
            }
        }
        result = slack_utils.get_bot_name_from_message(message)
        assert result == "B1234567890"

    def test_get_bot_name_from_message_message_level_name(self):
        """Test get_bot_name_from_message with message-level name fallback."""
        message = {
            "name": "MessageBot"
        }
        result = slack_utils.get_bot_name_from_message(message)
        assert result == "MessageBot"

    def test_get_bot_name_from_message_message_level_username(self):
        """Test get_bot_name_from_message with message-level username fallback."""
        message = {
            "username": "messagebot"
        }
        result = slack_utils.get_bot_name_from_message(message)
        assert result == "messagebot"

    def test_get_bot_name_from_message_message_level_app_id(self):
        """Test get_bot_name_from_message with message-level app_id fallback."""
        message = {
            "app_id": "A9876543210"
        }
        result = slack_utils.get_bot_name_from_message(message)
        assert result == "A9876543210"

    def test_get_bot_name_from_message_message_level_id(self):
        """Test get_bot_name_from_message with message-level id fallback."""
        message = {
            "id": "B9876543210"
        }
        result = slack_utils.get_bot_name_from_message(message)
        assert result == "B9876543210"

    def test_get_bot_name_from_message_empty_message(self):
        """Test get_bot_name_from_message with empty message."""
        message = {}
        result = slack_utils.get_bot_name_from_message(message)
        assert result == "Bot"

    def test_get_bot_name_from_message_none_message(self):
        """Test get_bot_name_from_message with None message raises exception."""
        with pytest.raises(AttributeError):
            slack_utils.get_bot_name_from_message(None)

    def test_get_bot_name_from_message_empty_bot_profile(self):
        """Test get_bot_name_from_message with empty bot_profile."""
        message = {
            "bot_profile": {}
        }
        result = slack_utils.get_bot_name_from_message(message)
        assert result == "Bot"

    def test_get_bot_name_from_message_priority_order(self):
        """Test get_bot_name_from_message priority order (name > username > app_id > id)."""
        message = {
            "bot_profile": {
                "name": "PriorityBot",
                "username": "prioritybot",
                "app_id": "A1111111111",
                "id": "B1111111111"
            }
        }
        result = slack_utils.get_bot_name_from_message(message)
        assert result == "PriorityBot"  # Should pick name first

    def test_get_bot_name_from_message_whitespace_handling(self):
        """Test get_bot_name_from_message with whitespace in names."""
        message = {
            "bot_profile": {
                "name": "  WhitespaceBot  ",
                "username": "   whitespacebot   "
            }
        }
        result = slack_utils.get_bot_name_from_message(message)
        assert result == "WhitespaceBot"  # Should strip whitespace

    @pytest.mark.asyncio
    async def test_get_bot_user_id_success(self, monkeypatch):
        """Test get_bot_user_id with successful auth_test response."""
        class DummyClient:
            async def auth_test(self):
                return {
                    "ok": True,
                    "user_id": "U1234567890"
                }

        dummy_client = DummyClient()
        monkeypatch.setattr(slack_utils, "slack_client", dummy_client)
        
        result = await slack_utils.get_bot_user_id()
        assert result == "U1234567890"

    @pytest.mark.asyncio
    async def test_get_bot_user_id_cached(self, monkeypatch):
        """Test get_bot_user_id with cached result."""
        # Pre-populate cache
        slack_utils._BOT_USER_ID = "U9876543210"
        
        class DummyClient:
            call_count = 0
            async def auth_test(self):
                self.call_count += 1
                return {"ok": True, "user_id": "U1234567890"}

        dummy_client = DummyClient()
        monkeypatch.setattr(slack_utils, "slack_client", dummy_client)
        
        result = await slack_utils.get_bot_user_id()
        assert result == "U9876543210"  # Should return cached value
        assert dummy_client.call_count == 0  # Should not call API

    @pytest.mark.asyncio
    async def test_get_bot_user_id_api_failure(self, monkeypatch):
        """Test get_bot_user_id with API failure."""
        class DummyClient:
            async def auth_test(self):
                raise Exception("API Error")

        dummy_client = DummyClient()
        monkeypatch.setattr(slack_utils, "slack_client", dummy_client)
        
        result = await slack_utils.get_bot_user_id()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_bot_user_id_response_with_data_attribute(self, monkeypatch):
        """Test get_bot_user_id with response object having .data attribute."""
        class ResponseWithData:
            def __init__(self):
                self.data = {
                    "ok": True,
                    "user_id": "U1234567890"
                }

        class DummyClient:
            async def auth_test(self):
                return ResponseWithData()

        dummy_client = DummyClient()
        monkeypatch.setattr(slack_utils, "slack_client", dummy_client)
        
        result = await slack_utils.get_bot_user_id()
        assert result == "U1234567890"

    @pytest.mark.asyncio
    async def test_get_bot_user_id_invalid_response(self, monkeypatch):
        """Test get_bot_user_id with invalid response format."""
        class DummyClient:
            async def auth_test(self):
                return {
                    "ok": False,
                    "user_id": None
                }

        dummy_client = DummyClient()
        monkeypatch.setattr(slack_utils, "slack_client", dummy_client)
        
        result = await slack_utils.get_bot_user_id()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_bot_user_id_empty_user_id(self, monkeypatch):
        """Test get_bot_user_id with empty user_id in response."""
        class DummyClient:
            async def auth_test(self):
                return {
                    "ok": True,
                    "user_id": ""
                }

        dummy_client = DummyClient()
        monkeypatch.setattr(slack_utils, "slack_client", dummy_client)
        
        result = await slack_utils.get_bot_user_id()
        assert result is None


class TestMessageSimplificationFunctions:
    """Test message simplification and utility functions."""

    def test_trim_text_within_limit(self):
        """Test _trim_text with text within limit."""
        result = slack_utils._trim_text("Hello world", limit=20)
        assert result == "Hello world"

    def test_trim_text_exceeds_limit(self):
        """Test _trim_text with text exceeding limit."""
        result = slack_utils._trim_text("Hello world", limit=5)
        assert result == "Hell…"

    def test_trim_text_exactly_at_limit(self):
        """Test _trim_text with text exactly at limit."""
        result = slack_utils._trim_text("Hello", limit=5)
        assert result == "Hello"

    def test_trim_text_none_input(self):
        """Test _trim_text with None input."""
        result = slack_utils._trim_text(None, limit=10)
        assert result == ""

    def test_trim_text_empty_string(self):
        """Test _trim_text with empty string."""
        result = slack_utils._trim_text("", limit=10)
        assert result == ""

    def test_trim_text_limit_zero(self):
        """Test _trim_text with limit of zero."""
        result = slack_utils._trim_text("Hello", limit=0)
        assert result == "…"

    def test_trim_text_limit_one(self):
        """Test _trim_text with limit of one."""
        result = slack_utils._trim_text("Hello", limit=1)
        assert result == "…"

    def test_trim_text_very_long_text(self):
        """Test _trim_text with very long text."""
        long_text = "A" * 1000
        result = slack_utils._trim_text(long_text, limit=10)
        assert result == "AAAAAAAAA…"
        assert len(result) == 10

    def test_simplify_files_valid_list(self):
        """Test _simplify_files with valid file list."""
        files = [
            {
                "id": "F1234567890",
                "name": "document.pdf",
                "mimetype": "application/pdf",
                "filetype": "pdf",
                "permalink": "https://files.slack.com/F1234567890",
                "extra_field": "should_be_ignored"
            },
            {
                "id": "F0987654321",
                "name": "image.jpg",
                "mimetype": "image/jpeg",
                "filetype": "jpg",
                "permalink": "https://files.slack.com/F0987654321"
            }
        ]
        result = slack_utils._simplify_files(files)
        
        assert len(result) == 2
        assert result[0]["id"] == "F1234567890"
        assert result[0]["name"] == "document.pdf"
        assert result[0]["mimetype"] == "application/pdf"
        assert result[0]["filetype"] == "pdf"
        assert result[0]["permalink"] == "https://files.slack.com/F1234567890"
        assert "extra_field" not in result[0]  # Should be filtered out

    def test_simplify_files_empty_list(self):
        """Test _simplify_files with empty list."""
        result = slack_utils._simplify_files([])
        assert result == []

    def test_simplify_files_none_input(self):
        """Test _simplify_files with None input."""
        result = slack_utils._simplify_files(None)
        assert result == []

    def test_simplify_files_non_dict_elements(self):
        """Test _simplify_files with non-dict elements."""
        files = ["not_a_dict", {"id": "F123"}, 123, None]
        result = slack_utils._simplify_files(files)
        assert len(result) == 1
        assert result[0]["id"] == "F123"

    def test_simplify_files_missing_fields(self):
        """Test _simplify_files with files missing some fields."""
        files = [{"id": "F123", "name": "test.txt"}]  # Missing other fields
        result = slack_utils._simplify_files(files)
        assert len(result) == 1
        assert result[0]["id"] == "F123"
        assert result[0]["name"] == "test.txt"
        assert result[0]["mimetype"] is None
        assert result[0]["filetype"] is None
        assert result[0]["permalink"] is None

    def test_simplify_reactions_valid_list(self):
        """Test _simplify_reactions with valid reaction list."""
        reactions = [
            {
                "name": "thumbsup",
                "count": 5,
                "users": ["U1", "U2", "U3", "U4", "U5"],
                "extra_field": "should_be_ignored"
            },
            {
                "name": "heart",
                "count": 2,
                "users": ["U6", "U7"]
            }
        ]
        result = slack_utils._simplify_reactions(reactions)
        
        assert len(result) == 2
        assert result[0]["name"] == "thumbsup"
        assert result[0]["count"] == 5
        assert result[0]["users"] == ["U1", "U2", "U3", "U4", "U5"]
        assert "extra_field" not in result[0]  # Should be filtered out

    def test_simplify_reactions_empty_list(self):
        """Test _simplify_reactions with empty list."""
        result = slack_utils._simplify_reactions([])
        assert result == []

    def test_simplify_reactions_none_input(self):
        """Test _simplify_reactions with None input."""
        result = slack_utils._simplify_reactions(None)
        assert result == []

    def test_simplify_reactions_non_dict_elements(self):
        """Test _simplify_reactions with non-dict elements."""
        reactions = ["not_a_dict", {"name": "smile"}, 123, None]
        result = slack_utils._simplify_reactions(reactions)
        assert len(result) == 1
        assert result[0]["name"] == "smile"

    def test_simplify_reactions_missing_fields(self):
        """Test _simplify_reactions with reactions missing some fields."""
        reactions = [{"name": "smile"}]  # Missing count and users
        result = slack_utils._simplify_reactions(reactions)
        assert len(result) == 1
        assert result[0]["name"] == "smile"
        assert result[0]["count"] is None
        assert result[0]["users"] is None

    def test_simplify_message_complete_message(self, monkeypatch):
        """Test _simplify_message with complete message."""
        # Mock config for text limit
        monkeypatch.setattr(slack_utils.config, "SLACK_TOOL_HISTORY_TEXT_CHAR_CAP", 100)
        
        message = {
            "ts": "1234567890.123456",
            "user": "U1234567890",
            "bot_id": "B1234567890",
            "username": "testbot",
            "text": "Hello world!",
            "thread_ts": "1234567890.123456",
            "parent_user_id": "U0987654321",
            "reply_count": 5,
            "reactions": [{"name": "thumbsup", "count": 3, "users": ["U1", "U2", "U3"]}],
            "files": [{"id": "F123", "name": "test.txt", "mimetype": "text/plain"}],
            "subtype": "bot_message"
        }
        result = slack_utils._simplify_message(message, text_limit=100)
        
        assert result["ts"] == "1234567890.123456"
        assert result["user"] == "U1234567890"
        assert result["bot_id"] == "B1234567890"
        assert result["username"] == "testbot"
        assert result["text"] == "Hello world!"
        assert result["thread_ts"] == "1234567890.123456"
        assert result["parent_user_id"] == "U0987654321"
        assert result["reply_count"] == 5
        assert len(result["reactions"]) == 1
        assert result["reactions"][0]["name"] == "thumbsup"
        assert len(result["files"]) == 1
        assert result["files"][0]["id"] == "F123"
        assert result["subtype"] == "bot_message"

    def test_simplify_message_text_exceeds_limit(self, monkeypatch):
        """Test _simplify_message with text exceeding limit."""
        monkeypatch.setattr(slack_utils.config, "SLACK_TOOL_HISTORY_TEXT_CHAR_CAP", 10)
        
        message = {
            "ts": "1234567890.123456",
            "text": "This is a very long message that exceeds the limit"
        }
        result = slack_utils._simplify_message(message, text_limit=10)
        
        assert result["text"] == "This is a…"  # Should be trimmed with ellipsis

    def test_simplify_message_minimal_message(self, monkeypatch):
        """Test _simplify_message with minimal message."""
        monkeypatch.setattr(slack_utils.config, "SLACK_TOOL_HISTORY_TEXT_CHAR_CAP", 100)
        
        message = {
            "ts": "1234567890.123456",
            "text": "Hello"
        }
        result = slack_utils._simplify_message(message, text_limit=100)
        
        assert result["ts"] == "1234567890.123456"
        assert result["text"] == "Hello"
        assert result["user"] is None
        assert result["bot_id"] is None
        assert result["username"] is None
        assert result["thread_ts"] is None
        assert result["parent_user_id"] is None
        assert result["reply_count"] is None
        assert result["reactions"] == []
        assert result["files"] == []
        assert result["subtype"] is None

    def test_simplify_message_none_text(self, monkeypatch):
        """Test _simplify_message with None text."""
        monkeypatch.setattr(slack_utils.config, "SLACK_TOOL_HISTORY_TEXT_CHAR_CAP", 100)
        
        message = {
            "ts": "1234567890.123456",
            "text": None
        }
        result = slack_utils._simplify_message(message, text_limit=100)
        
        assert result["text"] == ""

    def test_simplify_message_empty_text(self, monkeypatch):
        """Test _simplify_message with empty text."""
        monkeypatch.setattr(slack_utils.config, "SLACK_TOOL_HISTORY_TEXT_CHAR_CAP", 100)
        
        message = {
            "ts": "1234567890.123456",
            "text": ""
        }
        result = slack_utils._simplify_message(message, text_limit=100)
        
        assert result["text"] == ""

    def test_simplify_message_with_files_and_reactions(self, monkeypatch):
        """Test _simplify_message with files and reactions."""
        monkeypatch.setattr(slack_utils.config, "SLACK_TOOL_HISTORY_TEXT_CHAR_CAP", 100)
        
        message = {
            "ts": "1234567890.123456",
            "text": "Check this out!",
            "files": [
                {"id": "F1", "name": "doc.pdf", "mimetype": "application/pdf"},
                {"id": "F2", "name": "img.jpg", "mimetype": "image/jpeg"}
            ],
            "reactions": [
                {"name": "thumbsup", "count": 2, "users": ["U1", "U2"]},
                {"name": "heart", "count": 1, "users": ["U3"]}
            ]
        }
        result = slack_utils._simplify_message(message, text_limit=100)
        
        assert len(result["files"]) == 2
        assert result["files"][0]["id"] == "F1"
        assert result["files"][1]["id"] == "F2"
        assert len(result["reactions"]) == 2
        assert result["reactions"][0]["name"] == "thumbsup"
        assert result["reactions"][1]["name"] == "heart"


class TestEventValidationFunctions:
    """Test event validation and filtering functions."""

    def test_is_supported_event_valid_user_message(self):
        """Test is_supported_event with valid user message."""
        event = {
            "type": "message",
            "subtype": None,
            "user": "U1234567890",
            "channel": "C1234567890",
            "event_ts": "1234567890.123456",
            "text": "Hello world"
        }
        logger = logging.getLogger("test")
        result = slack_utils.is_supported_event(event, logger)
        assert result is True

    def test_is_supported_event_bot_message_subtype(self):
        """Test is_supported_event with bot_message subtype (should be rejected)."""
        event = {
            "type": "message",
            "subtype": "bot_message",
            "user": "U1234567890",
            "channel": "C1234567890",
            "event_ts": "1234567890.123456",
            "text": "Bot message"
        }
        logger = logging.getLogger("test")
        result = slack_utils.is_supported_event(event, logger)
        assert result is False

    def test_is_supported_event_message_changed_subtype(self):
        """Test is_supported_event with message_changed subtype (should be rejected)."""
        event = {
            "type": "message",
            "subtype": "message_changed",
            "user": "U1234567890",
            "channel": "C1234567890",
            "event_ts": "1234567890.123456",
            "text": "Edited message"
        }
        logger = logging.getLogger("test")
        result = slack_utils.is_supported_event(event, logger)
        assert result is False

    def test_is_supported_event_has_bot_id(self):
        """Test is_supported_event with bot_id present (should be rejected)."""
        event = {
            "type": "message",
            "subtype": None,
            "user": "U1234567890",
            "bot_id": "B1234567890",
            "channel": "C1234567890",
            "event_ts": "1234567890.123456",
            "text": "Message from bot"
        }
        logger = logging.getLogger("test")
        result = slack_utils.is_supported_event(event, logger)
        assert result is False

    def test_is_supported_event_missing_user(self):
        """Test is_supported_event with missing user field (should be rejected)."""
        event = {
            "type": "message",
            "subtype": None,
            "channel": "C1234567890",
            "event_ts": "1234567890.123456",
            "text": "Message without user"
        }
        logger = logging.getLogger("test")
        result = slack_utils.is_supported_event(event, logger)
        assert result is False

    def test_is_supported_event_empty_user(self):
        """Test is_supported_event with empty user field (should be rejected)."""
        event = {
            "type": "message",
            "subtype": None,
            "user": "",
            "channel": "C1234567890",
            "event_ts": "1234567890.123456",
            "text": "Message with empty user"
        }
        logger = logging.getLogger("test")
        result = slack_utils.is_supported_event(event, logger)
        assert result is False

    def test_is_supported_event_missing_channel(self):
        """Test is_supported_event with missing channel field (should be rejected)."""
        event = {
            "type": "message",
            "subtype": None,
            "user": "U1234567890",
            "event_ts": "1234567890.123456",
            "text": "Message without channel"
        }
        logger = logging.getLogger("test")
        result = slack_utils.is_supported_event(event, logger)
        assert result is False

    def test_is_supported_event_empty_channel(self):
        """Test is_supported_event with empty channel field (should be rejected)."""
        event = {
            "type": "message",
            "subtype": None,
            "user": "U1234567890",
            "channel": "",
            "event_ts": "1234567890.123456",
            "text": "Message with empty channel"
        }
        logger = logging.getLogger("test")
        result = slack_utils.is_supported_event(event, logger)
        assert result is False

    def test_is_supported_event_missing_event_ts(self):
        """Test is_supported_event with missing event_ts field (should be rejected)."""
        event = {
            "type": "message",
            "subtype": None,
            "user": "U1234567890",
            "channel": "C1234567890",
            "text": "Message without event_ts"
        }
        logger = logging.getLogger("test")
        result = slack_utils.is_supported_event(event, logger)
        assert result is False

    def test_is_supported_event_empty_event_ts(self):
        """Test is_supported_event with empty event_ts field (should be rejected)."""
        event = {
            "type": "message",
            "subtype": None,
            "user": "U1234567890",
            "channel": "C1234567890",
            "event_ts": "",
            "text": "Message with empty event_ts"
        }
        logger = logging.getLogger("test")
        result = slack_utils.is_supported_event(event, logger)
        assert result is False

    def test_is_supported_event_app_mention_event(self):
        """Test is_supported_event with app_mention event type (should be accepted)."""
        event = {
            "type": "app_mention",
            "user": "U1234567890",
            "channel": "C1234567890",
            "event_ts": "1234567890.123456",
            "text": "Hello @bot"
        }
        logger = logging.getLogger("test")
        result = slack_utils.is_supported_event(event, logger)
        assert result is True

    def test_is_supported_event_im_message(self):
        """Test is_supported_event with direct message (should be accepted)."""
        event = {
            "type": "message",
            "subtype": None,
            "user": "U1234567890",
            "channel": "D1234567890",
            "channel_type": "im",
            "event_ts": "1234567890.123456",
            "text": "Direct message"
        }
        logger = logging.getLogger("test")
        result = slack_utils.is_supported_event(event, logger)
        assert result is True

    def test_is_supported_event_with_channel_type(self):
        """Test is_supported_event with channel_type field (should be accepted)."""
        event = {
            "type": "message",
            "subtype": None,
            "user": "U1234567890",
            "channel": "C1234567890",
            "channel_type": "channel",
            "event_ts": "1234567890.123456",
            "text": "Channel message"
        }
        logger = logging.getLogger("test")
        result = slack_utils.is_supported_event(event, logger)
        assert result is True

    def test_is_supported_event_with_text(self):
        """Test is_supported_event with text field (should be accepted)."""
        event = {
            "type": "message",
            "subtype": None,
            "user": "U1234567890",
            "channel": "C1234567890",
            "event_ts": "1234567890.123456",
            "text": "Message with text"
        }
        logger = logging.getLogger("test")
        result = slack_utils.is_supported_event(event, logger)
        assert result is True

    def test_is_supported_event_empty_text(self):
        """Test is_supported_event with empty text field (should be accepted)."""
        event = {
            "type": "message",
            "subtype": None,
            "user": "U1234567890",
            "channel": "C1234567890",
            "event_ts": "1234567890.123456",
            "text": ""
        }
        logger = logging.getLogger("test")
        result = slack_utils.is_supported_event(event, logger)
        assert result is True

    def test_is_supported_event_missing_text(self):
        """Test is_supported_event with missing text field (should be accepted)."""
        event = {
            "type": "message",
            "subtype": None,
            "user": "U1234567890",
            "channel": "C1234567890",
            "event_ts": "1234567890.123456"
        }
        logger = logging.getLogger("test")
        result = slack_utils.is_supported_event(event, logger)
        assert result is True

    def test_is_supported_event_minimal_valid_event(self):
        """Test is_supported_event with minimal valid event."""
        event = {
            "type": "message",
            "user": "U1234567890",
            "channel": "C1234567890",
            "event_ts": "1234567890.123456"
        }
        logger = logging.getLogger("test")
        result = slack_utils.is_supported_event(event, logger)
        assert result is True

    def test_is_supported_event_multiple_rejection_reasons(self):
        """Test is_supported_event with multiple rejection reasons (bot_id + subtype)."""
        event = {
            "type": "message",
            "subtype": "bot_message",
            "user": "U1234567890",
            "bot_id": "B1234567890",
            "channel": "C1234567890",
            "event_ts": "1234567890.123456",
            "text": "Bot message"
        }
        logger = logging.getLogger("test")
        result = slack_utils.is_supported_event(event, logger)
        assert result is False  # Should fail on first check (subtype)


class TestUserMentionFunctions:
    """Test user mention normalization functions."""

    def test_normalise_user_mentions_wraps_ids(self):
        """Test normalise_user_mentions wraps user IDs in Slack mention format."""
        text = "Ping @UH4AMCRA7 and @WABC12345 in thread"
        expected = "Ping <@UH4AMCRA7> and <@WABC12345> in thread"
        assert slack_utils.normalise_user_mentions(text) == expected

    def test_normalise_user_mentions_ignores_existing_markup(self):
        """Test normalise_user_mentions ignores already formatted mentions."""
        text = "Already <@UH4AMCRA7> linked"
        assert slack_utils.normalise_user_mentions(text) == text

    def test_normalise_user_mentions_ignores_special_tokens(self):
        """Test normalise_user_mentions ignores special Slack tokens."""
        text = "Alert @here and @channel now"
        assert slack_utils.normalise_user_mentions(text) == text

    def test_normalise_user_mentions_handles_non_string(self):
        """Test normalise_user_mentions handles non-string input."""
        assert slack_utils.normalise_user_mentions(None) == ""


class TestCleanUserMessageFunctions:
    """Test clean_user_message function."""

    def test_clean_user_message_with_bot_uid_single_mention(self):
        """Test clean_user_message with single bot mention at start."""
        result = slack_utils.clean_user_message("<@U1234567890> hello world", "U1234567890")
        assert result == "hello world"

    def test_clean_user_message_with_bot_uid_multiple_mentions(self):
        """Test clean_user_message with multiple bot mentions at start."""
        result = slack_utils.clean_user_message("<@U1234567890> <@U1234567890> hello world", "U1234567890")
        assert result == "hello world"

    def test_clean_user_message_with_bot_uid_mention_with_colon(self):
        """Test clean_user_message with bot mention followed by colon."""
        result = slack_utils.clean_user_message("<@U1234567890>: hello world", "U1234567890")
        assert result == "hello world"

    def test_clean_user_message_with_bot_uid_mention_with_comma(self):
        """Test clean_user_message with bot mention followed by comma."""
        result = slack_utils.clean_user_message("<@U1234567890>, hello world", "U1234567890")
        assert result == "hello world"

    def test_clean_user_message_with_bot_uid_mention_with_colon_and_comma(self):
        """Test clean_user_message with bot mention followed by colon and comma."""
        result = slack_utils.clean_user_message("<@U1234567890>:, hello world", "U1234567890")
        assert result == ", hello world"  # The regex only matches : or , separately, not both

    def test_clean_user_message_with_bot_uid_whitespace_before_mention(self):
        """Test clean_user_message with whitespace before bot mention."""
        result = slack_utils.clean_user_message("  <@U1234567890> hello world", "U1234567890")
        assert result == "hello world"

    def test_clean_user_message_with_bot_uid_whitespace_after_mention(self):
        """Test clean_user_message with whitespace after bot mention."""
        result = slack_utils.clean_user_message("<@U1234567890>   hello world", "U1234567890")
        assert result == "hello world"

    def test_clean_user_message_with_bot_uid_multiple_whitespace(self):
        """Test clean_user_message with multiple whitespace around mentions."""
        result = slack_utils.clean_user_message("  <@U1234567890>  <@U1234567890>  hello world  ", "U1234567890")
        assert result == "hello world"

    def test_clean_user_message_with_bot_uid_no_mention(self):
        """Test clean_user_message with no bot mention."""
        result = slack_utils.clean_user_message("hello world", "U1234567890")
        assert result == "hello world"

    def test_clean_user_message_with_bot_uid_mention_in_middle(self):
        """Test clean_user_message with bot mention in middle of message."""
        result = slack_utils.clean_user_message("hello <@U1234567890> world", "U1234567890")
        assert result == "hello <@U1234567890> world"  # Should not remove middle mentions

    def test_clean_user_message_with_bot_uid_mention_at_end(self):
        """Test clean_user_message with bot mention at end of message."""
        result = slack_utils.clean_user_message("hello world <@U1234567890>", "U1234567890")
        assert result == "hello world <@U1234567890>"  # Should not remove end mentions

    def test_clean_user_message_with_bot_uid_different_bot_mention(self):
        """Test clean_user_message with different bot mention."""
        result = slack_utils.clean_user_message("<@U9876543210> hello world", "U1234567890")
        assert result == "<@U9876543210> hello world"  # Should not remove different bot

    def test_clean_user_message_with_bot_uid_mixed_mentions(self):
        """Test clean_user_message with mixed bot mentions."""
        result = slack_utils.clean_user_message("<@U1234567890> <@U9876543210> hello world", "U1234567890")
        assert result == "<@U9876543210> hello world"  # Should only remove matching bot

    def test_clean_user_message_with_bot_uid_empty_string(self):
        """Test clean_user_message with empty string."""
        result = slack_utils.clean_user_message("", "U1234567890")
        assert result == ""

    def test_clean_user_message_with_bot_uid_whitespace_only(self):
        """Test clean_user_message with whitespace only."""
        result = slack_utils.clean_user_message("   ", "U1234567890")
        assert result == ""

    def test_clean_user_message_with_bot_uid_only_mention(self):
        """Test clean_user_message with only bot mention."""
        result = slack_utils.clean_user_message("<@U1234567890>", "U1234567890")
        assert result == ""

    def test_clean_user_message_with_bot_uid_only_mention_with_punctuation(self):
        """Test clean_user_message with only bot mention and punctuation."""
        result = slack_utils.clean_user_message("<@U1234567890>:", "U1234567890")
        assert result == ""

    def test_clean_user_message_with_bot_uid_special_characters_in_uid(self):
        """Test clean_user_message with special characters in bot UID."""
        special_uid = "U123-456_7890"
        result = slack_utils.clean_user_message(f"<@{special_uid}> hello world", special_uid)
        assert result == "hello world"

    def test_clean_user_message_with_bot_uid_unicode_characters(self):
        """Test clean_user_message with unicode characters."""
        result = slack_utils.clean_user_message("<@U1234567890> hello 世界", "U1234567890")
        assert result == "hello 世界"

    def test_clean_user_message_with_bot_uid_newlines(self):
        """Test clean_user_message with newlines."""
        result = slack_utils.clean_user_message("<@U1234567890>\nhello world", "U1234567890")
        assert result == "hello world"

    def test_clean_user_message_with_bot_uid_tabs(self):
        """Test clean_user_message with tabs."""
        result = slack_utils.clean_user_message("<@U1234567890>\thello world", "U1234567890")
        assert result == "hello world"

    def test_clean_user_message_with_bot_uid_complex_pattern(self):
        """Test clean_user_message with complex mention pattern."""
        result = slack_utils.clean_user_message("  <@U1234567890>: <@U1234567890>, hello world  ", "U1234567890")
        assert result == "hello world"

    def test_clean_user_message_with_bot_uid_none_bot_uid(self):
        """Test clean_user_message with None bot_uid."""
        result = slack_utils.clean_user_message("<@U1234567890> hello world", None)
        assert result == "<@U1234567890> hello world"  # Should not remove anything

    def test_clean_user_message_with_bot_uid_empty_bot_uid(self):
        """Test clean_user_message with empty bot_uid."""
        result = slack_utils.clean_user_message("<@U1234567890> hello world", "")
        assert result == "<@U1234567890> hello world"  # Should not remove anything

    def test_clean_user_message_with_bot_uid_none_raw_text(self):
        """Test clean_user_message with None raw_text."""
        result = slack_utils.clean_user_message(None, "U1234567890")
        assert result == "None"  # str(None) converts to "None"

    def test_clean_user_message_with_bot_uid_non_string_raw_text(self):
        """Test clean_user_message with non-string raw_text."""
        result = slack_utils.clean_user_message(123, "U1234567890")
        assert result == "123"

    def test_clean_user_message_with_bot_uid_very_long_message(self):
        """Test clean_user_message with very long message."""
        long_message = "<@U1234567890> " + "hello " * 1000
        result = slack_utils.clean_user_message(long_message, "U1234567890")
        expected = ("hello " * 1000).strip()  # Note: the trailing space is removed by strip()
        assert result == expected

    def test_clean_user_message_with_bot_uid_regex_special_chars_in_uid(self):
        """Test clean_user_message with regex special characters in UID."""
        special_uid = "U123.456+7890"
        result = slack_utils.clean_user_message(f"<@{special_uid}> hello world", special_uid)
        assert result == "hello world"

    def test_clean_user_message_with_bot_uid_question_mark_in_uid(self):
        """Test clean_user_message with question mark in UID."""
        special_uid = "U123?456"
        result = slack_utils.clean_user_message(f"<@{special_uid}> hello world", special_uid)
        assert result == "hello world"

    def test_clean_user_message_with_bot_uid_parentheses_in_uid(self):
        """Test clean_user_message with parentheses in UID."""
        special_uid = "U123(456)7890"
        result = slack_utils.clean_user_message(f"<@{special_uid}> hello world", special_uid)
        assert result == "hello world"

    def test_clean_user_message_with_bot_uid_square_brackets_in_uid(self):
        """Test clean_user_message with square brackets in UID."""
        special_uid = "U123[456]7890"
        result = slack_utils.clean_user_message(f"<@{special_uid}> hello world", special_uid)
        assert result == "hello world"

    def test_clean_user_message_with_bot_uid_curly_braces_in_uid(self):
        """Test clean_user_message with curly braces in UID."""
        special_uid = "U123{456}7890"
        result = slack_utils.clean_user_message(f"<@{special_uid}> hello world", special_uid)
        assert result == "hello world"

    def test_clean_user_message_with_bot_uid_pipe_in_uid(self):
        """Test clean_user_message with pipe character in UID."""
        special_uid = "U123|456"
        result = slack_utils.clean_user_message(f"<@{special_uid}> hello world", special_uid)
        assert result == "hello world"

    def test_clean_user_message_with_bot_uid_caret_in_uid(self):
        """Test clean_user_message with caret in UID."""
        special_uid = "U123^456"
        result = slack_utils.clean_user_message(f"<@{special_uid}> hello world", special_uid)
        assert result == "hello world"

    def test_clean_user_message_with_bot_uid_dollar_in_uid(self):
        """Test clean_user_message with dollar sign in UID."""
        special_uid = "U123$456"
        result = slack_utils.clean_user_message(f"<@{special_uid}> hello world", special_uid)
        assert result == "hello world"


class TestChannelHistoryFunctions:
    """Test channel history fetching functions."""

    @pytest.mark.asyncio
    async def test_fetch_channel_history_includes_threads(self, monkeypatch):
        """Test fetch_channel_history includes thread expansion and message simplification."""
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
        assert result["next_cursor"] is None

    @pytest.mark.asyncio
    async def test_fetch_channel_history_exposes_next_cursor(self, monkeypatch):
        """Verify pagination cursors are surfaced and accepted."""

        class DummyClient:
            def __init__(self):
                self.history_calls = []

            async def conversations_history(self, **kwargs):
                self.history_calls.append(kwargs)
                if len(self.history_calls) == 1:
                    return {
                        "ok": True,
                        "messages": [{"ts": "1.0", "user": "U1", "text": "page one"}],
                        "has_more": True,
                        "response_metadata": {"next_cursor": "cursor_next"},
                    }
                return {
                    "ok": True,
                    "messages": [{"ts": "2.0", "user": "U2", "text": "page two"}],
                    "has_more": False,
                    "response_metadata": {"next_cursor": ""},
                }

            async def conversations_replies(self, **kwargs):
                raise AssertionError("Threads should not be fetched in this test")

        dummy_client = DummyClient()
        monkeypatch.setattr(slack_utils, "slack_client", dummy_client)

        first_page = await slack_utils.fetch_channel_history("C123", limit=3)
        assert first_page["truncated"] is True
        assert first_page["next_cursor"] == "cursor_next"
        assert first_page["requested"]["cursor"] is None

        second_page = await slack_utils.fetch_channel_history("C123", limit=3, cursor="cursor_next")
        assert second_page["truncated"] is False
        assert second_page["next_cursor"] is None
        assert dummy_client.history_calls[1]["cursor"] == "cursor_next"


class TestBuildConversationMessages:
    """Test the build_conversation_messages function."""

    def test_build_conversation_messages_skips_duplicate_event(self, monkeypatch):
        """Verify triggering message from history is not duplicated."""
        from slack_types import ThreadHistoryMessage
        
        # Mock format_ts_utc to return consistent timestamps
        monkeypatch.setattr(slack_utils, "format_ts_utc", lambda ts: f"[{ts}]")
        
        # Pre-formatted history (as if user names were already resolved)
        thread_history: List[ThreadHistoryMessage] = [
            {"ts": "100.0", "user": "U1", "text": "first message"},
            {"ts": "200.0", "user": "U2", "text": "second message"},
            {"ts": "300.0", "user": "U3", "text": "triggering message"},
        ]
        
        messages = slack_utils.build_conversation_messages(
            system_prompt="You are a bot",
            thread_history=thread_history,
            current_event_ts="300.0",  # Same as last message in history
            current_user_display="Charlie",
            current_user_id="U3",
            current_message_text="triggering message",
            bot_name="TestBot",
            history_limit=20,
        )
        
        # Count occurrences of "triggering message"
        triggering_content = [m["content"] for m in messages if "triggering message" in m["content"]]
        assert len(triggering_content) == 1, f"Expected 1 occurrence of 'triggering message', got {len(triggering_content)}: {triggering_content}"
        
        # Verify structure: system + history (excluding duplicate) + current
        assert len(messages) == 4  # system + 2 history + 1 current
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are a bot"
        
        # The last message should be the current user message
        assert messages[-1]["role"] == "user"
        assert "triggering message" in messages[-1]["content"]
        assert "Charlie" in messages[-1]["content"]

    def test_build_conversation_messages_with_bot_messages(self, monkeypatch):
        """Verify bot messages are marked as assistant role."""
        from slack_types import ThreadHistoryMessage
        
        monkeypatch.setattr(slack_utils, "format_ts_utc", lambda ts: f"[{ts}]")
        
        thread_history: List[ThreadHistoryMessage] = [
            {"ts": "100.0", "user": "U1", "text": "user question"},
            {"ts": "200.0", "bot_id": "B123", "text": "bot response", "username": "testbot"},
        ]
        
        messages = slack_utils.build_conversation_messages(
            system_prompt="You are a bot",
            thread_history=thread_history,
            current_event_ts="300.0",
            current_user_display="Alice",
            current_user_id="U1",
            current_message_text="follow up",
            bot_name="TestBot",
            history_limit=20,
        )
        
        # Find the bot message
        bot_messages = [m for m in messages if m["role"] == "assistant"]
        assert len(bot_messages) == 1
        assert "bot response" in bot_messages[0]["content"]
        assert "TestBot" in bot_messages[0]["content"]  # Should use provided bot_name

    def test_build_conversation_messages_empty_history(self, monkeypatch):
        """Verify function works with empty thread history."""
        from slack_types import ThreadHistoryMessage
        
        monkeypatch.setattr(slack_utils, "format_ts_utc", lambda ts: f"[{ts}]")
        
        messages = slack_utils.build_conversation_messages(
            system_prompt="You are a bot",
            thread_history=[],
            current_event_ts="100.0",
            current_user_display="Alice",
            current_user_id="U1",
            current_message_text="hello",
            bot_name="TestBot",
            history_limit=20,
        )
        
        # Should have system + current message only
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "hello" in messages[1]["content"]

    def test_build_conversation_messages_respects_history_limit(self, monkeypatch):
        """Verify function respects history_limit parameter."""
        from slack_types import ThreadHistoryMessage
        
        monkeypatch.setattr(slack_utils, "format_ts_utc", lambda ts: f"[{ts}]")
        
        # Create more history than the limit
        thread_history: List[ThreadHistoryMessage] = [
            {"ts": f"{i}.0", "user": "U1", "text": f"message {i}"}
            for i in range(1, 6)  # 5 messages
        ]
        
        messages = slack_utils.build_conversation_messages(
            system_prompt="You are a bot",
            thread_history=thread_history,
            current_event_ts="6.0",
            current_user_display="Alice",
            current_user_id="U1",
            current_message_text="current",
            bot_name="TestBot",
            history_limit=3,  # Only 3 history messages should be included
        )
        
        # Should have system + 3 history + 1 current = 5 total
        assert len(messages) == 5
        assert messages[0]["role"] == "system"
        assert messages[-1]["role"] == "user"
        
        # Should include the last 3 history messages (3, 4, 5)
        history_messages = [m for m in messages[1:-1] if m["role"] == "user"]
        assert len(history_messages) == 3
        assert "message 3" in history_messages[0]["content"]
        assert "message 4" in history_messages[1]["content"]
        assert "message 5" in history_messages[2]["content"]


class TestChannelDescriptorFunctions:
    """Test the get_channel_descriptor function."""

    def test_im_channel(self):
        """Test direct message channel descriptor."""
        result = slack_utils.get_channel_descriptor("D1234567890", "im")
        assert result == "D1234567890 (direct message)"

    def test_public_channel(self):
        """Test public channel descriptor."""
        result = slack_utils.get_channel_descriptor("C1234567890", "channel")
        assert result == "C1234567890 (public channel)"

    def test_private_channel(self):
        """Test private channel descriptor."""
        result = slack_utils.get_channel_descriptor("G1234567890", "group")
        assert result == "G1234567890 (private channel)"

    def test_mpim_channel(self):
        """Test multi-person direct message descriptor."""
        result = slack_utils.get_channel_descriptor("G1234567890", "mpim")
        assert result == "G1234567890 (multi-person DM)"

    def test_unknown_channel_type(self):
        """Test unknown channel type returns the type as-is."""
        result = slack_utils.get_channel_descriptor("C1234567890", "unknown_type")
        assert result == "C1234567890 (unknown_type)"

    def test_none_channel_type(self):
        """Test None channel type returns just the channel ID."""
        result = slack_utils.get_channel_descriptor("C1234567890", None)
        assert result == "C1234567890"

    def test_empty_string_channel_type(self):
        """Test empty string channel type returns just the channel ID."""
        result = slack_utils.get_channel_descriptor("C1234567890", "")
        assert result == "C1234567890"

    def test_non_string_channel(self):
        """Test non-string channel returns None."""
        result = slack_utils.get_channel_descriptor(123, "channel")
        assert result is None

    def test_non_string_channel_with_none_type(self):
        """Test non-string channel with None type returns None."""
        result = slack_utils.get_channel_descriptor(123, None)
        assert result is None

    def test_none_channel(self):
        """Test None channel returns None."""
        result = slack_utils.get_channel_descriptor(None, "channel")
        assert result is None

    def test_empty_string_channel(self):
        """Test empty string channel returns empty string."""
        result = slack_utils.get_channel_descriptor("", "channel")
        assert result == " (public channel)"

    def test_whitespace_channel(self):
        """Test whitespace-only channel returns whitespace with type."""
        result = slack_utils.get_channel_descriptor("   ", "channel")
        assert result == "    (public channel)"

    def test_channel_with_special_characters(self):
        """Test channel ID with special characters."""
        result = slack_utils.get_channel_descriptor("C123-ABC_456", "channel")
        assert result == "C123-ABC_456 (public channel)"

    def test_all_channel_types(self):
        """Test all known channel types."""
        test_cases = [
            ("im", "direct message"),
            ("mpim", "multi-person DM"),
            ("group", "private channel"),
            ("channel", "public channel"),
        ]
        
        for channel_type, expected_label in test_cases:
            result = slack_utils.get_channel_descriptor("C1234567890", channel_type)
            assert result == f"C1234567890 ({expected_label})"

    def test_channel_type_case_sensitivity(self):
        """Test that channel type matching is case sensitive."""
        result = slack_utils.get_channel_descriptor("C1234567890", "CHANNEL")
        assert result == "C1234567890 (CHANNEL)"

    def test_channel_type_with_whitespace(self):
        """Test channel type with leading/trailing whitespace."""
        result = slack_utils.get_channel_descriptor("C1234567890", " channel ")
        assert result == "C1234567890 ( channel )"

    @pytest.mark.parametrize("channel_type,expected_label", [
        ("im", "direct message"),
        ("mpim", "multi-person DM"),
        ("group", "private channel"),
        ("channel", "public channel"),
        ("unknown", "unknown"),
        ("", ""),
        (None, None),
    ])
    def test_channel_types_parametrized(self, channel_type, expected_label):
        """Test various channel types with parametrized test."""
        result = slack_utils.get_channel_descriptor("C1234567890", channel_type)
        if expected_label is None:
            assert result == "C1234567890"
        elif expected_label == "":
            assert result == "C1234567890"
        else:
            assert result == f"C1234567890 ({expected_label})"

    @pytest.mark.parametrize("channel,channel_type,expected", [
        # Valid string channels
        ("D1234567890", "im", "D1234567890 (direct message)"),
        ("C1234567890", "channel", "C1234567890 (public channel)"),
        ("G1234567890", "group", "G1234567890 (private channel)"),
        ("G1234567890", "mpim", "G1234567890 (multi-person DM)"),
        ("C1234567890", "unknown", "C1234567890 (unknown)"),
        ("C1234567890", None, "C1234567890"),
        ("C1234567890", "", "C1234567890"),
        
        # Invalid channels (non-string)
        (123, "channel", None),
        (None, "channel", None),
        ([], "channel", None),
        ({}, "channel", None),
        (True, "channel", None),
    ])
    def test_comprehensive_scenarios(self, channel, channel_type, expected):
        """Test comprehensive scenarios with parametrized test."""
        result = slack_utils.get_channel_descriptor(channel, channel_type)
        assert result == expected
