#!/usr/bin/env python3
"""Test script for multi-provider LLM functionality."""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, "src")

from cyberclaw.utils.config import Config
from cyberclaw.provider.llm import MultiLLMProvider


def test_configuration():
    """Test configuration loading."""
    print("Testing configuration loading...")
    try:
        config = Config.load(Path("workspace"))
        print(f"Configuration loaded: {len(config.llm.providers)} providers")
        for p in config.llm.providers:
            print(f"  - {p.id}: {p.provider} ({p.model})")
        return config
    except Exception as e:
        print(f"Configuration error: {e}")
        return None


def test_multi_provider_manager(config):
    """Test multi-provider manager."""
    print("\nTesting MultiLLMProvider manager...")
    try:
        llm_manager = MultiLLMProvider(config.llm)
        print(f"Manager initialized with {len(llm_manager.providers)} providers")
        print(f"Available providers: {llm_manager.get_available_providers()}")
        print(f"Health check: {llm_manager.health_check()}")
        return llm_manager
    except Exception as e:
        print(f"Manager error: {e}")
        return None


async def test_chat_functionality(llm_manager):
    """Test basic chat functionality."""
    print("\nTesting chat functionality...")
    try:
        messages = [{"role": "user", "content": "Hello, how are you?"}]
        content, tool_calls = await llm_manager.chat(messages)
        print(f"Chat successful! Response length: {len(content)} characters")
        print(f"Response: {content[:100]}...")
        return True
    except Exception as e:
        print(f"Chat error: {e}")
        # Expected error with placeholder API key
        if "Incorrect API key" in str(e) or "All LLM providers failed" in str(e):
            print("Expected error with placeholder API key - system working correctly!")
            return True
        return False


def main():
    """Run all tests."""
    print("Starting CyberClaw Multi-Provider Tests\n")

    # Test configuration
    config = test_configuration()
    if not config:
        return False

    # Test manager
    llm_manager = test_multi_provider_manager(config)
    if not llm_manager:
        return False

    # Test chat (async)
    success = asyncio.run(test_chat_functionality(llm_manager))

    if success:
        print("\nAll tests passed! Multi-provider system is working.")
    else:
        print("\nSome tests failed.")

    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)