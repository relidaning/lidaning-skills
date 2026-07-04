---
name: paper-fetch
description: >
  Activate whenever research papers come up in the conversation — asking
  whether a paper exists, discussing a paper or model report, or asking to
  search, find, fetch, read, or download AI/ML/DL papers; also on any mention
  of arXiv, Hugging Face papers, Semantic Scholar, an arXiv ID, paper title,
  or paper URL. Searches arXiv, HF papers, and Semantic Scholar via their
  public APIs, downloads PDFs to ~/papers/, and stores them in Nextcloud
  papers/.
---

## Overview

Search and download research papers from the places people actually find AI/DL
papers: **arXiv** (canonical source + PDFs), **Hugging Face papers** (trending
/ daily papers, community picks), and **Semantic Scholar** (citation counts,
open-access PDFs for non-arXiv venues). All via public APIs with `curl` — no
keys, no MCP server.

Downloads go to `~/papers/` (create it if missing), named
`<arxiv-id> - <title>.pdf` (sanitize `/`, `:`, `?` out of titles), and are
then uploaded to Nextcloud `papers/` (see "Store in Nextcloud" below) — the
local copy stays as a cache.

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

### Search vs download

"Is there a paper about X?" / "what's new?" = **search**: run the queries,
present hits, and end by offering to download. Fetch PDFs only when the user
asks for a download (or accepts the offer) — never auto-download every
search hit.

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
5. Upload the verified PDF to Nextcloud `papers/` (next section). If Nextcloud
   is unreachable, keep the local copy, tell the user the upload failed, and
   don't retry endlessly.

### "What's new / trending this week?"

HF `daily_papers` for today and recent dates; dedupe, present upvotes + titles.

### Store in Nextcloud (standard step after every download)

Every verified download is uploaded to Nextcloud `papers/` — the one
directory the `nextcloud-paper` skill's allowlist permits. Use curl WebDAV
directly (not MCP write — PDFs are too big to pipe through context):

```bash
source ~/.zshrc.local   # NEXTCLOUD_HOST / _USERNAME / _PASSWORD (app password)
f="1706.03762 - Attention Is All You Need.pdf"
enc=$(python3 -c 'import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))' "$f")
curl -s --noproxy '*' -u "$NEXTCLOUD_USERNAME:$NEXTCLOUD_PASSWORD" \
  -T ~/papers/"$f" \
  "$NEXTCLOUD_HOST/remote.php/dav/files/$NEXTCLOUD_USERNAME/papers/$enc" \
  -w "%{http_code}\n"
```

- **201** = created, **204** = overwrote an existing file; anything else is a
  failure — report it.
- **`--noproxy '*'` is mandatory** — this machine's global `http_proxy`
  points at the xray proxy and `no_proxy` is empty, so without it requests to
  `127.0.0.1:8080` get routed into the proxy and fail.
- **URL-encode the filename** (spaces, `&`, …) as shown; curl does not encode
  `-T` target URLs for you.
- Skip the upload only if the user explicitly says local-only.

## Rules

- **HTTPS everywhere** — the proxy silently drops plain-HTTP arXiv requests.
- **Be polite to arXiv**: one request at a time, no bulk scraping; batch ID
  lookups into a single `id_list` call. arXiv also 429s ("Rate exceeded",
  sometimes as an empty body) after repeated calls — wait ~10 s and retry
  once; if a search just ran minutes ago, reuse its result instead of
  re-querying.
- **Never fetch paywalled/pirated sources** (Sci-Hub etc.) — arXiv, HF, and
  `openAccessPdf` links only.
- **Don't read PDFs into context to "verify" them** — `file` + size check is
  enough; use the Read tool on a PDF only when the user asks about its content.
- **URL-encode queries** — spaces as `+`, quotes as `%22`.
