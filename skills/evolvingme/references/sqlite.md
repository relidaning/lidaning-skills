# SQLite operations

Install Python dependencies from `../requirements.txt` into your chosen Python
environment (`python3 -m pip install -r <skill>/requirements.txt`). Python's
standard `sqlite3` module handles storage; no server or MCP registration is needed.
Resolve `<skill>` from the installed symlink before running these commands.

```sh
python3 <skill>/scripts/store.py append < revision.json
python3 <skill>/scripts/store.py list --domain coding
python3 <skill>/scripts/store.py list --id <record-uuid>
python3 <skill>/scripts/store.py import-jsonl /absolute/selected/data/root
python3 <skill>/scripts/store.py forget <record-uuid>
python3 <skill>/scripts/store.py metrics
```

Use host stdin/file tools with proper quoting; the placeholder syntax above is
illustrative. Supply the full record schema, not a partial payload. `append`
prints saved IDs; read back the current revision before showing a receipt.
`list` returns current heads only. SQL queries against `revisions` are available
for authorized historical inspection; domain reclassification preserves history.

Configuration: `EVOLVINGME_DATA_DIR` overrides `<app-root>/data/evolvingme/` and
must be absolute. The app root resolves from the script's real source, never cwd.
No automatic migration or root guessing occurs. The database uses a 30 second
busy timeout; busy/stale writes fail and must be retried after rereading the head.
Before cutover, run `import-jsonl` against the selected root. A malformed input
or conflict rolls back the whole import; correct it within authorized scope and
retry. No source file is deleted. Per-revision legacy JSON files require explicit
conversion to domain JSONL preserving all fields before import.

Technology map: Python CLI owns validation and lifecycle; jsonschema (dependency
constraint in requirements.txt) enforces record.schema.json; SQLite owns atomic
revision storage and indexed current heads. The stable boundary is complete v1
revision JSON. Replacing SQLite requires an adapter and a migration preserving
IDs, all revisions and provenance; changing an environment path cannot do that.

CLI invocations append payload-free JSON events to `<app-root>/logs/YYYY-MM-DD.log`
in UTC. Each event counts one completed invocation (including failures), with
operation, outcome and duration in milliseconds. `metrics` draws daily terminal
bars for run count, failure percentage and mean duration over the last seven
available daily files; unparseable lines are counted explicitly. No observations
means unavailable metrics. No record contents, source paths, IDs or exception
payloads enter these logs. Logs are append-only with no automatic retention;
rotate/remove them explicitly as needed. A log-write failure fails the invocation
and may occur after database commit: reread the saved head before retrying.
