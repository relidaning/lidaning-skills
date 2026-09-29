"""rag-mcp — Source-agnostic semantic search with Obsidian vault watcher.

MCP server that embeds text content via ChromaDB's built-in ONNX embedding
function (all-MiniLM-L6-v2, no torch needed), stores in ChromaDB, and exposes
search/ingest/load tools. Watches the Obsidian vault folder on disk for
changes and keeps the index in sync automatically.

The vault is read from a read-only bind mount (VAULT_DIR), not the Obsidian
app's REST API: the app isn't kept running, and when it stopped on
2026-09-26 the watcher silently froze the index for days.
"""

import asyncio
import hashlib
import logging
import os
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    force=True,
)
logging.getLogger("httpx").setLevel(logging.WARNING)

_log = logging.getLogger(__name__)

from chromadb import HttpClient
from chromadb.utils import embedding_functions
from fastmcp import FastMCP
from openai import AsyncOpenAI
from starlette.responses import PlainTextResponse

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = os.getenv("CHROMA_PORT", "8000")

VAULT_DIR = Path(os.getenv("VAULT_DIR", "/vault"))
WATCH_INTERVAL = int(os.getenv("WATCH_INTERVAL", "60"))

COLLECTION_NAME = "documents"  # the vault index; other collections are opt-in
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100

LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")   # empty = OpenAI default
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

_llm: Optional[AsyncOpenAI] = None


def get_llm() -> AsyncOpenAI:
    global _llm
    if _llm is None:
        if not LLM_API_KEY:
            raise RuntimeError("LLM_API_KEY env var is not set")
        kwargs = {"api_key": LLM_API_KEY}
        if LLM_BASE_URL:
            kwargs["base_url"] = LLM_BASE_URL
        _llm = AsyncOpenAI(**kwargs)
    return _llm


_ANSWER_SYSTEM = """\
You are a helpful assistant. Answer the user's question using ONLY the numbered context passages below.
If the context does not contain enough information, say so honestly — do not invent facts.
After your answer include a "Sources:" line listing the document names you drew from."""

# ---------------------------------------------------------------------------
# Vault watcher state
# ---------------------------------------------------------------------------

_vault_state: dict[str, str] = {}  # path -> content md5
_vault_mtime: dict[str, float] = {}  # path -> mtime at last check, to skip re-hashing


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


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    # The Docker healthcheck used to GET /mcp, which opened a new MCP
    # session every 30s that was never closed.
    return PlainTextResponse("ok")

_embedder = embedding_functions.DefaultEmbeddingFunction()
_chroma: Optional[HttpClient] = None


def get_chroma() -> HttpClient:
    global _chroma
    if _chroma is None:
        _chroma = HttpClient(host=CHROMA_HOST, port=int(CHROMA_PORT))
    return _chroma


