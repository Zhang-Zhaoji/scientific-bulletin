from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_bulletin_abstracts import canonical_doi, identity, substantive
from recover_bulletin_abstracts import verified
from sync_recovered_abstract_database import projection


class AbstractRecoveryTests(unittest.TestCase):
    def test_commentary_pointer_is_not_an_abstract(self):
        self.assertFalse(substantive('This scientific commentary refers to a published study. ' * 3))
        self.assertFalse(substantive('No abstract available. ' * 5))
        self.assertTrue(substantive('We measured neuronal responses and tested a causal hypothesis. ' * 3))

    def test_identifier_conflict_overrides_matching_title_and_pmid(self):
        paper = {'title': 'A measured neural mechanism', 'doi': '10.1234/original', 'pmid': '123'}
        self.assertFalse(verified(paper, dict(paper, doi='10.1234/another')))
        self.assertFalse(verified(paper, dict(paper, pmid='456')))
        self.assertTrue(verified(paper, dict(paper, doi='https://doi.org/10.1234/ORIGINAL')))

    def test_matching_title_alone_is_insufficient(self):
        self.assertFalse(verified({'title': 'A measured neural mechanism'}, {'title': 'A measured neural mechanism'}))
        self.assertFalse(verified({'title': 'A measured neural mechanism', 'pmid': '123'},
                                  {'title': 'A completely unrelated article', 'pmid': '123'}))

    def test_preprint_versions_remain_distinct(self):
        paper = {'title': 'A preprint', 'source': 'bioRxiv', 'doi': '10.1101/example', 'version': '1'}
        self.assertNotEqual(identity(paper), identity(dict(paper, version='2')))
        self.assertEqual(canonical_doi('https://doi.org/10.1234/EXAMPLE'), '10.1234/example')

    def test_database_projection_preserves_stored_publication_variant(self):
        stored = {'title': 'A measured neural mechanism', 'doi': '10.1234/example', 'pub_date': '2026-04-01'}
        earlier = {'_issue_date': '20260404', 'paper': {'raw_data': dict(stored, date='2026-04-01')}}
        later = {'_issue_date': '20260501', 'paper': {'raw_data': dict(stored, date='2026-04-28')}}
        self.assertIs(projection([later, earlier], stored), earlier)


if __name__ == '__main__':
    unittest.main()
