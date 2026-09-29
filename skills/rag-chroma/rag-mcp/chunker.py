"""Markdown-aware chunking for vault notes.

A note is cut at its headings first, then at blank-line blocks (a fenced code
block counts as one block), and only an oversized block is broken further: by
line, then by sentence, then hard by token count. Sizes are measured in the
embedding model's tokens, so no chunk is silently truncated by the model.

Every chunk starts with a context header, "<note path> > <heading> > ...", so a
chunk from the middle of a note still says which note and section it is from.
YAML frontmatter is dropped; its `title`, when it differs from the file name,
goes into the header.
"""

import re
from typing import Callable

FRONTMATTER = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.S)
FM_TITLE = re.compile(r"^title:[ \t]*(.+?)[ \t]*$", re.M)
HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t#]*$")
FENCE = re.compile(r"^[ \t]*(```|~~~)")
# Heading numbering some Obsidian plugins insert, e.g. "⁠1.1.2. Title"
HEADING_NUMBER = re.compile(r"^[⁠​\s]*(?:\d+\.)+\d*\s+")
# A sentence with its trailing whitespace, so pieces re-join with ""
SENTENCE = re.compile(r".+?(?:[。！？!?；;]+|[.:](?=\s)|$)\s*", re.S)


def _clean_heading(text: str) -> str:
    text = HEADING_NUMBER.sub("", text)
    return text.replace("⁠", "").replace("​", "").strip()


def _split_frontmatter(text: str) -> tuple[str, str]:
    """(frontmatter title or "", body without the frontmatter)."""
    m = FRONTMATTER.match(text)
    if not m:
        return "", text
    t = FM_TITLE.search(m.group(1))
    return (t.group(1).strip("'\"") if t else ""), text[m.end():]


def _units(body: str):
    """Yield (kind, path, text): kind "heading" (text = the heading line) or
    "block" (a paragraph, list, table or whole fenced code block)."""
    path: list[tuple[int, str]] = []
    block: list[str] = []
    fence = None

    def flush():
        text = "\n".join(block).strip("\n")
        block.clear()
        return text

    for line in body.split("\n"):
        f = FENCE.match(line)
        if fence:
            block.append(line)
            if f and f.group(1) == fence:
                fence = None
            continue
        if f:
            fence = f.group(1)
            block.append(line)
            continue
        h = HEADING.match(line)
        if h:
            if (text := flush()).strip():
                yield "block", tuple(p for _, p in path), text
            level = len(h.group(1))
            path = [(lv, p) for lv, p in path if lv < level] + [(level, _clean_heading(h.group(2)))]
            yield "heading", tuple(p for _, p in path), line
        elif not line.strip():
            if (text := flush()).strip():
                yield "block", tuple(p for _, p in path), text
        else:
            block.append(line)
    if (text := flush()).strip():
        yield "block", tuple(p for _, p in path), text


def _hard_split(text: str, budget: int, ntok) -> list[str]:
    """Cut text into pieces of at most `budget` tokens, by character halving."""
    out, rest = [], text
    while rest:
        lo, hi = 1, len(rest)
        while lo < hi:  # longest prefix within budget
            mid = (lo + hi + 1) // 2
            if ntok(rest[:mid]) <= budget:
                lo = mid
            else:
                hi = mid - 1
        out.append(rest[:lo])
        rest = rest[lo:]
    return out


def _pieces(block: str, budget: int, ntok) -> list[tuple[str, str]]:
    """(joiner, text) pieces of a block, each within budget. The joiner is what
    goes between this piece and the previous one when they share a chunk."""
    if ntok(block) <= budget:
        return [("\n\n", block)]
    out = []
    for i, line in enumerate(block.split("\n")):
        joiner = "\n\n" if i == 0 else "\n"
        if ntok(line) <= budget:
            out.append((joiner, line))
            continue
        for j, sent in enumerate(SENTENCE.findall(line)):
            for k, part in enumerate(_hard_split(sent, budget, ntok)):
                out.append((joiner if j == k == 0 else "", part))
    return out


