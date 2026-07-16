# MIS Engine — Dockerfile v3
# Minimal image, explicit startup logging

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils curl procps \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Log startup to both stdout and a file
RUN echo '#!/bin/bash\n\
echo "=== $(date): MIS Engine startup ===" \n\
echo "Python: $(python3 --version)" \n\
echo "Files: $(ls /app/*.py | head -5)" \n\
echo "=== Starting uvicorn ===" \n\
cd /app && exec python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --log-level debug 2>&1' > /app/start.sh \
    && chmod +x /app/start.sh

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=5 \
    CMD curl -sf http://localhost:8000/api/v1/health || exit 1

EXPOSE 8000
CMD ["/app/start.sh"]
