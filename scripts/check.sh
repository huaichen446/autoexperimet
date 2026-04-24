#!/usr/bin/env sh
set -eu

echo "Running full test suite..."
PYTHONPATH=src pytest -q

echo "Running Phase 6 runtime test slice..."
PYTHONPATH=src pytest tests/runtime/test_phase6_runtime.py -q
