# Configuration and technology map

`config.toml` is the runtime source of defaults for the server, embedding
engine, vault connector, audit logger and unattended Python client. Python
3.12+ loads it with the standard library; no configuration dependency is needed.
Each key is also its environment variable name. Precedence is environment,
then `RAG_CONFIG_FILE` (optional partial TOML), then shipped defaults. Empty
`LLM_MODEL`/`LLM_BASE_URL` environment values use file values for compatibility
with Compose. Other invalid or empty settings fail at import/startup with the
setting name. Secrets are never read from TOML; `LLM_API_KEY` is environment-only.

Paths inside a selected TOML are relative to that file's directory, including
inherited relative defaults. `RAG_CONFIG_FILE` itself is an explicit filesystem
path (relative to the caller if not absolute). By default paths resolve relative
to the skill, so the Python client can be called from anywhere. Containers use
`/config.toml` and override the log directory to `/skill/logs` to preserve the
existing persistent mount. `EMBED_MODEL_DIR` is a container path by default;
local inference must set it to a local downloaded model directory.

Copy `.env.example` to `.env` alongside Compose for private deployment/runtime
overrides. Compose loads it for interpolation and passes it into rag-mcp.
Existing shell `LLM_API_KEY`, `LLM_BASE_URL` and `LLM_MODEL` overrides still work;
put other runtime overrides in `.env` or TOML. A separate `--env-file` changes
Compose interpolation only; the service still reads its sibling `.env`.
Do not commit `.env`, model downloads, database data or logs.

| Role | Current implementation / source of truth | Replacement contract |
|---|---|---|
| Runtime | Python image in Compose/Dockerfile; dependencies in `rag-mcp/requirements.txt` | Python 3.12+; rebuild image after dependency changes. Dependency ranges remain ranges, not a lockfile. |
| Vector storage | Chroma 0.6.3 image in Compose; `CHROMA_HOST`/`CHROMA_PORT` in TOML | Chroma HTTP API compatible with installed client; another database needs a storage adapter in `server.py` and data migration. Changing image alone does not provide that. |
| Embeddings | ONNX Runtime + tokenizers; `E5_REPO`, `E5_REVISION`, `E5_MODEL_FILE` build arguments; `EMBED_*` runtime keys | Compatible ONNX inputs/output, tokenizer, mean pooling and e5 query/passage prefixes. Align downloaded filename with `EMBED_MODEL_FILE`; change `EMBED_MODEL_ID` for different vectors. Other model families need embedder code. |
| Answer generation | OpenAI Python SDK; `LLM_BASE_URL`, `LLM_MODEL`, environment-only `LLM_API_KEY` | OpenAI-compatible chat completions. No effect on retrieval embeddings. |
| Vault source | MCP over HTTP; `VAULT_MCP_URL`, `VAULT_MCP_TIMEOUT`, `WATCH_INTERVAL` | `list_directory`, `get_notes_info`, `read_multiple_notes` response contracts in `vault_client.py`. Another API requires an adapter. |
| Retrieval | BM25 + cosine RRF; `RRF_K`, `EXACT_KEYWORD_WEIGHT`, `CHUNK_TOKENS` | Changing chunk budget affects new/reloaded notes. No-overlap policy, model pooling and protocol/API bounds remain code invariants. |
| Transport/UI | FastMCP + Starlette, vanilla JS; `RAG_HOST`, `RAG_PORT`, `RAG_MCP_URL` | Keep the client URL and installed agent MCP registrations (`mcp.json` template) aligned with the server port. Healthcheck reads the same configured port. |
| Persistence | Compose host bind mounts; `CHROMA_DATA_DIR`, `RAG_LOG_HOST_DIR` | Preserve existing data; changing a path does not move it. Back up and migrate explicitly. |

The default deployment uses Linux host networking for rag-mcp and a published
Chroma container port. Set both `CHROMA_PUBLISH_PORT` and runtime `CHROMA_PORT`
when changing that port. Chroma's internal port/healthcheck remain 8000.
Network topology changes require adapting Compose; this configuration is
portable across paths/deployments but does not claim host networking works on
every platform. The `.dockerignore` excludes private data and logs from builds.

After configuration changes, recreate rag-mcp to load them; build-time/model
changes additionally require rebuilding. **A changed embedding identity triggers
the existing collection replacement logic at startup, which can delete stored
collections, including non-vault collections.** Back up and plan re-ingestion
before deploying it. Do not change identity simply to rename a model. A chunk
budget change preserves unchanged notes; explicitly reload the desired scope
to apply it everywhere. No service restart or reindex is part of an offline
configuration check.

Offline regression checks can use an existing service image without rebuilding
or connecting to any live dependencies. From the repository root:

```bash
docker run --rm --network none \
  -v "$PWD/skills/rag-chroma:/workspace/skill:ro" \
  -w /workspace/skill/rag-mcp rag-chroma-rag-mcp:latest \
  python -m unittest discover -s ../tests -v
docker compose -f skills/rag-chroma/docker-compose.yml config --quiet
```
