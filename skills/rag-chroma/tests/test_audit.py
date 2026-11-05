import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'rag-mcp'))
import audit


class AuditTests(unittest.TestCase):
    def test_calls_and_errors_share_ids_and_store_retrieval(self):
        async def search(query):
            return {'results': [{'id': 'note::1', 'score': .9, 'metadata': {'source': 'note'}}]}
        async def failure(query):
            raise ValueError('bad query')
        with tempfile.TemporaryDirectory() as temp, patch.object(audit, 'LOG_DIR', Path(temp)):
            asyncio.run(audit.audited(search)('hello'))
            with self.assertRaises(ValueError):
                asyncio.run(audit.audited(failure)('broken'))
            rows = list(reversed(audit.read_events()['events']))
            self.assertEqual([r['event'] for r in rows], ['tool_start', 'tool_end', 'tool_start', 'tool_error'])
            self.assertEqual(rows[0]['call_id'], rows[1]['call_id'])
            self.assertNotEqual(rows[0]['call_id'], rows[2]['call_id'])
            self.assertEqual(rows[1]['retrieved'][0]['id'], 'note::1')
            self.assertEqual(rows[0]['arguments']['query'], 'hello')

    def test_ingest_logs_ids_not_full_content(self):
        async def ingest(documents):
            return {'ingested': 1}
        with tempfile.TemporaryDirectory() as temp, patch.object(audit, 'LOG_DIR', Path(temp)):
            asyncio.run(audit.audited(ingest)([{'id': 'one', 'content': 'private document'}]))
            self.assertNotIn('private document', json.dumps(audit.read_events()))

    def test_date_rejects_traversal(self):
        with self.assertRaises(ValueError):
            audit.read_events('../secret')


if __name__ == '__main__':
    unittest.main()
