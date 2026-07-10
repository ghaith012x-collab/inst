FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    tor \
    libnss3 \
    libatk-bridge2.0-0 \
    libxss1 \
    libgtk-3-0 \
    libgbm1 \
    libasound2 \
    fonts-liberation \
    libappindicator3-1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ENV PLAYWRIGHT_BROWSERS_PATH=/app/ms-playwright
RUN playwright install chromium
RUN playwright install-deps chromium

COPY . .

RUN mkdir -p /app/buster
RUN mkdir -p /var/run/tor

COPY torrc /etc/tor/torrc

EXPOSE 5000

CMD tor & \
    sleep 5 && \
    curl --socks5-hostname 127.0.0.1:9050 https://check.torproject.org || echo "Tor check failed" && \
    python app.py
