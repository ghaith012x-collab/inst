FROM python:3.11-bookworm

RUN apt-get update && apt-get install -y \
    tor curl libnss3 libatk-bridge2.0-0 libxss1 libgtk-3-0 libgbm1 \
    libasound2 fonts-liberation libappindicator3-1 libxtst6 libxrandr2 \
    libxcomposite1 libxdamage1 libxi6 libpangocairo-1.0-0 libpango-1.0-0 \
    libatk1.0-0 libcairo-gobject2 libcairo2 libgdk-pixbuf2.0-0 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium
RUN playwright install-deps chromium

COPY . .
RUN mkdir -p /app/buster
RUN chmod +x start.sh

EXPOSE 8080

CMD ["./start.sh"]