def get_collection(name: str = COLLECTION_NAME):
    return get_chroma().get_or_create_collection(
        name=name,
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


def _sig(content: bytes) -> str:
    return hashlib.md5(content).hexdigest()


def _list_vault() -> list[str]:
    """Vault-relative paths of all .md notes, skipping dot-dirs (.obsidian, .trash)."""
    if not VAULT_DIR.is_dir():
        raise RuntimeError(f"vault not mounted at {VAULT_DIR}")
    return sorted(
        str(p.relative_to(VAULT_DIR)) for p in VAULT_DIR.rglob("*.md")
        if not any(part.startswith(".") for part in p.relative_to(VAULT_DIR).parts)
    )


def _index_note(collection, path: str, raw: bytes, sig: str) -> int:
    """Replace a note's chunks in the index; returns the chunk count."""
    existing = collection.get(where={"source": path}, limit=10000)
    if existing["ids"]:
        collection.delete(ids=existing["ids"])
    chunks = _chunk(raw.decode("utf-8", errors="replace"))
    ids = [f"{path}::{i}" for i in range(len(chunks))]
    metadatas = [
        {"source": path, "chunk": i, **({"sig": sig} if i == 0 else {})}
        for i in range(len(chunks))
    ]
    collection.upsert(ids=ids, documents=chunks, metadatas=metadatas)
    _vault_state[path] = sig
    return len(chunks)


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
    try:
        current_paths = set(_list_vault())
    except Exception as e:
        _log.warning("vault sync skipped: %s", e)
        return

    collection = get_collection()

    # Deleted files — remove all their chunks
    for path in set(_vault_state) - current_paths:
        try:
            existing = collection.get(where={"source": path}, limit=10000)
            if existing["ids"]:
                collection.delete(ids=existing["ids"])
            _vault_state.pop(path, None)
            _vault_mtime.pop(path, None)
            _log.info("removed: %s", path)
        except Exception as e:
            _log.warning("remove failed: %s: %s", path, e)

    # New and modified files; an unchanged mtime skips reading the file at all
    for path in current_paths:
        try:
            full = VAULT_DIR / path
            mtime = full.stat().st_mtime
            if _vault_mtime.get(path) == mtime and path in _vault_state:
                continue
            raw = full.read_bytes()
            sig = _sig(raw)
            _vault_mtime[path] = mtime
            if _vault_state.get(path) == sig:
                continue  # touched, content unchanged
            n = _index_note(collection, path, raw, sig)
            _log.info("re-indexed: %s (%d chunks)", path, n)
        except Exception as e:
            _log.warning("index failed: %s: %s", path, e)


async def _watch_loop():
    while True:
        await asyncio.sleep(WATCH_INTERVAL)
        await _sync_vault()


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def rag_search(query: str, k: int = 5, collection: str = COLLECTION_NAME) -> dict:
    """Semantic search over stored documents.

    Args:
        query: Natural-language search query.
        k: Number of results to return (default 5).
        collection: Collection to search (default "documents", the vault index).

    Returns dict with 'results': list of {id, metadata, score, snippet}.
    """
    collection = get_collection(collection)
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
async def rag_ingest(documents: list[dict], collection: str = COLLECTION_NAME) -> dict:
    """Embed and store documents in ChromaDB.

    Args:
        documents: List of {id, content, metadata}. Each entry must have a
                   unique 'id' (str), 'content' (str), and optional 'metadata'
                   (dict of arbitrary key-value pairs).
        collection: Target collection (default "documents"). Use a separate
                    collection for data that isn't vault notes, e.g. "papers".

    Returns dict with 'ingested': count and 'errors': list of failures.
    """
    collection = get_collection(collection)

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
    """Show index statistics: model, doc count per collection, watcher state."""
    counts = {}
    try:
        for name in get_chroma().list_collections():
            counts[str(name)] = get_chroma().get_collection(str(name)).count()
    except Exception as e:
        counts["error"] = str(e)

    return {
        "model": "all-MiniLM-L6-v2 (ONNX)",
        "collection": COLLECTION_NAME,
        "docs": counts.get(COLLECTION_NAME, 0),
        "collections": counts,
        "vault_dir": str(VAULT_DIR),
        "watch_interval_seconds": WATCH_INTERVAL,
        "tracked_files": len(_vault_state),
    }


@mcp.tool()
async def rag_list(collection: str, limit: int = 1000) -> dict:
    """List a collection's entries (id + metadata, no content), e.g. every
    paper in "papers". Not meant for the vault index, which is large.

    Returns dict with 'items': list of {id, metadata} and 'count'.
    """
    got = get_collection(collection).get(include=["metadatas"], limit=limit)
    items = [{"id": i, "metadata": m} for i, m in zip(got["ids"], got["metadatas"])]
    return {"items": items, "count": len(items)}


@mcp.tool()
async def rag_remove(doc_id: str, collection: str = COLLECTION_NAME) -> dict:
    """Remove a document from the index by its ID."""
    collection = get_collection(collection)
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
    paths = [doc_id] if doc_id is not None else _list_vault()
    collection = get_collection()
    total_chunks = 0
    processed = []
    errors = []

    for path in paths:
        try:
            raw = (VAULT_DIR / path).read_bytes()
            n = _index_note(collection, path, raw, _sig(raw))
            total_chunks += n
            processed.append({"file": path, "chunks": n})
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


@mcp.tool()
async def rag_answer(query: str, k: int = 4) -> dict:
    """Retrieve relevant chunks and generate a grounded answer with citations.

    Args:
        query: The question to answer.
        k: Number of chunks to retrieve as context (default 4).

    Returns dict with:
        - answer: LLM response grounded in retrieved context, with a Sources section.
        - sources: Deduplicated list of source document names used.
        - chunks: The retrieved context passages with scores.
    """
    collection = get_collection()
    results = collection.query(query_texts=[query], n_results=k)

    ids = results.get("ids", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    documents = results.get("documents", [[]])[0]
    distances = results.get("distances", [[]])[0]

    if not ids:
        return {"answer": "No relevant documents found in the index.", "sources": [], "chunks": []}

    # Build numbered context block for the LLM
    context_parts = []
    chunks_info = []
    for i, doc_id in enumerate(ids):
        meta = metadatas[i] if i < len(metadatas) else {}
        text = documents[i] if i < len(documents) else ""
        score = round(1 - distances[i], 4) if i < len(distances) else 0.0
        source = meta.get("source", doc_id)
        context_parts.append(f"[{i + 1}] (source: {source}, score: {score})\n{text}")
        chunks_info.append({"id": doc_id, "source": source, "score": score})

    context_block = "\n\n".join(context_parts)
    user_message = f"Context:\n{context_block}\n\nQuestion: {query}"

    response = await get_llm().chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": _ANSWER_SYSTEM},
            {"role": "user", "content": user_message},
        ],
        temperature=0.2,
    )
    answer = response.choices[0].message.content

    # Extract unique source names from chunks actually used
    sources = list(dict.fromkeys(c["source"] for c in chunks_info))

    return {"answer": answer, "sources": sources, "chunks": chunks_info}


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8081)
