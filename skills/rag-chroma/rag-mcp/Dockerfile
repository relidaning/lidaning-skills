ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE}

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Embedding model (int8 ONNX export of intfloat/multilingual-e5-small, ~118MB),
# baked into the image so startup needs no network.
# http_proxy/https_proxy come in as build args from docker-compose.yml.
ARG E5_REPO=Xenova/multilingual-e5-small
ARG E5_REVISION=main
ARG E5_MODEL_FILE=model_quantized.onnx
RUN mkdir -p /models/multilingual-e5-small && cd /models/multilingual-e5-small && \
    for f in onnx/$E5_MODEL_FILE tokenizer.json config.json; do \
      curl -fsSL --retry 3 -o "$(basename $f)" "https://huggingface.co/$E5_REPO/resolve/$E5_REVISION/$f"; \
    done

COPY rag-mcp/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config.toml /config.toml
COPY rag-mcp/*.py ./
COPY rag-mcp/static ./static
# Bundle KaTeX for offline use under the inspector's same-origin CSP.
RUN curl -fsSL --retry 3 -o /tmp/katex.tgz https://registry.npmjs.org/katex/-/katex-0.19.1.tgz && \
    echo "24da5a599eb2fcede2e270b99a6ff48bca816beecc95feeb84e8cccbd1bb34fd  /tmp/katex.tgz" | sha256sum -c - && \
    tar -xzf /tmp/katex.tgz -C static --strip-components=2 package/dist/katex.min.js package/dist/contrib/auto-render.min.js && \
    tar -xOf /tmp/katex.tgz package/LICENSE > static/katex.LICENSE && rm /tmp/katex.tgz

ENV RAG_LOG_DIR=/skill/logs

EXPOSE 8081

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "from rag_config import CONFIG; import urllib.request; urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:%s/health' % CONFIG['RAG_PORT'], timeout=4).close()" || exit 1

CMD ["python", "server.py"]
