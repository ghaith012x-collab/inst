#!/bin/bash
set -e

echo "[STARTUP] Configuring Tor..."
cp /app/torrc /etc/tor/torrc 2>/dev/null || true

echo "[STARTUP] Starting Tor daemon in background..."
tor -f /app/torrc > /dev/null 2>&1 &
echo "[STARTUP] Tor PID: $!"

# Don't wait for Tor - start Flask immediately
echo "[STARTUP] Starting Flask on port ${PORT:-8080}..."
exec python app.py