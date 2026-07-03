---
name: paper
description: >
  Activate when user asks to search, find, fetch, or download AI/ML/DL research
  papers, mentions arXiv, Hugging Face papers, Semantic Scholar, or gives an
  arXiv ID, paper title, or paper URL. Searches arXiv, HF papers, and Semantic
  Scholar via their public APIs and downloads PDFs to ~/papers/.
---

## Overview

Search and download research papers from the places people actually find AI/DL
papers: **arXiv** (canonical source + PDFs), **Hugging Face papers** (trending
/ daily papers, community picks), and **Semantic Scholar** (citation counts,
open-access PDFs for non-arXiv venues). All via public APIs with `curl` — no
keys, no MCP server.

Downloads go to `~/papers/` (create it if missing), named
`<arxiv-id> - <title>.pdf` (sanitize `/`, `:`, `?` out of titles).

## Sources

### arXiv — canonical search + PDF host

**Use HTTPS only** — plain `http://export.arxiv.org` returns nothing through
this machine's proxy.

```bash
# Search (Atom XML). Fields: all: ti: au: abs: cat:  — quote phrases as %22...%22
curl -s "https://export.arxiv.org/api/query?search_query=all:%22state+space+model%22&start=0&max_results=10&sortBy=relevance"

# Newest first: &sortBy=submittedDate&sortOrder=descending
# By ID (also accepts comma-separated list):
curl -s "https://export.arxiv.org/api/query?id_list=2312.00752"

# Download PDF (versionless URL = latest version; append v1/v2 to pin)
curl -sL -o ~/papers/"2312.00752 - Mamba.pdf" "https://arxiv.org/pdf/2312.00752"
```

Parse the Atom XML with python3 rather than grep:

```bash
curl -s "https://export.arxiv.org/api/query?search_query=ti:%22mamba%22&max_results=5" | python3 -c '
import sys, xml.etree.ElementTree as ET
ns = {"a": "http://www.w3.org/2005/Atom"}
for e in ET.parse(sys.stdin).getroot().findall("a:entry", ns):
    arxid = e.find("a:id", ns).text.split("/abs/")[-1]
    title = " ".join(e.find("a:title", ns).text.split())
    date  = e.find("a:published", ns).text[:10]
    print(f"{arxid}  {date}  {title}")'
```

### Hugging Face papers — trending & community

HF paper IDs **are** arXiv IDs; download the PDF from arXiv.

```bash
# Search
curl -s "https://huggingface.co/api/papers/search?q=<query>" | jq -r '.[].paper | "\(.id)  \(.title)"'

# Daily / trending papers (today, or pin a day with &date=YYYY-MM-DD)
curl -s "https://huggingface.co/api/daily_papers?limit=10" | jq -r '.[].paper | "\(.id)  \(.title)"'

# Detail for one paper (abstract, upvotes, authors)
curl -s "https://huggingface.co/api/papers/<arxiv_id>" | jq '{id, title, upvotes, summary}'
```

### Semantic Scholar — citations & non-arXiv PDFs (fallback)

Keyless access is aggressively rate-limited (429 is normal). Use it only when
arXiv/HF can't answer: citation counts, DOI lookup, or an open-access PDF for
a paper that isn't on arXiv. On 429, wait ~5s and retry once; if it still
fails, say so and move on.

```bash
curl -s "https://api.semanticscholar.org/graph/v1/paper/search?query=<query>&limit=10&fields=title,year,externalIds,openAccessPdf,citationCount"

# Direct lookup by external ID
curl -s "https://api.semanticscholar.org/graph/v1/paper/arXiv:2312.00752?fields=title,citationCount,openAccessPdf"
# also: paper/DOI:10.xxxx/yyyy
```

`openAccessPdf.url` is a direct PDF link when present.

## Workflows

### "Find papers about X"

1. Search arXiv (`search_query=all:%22X%22`, relevance sort) — present ID,
   date, title.
2. If the user wants "hot"/"trending"/"recent community" papers, use HF
   `daily_papers` or HF search instead.
3. Offer to download any of the hits.

### "Download <title | arXiv ID | URL>"

1. Extract the arXiv ID if present (`\d{4}\.\d{4,5}` — from `arxiv.org/abs/…`,
   `arxiv.org/pdf/…`, or `huggingface.co/papers/…` URLs).
2. Title only → search arXiv `ti:%22<title>%22` first; ambiguous matches →
   show the top hits and ask.
3. `mkdir -p ~/papers` then `curl -sL -o` the PDF.
4. Verify: `file` must say PDF and size must be plausible (>10 KB). arXiv
   sometimes serves an HTML error page with HTTP 200 — a tiny or non-PDF file
   means the download failed; report it, don't leave the bad file behind.

### "What's new / trending this week?"

HF `daily_papers` for today and recent dates; dedupe, present upvotes + titles.

### Save to Nextcloud

If the user asks to put a paper in their cloud storage, the `nextcloud`
skill's allowed scope already includes `papers/` — download locally first,
then upload via that skill (curl `-T` for PDFs, not MCP write).

## Rules

- **HTTPS everywhere** — the proxy silently drops plain-HTTP arXiv requests.
- **Be polite to arXiv**: one request at a time, no bulk scraping; batch ID
  lookups into a single `id_list` call.
- **Never fetch paywalled/pirated sources** (Sci-Hub etc.) — arXiv, HF, and
  `openAccessPdf` links only.
- **Don't read PDFs into context to "verify" them** — `file` + size check is
  enough; use the Read tool on a PDF only when the user asks about its content.
- **URL-encode queries** — spaces as `+`, quotes as `%22`.
