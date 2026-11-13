import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

SCRIPT = Path(__file__).resolve().parents[1] / 'skills/evolvingme/scripts/store.py'
spec = importlib.util.spec_from_file_location('evolvingme_store', SCRIPT)
store = importlib.util.module_from_spec(spec)
spec.loader.exec_module(store)


def record():
    return dict(schema_version=1, kind='decision', id=str(uuid.uuid4()),
                revision_id=str(uuid.uuid4()), supersedes=None,
                created_at='2026-11-13T00:00:00Z',
                scope=dict(project='synthetic', domain='coding', conditions=[]),
                source=dict(kind='user', locator=None, summary='Synthetic fixture'),
                payload=dict(status='confirmed', situation='fixture', question='',
                             options=[], constraints=[], prediction=None, choice='SQLite',
                             user_rationale=None, agent_interpretation=None, principle_ids=[]))


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.env = patch.dict('os.environ', {'EVOLVINGME_DATA_DIR': str(self.base / 'data')})
        self.env.start()
        self.db = store.connect()

    def tearDown(self):
        self.db.close()
        self.env.stop()
        self.temp.cleanup()

    def test_revisions_idempotence_and_stale_writer(self):
        first = record()
        with self.db:
            self.assertTrue(store.append(self.db, first))
            self.assertFalse(store.append(self.db, first))
        second = copy.deepcopy(first)
        second.update(revision_id=str(uuid.uuid4()), supersedes=first['revision_id'])
        second['scope']['domain'] = 'storage'
        with self.db:
            store.append(self.db, second)
        self.assertEqual(self.db.execute('SELECT domain FROM heads').fetchall(), [('storage',)])
        stale = dict(second, revision_id=str(uuid.uuid4()))
        with self.assertRaises(ValueError), self.db:
            store.append(self.db, stale)
        changed = dict(first, created_at='2026-11-14T00:00:00Z')
        with self.assertRaises(ValueError), self.db:
            store.append(self.db, changed)

    def test_import_rollback_and_retry(self):
        directory = self.base / 'legacy/decisions'
        directory.mkdir(parents=True)
        first = record()
        second = dict(first, revision_id=str(uuid.uuid4()), supersedes=first['revision_id'])
        path = directory / 'coding.jsonl'
        path.write_text(json.dumps(second)+'\n'+json.dumps(first)+'\n')
        with self.db:
            self.assertEqual(store.import_jsonl(self.db, directory.parent), 2)
        with self.db:
            self.assertEqual(store.import_jsonl(self.db, directory.parent), 0)
        invalid = dict(record(), supersedes=str(uuid.uuid4()))
        path.write_text(json.dumps(record())+'\n'+json.dumps(invalid)+'\n')
        with self.assertRaises(ValueError), self.db:
            store.import_jsonl(self.db, directory.parent)
        self.assertEqual(self.db.execute('SELECT count(*) FROM revisions').fetchone()[0], 2)

    def test_validation_and_forget(self):
        bad = dict(record(), id='not-a-uuid')
        with self.assertRaises(Exception), self.db:
            store.append(self.db, bad)
        item = record()
        with self.db:
            store.append(self.db, item)
            store.append(self.db, dict(item, revision_id=str(uuid.uuid4()), supersedes=item['revision_id']))
        with self.db:
            self.db.execute('DELETE FROM revisions WHERE id=?', (item['id'],))
        self.assertEqual(self.db.execute('SELECT count(*) FROM heads').fetchone()[0], 0)

    def test_cli_logs_success_error_and_metrics(self):
        with patch.object(store, 'APP', self.base), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            with patch('sys.argv', ['store', 'append']), patch('sys.stdin', io.StringIO(json.dumps(record()))):
                self.assertEqual(store.main(), 0)
            with patch('sys.argv', ['store', 'append']), patch('sys.stdin', io.StringIO('{}')):
                self.assertEqual(store.main(), 1)
        events = [json.loads(line) for p in (self.base/'logs').glob('*.log') for line in p.read_text().splitlines()]
        self.assertEqual([e['success'] for e in events], [True, False])
        output = io.StringIO()
        with patch.object(store, 'APP', self.base), contextlib.redirect_stdout(output):
            store.metrics()
        self.assertIn('failures=50.0%', output.getvalue())
        self.assertNotIn('SQLite', json.dumps(events))

    def test_relative_override_rejected(self):
        with patch.dict('os.environ', {'EVOLVINGME_DATA_DIR': 'relative'}):
            with self.assertRaises(ValueError):
                store.root()


if __name__ == '__main__':
    unittest.main()
