import json
from pathlib import Path
import tempfile
import unittest

from scripts.page_builder.issue_explorer import explorer_payload, render_issue_explorer


class IssueExplorerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir='tmps')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.report = self.root / 'report_20261107.md'
        self.markdown = '### Included paper\n\n**评分**: 8.0/10\n\n**期刊**: Nature\n'
        self.values = [
            {'paper': {'title': 'Included paper'}, 'primary_category': '认知神经科学', 'domain': '核心域', 'total_score': 8, 'cross_tags': ['记忆', '记忆']},
            {'paper': {'title': 'Not expanded'}, 'domain': '域外高影响', 'total_score': None},
            {'paper': {'title': 'Excluded paper'}, 'domain': '域外局限', 'total_score': 9},
        ]

    def write(self, name='LLM_results_20261107.json'):
        (self.root / name).write_text(json.dumps(self.values), encoding='utf-8')

    def test_cohort_and_unknowns_preserve_totals(self):
        self.write()
        data = explorer_payload(self.root, self.report, self.markdown)
        self.assertEqual((data['evaluated'], data['excluded'], len(data['rows'])), (3, 1, 2))
        self.assertEqual(sum(r['expanded'] for r in data['rows']), 1)
        self.assertEqual(data['rows'][1]['field'], '域外高影响（未分领域）')
        self.assertIsNone(data['rows'][1]['score'])
        self.assertEqual(data['rows'][0]['tags'], ['记忆'])

    def test_unmatched_or_ambiguous_corpus_is_not_used(self):
        self.write()
        self.assertIsNone(explorer_payload(self.root, self.report, self.markdown.replace('Included paper', 'Wrong paper')))
        self.write('LLM_results_20261107_alternate.json')
        self.assertIsNone(explorer_payload(self.root, self.report, self.markdown))

    def test_legacy_date_offset_requires_identity_match(self):
        self.write('LLM_results_20261106.json')
        self.assertEqual(explorer_payload(self.root, self.report, self.markdown)['source'], 'LLM_results_20261106.json')

    def test_duplicate_titles_do_not_inflate_counts(self):
        self.values.append(self.values[0])
        self.write()
        self.assertIsNone(explorer_payload(self.root, self.report, self.markdown))

    def test_invalid_scores_are_missing_and_script_text_is_safe(self):
        self.values[0]['total_score'] = float('nan')
        self.values[0]['title_zh'] = '</script><script>alert(1)</script>'
        self.write()
        data = explorer_payload(self.root, self.report, self.markdown)
        self.assertIsNone(data['rows'][0]['score'])
        rendered = render_issue_explorer(data)
        self.assertNotIn('</script><script>alert', rendered)
        self.assertIn('\\u003c/script', rendered)


if __name__ == '__main__':
    unittest.main()
