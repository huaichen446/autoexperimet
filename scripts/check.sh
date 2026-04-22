#!/usr/bin/env sh
set -eu

echo "Running full test suite..."
PYTHONPATH=src pytest -q

echo "Running acceptance test slice..."
PYTHONPATH=src pytest tests/acceptance/test_phase4_acceptance.py -q
