"""rag-mcp — Source-agnostic semantic search.

MCP server that embeds text content via ChromaDB's built-in ONNX embedding
function (all-MiniLM-L6-v2, no torch needed), stores in ChromaDB, and exposes
search/ingest tools. Knows nothing about where content comes from — the LLM
provides text, IDs, and metadata.
"""

import os
from typing import Optional

from chromadb import HttpClient
from chromadb.utils import embedding_functions
from fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = os.getenv("CHROMA_PORT", "8000")

COLLECTION_NAME = "documents"

# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

mcp = FastMCP("rag")

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

    ids = []
    texts = []
    metadatas = []
    errors = []

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
    """Show index statistics: model, doc count, collection name."""
    try:
        collection = get_collection()
        count = collection.count()
    except Exception:
        count = 0

    return {
        "model": "all-MiniLM-L6-v2 (ONNX)",
        "collection": COLLECTION_NAME,
        "docs": count,
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
async def rag_clear() -> dict:
    """Delete all indexed documents. Irreversible."""
    client = get_chroma()
    count = client.get_collection(COLLECTION_NAME).count()
    client.delete_collection(COLLECTION_NAME)
    return {"cleared": count}


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8081)
