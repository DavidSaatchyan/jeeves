FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential curl \
 && rm -rf /var/lib/apt/lists/*

COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api/app ./app
COPY api/alembic ./alembic
COPY api/alembic.ini .
COPY config.yaml .
COPY frontend ./frontend

EXPOSE 8000

# Default: run API server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Alternative entrypoints for worker processes:
# docker run --entrypoint "python" ... -m app.workers.scheduler
# docker run --entrypoint "python" ... -m app.workers.event_worker
# docker run --entrypoint "python" ... -m app.workers.workflow_worker
