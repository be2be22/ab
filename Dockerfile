FROM node:20-slim AS frontend-builder
WORKDIR /app
COPY tma/package.json ./
RUN npm install
COPY tma/ ./
RUN npm run build

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
# Copy compiled frontend
COPY --from=frontend-builder /app/dist ./tma/dist

# مسیر ذخیره‌سازی SQLite - اگه یه Volume روی Railway وصل کنی به /data، دیتا بین دیپلوی‌ها می‌مونه
RUN mkdir -p /data

ENV PYTHONUNBUFFERED=1
EXPOSE 8080

CMD ["python", "-u", "main.py"]
