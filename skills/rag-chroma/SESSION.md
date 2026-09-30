# Sessions

## 2026-09-29 — Why the rag-mcp container "shrank"
Explained that the 1 GB → <500 MB drop the user saw was rag-mcp's memory use, not the image (still 1.05 GB on disk): after the morning's int8/arena-off/batch-4/malloc tuning and the 12:35 rebuild, rag-mcp sat at 0.8–0.9 GB during the re-index and settled to ~331 MiB once idle (chromadb ~108 MiB). No code changes.
