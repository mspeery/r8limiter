# Dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps (curl only for health/debug)
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Copy and install
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY app ./app
COPY tests ./tests

# Expose & run
EXPOSE 8000
CMD ["uvicorn", "app.app_async:app", "--host", "0.0.0.0", "--port", "8000"]