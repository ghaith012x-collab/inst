#!/bin/bash
set -e

echo "[STARTUP] Initializing container..."

# Start tor in foreground or with proper daemon management
tor &
TOR_PID=$!
sleep 4

# Verify tor is working
if curl -s --socks5-hostname 127.0.0.1:9050 https://check.torproject.org | grep -q "Congratulations"; then
    echo "[STARTUP] Tor is running and functional"
else
    echo "[STARTUP] WARNING: Tor check failed, continuing anyway"
fi

# Verify python deps
python -c "import flask" || { echo "[STARTUP] Flask missing"; exit 1; }
python -c "from playwright.sync_api import sync_playwright" || { echo "[STARTUP] Playwright missing"; exit 1; }
python -c "import requests" || { echo "[STARTUP] Requests missing"; exit 1; }

echo "[STARTUP] All dependencies verified"
echo "[STARTUP] Starting Flask on port 8080"

# Run flask - this must stay in foreground
exec python app.py
