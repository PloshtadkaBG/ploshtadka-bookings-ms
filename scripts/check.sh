#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
BOLD='\033[1m'
RESET='\033[0m'

pass() { echo -e "${GREEN}✓ $1${RESET}"; }
fail() { echo -e "${RED}✗ $1${RESET}"; exit 1; }
step() { echo -e "\n${BOLD}==> $1${RESET}"; }

step "Ruff lint"
ruff check app/ tests/ && pass "lint" || fail "lint"

step "Ruff format"
ruff format --check app/ tests/ && pass "format" || fail "format"

step "Pytest + coverage"
pytest --cov=app --cov-report=term-missing && pass "tests" || fail "tests"

echo -e "\n${GREEN}${BOLD}All checks passed.${RESET}"
