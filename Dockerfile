# MIS Engine — Dockerfile
# Multi-stage build: slim Python base, install deps, copy source.
#
# Usage:
#   docker build -t mis-engine .
#   docker run -p 8000:8000 -e MIS_SECRETS_PATH=/run/secrets/mis-secrets mis-engine
#
# Railway: auto-detects Dockerfile
# Render:  set "Docker" as runtime in render.yaml or dashboard

FROM python:3.11-slim

WORKDIR /app

# System deps for ezdxf + poppler (PDF support)
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Source code
COPY . .

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')" || exit 1

EXPOSE 8000

CMD ["python", "main.py"]
