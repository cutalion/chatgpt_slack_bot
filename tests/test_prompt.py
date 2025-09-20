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
