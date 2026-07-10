#!/bin/bash
set -e

echo "[STARTUP] Configuring Tor..."
# Ensure Tor config is in place
cp /app/torrc /etc/tor/torrc 2>/dev/null || true

echo "[STARTUP] Starting Tor daemon..."
tor -f /app/torrc &
TOR_PID=$!

# Wait for Tor to be ready
echo "[STARTUP] Waiting for Tor SOCKS proxy on 127.0.0.1:9050..."
for i in $(seq 1 30); do
    if curl -s --socks5-hostname 127.0.0.1:9050 https://check.torproject.org/api/ip 2>/dev/null | grep -q '"IsTor":true'; then
        echo "[STARTUP] ✅ Tor is ready (attempt $i)"
        break
    fi
    sleep 1
done

echo "[STARTUP] Starting Flask on port ${PORT:-8080}..."
exec python app.py
