#!/bin/bash
echo "[STARTUP] Starting Flask on port ${PORT:-8080}..."
exec python app.py