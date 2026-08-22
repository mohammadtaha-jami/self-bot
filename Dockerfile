FROM python:3.11-slim

WORKDIR /app

# نصب پیش‌نیازهای سیستم‌عامل
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# کپی و نصب کتابخانه‌ها
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# کپی کل پروژه
COPY . .

CMD ["python"]