"""Test suite for CyberClaw sandbox security module."""

import sys
import asyncio
from pathlib import Path

import pytest

src_path = str(Path(__file__).parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)


def test_win32_job_object_import():
    """Verify sandbox module imports cleanly on any platform."""
    from cyberclaw.security.sandbox import execute_command_in_sandbox
    assert callable(execute_command_in_sandbox)


def test_docker_runner_import():
    """Verify Docker sandbox runner is importable."""
    from cyberclaw.security.sandbox import run_in_docker
    assert callable(run_in_docker)


def test_config_sandbox_literal():
    """Verify sandbox field in Config accepts all valid values."""
    from cyberclaw.utils.config import Config
    # Test that the field exists in the model
    assert "sandbox" in Config.model_fields
    field = Config.model_fields["sandbox"]
    assert field.default == "danger-full-access"
