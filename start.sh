#!/bin/bash
set -e
echo "[STARTUP] Starting Tor..."
tor &
sleep 5
echo "[STARTUP] Tor should be ready"
echo "[STARTUP] Starting Flask..."
exec python app.py
