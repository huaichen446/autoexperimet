"""Smoke tests for the Phase 0 baseline."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


def test_package_imports() -> None:
    package_names = [
        "agent_runtime",
        "agent_runtime.models",
        "agent_runtime.execution",
        "agent_runtime.scheduling",
        "agent_runtime.acceptance",
        "agent_runtime.migration",
        "agent_runtime.common",
    ]

    for package_name in package_names:
        module = importlib.import_module(package_name)
        assert module is not None
