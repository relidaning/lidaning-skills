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

Configuration is owned by EvolvingMe: `EVOLVINGME_DATA_DIR` overrides `data_dir`
in `EVOLVINGME_CONFIG` (absolute JSON filename), or the default
`scripts/config.local.json` relative to the real skill source. Without either setting the existing
`<app-root>/data/evolvingme/` default remains. See the SKILL.md configuration
contract and tracked `../scripts/config.example.json`; copy the example to the
Git-ignored `../scripts/config.local.json` and edit only that local copy; no cloud-storage skill is required.
Config-file data paths may be absolute, start with `~/`, or be relative to the
config file directory. The environment data-path override must be absolute. Invalid
configuration fails without a fallback. No setting migrates existing records.
The app root resolves from the script's real source, never cwd.
The database uses a 30 second
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

### Database-file path compatibility

`data_dir` and `EVOLVINGME_DATA_DIR` also accept a SQLite filename ending in
`.sqlite3`, `.sqlite`, or `.db`. An existing directory always remains a data
directory, regardless of its suffix. For file paths, the database is opened
at that exact path; domain notebooks and legacy imports use its parent directory.
Relative config-file paths still resolve against the config file directory.
This selects storage only; it never moves or merges existing data.
