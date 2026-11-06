# [Member 3] Dashboard image.
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY pyproject.toml README.md ./
COPY src ./src
COPY params.yaml ./
COPY configs ./configs

RUN pip install --no-cache-dir ".[dashboard]"

EXPOSE 8501
CMD ["streamlit", "run", "src/solarcast/dashboard/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
