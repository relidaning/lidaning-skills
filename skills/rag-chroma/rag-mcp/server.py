"""rag-mcp — Source-agnostic semantic search with Obsidian vault watcher.

MCP server that embeds text with multilingual-e5-small on ONNX Runtime (no
torch; see embedder.py), stores it in ChromaDB, and exposes search/ingest/load
tools. Search is hybrid: vector similarity and BM25 keyword ranking (bm25.py),
merged by reciprocal rank fusion. Vault notes are cut at headings and
paragraphs into token-sized chunks with a note/heading header (chunker.py).
Watches the Obsidian vault for changes and keeps the index in sync.

The vault is read through the obsidian-vault MCP server (vault_client.py),
so the index holds exactly what that server exposes. Its availability is the
watcher's one dependency: when an earlier source (the Obsidian app's REST
API) stopped on 2026-09-26, the index silently froze for days, so rag_status
reports the last successful sync and the last error.
"""

import asyncio
import hashlib
import json
import time
import logging
import os
import re
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

import numpy as np
from chromadb import HttpClient
from fastmcp import FastMCP
from openai import AsyncOpenAI
from starlette.responses import PlainTextResponse

from bm25 import BM25
from chunker import chunk_note
from embedder import MODEL_ID, E5Embedder
from vault_client import URL as VAULT_MCP_URL, VaultClient

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = os.getenv("CHROMA_PORT", "8000")

WATCH_INTERVAL = int(os.getenv("WATCH_INTERVAL", "60"))

COLLECTION_NAME = "documents"  # the vault index; other collections are opt-in
CHUNK_TOKENS = 300          # per chunk, header included; e5 reads up to 512
CHUNK_OVERLAP_TOKENS = 50
# Stored in each collection's metadata. A collection built by another model
# (or, for the vault index, another chunker) is rebuilt at startup: vectors
# from two models must never share a collection, and MiniLM and e5 are both
# 384-dim, so Chroma would not notice.
CHUNKER_VERSION = "md-headings-v2"
RRF_K = 60  # reciprocal rank fusion constant (the usual default)
# A short query with digits/symbols ("2203.15556", "rag_mcp.py") is a lookup
# of an exact string; embeddings rank such queries near-randomly, so BM25
# gets this much more weight in the fusion.
EXACT_QUERY = re.compile(r"[\d_.\-/]")
EXACT_KEYWORD_WEIGHT = 2.0

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
_vault = VaultClient()
_sync_status: dict = {"last_ok": None, "last_error": None, "notes": None}


@asynccontextmanager
async def lifespan(server: FastMCP):
    for _ in range(10):
        try:
            await asyncio.to_thread(_migrate_collections)
            await _init_vault_state()
            break
        except Exception:
            await asyncio.sleep(3)
    asyncio.create_task(_watch_loop())
    try:
        yield
    finally:
        _vault.close()  # else the vault server keeps a process for it for an hour


# ---------------------------------------------------------------------------
# ChromaDB
# ---------------------------------------------------------------------------

mcp = FastMCP("rag", lifespan=lifespan)


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    # The Docker healthcheck used to GET /mcp, which opened a new MCP
    # session every 30s that was never closed.
    return PlainTextResponse("ok")

_embedder = E5Embedder()
_chroma: Optional[HttpClient] = None
_bm25: dict[str, BM25] = {}  # collection -> keyword index, dropped on any write


def get_chroma() -> HttpClient:
    global _chroma
    if _chroma is None:
        _chroma = HttpClient(host=CHROMA_HOST, port=int(CHROMA_PORT))
    return _chroma


def _collection_meta(name: str) -> dict:
    meta = {"hnsw:space": "cosine", "embed": MODEL_ID}
    if name == COLLECTION_NAME:
        meta["chunker"] = CHUNKER_VERSION
    return meta


def get_collection(name: str = COLLECTION_NAME):
    return get_chroma().get_or_create_collection(
        name=name,
        embedding_function=_embedder,
        metadata=_collection_meta(name),
    )


def _migrate_collections():
    """Rebuild collections made by another embedding model or chunker. The
    vault index is recreated empty (the watcher re-chunks every note); any
    other collection is re-embedded from its stored text and metadata."""
    client = get_chroma()
    for name in map(str, client.list_collections()):
        col = client.get_collection(name)
        want = _collection_meta(name)
        have = col.metadata or {}
        if all(have.get(k) == v for k, v in want.items() if k != "hnsw:space"):
            continue
        _log.warning("rebuilding collection %s (%s -> %s)", name,
                     {k: have.get(k) for k in want}, want)
        if name == COLLECTION_NAME:
            client.delete_collection(name)
            get_collection(name)
            continue
        got = col.get(include=["documents", "metadatas"])
        client.delete_collection(name)
        new = get_collection(name)
        for i in range(0, len(got["ids"]), 256):
            new.upsert(ids=got["ids"][i:i + 256], documents=got["documents"][i:i + 256],
                       metadatas=[m or None for m in got["metadatas"][i:i + 256]])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _chunk(text: str, path: str, title: str = "") -> list[dict]:
    return chunk_note(text, path, _embedder.count_tokens, title=title,
                      max_tokens=CHUNK_TOKENS, overlap_tokens=CHUNK_OVERLAP_TOKENS)


