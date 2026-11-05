import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'rag-mcp'))
from chunker import chunk_note


class ChunkerTests(unittest.TestCase):
    def chunks(self, text, budget=1000, path='AI/note.md'):
        chunks = chunk_note(text, path, len, max_tokens=budget)
        self.assertTrue(all(len(c['text']) <= budget for c in chunks))
        return chunks

    def test_small_sibling_sections_never_merge(self):
        chunks = self.chunks('# A\nOne.\n# B\nTwo.')
        self.assertEqual([c['heading'] for c in chunks], ['A', 'B'])

    def test_whole_section_keeps_subsections(self):
        chunks = self.chunks('# A\nIntro.\n## B\nOne.\n## C\nTwo.')
        self.assertEqual(len(chunks), 1)
        self.assertIn('## B', chunks[0]['text'])
        self.assertIn('## C', chunks[0]['text'])

    def test_oversized_parent_recurses_before_paragraphs(self):
        chunks = self.chunks('# A\n## B\n' + 'word ' * 10 + '\n## C\n' + 'else ' * 10, 90)
        self.assertEqual([c['heading'] for c in chunks], ['A > B', 'A > C'])

    def test_paragraphs_preserved_without_overlap(self):
        chunks = self.chunks('# A\n' + 'a' * 40 + '\n\n' + 'b' * 40, 70)
        self.assertEqual(len(chunks), 2)
        self.assertNotIn('a', chunks[1]['text'].split('\n\n')[1])

    def test_sentences_are_last_semantic_boundary(self):
        chunks = self.chunks('# A\n' + 'First sentence is complete. Second sentence is complete.', 55)
        self.assertEqual(len(chunks), 2)
        self.assertTrue(all(c['text'].endswith('.') or c['text'].endswith('. ') for c in chunks))

    def test_unsplittable_text_has_explicit_fallback(self):
        chunks = self.chunks('# A\n' + 'z' * 200, 60)
        self.assertTrue(all(c['split_reason'] == 'token-limit' for c in chunks))
        self.assertEqual(''.join(c['text'].split('\n\n')[1] for c in chunks), 'z' * 200)

    def test_fenced_headings_are_not_sections(self):
        chunks = self.chunks('# A\n````python\n# code\n```\n\nmore\n````\n## B\ncontent')
        self.assertEqual(len(chunks), 1)
        self.assertIn('# code', chunks[0]['text'])

    def test_setext_and_skipped_heading_levels(self):
        chunks = self.chunks('Parent\n======\n#### Deep\n' + 'x' * 90, 70)
        self.assertTrue(all(c['heading'] == 'Parent > Deep' for c in chunks))

    def test_frontmatter_and_title(self):
        c = self.chunks('---\ntitle: Other title\nsecret: value\n---\n# A\nBody')[0]
        self.assertIn('note (Other title) > A', c['text'])
        self.assertNotIn('secret:', c['text'])

    def test_header_counts_toward_budget(self):
        self.chunks('# A\n' + '中文' * 60, 75, 'AI/longer/note.md')

    def test_oversized_header_fails_explicitly(self):
        with self.assertRaises(ValueError):
            self.chunks('# ' + 'a' * 200 + '\nbody', 40)

    def test_empty_and_heading_only(self):
        self.assertEqual(len(self.chunks('')), 1)
        self.assertEqual(self.chunks('# A')[0]['heading'], 'A')

    def test_trailing_heading_hashes_are_cleaned(self):
        self.assertEqual(self.chunks('# A ###\nbody')[0]['heading'], 'A')


if __name__ == '__main__':
    unittest.main()
