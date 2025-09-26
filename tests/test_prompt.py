import re

from bot.prompt import build_system_prompt

def test_system_prompt_contains_core_sections():
    prompt = build_system_prompt(bot_name="HelperBot", web_search_enabled=True, web_search_strict=True)
    assert isinstance(prompt, str)
    assert "<core_instructions>" in prompt
    assert "HelperBot" in prompt
    assert "<tools>" in prompt
    assert re.search(r"web_search", prompt)


def test_system_prompt_mentions_slack_tools():
    prompt = build_system_prompt(slack_tools_enabled=True)
    assert "get_user_info" in prompt
    assert "<tools>" in prompt
    assert "If you do not need a fixed period" in prompt


def test_system_prompt_includes_channel_metadata():
    prompt = build_system_prompt(
        current_channel_descriptor='C123 (public channel)',
        current_channel_id='C123',
        current_thread_ts='1723456789.123456',
    )
    assert '- Current channel: C123 (public channel)' in prompt
    assert '- Current channel ID: C123' in prompt
    assert '- Current thread root timestamp: 1723456789.123456' in prompt
