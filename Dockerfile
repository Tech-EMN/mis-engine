# MIS Engine — Dockerfile
# Railway auto-detects and builds from this file.

FROM python:3.11-slim

WORKDIR /app

# System deps for ezdxf + poppler (PDF support)
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Source code
COPY . .

# Healthcheck using curl (more reliable than urllib in container)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost:8000/api/v1/health || exit 1

EXPOSE 8000

# Use uvicorn directly for reliable startup
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
