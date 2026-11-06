# [Member 1] Pipeline image for Prefect flows (ingestion, validation, monitoring, retraining).
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY pyproject.toml README.md ./
COPY src ./src
COPY params.yaml ./
COPY configs ./configs

RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch \
 && pip install --no-cache-dir ".[data,train]"

CMD ["python", "-m", "solarcast.flows.schedules"]
