FROM python:3.12-slim

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Embedding model (int8 ONNX export of intfloat/multilingual-e5-small, ~118MB),
# baked into the image so startup needs no network.
# http_proxy/https_proxy come in as build args from docker-compose.yml.
ARG E5_REPO=Xenova/multilingual-e5-small
RUN mkdir -p /models/multilingual-e5-small && cd /models/multilingual-e5-small && \
    for f in onnx/model_quantized.onnx tokenizer.json config.json; do \
      curl -fsSL --retry 3 -o "$(basename $f)" "https://huggingface.co/$E5_REPO/resolve/main/$f"; \
    done

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py chunker.py bm25.py embedder.py vault_client.py ./

EXPOSE 8081

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -sf --max-time 4 http://localhost:8081/health > /dev/null || exit 1

CMD ["python", "server.py"]
