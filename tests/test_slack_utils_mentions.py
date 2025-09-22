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

from slack_utils import normalise_user_mentions


def test_normalise_user_mentions_wraps_ids():
    text = "Ping @UH4AMCRA7 and @WABC12345 in thread"
    expected = "Ping <@UH4AMCRA7> and <@WABC12345> in thread"
    assert normalise_user_mentions(text) == expected


def test_normalise_user_mentions_ignores_existing_markup():
    text = "Already <@UH4AMCRA7> linked"
    assert normalise_user_mentions(text) == text


def test_normalise_user_mentions_ignores_special_tokens():
    text = "Alert @here and @channel now"
    assert normalise_user_mentions(text) == text


def test_normalise_user_mentions_handles_non_string():
    assert normalise_user_mentions(None) == ""
