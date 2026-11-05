"""Index replacement and scoped loading, with in-memory data and a fake vault."""
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1] / 'rag-mcp'
if not (ROOT / 'server.py').exists():
    ROOT = Path('/app')  # Docker test copy
sys.path.insert(0, str(ROOT))


class IndexingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fake_embedder = types.ModuleType('embedder')
        fake_embedder.MODEL_ID = 'test-model'
        fake_embedder.E5Embedder = type('Embedder', (), {'count_tokens': lambda self, t: len(t)})
        with patch.dict(sys.modules, {'embedder': fake_embedder}):
            spec = importlib.util.spec_from_file_location('rag_server_under_test', ROOT / 'server.py')
            cls.s = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.s)

    def test_chunker_only_upgrade_preserves_existing_collection(self):
        from unittest.mock import MagicMock
        client = MagicMock()
        client.list_collections.return_value = ['documents']
        client.get_collection.return_value.metadata = {'embed': 'test-model', 'chunker': 'old'}
        with patch.object(self.s, 'get_chroma', return_value=client):
            self.s._migrate_collections()
        client.delete_collection.assert_not_called()

    def test_failed_upsert_keeps_old_chunks(self):
        from unittest.mock import MagicMock
        col = MagicMock()
        col.get.return_value = {'ids': ['note.md::0', 'note.md::1']}
        col.upsert.side_effect = RuntimeError('embedding failed')
        with self.assertRaises(RuntimeError):
            self.s._index_note(col, 'note.md', {'content': '# One\nbody', 'frontmatter': {}}, 'sig')
        col.delete.assert_not_called()

    def test_successful_replace_removes_only_stale_ids(self):
        from unittest.mock import MagicMock
        col = MagicMock()
        col.get.return_value = {'ids': ['note.md::0', 'note.md::1']}
        with patch.object(self.s, 'event'):
            self.s._index_note(col, 'note.md', {'content': '# One\nbody', 'frontmatter': {}}, 'sig')
        col.delete.assert_called_once_with(ids=['note.md::1'])
        self.assertEqual(col.upsert.call_args.kwargs['metadatas'][0]['chunker'], 'md-structure-v3')

    def test_directory_load_uses_slash_boundary_and_reports_missing_notes(self):
        from unittest.mock import MagicMock
        vault = MagicMock()
        vault.list_notes.return_value = ['0_AI/one.md', '0_AI/missing.md', '0_AI_other/two.md', 'other.md']
        vault.read.return_value = {'0_AI/one.md': {'content': 'body', 'frontmatter': {}}}
        with patch.object(self.s, '_vault', vault), patch.object(self.s, 'get_collection'), patch.object(self.s, '_index_note', return_value=3):
            result = self.s._load(None, '0_AI/')
        vault.read.assert_called_once_with(['0_AI/one.md', '0_AI/missing.md'])
        self.assertEqual(result['ingested'], 3)
        self.assertEqual(result['errors'][0]['file'], '0_AI/missing.md')


if __name__ == '__main__':
    unittest.main()
