#!/bin/bash
# Run the activity tracker daemon on the host machine
# This MUST run outside Docker to access browser, VS Code, etc.

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3.11 -m venv venv
    source venv/bin/activate
    pip install -e ".[web]"
    pip install aiohttp
else
    source venv/bin/activate
fi

echo "Starting Activity Tracker..."
echo "This must run on your local machine (not in Docker)"
echo ""

python -m agentic.tracker_daemon --data-dir ./data/activity --port 8001
