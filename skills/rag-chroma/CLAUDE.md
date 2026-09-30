# CLAUDE.md — rag-chroma

## Key Concepts

**rag-mcp's memory has two levels: ~0.8–0.9 GB during a full re-index, ~330 MiB idle.** Measured 2026-09-29 with `docker stats`: 10 hours after the 12:35 rebuild, rag-mcp held 331 MiB (chromadb 108 MiB), so the post-inference working memory is eventually released rather than kept for good, as first assumed. The idle figure is roughly imports + the int8 e5 model + the BM25 index. What makes it possible: the int8 `model_quantized.onnx`, `enable_cpu_mem_arena = False`, batches of 4 (`rag-mcp/embedder.py`), and `MALLOC_ARENA_MAX=2` plus `MALLOC_TRIM_THRESHOLD_=0` in `docker-compose.yml`. Expect the peak again after anything that forces a full re-index (a `CHUNKER_VERSION` bump, an embed-model change). Don't confuse this with the image size, which stays ~1.05 GB on disk.