def _sig(note: dict) -> str:
    raw = json.dumps([note["frontmatter"], note["content"]], sort_keys=True, default=str)
    return hashlib.md5(raw.encode()).hexdigest()


def _index_note(collection, path: str, note: dict, sig: str) -> int:
    """Replace a note's chunks in the index; returns the chunk count.
    `note` is {"content", "frontmatter"} as the vault server returns it."""
    existing = collection.get(where={"source": path}, limit=10000)
    if existing["ids"]:
        collection.delete(ids=existing["ids"])
    title = note["frontmatter"].get("title") or ""
    chunks = _chunk(note["content"], path, str(title))
    ids = [f"{path}::{i}" for i in range(len(chunks))]
    metadatas = [
        {"source": path, "chunk": i, "heading": c["heading"], **({"sig": sig} if i == 0 else {})}
        for i, c in enumerate(chunks)
    ]
    collection.upsert(ids=ids, documents=[c["text"] for c in chunks], metadatas=metadatas)
    _bm25.pop(collection.name, None)
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


def _sync_vault():
    """Detect and apply vault changes to ChromaDB. Blocking: embedding a
    changed note takes seconds (a full re-index, minutes), so the watcher
    runs it in a worker thread to keep the MCP server responsive."""
    try:
        current_paths = set(_vault.list_notes())
        mtimes = _vault.mtimes(sorted(current_paths))
    except Exception as e:
        # Never treat an unreachable server as an empty vault
        _log.warning("vault sync skipped: %s", e)
        _sync_status.update(last_error=f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {e}")
        return

    collection = get_collection()

    # Deleted files — remove all their chunks
    for path in set(_vault_state) - current_paths:
        try:
            existing = collection.get(where={"source": path}, limit=10000)
            if existing["ids"]:
                collection.delete(ids=existing["ids"])
                _bm25.pop(collection.name, None)
            _vault_state.pop(path, None)
            _vault_mtime.pop(path, None)
            _log.info("removed: %s", path)
        except Exception as e:
            _log.warning("remove failed: %s: %s", path, e)

    # New and modified notes; an unchanged mtime skips reading the note at all
    changed = sorted(p for p in current_paths
                     if not (_vault_mtime.get(p) == mtimes.get(p) and p in _vault_state))
    for i in range(0, len(changed), 10):
        batch = changed[i:i + 10]
        try:
            notes = _vault.read(batch)
        except Exception as e:
            _log.warning("vault read failed, retrying next tick: %s", e)
            _sync_status.update(last_error=f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {e}")
            return
        for path, note in notes.items():
            try:
                sig = _sig(note)
                _vault_mtime[path] = mtimes.get(path)
                if _vault_state.get(path) == sig:
                    continue  # touched, content unchanged
                n = _index_note(collection, path, note, sig)
                _log.info("re-indexed: %s (%d chunks)", path, n)
            except Exception as e:
                _log.warning("index failed: %s: %s", path, e)
    _sync_status.update(last_ok=time.strftime("%Y-%m-%dT%H:%M:%S"), notes=len(current_paths))


async def _watch_loop():
    while True:
        await asyncio.sleep(WATCH_INTERVAL)
        await asyncio.to_thread(_sync_vault)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def _keyword_index(collection) -> BM25:
    index = _bm25.get(collection.name)
    if index is None:
        got = collection.get(include=["documents"])
        index = _bm25[collection.name] = BM25(got["ids"], got["documents"])
    return index


def _search(name: str, query: str, k: int, mode: str = "hybrid") -> list[dict]:
    """Top-k hits as {id, metadata, score, text, match}.

    Ranking: "vector" by embedding similarity, "keyword" by BM25, "hybrid"
    (default) by reciprocal rank fusion of both lists, so a chunk found by
    either can surface and one found by both ranks highest. Whatever the
    ranking, `score` is the cosine similarity of query and chunk, so a
    threshold on it (e.g. claude-maxer's paper dedup) means the same thing
    in every mode.
    """
    if mode not in ("hybrid", "vector", "keyword"):
        raise ValueError(f"mode must be hybrid, vector or keyword, not {mode!r}")
    collection = get_collection(name)
    total = collection.count()
    if not total:
        return []
    q = _embedder.embed_query(query)
    pool = min(max(k * 4, 20), total)

    hits: dict[str, dict] = {}
    rrf: dict[str, float] = {}
    if mode != "keyword":
        res = collection.query(query_embeddings=[q.tolist()], n_results=pool if mode == "hybrid" else min(k, total))
        for rank, (i, m, d, dist) in enumerate(zip(res["ids"][0], res["metadatas"][0],
                                                   res["documents"][0], res["distances"][0])):
            hits[i] = {"id": i, "metadata": m or {}, "score": round(1 - dist, 4), "text": d, "match": "vector"}
            rrf[i] = 1 / (RRF_K + rank + 1)
    if mode != "vector":
        weight = (EXACT_KEYWORD_WEIGHT
                  if len(query.split()) <= 2 and EXACT_QUERY.search(query) else 1.0)
        for rank, (i, _) in enumerate(_keyword_index(collection).search(query, pool)):
            rrf[i] = rrf.get(i, 0) + weight / (RRF_K + rank + 1)
            if i in hits:
                hits[i]["match"] = "both"
            else:
                hits[i] = {"id": i, "match": "keyword"}

    top = sorted(rrf, key=rrf.get, reverse=True)[:k]
    missing = [i for i in top if "text" not in hits[i]]
    if missing:  # keyword-only hits: fetch text and embedding to score them
        got = collection.get(ids=missing, include=["documents", "metadatas", "embeddings"])
        for i, d, m, e in zip(got["ids"], got["documents"], got["metadatas"], got["embeddings"]):
            hits[i].update(metadata=m or {}, text=d, score=round(float(np.dot(q, e)), 4))
    return [hits[i] for i in top if "text" in hits[i]]


@mcp.tool()
async def rag_search(query: str, k: int = 5, collection: str = COLLECTION_NAME,
                     mode: str = "hybrid") -> dict:
    """Semantic + keyword search over stored documents.

    Args:
        query: Natural-language search query (any language).
        k: Number of results to return (default 5).
        collection: Collection to search (default "documents", the vault index).
        mode: "hybrid" (default: meaning and exact terms, fused), "vector"
              (meaning only), or "keyword" (BM25 exact terms only, good for
              file names, IDs and rare words).

    Returns dict with 'results': list of {id, metadata, score, snippet, match};
    score is cosine similarity, match says which ranker found the hit.
    """
    hits = await asyncio.to_thread(_search, collection, query, k, mode)
    return {"results": [
        {"id": h["id"], "metadata": h["metadata"], "score": h["score"],
         "snippet": h["text"][:300], "match": h["match"]} for h in hits
    ], "count": len(hits)}


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

    await asyncio.to_thread(collection.upsert, ids=ids, documents=texts, metadatas=metadatas)
    _bm25.pop(collection.name, None)
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
        "model": f"{MODEL_ID} (ONNX)",
        "search": "hybrid: vector + BM25, reciprocal rank fusion",
        "chunking": f"{CHUNKER_VERSION}, <= {CHUNK_TOKENS} tokens",
        "collection": COLLECTION_NAME,
        "docs": counts.get(COLLECTION_NAME, 0),
        "collections": counts,
        "vault_source": VAULT_MCP_URL,
        "vault_sync": dict(_sync_status),
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
        _bm25.pop(collection.name, None)
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
    return await asyncio.to_thread(_load, doc_id)


def _load(doc_id: Optional[str]) -> dict:
    paths = [doc_id] if doc_id is not None else _vault.list_notes()
    collection = get_collection()
    total_chunks = 0
    processed = []
    errors = []

    for i in range(0, len(paths), 10):
        batch = paths[i:i + 10]
        try:
            notes = _vault.read(batch)
        except Exception as e:
            errors += [{"file": p, "error": str(e)} for p in batch]
            continue
        errors += [{"file": p, "error": "not readable through the vault server"}
                   for p in batch if p not in notes]
        for path, note in notes.items():
            try:
                n = _index_note(collection, path, note, _sig(note))
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
    _bm25.pop(COLLECTION_NAME, None)
    _vault_state.clear()
    _vault_mtime.clear()
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
    hits = await asyncio.to_thread(_search, COLLECTION_NAME, query, k)

    if not hits:
        return {"answer": "No relevant documents found in the index.", "sources": [], "chunks": []}

    # Build numbered context block for the LLM
    context_parts = []
    chunks_info = []
    for i, h in enumerate(hits):
        doc_id, text, score = h["id"], h["text"], h["score"]
        source = h["metadata"].get("source", doc_id)
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
