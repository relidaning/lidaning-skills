FROM python:3.12-slim

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download ONNX embedding model (~80MB) so first request doesn't time out
COPY preload.py .
RUN python preload.py

COPY server.py .

EXPOSE 8081

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -s --max-time 4 http://localhost:8081/mcp > /dev/null || exit 1

CMD ["python", "server.py"]
