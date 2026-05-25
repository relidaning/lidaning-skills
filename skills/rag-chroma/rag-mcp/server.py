"""rag-mcp — Source-agnostic semantic search with Obsidian vault watcher.

MCP server that embeds text content via ChromaDB's built-in ONNX embedding
function (all-MiniLM-L6-v2, no torch needed), stores in ChromaDB, and exposes
search/ingest/load tools. Watches the Obsidian vault for changes and keeps
the index in sync automatically.
"""

import asyncio
import hashlib
import os
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from chromadb import HttpClient
from chromadb.utils import embedding_functions
from fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = os.getenv("CHROMA_PORT", "8000")

OBSIDIAN_URL = os.getenv("OBSIDIAN_URL", "http://127.0.0.1:27123").rstrip("/")
OBSIDIAN_TOKEN = os.getenv("OBSIDIAN_TOKEN", "")
WATCH_INTERVAL = int(os.getenv("WATCH_INTERVAL", "60"))

COLLECTION_NAME = "documents"
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100

# ---------------------------------------------------------------------------
# Vault watcher state
# ---------------------------------------------------------------------------

_vault_state: dict[str, str] = {}  # path -> content md5


@asynccontextmanager
async def lifespan(server: FastMCP):
    for _ in range(10):
        try:
            await _init_vault_state()
            break
        except Exception:
            await asyncio.sleep(3)
    asyncio.create_task(_watch_loop())
    yield


# ---------------------------------------------------------------------------
# ChromaDB
# ---------------------------------------------------------------------------

mcp = FastMCP("rag", lifespan=lifespan)

_embedder = embedding_functions.DefaultEmbeddingFunction()
_chroma: Optional[HttpClient] = None


def get_chroma() -> HttpClient:
    global _chroma
    if _chroma is None:
        _chroma = HttpClient(host=CHROMA_HOST, port=int(CHROMA_PORT))
    return _chroma


def get_collection():
    return get_chroma().get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=_embedder,
        metadata={"hnsw:space": "cosine"},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _chunk(text: str) -> list[str]:
    if len(text) <= CHUNK_SIZE:
        return [text]
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start:start + CHUNK_SIZE])
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def _obsidian_headers() -> dict:
    return {"Authorization": f"Bearer {OBSIDIAN_TOKEN}"}


def _sig(content: bytes) -> str:
    return hashlib.md5(content).hexdigest()


async def _list_vault_recursive(client: httpx.AsyncClient, prefix: str = "") -> list[str]:
    """Recursively list all .md files under a vault path."""
    resp = await client.get(f"{OBSIDIAN_URL}/vault/{prefix}", headers=_obsidian_headers())
    resp.raise_for_status()
    entries = resp.json().get("files", [])
    paths = []
    for entry in entries:
        full = f"{prefix}{entry}"
        if entry.endswith("/"):
            paths.extend(await _list_vault_recursive(client, full))
        elif entry.endswith(".md"):
            paths.append(full)
    return paths


# ---------------------------------------------------------------------------
# Watcher
# ---------------------------------------------------------------------------


async def _init_vault_state():
    """Rebuild _vault_state from ChromaDB so restarts don't trigger full re-index."""
    collection = get_collection()
    results = collection.get(where={"chunk": 0}, include=["metadatas"], limit=10000)
    for meta in results.get("metadatas") or []:
        source = meta.get("source")
        sig = meta.get("sig", "")
        if source and sig:
            _vault_state[source] = sig


async def _sync_vault():
    """Detect and apply vault changes to ChromaDB."""
    async with httpx.AsyncClient(verify=False, timeout=60) as client:
        try:
            current_paths = set(await _list_vault_recursive(client))
        except Exception:
            return

        prev_paths = set(_vault_state.keys())
        collection = get_collection()

        # Deleted files — remove all their chunks
        for path in prev_paths - current_paths:
            try:
                existing = collection.get(where={"source": path}, limit=10000)
                if existing["ids"]:
                    collection.delete(ids=existing["ids"])
                _vault_state.pop(path, None)
            except Exception:
                pass

        # New and modified files
        for path in current_paths:
            try:
                resp = await client.get(
                    f"{OBSIDIAN_URL}/vault/{path}",
                    headers={**_obsidian_headers(), "Accept": "text/markdown"},
                )
                resp.raise_for_status()
                sig = _sig(resp.content)

                if _vault_state.get(path) == sig:
                    continue  # unchanged

                content = resp.text

                # Remove stale chunks before re-indexing a modified file
                if path in _vault_state:
                    existing = collection.get(where={"source": path}, limit=10000)
                    if existing["ids"]:
                        collection.delete(ids=existing["ids"])

                chunks = _chunk(content)
                ids = [f"{path}::{i}" for i in range(len(chunks))]
                metadatas = [
                    {"source": path, "chunk": i, **({"sig": sig} if i == 0 else {})}
                    for i in range(len(chunks))
                ]
                collection.upsert(ids=ids, documents=chunks, metadatas=metadatas)
                _vault_state[path] = sig

            except Exception:
                continue


