# deploy/docker/Dockerfile

# ---- base (runtime) ----
FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY app/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
EXPOSE 8000
CMD ["uvicorn", "app.app_async:app", "--host", "0.0.0.0", "--port", "8000"]

# ---- test ----
FROM base AS test
RUN pip install --no-cache-dir pytest httpx pytest-asyncio
COPY tests ./tests
