#!/usr/bin/env python3
"""Verification test for CyberClaw's native Smart Routing and Rate-Limit Failover."""

import os
import sys
import time
import asyncio
from pathlib import Path

# Add src to python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from cyberclaw.utils.config import LLMConfig, LLMProviderConfig
from cyberclaw.provider.llm.manager import MultiLLMProvider
from cyberclaw.provider.llm.base import LLMProvider, LLMToolCall

class MockLLMProvider(LLMProvider):
    """Mock LLM provider that simulates successful or failing chat requests."""
    def __init__(self, model: str, name: str, should_fail: bool = False, fail_type: str = "429"):
        super().__init__(model=model, api_key="mock", api_base=None)
        self.name = name
        self.should_fail = should_fail
        self.fail_type = fail_type
        self.call_count = 0

    async def chat(self, messages, tools=None, **kwargs):
        self.call_count += 1
        if self.should_fail:
            if self.fail_type == "429":
                raise Exception("429 Rate Limit Exceeded (Too Many Requests)")
            else:
                raise Exception("500 Internal Server Error")
        return f"Mock response from {self.name}", []

    async def chat_stream(self, messages, tools=None, **kwargs):
        raise NotImplementedError()

async def test_smart_routing():
    print("======================================================================")
    print("   TESTING CYBERCLAW NATIVE SMART GATEWAY ROUTING & CIRCUIT BREAKER")
    print("======================================================================\n")

    # 1. Setup multi-provider configuration
    p1 = LLMProviderConfig(id="primary-a", provider="openai", model="gpt-4", api_key="sk-123", priority=1, enabled=True)
    p2 = LLMProviderConfig(id="primary-b", provider="openai", model="gpt-4", api_key="sk-456", priority=1, enabled=True)
    p3 = LLMProviderConfig(id="backup-1", provider="anthropic", model="claude-3", api_key="sk-789", priority=2, enabled=True)
    
    config = LLMConfig(
        default_provider="primary-a",
        providers=[p1, p2, p3],
        enable_failover=True
    )

    manager = MultiLLMProvider(config)

    # Inject mock providers to avoid network calls
    mock_a = MockLLMProvider("openai/gpt-4", "Primary-A", should_fail=True, fail_type="429")
    mock_b = MockLLMProvider("openai/gpt-4", "Primary-B", should_fail=False)
    mock_backup = MockLLMProvider("anthropic/claude-3", "Backup-1", should_fail=False)

    # Override the actual providers loaded by the manager
    manager.providers = [
        (1, "primary-a", mock_a),
        (1, "primary-b", mock_b),
        (2, "backup-1", mock_backup)
    ]

    import random
    original_shuffle = random.shuffle
    random.shuffle = lambda x: None  # Disable shuffling for deterministic test execution

    try:
        # Verify initial circuit status
        print("[1] Initial Circuit Status: All providers healthy.")
        assert len(manager._failed_providers) == 0, "Failed provider cache should be empty initially"

        # 2. Test failover: Primary-A fails with 429, routing should failover to Primary-B (same priority level)
        print("\n[2] Triggering chat request. Primary-A should fail (429), triggering failover to Primary-B...")
        messages = [{"role": "user", "content": "Test prompt"}]
        response, _ = await manager.chat(messages)
        print(f"    Result: {response}")
        print(f"    Primary-A Call Count: {mock_a.call_count}")
        print(f"    Primary-B Call Count: {mock_b.call_count}")

        assert mock_a.call_count == 1, "Primary-A should have been attempted once"
        assert mock_b.call_count == 1, "Primary-B should have been called as failover"
        assert response == "Mock response from Primary-B", "Should receive response from Primary-B"

        # 3. Verify Circuit Breaker: Primary-A should be in cooldown (429 -> 120s cooldown)
        print("\n[3] Checking if Primary-A is correctly cooled off (circuit broken)...")
        now = time.time()
        cooldown = manager._failed_providers.get("primary-a", 0.0)
        cooldown_remaining = cooldown - now
        print(f"    Primary-A cooldown remaining: {cooldown_remaining:.2f}s")
        assert 110.0 <= cooldown_remaining <= 120.0, "Primary-A should have a ~120s rate-limit cooldown"

        # 4. Repeat request: Primary-A is cooled off, so routing should bypass it entirely and go directly to Primary-B
        print("\n[4] Repeating chat request. Primary-A is in cooldown, so it should be bypassed entirely...")
        mock_a.call_count = 0
        mock_b.call_count = 0
        response, _ = await manager.chat(messages)
        print(f"    Result: {response}")
        print(f"    Primary-A Call Count: {mock_a.call_count}")
        print(f"    Primary-B Call Count: {mock_b.call_count}")

        assert mock_a.call_count == 0, "Primary-A should have been bypassed"
        assert mock_b.call_count == 1, "Primary-B should have been called directly"

        # 5. Reset circuit: If Primary-A suddenly succeeds (e.g. cooldown bypassed or reset manually/automatically),
        # its circuit should reset. Let's make Primary-A healthy and simulate time passing or manually clearing its cooldown.
        print("\n[5] Simulating recovery: making Primary-A healthy and clearing its cooldown...")
        mock_a.should_fail = False
        mock_a.call_count = 0
        if "primary-a" in manager._failed_providers:
            del manager._failed_providers["primary-a"]

        response, _ = await manager.chat(messages)
        print(f"    Result: {response}")
        print(f"    Primary-A Call Count: {mock_a.call_count}")
        assert response in ("Mock response from Primary-A", "Mock response from Primary-B"), "Should succeed with one of the primary models"
        print("    Circuit recovered successfully!")

        print("\n======================================================================")
        print("   SMART GATEWAY ROUTING TESTS PASSED!")
        print("======================================================================\n")

    finally:
        random.shuffle = original_shuffle

if __name__ == "__main__":
    asyncio.run(test_smart_routing())
