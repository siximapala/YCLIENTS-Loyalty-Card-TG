FROM python:3.10-slim

WORKDIR /app

# Установка зависимостей
RUN apt-get update && \
    apt-get install -y libpq-dev gcc && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY ./app ./app
COPY ./alembic ./alembic
COPY alembic.ini .


RUN mkdir -p /run/secrets && \
    chmod 755 /run/secrets

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

CMD ["bash", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
