FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential curl \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser \
 && chown -R appuser:appuser /app

COPY requirements.txt requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r requirements-worker.txt

COPY app ./app
COPY worker ./worker
COPY supervisord.conf .

RUN chown -R appuser:appuser /app

EXPOSE 8000

USER appuser

CMD ["supervisord", "-c", "supervisord.conf"]