async def _watch_loop():
    while True:
        await asyncio.sleep(WATCH_INTERVAL)
        await _sync_vault()


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def rag_search(query: str, k: int = 5) -> dict:
    """Semantic search over stored documents.

    Args:
        query: Natural-language search query.
        k: Number of results to return (default 5).

    Returns dict with 'results': list of {id, metadata, score, snippet}.
    """
    collection = get_collection()
    results = collection.query(query_texts=[query], n_results=k)

    items = []
    ids = results.get("ids", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    documents = results.get("documents", [[]])[0]
    distances = results.get("distances", [[]])[0]

    for i, doc_id in enumerate(ids):
        meta = metadatas[i] if i < len(metadatas) else {}
        snippet = documents[i][:300] if i < len(documents) else ""
        score = 1 - distances[i] if i < len(distances) else 0.0
        items.append({
            "id": doc_id,
            "metadata": meta,
            "score": round(score, 4),
            "snippet": snippet,
        })

    return {"results": items, "count": len(items)}


@mcp.tool()
async def rag_ingest(documents: list[dict]) -> dict:
    """Embed and store documents in ChromaDB.

    Args:
        documents: List of {id, content, metadata}. Each entry must have a
                   unique 'id' (str), 'content' (str), and optional 'metadata'
                   (dict of arbitrary key-value pairs).

    Returns dict with 'ingested': count and 'errors': list of failures.
    """
    collection = get_collection()

    ids, texts, metadatas, errors = [], [], [], []

    for doc in documents:
        doc_id = doc.get("id")
        content = doc.get("content")
        meta = doc.get("metadata", {})

        if not doc_id or not content:
            errors.append({"doc": doc, "error": "Missing 'id' or 'content'"})
            continue

        ids.append(str(doc_id))
        texts.append(str(content))
        metadatas.append(meta)

    if not ids:
        return {"ingested": 0, "errors": errors, "message": "No valid documents."}

    collection.upsert(ids=ids, documents=texts, metadatas=metadatas)
    return {"ingested": len(ids), "errors": errors}


@mcp.tool()
async def rag_status() -> dict:
    """Show index statistics: model, doc count, watcher state."""
    try:
        collection = get_collection()
        count = collection.count()
    except Exception:
        count = 0

    return {
        "model": "all-MiniLM-L6-v2 (ONNX)",
        "collection": COLLECTION_NAME,
        "docs": count,
        "watch_interval_seconds": WATCH_INTERVAL,
        "tracked_files": len(_vault_state),
    }


@mcp.tool()
async def rag_remove(doc_id: str) -> dict:
    """Remove a document from the index by its ID."""
    collection = get_collection()
    try:
        collection.delete(ids=[doc_id])
        return {"removed": doc_id}
    except Exception as e:
        return {"removed": None, "error": str(e)}


@mcp.tool()
async def rag_load(doc_id: Optional[str] = None) -> dict:
    """Load notes from the Obsidian vault into the vector index.

    Args:
        doc_id: Vault-relative path of a specific note to load (e.g. "folder/note.md").
                If omitted, all markdown notes in the vault are loaded recursively.

    Returns dict with 'ingested': chunk count and 'files': list of processed notes.
    """
    async with httpx.AsyncClient(verify=False, timeout=30) as client:
        paths = [doc_id] if doc_id is not None else await _list_vault_recursive(client)

    collection = get_collection()
    total_chunks = 0
    processed = []
    errors = []

    async with httpx.AsyncClient(verify=False, timeout=30) as client:
        for path in paths:
            try:
                resp = await client.get(
                    f"{OBSIDIAN_URL}/vault/{path}",
                    headers={**_obsidian_headers(), "Accept": "text/markdown"},
                )
                resp.raise_for_status()
                sig = _sig(resp.content)
                content = resp.text
                chunks = _chunk(content)
                ids = [f"{path}::{i}" for i in range(len(chunks))]
                metadatas = [
                    {"source": path, "chunk": i, **({"sig": sig} if i == 0 else {})}
                    for i in range(len(chunks))
                ]
                collection.upsert(ids=ids, documents=chunks, metadatas=metadatas)
                _vault_state[path] = sig
                total_chunks += len(chunks)
                processed.append({"file": path, "chunks": len(chunks)})
            except Exception as e:
                errors.append({"file": path, "error": str(e)})

    return {"ingested": total_chunks, "files": processed, "errors": errors}


@mcp.tool()
async def rag_clear() -> dict:
    """Delete all indexed documents. Irreversible."""
    client = get_chroma()
    count = client.get_collection(COLLECTION_NAME).count()
    client.delete_collection(COLLECTION_NAME)
    _vault_state.clear()
    return {"cleared": count}


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8081)