def _common(paths) -> tuple:
    paths = list(paths)
    out = paths[0]
    for p in paths[1:]:
        n = 0
        while n < min(len(out), len(p)) and out[n] == p[n]:
            n += 1
        out = out[:n]
    return out


def chunk_note(
    text: str,
    path: str,
    ntok: Callable[[str], int],
    max_tokens: int = 300,
    overlap_tokens: int = 50,
    min_tokens: int = 80,
    title: str = "",
) -> list[dict]:
    """Chunk one note. Returns [{"text", "heading"}], never empty.

    Args:
        text: The note's markdown.
        path: Vault-relative path, used in the context header.
        ntok: Token counter of the embedding model (no special tokens).
        max_tokens: Upper bound per chunk, header included.
        overlap_tokens: Trailing text of a chunk repeated at the start of the
            next, only within one section and only in whole pieces.
        min_tokens: A chunk smaller than this absorbs the next section instead
            of ending at its heading, so runs of tiny sections don't become
            near-empty chunks.
        title: The note's title when the caller already split off the
            frontmatter; otherwise it is read from the frontmatter in `text`.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    fm_title, body = _split_frontmatter(text)
    title = title or fm_title
    name = path[:-3] if path.endswith(".md") else path
    stem = name.rsplit("/", 1)[-1]
    base = name if not title or title == stem else f"{name} ({title})"

    def header(p: tuple) -> str:
        if p and p[0] in (stem, title):  # "Git > Git": the H1 repeats the name
            p = p[1:]
        return " > ".join((base,) + p)

    chunks: list[dict] = []
    # (path, joiner, text, tokens, is_heading)
    cur: list[tuple[tuple, str, str, int, bool]] = []

    def size() -> int:
        return sum(c[3] for c in cur)

    def path_of(items) -> tuple:
        blocks = [c[0] for c in items if not c[4]]
        return _common(blocks or [c[0] for c in items])

    def budget(p: tuple) -> int:
        return max(max_tokens - ntok(header(p)) - 2, 64)

    def flush(overlap_path=None):
        nonlocal cur
        if not any(not c[4] for c in cur):  # headings with no text under them
            cur = []
            return
        p = path_of(cur)
        items = list(cur)
        while items and items[0][4] and len(items[0][0]) <= len(p):
            items.pop(0)  # a leading heading the chunk header already names
        while items and items[-1][4]:
            items.pop()  # a trailing heading whose text went to the next chunk
        body_text = "".join((c[1] if i else "") + c[2] for i, c in enumerate(items))
        chunks.append({"text": header(p) + "\n\n" + body_text.strip("\n"), "heading": " > ".join(p)})
        keep: list = []
        if overlap_path is not None:
            for item in reversed(cur):
                if item[0] != overlap_path or sum(c[3] for c in keep) + item[3] > overlap_tokens:
                    break
                keep.insert(0, item)
        cur = keep

    for kind, p, text_ in _units(body):
        if kind == "heading":
            if cur and size() >= min_tokens:
                flush()
            # Kept inline; dropped at flush if it leads the chunk and the
            # header names it, so it only shows when tiny sections merge.
            cur.append((p, "\n\n", text_, ntok(text_), True))
            continue
        for joiner, piece in _pieces(text_, budget(p), ntok):
            t = ntok(piece)
            if any(not c[4] for c in cur) and size() + t > budget(path_of(cur + [(p, "", "", 0, False)])):
                flush(overlap_path=p)
                # an overlap that no longer leaves room for this piece is dropped
                if cur and size() + t > budget(p):
                    cur = []
            cur.append((p, joiner, piece, t, False))
    flush()
    if not chunks:
        chunks.append({"text": header(()), "heading": ""})
    return chunks
