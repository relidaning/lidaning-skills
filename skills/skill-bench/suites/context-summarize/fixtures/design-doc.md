# Design doc: transcript storage for skill-bench

## Context

The skill-bench harness needs a place to store raw trial transcripts. Today every run writes JSONL transcripts to .claude/skill-bench-runs, which is gitignored, so transcripts vanish when the directory is cleaned. Over the last month 14 runs produced 1.1 GB of transcripts, 92 percent of which were never opened after the run finished. This section was reviewed by the team and the numbers above were measured on the main workstation, not estimated, unless stated otherwise.

## Goals

Keep every transcript that a report links to for at least 90 days. Keep total disk use under 2 GB. Do not make runs slower: writing a transcript must stay under 50 milliseconds at the 95th percentile. Stay stdlib-only so the harness keeps working without a virtualenv. This section was reviewed by the team and the numbers above were measured on the main workstation, not estimated, unless stated otherwise.

## Non-goals

Searching across transcripts, deduplicating transcripts between runs, and uploading anything to a remote service are all out of scope for this change. A separate proposal may revisit remote storage once the Nextcloud quota question is settled. This section was reviewed by the team and the numbers above were measured on the main workstation, not estimated, unless stated otherwise.

## Options considered

Option A keeps plain JSONL files but gzips them after the run finishes; measured compression on real transcripts was 11 to 1. Option B stores transcripts in a single SQLite database with one row per trial; it compresses less well, about 4 to 1 with zlib on the blob column, and turns every write into a transaction, which measured 180 milliseconds at the 95th percentile on this machine because of fsync. Option C pushes transcripts to Nextcloud over WebDAV after each run; it removes the local disk limit but adds a network dependency that fails in cron sessions where the proxy environment is not set. This section was reviewed by the team and the numbers above were measured on the main workstation, not estimated, unless stated otherwise.

## Decision

We chose Option A, gzip after the run. It meets the latency goal because compression happens once, after all trials finish, not per write. With an 11 to 1 ratio, 90 days of transcripts at the current rate fit in roughly 300 MB. Option B was rejected on write latency. Option C was rejected because of the cron proxy problem, which has already broken two other automations on this machine. This section was reviewed by the team and the numbers above were measured on the main workstation, not estimated, unless stated otherwise.

## Retention

A retention sweep runs at the start of every benchmark run and deletes gzipped transcripts older than 90 days unless the run is pinned. Pinning is a file named PINNED in the run directory. Runs referenced from history.jsonl as the latest entry for a model are pinned automatically so that comparisons never point at deleted data. This section was reviewed by the team and the numbers above were measured on the main workstation, not estimated, unless stated otherwise.

## Risks

If a run crashes before compression, its transcripts stay uncompressed; the sweep compresses any leftover plain files it finds, so the worst case is one run's worth of uncompressed data. Gzip makes grep slower; zgrep covers the common debugging path. The 90 day window is a guess and may need to become 180 days if regressions are often discovered late. This section was reviewed by the team and the numbers above were measured on the main workstation, not estimated, unless stated otherwise.

## Rollout

Ship behind no flag, since the change is internal. Owner: Jing. Target date: 2026-10-15. The first run after upgrade compresses the existing backlog once, which is expected to take about two minutes. This section was reviewed by the team and the numbers above were measured on the main workstation, not estimated, unless stated otherwise.

## Open questions

Should pinned runs count toward the 2 GB cap? Should the sweep log what it deleted to the run manifest, or to a separate log file? Nobody has decided whether the 2 GB cap is a hard limit that blocks new runs or a soft warning. This section was reviewed by the team and the numbers above were measured on the main workstation, not estimated, unless stated otherwise.

