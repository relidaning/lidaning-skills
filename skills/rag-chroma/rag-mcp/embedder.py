"""multilingual-e5-small on ONNX Runtime (no torch).

Replaced Chroma's default all-MiniLM-L6-v2 on 2026-09-29: MiniLM's vocabulary
is English-only (most Chinese characters tokenize to [UNK], and ~43% of the
vault's chunks are mostly Chinese) and it truncates at 256 tokens. e5 covers
~100 languages and reads 512 tokens.

e5 expects "query: " before a search query and "passage: " before indexed
text; the Chroma embedding-function call (used when Chroma embeds documents
on add/upsert) applies the passage prefix, and embed_query() the query one.
"""

import os
from pathlib import Path

import numpy as np
import onnxruntime as ort
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from tokenizers import Tokenizer

MODEL_DIR = Path(os.getenv("EMBED_MODEL_DIR", "/models/multilingual-e5-small"))
# int8-quantized export: fp32 with 16-text batches held ~1.7GB resident after
# a re-index; int8, batches of 4 and no ONNX memory arena hold ~0.5GB
# (measured 2026-09-29).
MODEL_ID = "multilingual-e5-small-int8"
MAX_TOKENS = 512
BATCH = 4


class E5Embedder(EmbeddingFunction[Documents]):
    def __init__(self, model_dir: Path = MODEL_DIR):
        self._tok = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        self._tok.enable_truncation(max_length=MAX_TOKENS)
        self._tok.enable_padding(pad_id=self._tok.token_to_id("<pad>"), pad_token="<pad>")
        # Separate untruncated tokenizer for the chunker's token counts
        self._count = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        self._count.no_truncation()
        self._count.no_padding()
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = int(os.getenv("EMBED_THREADS", "4"))
        # The arena keeps the largest batch's buffers allocated forever
        opts.enable_cpu_mem_arena = False
        opts.enable_mem_pattern = False
        self._sess = ort.InferenceSession(
            str(model_dir / "model_quantized.onnx"), opts, providers=["CPUExecutionProvider"])
        self._inputs = {i.name for i in self._sess.get_inputs()}

    def __call__(self, input: Documents) -> Embeddings:
        return self._embed([f"passage: {t}" for t in input])

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed([f"query: {text}"])[0]

    def count_tokens(self, text: str) -> int:
        return len(self._count.encode(text, add_special_tokens=False).ids)

    def _embed(self, texts: list[str]) -> list[np.ndarray]:
        out = []
        for i in range(0, len(texts), BATCH):
            enc = self._tok.encode_batch(texts[i:i + BATCH])
            ids = np.array([e.ids for e in enc], dtype=np.int64)
            mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
            feed = {"input_ids": ids, "attention_mask": mask}
            if "token_type_ids" in self._inputs:
                feed["token_type_ids"] = np.zeros_like(ids)
            hidden = self._sess.run(None, feed)[0]  # (batch, seq, dim)
            m = mask[..., None].astype(np.float32)
            vec = (hidden * m).sum(1) / np.clip(m.sum(1), 1e-9, None)  # mean pooling
            vec /= np.linalg.norm(vec, axis=1, keepdims=True)
            out.extend(vec.astype(np.float32))
        return out
