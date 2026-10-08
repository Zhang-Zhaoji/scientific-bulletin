from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from enrich_source_metadata import enrich


class SourceMetadataTests(unittest.TestCase):
    def test_existing_publisher_affiliations_survive_enrichment(self):
        root = Path(__file__).resolve().parents[1] / 'tmps'
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as directory:
            folder = Path(directory)
            source, output = folder / 'input.jsonl', folder / 'output.jsonl'
            paper = {'title': 'Source metadata preservation fixture', 'source': 'Publisher',
                     'authors': ['Researcher A'], 'abstract': 'Source abstract. ' * 8,
                     'author_details': [{'name': 'Researcher A', 'affiliation': 'Original University',
                                         'source': 'Publisher metadata'}]}
            source.write_text(json.dumps(paper) + '\n', encoding='utf-8')
            with patch('enrich_source_metadata.load_pubmed', return_value={}):
                enrich(source, output, folder / 'cache')
            enriched = json.loads(output.read_text(encoding='utf-8'))
            self.assertEqual(enriched['author_details'], paper['author_details'])
            self.assertEqual(enriched['affiliations'], ['Original University'])
            self.assertEqual(json.loads(source.read_text(encoding='utf-8')), paper)


if __name__ == '__main__':
    unittest.main()
