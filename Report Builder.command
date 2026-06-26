#!/bin/bash
cd "$(dirname "$0")"
PORT=8011

# Kill any existing server on this port
lsof -ti :$PORT 2>/dev/null | xargs kill 2>/dev/null
sleep 0.5

echo "Starting Report Builder on http://127.0.0.1:$PORT/"
echo ""

# Open browser after a short delay
(sleep 1.5 && open "http://127.0.0.1:$PORT/") &

# Start the server (blocks until Ctrl-C)
python3 tools/report_builder_server.py $PORT
