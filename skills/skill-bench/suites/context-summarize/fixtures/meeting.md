# Sync: myfollows storage migration — 2026-09-18

Attendees: Li, Wei, Jing

## Discussion

Wei opened by recapping the problem: the SQLite file behind myfollows is now
2.3 GB, and the nightly sync job holds a write lock for up to 40 minutes,
which blocks the web UI's "mark watched" button during that window.

Two options were on the table. Mongo was attractive because the video
metadata is already JSON-shaped, but Jing pointed out we'd lose the ad-hoc SQL
queries she runs for the weekly stats. Postgres keeps SQL, handles concurrent
writers, and the FastAPI code already goes through SQLAlchemy, so the port is
mostly a connection-string change plus two raw queries.

## Decisions

- Migrate from SQLite to **Postgres 16** (not Mongo). Rationale: concurrent
  writes + keep SQL for stats.
- Li owns the migration. Target: cut over by **2026-10-03**.
- Keep the SQLite file read-only for 30 days after cutover as a fallback.

## Open questions

- Backup budget is unresolved: Wei wants daily off-site dumps (~$12/month),
  Jing thinks weekly is enough. Revisit next sync.
- Whether the thumbnail cache (18 GB on disk) moves too — nobody owned this.

## Action items

- Li: write the Alembic migration and a dry-run script by 2026-09-25.
- Wei: benchmark the nightly sync against a Postgres container.
- Jing: list every raw SQL query in the stats notebook.
