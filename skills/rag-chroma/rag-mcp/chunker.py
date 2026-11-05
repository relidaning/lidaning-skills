"""Section-first Markdown chunking with complete heading ancestry and no overlap.

Keep a section and its descendants together if it fits. Otherwise descend into
subsections, then paragraphs, sentences, and only then indivisible long text.
Token limits include the context header and are checked on the final text.
"""
import re
from dataclasses import dataclass, field
from typing import Callable

VERSION = "md-structure-v3"
FRONTMATTER = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.S)
FM_TITLE = re.compile(r"^title:[ \t]*(.+?)[ \t]*$", re.M)
HEADING = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.+?)[ \t]*$")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
SETEXT = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
HEADING_NUMBER = re.compile(r"^[⁠​\s]*(?:\d+\.)+\d*\s+")
SENTENCE = re.compile(r".+?(?:[。！？!?；;]+|\.(?=\s)|$)\s*", re.S)


@dataclass
class Section:
    level: int
    path: tuple
    heading: str = ""
    lines: list = field(default_factory=list)
    children: list = field(default_factory=list)


def _tree(body):
    root = Section(0, ())
    stack = [root]
    fence = None
    lines = body.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        f = FENCE.match(line)
        if fence:
            stack[-1].lines.append(line)
            if f and f[1][0] == fence[0] and len(f[1]) >= fence[1] and not f[2].strip():
                fence = None
            i += 1
            continue
        if f:
            fence = (f[1][0], len(f[1]))
        h = None if f else HEADING.match(line)
        setext = (SETEXT.match(lines[i + 1]) if not f and line.strip()
                  and i + 1 < len(lines) else None)
        if h or setext:
            level = len(h[1]) if h else (1 if setext[1][0] == "=" else 2)
            title = h[2] if h else line.strip()
            title = re.sub(r"\s+#+\s*$", "", title)
            title = HEADING_NUMBER.sub("", title).replace("⁠", "").replace("​", "").strip()
            while stack[-1].level >= level:
                stack.pop()
            section = Section(level, stack[-1].path + (title,), f"{'#' * level} {title}")
            stack[-1].children.append(section)
            stack.append(section)
            i += 2 if setext and not h else 1
        else:
            stack[-1].lines.append(line)
            i += 1
    return root


def _blocks(text):
    """Paragraphs, retaining blank lines within fenced blocks."""
    blocks, cur, fence = [], [], None
    for line in text.splitlines(keepends=True):
        f = FENCE.match(line.rstrip("\n"))
        if fence:
            cur.append(line)
            if f and f[1][0] == fence[0] and len(f[1]) >= fence[1] and not f[2].strip():
                fence = None
        elif f:
            fence = (f[1][0], len(f[1]))
            cur.append(line)
        elif not line.strip():
            if cur:
                blocks.append("".join(cur).strip("\n"))
                cur = []
        else:
            cur.append(line)
    if cur:
        blocks.append("".join(cur).strip("\n"))
    return blocks


def chunk_note(text: str, path: str, ntok: Callable[[str], int], max_tokens=300,
               overlap_tokens=0, min_tokens=0, title="") -> list[dict]:
    """Return text, heading and split_reason per chunk.

    overlap_tokens/min_tokens remain accepted for old callers; neither overlap
    nor merging unrelated sections is applied. An ancestry header too large to
    fit raises rather than silently dropping hierarchy or exceeding the limit.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    fm = FRONTMATTER.match(text)
    if fm:
        found = FM_TITLE.search(fm[1])
        title = title or (found[1].strip("'\"") if found else "")
        text = text[fm.end():]
    name = path[:-3] if path.endswith(".md") else path
    stem = name.rsplit("/", 1)[-1]
    base = name if not title or title == stem else f"{name} ({title})"
    out = []

    def render(p, body):
        header = " > ".join((base,) + p)
        return header + ("\n\n" + body.strip("\n") if body.strip("\n") else "")

    def fits(p, body):
        return ntok(render(p, body)) <= max_tokens

    def emit(p, body, reason):
        result = render(p, body)
        if ntok(result) > max_tokens:
            raise ValueError(f"Heading hierarchy exceeds {max_tokens} tokens: {path}")
        out.append({"text": result, "heading": " > ".join(p), "split_reason": reason})

    def hard_parts(p, value):
        # Only an indivisible sentence/block reaches this fallback.
        while value:
            lo, hi = 0, len(value)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if fits(p, value[:mid]):
                    lo = mid
                else:
                    hi = mid - 1
            if not lo:
                raise ValueError(f"No content fits after heading hierarchy: {path}")
            yield value[:lo]
            value = value[lo:]

    def split_body(p, body):
        current = ""
        for block in _blocks(body):
            candidate = current + ("\n\n" if current else "") + block
            if fits(p, candidate):
                current = candidate
                continue
            if current:
                emit(p, current, "paragraph")
                current = ""
            if fits(p, block):
                current = block
                continue
            sentence_chunk = ""
            for sentence in SENTENCE.findall(block):
                if fits(p, sentence_chunk + sentence):
                    sentence_chunk += sentence
                    continue
                if sentence_chunk:
                    emit(p, sentence_chunk, "sentence")
                    sentence_chunk = ""
                if fits(p, sentence):
                    sentence_chunk = sentence
                else:
                    for part in hard_parts(p, sentence):
                        emit(p, part, "token-limit")
            if sentence_chunk:
                emit(p, sentence_chunk, "sentence")
        if current:
            emit(p, current, "paragraph")

    def whole(node):
        parts = ["\n".join(node.lines).strip("\n")]
        for child in node.children:
            parts.append(child.heading + "\n\n" + whole(child))
        return "\n\n".join(p for p in parts if p)

    def visit(node):
        body = whole(node)
        if fits(node.path, body):
            emit(node.path, body, "section")
            return
        own = "\n".join(node.lines).strip("\n")
        if own.strip():
            split_body(node.path, own)
        for child in node.children:
            visit(child)

    root = _tree(text)
    # The document root is not permission to merge unrelated top-level sections.
    if (intro := "\n".join(root.lines).strip("\n")).strip():
        if fits((), intro):
            emit((), intro, "section")
        else:
            split_body((), intro)
    for node in root.children:
        visit(node)
    if not out:
        emit((), "", "section")
    return out
