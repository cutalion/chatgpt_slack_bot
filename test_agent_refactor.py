#!/usr/bin/env python
"""Quick test to verify agent provider refactor works correctly."""

import sys
sys.path.insert(0, 'bot')

print("Testing agent provider imports...")

# Test 1: Import agent_provider
try:
    from bot.agent_provider import get_agent_provider, AgentProvider
    print("✓ agent_provider imports successfully")
except Exception as e:
    print(f"✗ Failed to import agent_provider: {e}")
    sys.exit(1)

# Test 2: Import llm
try:
    from bot.llm import generate_ai_reply
    print("✓ llm imports successfully")
except Exception as e:
    print(f"✗ Failed to import llm: {e}")
    sys.exit(1)

# Test 3: Get agent provider instance
try:
    agent = get_agent_provider()
    print(f"✓ get_agent_provider() returns: {type(agent).__name__}")
except Exception as e:
    print(f"✗ Failed to get agent provider: {e}")
    sys.exit(1)

# Test 4: Verify agent has generate_reply method
try:
    assert hasattr(agent, 'generate_reply'), "Agent must have generate_reply method"
    assert callable(agent.generate_reply), "generate_reply must be callable"
    print("✓ Agent has generate_reply method")
except Exception as e:
    print(f"✗ Agent validation failed: {e}")
    sys.exit(1)

print("\n✅ All agent provider refactor tests passed!")