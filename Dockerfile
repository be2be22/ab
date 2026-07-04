FROM python:3.12-slim

WORKDIR /app

# ابزارهای پایه شل که ایجنت ممکنه بهشون نیاز داشته باشه
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    procps \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# مسیر ذخیره‌سازی SQLite - اگه یه Volume روی Railway وصل کنی به /data، دیتا بین دیپلوی‌ها می‌مونه
RUN mkdir -p /data

CMD ["python", "main.py"]
