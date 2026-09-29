"""In-memory BM25 keyword index, the lexical half of hybrid search.

Embeddings match meaning but blur exact strings (file names, arXiv IDs,
identifiers, rare terms); BM25 ranks by exact term overlap, weighting rare
terms up and long documents down. Chinese has no spaces, so CJK text is
indexed as character unigrams plus bigrams instead of words, which needs no
segmentation dictionary.
"""

import math
import re
from collections import Counter, defaultdict

WORD = re.compile(r"[a-z0-9]+(?:[._\-][a-z0-9]+)*")
CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]+")
PARTS = re.compile(r"[._\-]")


def tokenize(text: str) -> list[str]:
    text = text.lower()
    out = []
    for w in WORD.findall(text):
        out.append(w)
        parts = PARTS.split(w)
        if len(parts) > 1:  # "rag_mcp.py" also matches "rag", "mcp", "py"
            out.extend(p for p in parts if p)
    for run in CJK.findall(text):
        out.extend(run)
        out.extend(run[i:i + 2] for i in range(len(run) - 1))
    return out


class BM25:
    def __init__(self, ids: list[str], docs: list[str], k1: float = 1.5, b: float = 0.75):
        self.ids = ids
        self.k1, self.b = k1, b
        self.lens = []
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for i, doc in enumerate(docs):
            tf = Counter(tokenize(doc or ""))
            self.lens.append(sum(tf.values()))
            for term, n in tf.items():
                self.postings[term].append((i, n))
        self.avgdl = (sum(self.lens) / len(self.lens)) if self.lens else 0.0

    def search(self, query: str, k: int) -> list[tuple[str, float]]:
        n_docs = len(self.ids)
        scores: dict[int, float] = defaultdict(float)
        for term in set(tokenize(query)):
            posting = self.postings.get(term)
            if not posting:
                continue
            idf = math.log(1 + (n_docs - len(posting) + 0.5) / (len(posting) + 0.5))
            for i, tf in posting:
                norm = self.k1 * (1 - self.b + self.b * self.lens[i] / (self.avgdl or 1))
                scores[i] += idf * tf * (self.k1 + 1) / (tf + norm)
        top = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:k]
        return [(self.ids[i], s) for i, s in top]
