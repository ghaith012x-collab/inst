FROM python:3.11-bookworm

RUN apt-get update && apt-get install -y \
    tor curl netcat-openbsd \
    libnss3 libatk-bridge2.0-0 libxss1 libgtk-3-0 libgbm1 \
    libasound2 fonts-liberation libappindicator3-1 libxtst6 libxrandr2 \
    libxcomposite1 libxdamage1 libxi6 libpangocairo-1.0-0 libpango-1.0-0 \
    libatk1.0-0 libcairo-gobject2 libcairo2 libgdk-pixbuf2.0-0 libglib2.0-0 \
    libdrm2 libxkbcommon0 libenchant-2-2 libsecret-1-0 libmanette-0.2-0 \
    libgles2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium
RUN playwright install-deps chromium

COPY . .
RUN chmod +x start.sh

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/status || exit 1

CMD ["./start.sh"]
