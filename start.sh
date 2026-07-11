#!/bin/bash
set -e

echo "[STARTUP] Configuring Tor..."
cp /app/torrc /etc/tor/torrc 2>/dev/null || true

echo "[STARTUP] Starting Tor daemon..."
tor -f /app/torrc &
TOR_PID=$!

# Wait for Tor to be ready with a timeout - don't block startup
echo "[STARTUP] Waiting for Tor SOCKS proxy on 127.0.0.1:9050..."
TOR_READY=false
for i in $(seq 1 10); do
    if curl -s --socks5-hostname 127.0.0.1:9050 https://check.torproject.org/api/ip 2>/dev/null | grep -q '"IsTor":true'; then
        echo "[STARTUP] ✅ Tor is ready (attempt $i)"
        TOR_READY=true
        break
    fi
    echo "[STARTUP] Waiting for Tor... ($i/10)"
    sleep 1
done

if [ "$TOR_READY" = false ]; then
    echo "[STARTUP] ⚠️ Tor not ready after 10s - continuing without Tor proxy"
    kill $TOR_PID 2>/dev/null || true
fi

echo "[STARTUP] Starting Flask on port ${PORT:-8080}..."
exec python app.py