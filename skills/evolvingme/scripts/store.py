#!/usr/bin/env python3
"""Transactional EvolvingMe revision store. See references/sqlite.md."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

SKILL = Path(__file__).resolve().parents[1]
APP = SKILL.parents[1]


def root():
    value = os.environ.get('EVOLVINGME_DATA_DIR')
    path = Path(value) if value else APP / 'data/evolvingme'
    if not path.is_absolute():
        raise ValueError('EVOLVINGME_DATA_DIR must be absolute')
    return path


def validate(record):
    from jsonschema import Draft202012Validator, FormatChecker
    schema = json.loads((SKILL / 'references/record.schema.json').read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(record)


def connect():
    directory = root()
    directory.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(directory / 'evolvingme.sqlite3', timeout=30)
    db.execute('PRAGMA synchronous=FULL')
    db.execute('PRAGMA secure_delete=ON')
    db.executescript('''
        CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS revisions (
            revision_id TEXT PRIMARY KEY, id TEXT NOT NULL, kind TEXT NOT NULL,
            domain TEXT NOT NULL, supersedes TEXT UNIQUE REFERENCES revisions(revision_id),
            body TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS by_domain ON revisions(domain, kind, id);
        CREATE INDEX IF NOT EXISTS by_id ON revisions(id);
        CREATE VIEW IF NOT EXISTS heads AS
            SELECT r.* FROM revisions r WHERE NOT EXISTS
            (SELECT 1 FROM revisions n WHERE n.supersedes=r.revision_id);
    ''')
    return db


def append(db, record):
    validate(record)
    body = json.dumps(record, sort_keys=True, ensure_ascii=False)
    old = db.execute('SELECT body FROM revisions WHERE revision_id=?',
                     (record['revision_id'],)).fetchone()
    if old:
        if old[0] != body:
            raise ValueError('revision ID reused with different content')
        return False
    heads = db.execute('SELECT revision_id FROM heads WHERE id=?', (record['id'],)).fetchall()
    predecessor = record['supersedes']
    if predecessor:
        parent = db.execute('SELECT id, kind FROM revisions WHERE revision_id=?', (predecessor,)).fetchone()
        if parent != (record['id'], record['kind']) or heads != [(predecessor,)]:
            raise ValueError('predecessor must be the current head of the same record and kind')
    elif heads:
        raise ValueError('record already exists; supersedes is required')
    db.execute('INSERT INTO revisions VALUES (?,?,?,?,?,?)',
               (record['revision_id'], record['id'], record['kind'],
                record['scope']['domain'], predecessor, body))
    return True


def import_jsonl(db, source):
    pending = []
    for category, kind in [('decisions', 'decision'), ('principles', 'principle')]:
        for path in sorted((source / category).glob('*.jsonl')):
            with path.open() as stream:
                for line in stream:
                    record = json.loads(line)
                    validate(record)
                    if record['kind'] != kind or record['scope']['domain'] != path.stem:
                        raise ValueError('legacy file domain/kind mismatch')
                    pending.append(record)
    count = 0
    while pending:
        remaining = []
        for record in pending:
            parent = record['supersedes']
            if parent and not db.execute('SELECT 1 FROM revisions WHERE revision_id=?', (parent,)).fetchone():
                remaining.append(record)
            else:
                count += append(db, record)
        if len(remaining) == len(pending):
            raise ValueError('missing or cyclic predecessors in import')
        pending = remaining
    return count


def audit(command, ok, elapsed):
    now = datetime.now(timezone.utc)
    directory = APP / 'logs'
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / (now.strftime('%Y-%m-%d') + '.log')).open('a') as stream:
        stream.write(json.dumps(dict(timestamp=now.isoformat(), component='evolvingme',
                                    operation=command, success=ok, duration_ms=round(elapsed*1000, 2))) + '\n')


def metrics():
    buckets = {}
    for path in sorted((APP / 'logs').glob('????-??-??.log'))[-7:]:
        counts = Counter()
        with path.open() as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                    if event.get('component') == 'evolvingme':
                        counts['runs'] += 1
                        counts['failures'] += not event['success']
                        counts['duration_ms'] += event['duration_ms']
                except (ValueError, KeyError, TypeError):
                    counts['unparsed'] += 1
        buckets[path.stem] = counts
    print('UTC daily operations, last 7 available daily files; one event per completed CLI call')
    for day, c in buckets.items():
        n = c['runs']
        rate = f"{100*c['failures']/n:.1f}%" if n else 'N/A'
        mean = f"{c['duration_ms']/n:.1f}" if n else 'N/A'
        print(f"{day} {'█'*min(n, 60)} runs={n} failures={rate} mean_ms={mean} unparsed={c['unparsed']}")
    if not buckets:
        print('No observations available')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('append', help='read a complete revision from stdin')
    query = sub.add_parser('list', help='current heads, optionally filtered')
    query.add_argument('--domain')
    query.add_argument('--id')
    query.add_argument('--kind', choices=['decision', 'principle'])
    migration = sub.add_parser('import-jsonl')
    migration.add_argument('source', type=Path)
    forget = sub.add_parser('forget', help='delete all revisions of an explicitly authorized ID')
    forget.add_argument('id')
    sub.add_parser('metrics')
    args = parser.parse_args()
    started = time.monotonic()
    ok = False
    db = None
    try:
        if args.command == 'metrics':
            metrics()
        else:
            db = connect()
            db.execute('BEGIN IMMEDIATE')
            legacy = any(
                next((root() / category).glob('*.jsonl'), None) is not None
                for category in ('decisions', 'principles'))
            if args.command in ('append', 'list') and legacy and not db.execute(
                    "SELECT 1 FROM metadata WHERE key='legacy_imported'").fetchone():
                raise ValueError('import selected-root legacy records before recall or append')
            if args.command == 'append':
                record = json.load(sys.stdin)
                append(db, record)
                result = dict(id=record['id'], revision_id=record['revision_id'])
            elif args.command == 'import-jsonl':
                result = dict(imported=import_jsonl(db, args.source.resolve()))
                if args.source.resolve() == root().resolve():
                    db.execute("INSERT OR REPLACE INTO metadata VALUES ('legacy_imported','1')")
            elif args.command == 'forget':
                db.execute('DELETE FROM revisions WHERE id=?', (args.id,))
                result = dict(deleted_id=args.id)
            else:
                filters, values = [], []
                for key in ('domain', 'id', 'kind'):
                    value = getattr(args, key)
                    if value:
                        filters.append(key + '=?')
                        values.append(value)
                sql = 'SELECT body FROM heads' + (' WHERE ' + ' AND '.join(filters) if filters else '')
                result = [json.loads(row[0]) for row in db.execute(sql, values)]
            db.commit()
            print(json.dumps(result, ensure_ascii=False))
        ok = True
    except Exception as error:
        if db:
            db.rollback()
        # Do not leak record payloads through validator exception messages.
        print(f'EvolvingMe {args.command} failed ({type(error).__name__}); no transaction committed', file=sys.stderr)
        return 1
    finally:
        if db:
            db.close()
        audit(args.command, ok, time.monotonic()-started)
    return 0


if __name__ == '__main__':
    sys.exit(main())
