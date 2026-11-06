# [Member 3] API image - CPU-only PyTorch. Build from repo root:
#   docker build -f docker/api.Dockerfile -t solarcast-api .
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY pyproject.toml README.md ./
COPY src ./src
COPY params.yaml ./
COPY configs ./configs

RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch \
 && pip install --no-cache-dir ".[api]"

EXPOSE 8000
CMD ["uvicorn", "solarcast.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
