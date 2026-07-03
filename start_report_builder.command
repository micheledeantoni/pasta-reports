#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
PYTHON_BIN="${PYTHON:-python3}"
PORT="${REPORT_BUILDER_PORT:-8011}"

echo "Checking portable PASTA paths..."
"${PYTHON_BIN}" tools/report_builder_server.py --check

echo
echo "Starting PASTA report builder"
echo "Preferred port: ${PORT} (will try 8011-8020 when using the default)"
"${PYTHON_BIN}" tools/report_builder_server.py --port "${PORT}"

echo
read -r -p "Server stopped. Press Enter to close this window..." _
