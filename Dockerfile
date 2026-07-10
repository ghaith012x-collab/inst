FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    tor \
    curl \
    libnss3 \
    libatk-bridge2.0-0 \
    libxss1 \
    libgtk-3-0 \
    libgbm1 \
    libasound2 \
    fonts-liberation \
    libappindicator3-1 \
    libxtst6 \
    libxrandr2 \
    libxcomposite1 \
    libxdamage1 \
    libxi6 \
    libpangocairo-1.0-0 \
    libpango-1.0-0 \
    libatk1.0-0 \
    libcairo-gobject2 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ENV PLAYWRIGHT_BROWSERS_PATH=/app/ms-playwright
RUN playwright install chromium
RUN playwright install-deps chromium

COPY . .

RUN mkdir -p /app/buster

EXPOSE 8080

CMD ["sh", "-c", "tor --runasdaemon 1 && sleep 3 && curl -s --socks5-hostname 127.0.0.1:9050 https://check.torproject.org | grep -o 'Congratulations' || echo 'TOR_FAILED' && python app.py"]
