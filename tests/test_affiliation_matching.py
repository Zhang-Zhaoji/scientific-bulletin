import json
from pathlib import Path
import sys
import unittest
import tempfile
import xml.etree.ElementTree as ET
import sqlite3
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from supp_func import ROR_Search
from ror_refine_batch import ror_refine_paper
from enrich_source_metadata import author_name_matches, merge_author_details, load_pubmed, parse_pubmed_root,normalize_orcid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sql_scripts.build_sqlite import parse_work_details, resolved_author_institutions
from crawler_arxiv import parse_arxiv_entry
from scripts.refresh_bulletin_affiliations import refresh
from scripts.backfill_historical_authors import supplement_paper,valid_source
from source_author_parsers import parse_arxiv_authors


class AffiliationMatchingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matcher = ROR_Search()

    def test_california_campus_name_survives_comma(self):
        result = self.matcher.match_affiliation('Department of Psychology, University of California, Davis, USA')
        self.assertIn('University of California, Davis', [r['name'] for r in result['institutions']])
        self.assertEqual(result['countries'], ['United States'])

    def test_case_and_unicode_do_not_break_names(self):
        result = self.matcher.match_affiliation('UNIVERSITY OF OXFORD, Oxford, uk')
        self.assertEqual(result['institutions'][0]['name'], 'University of Oxford')
        self.assertEqual(result['countries'], ['United Kingdom'])

    def test_postal_state_codes_are_not_countries(self):
        for code in ['PA','MA','CA','IL','IN','GA']:
            with self.subTest(code=code):
                result = self.matcher.match_affiliation(f'Unregistered Laboratory, {code} 12345')
                self.assertEqual(result['countries'], ['United States'])
                self.assertEqual(result['institutions'], [])

    def test_short_acronym_requires_country_and_is_not_a_state_code(self):
        result=self.matcher.match_affiliation('NIH, Bethesda, USA')
        self.assertIn('National Institutes of Health',[r['name'] for r in result['institutions']])
        self.assertEqual(self.matcher.match_affiliation('NIH')['institutions'],[])
        self.assertEqual(self.matcher.match_affiliation('Unregistered Laboratory, MA, USA')['institutions'],[])

    def test_institution_without_address_commas_keeps_country_evidence(self):
        result=self.matcher.match_affiliation('University of Oxford Oxford UK')
        self.assertEqual(result['countries'],['United Kingdom'])
        self.assertEqual(result['institutions'][0]['name'],'University of Oxford')

    def test_beth_israel_is_not_an_israeli_address(self):
        result = self.matcher.match_affiliation('Beth Israel Deaconess Medical Center, Harvard Medical School, Boston, MA, USA.')
        self.assertEqual(result['countries'], ['United States'])
        self.assertIn('Beth Israel Deaconess Medical Center',[r['name'] for r in result['institutions']])

    def test_country_only_is_retained_without_institution(self):
        result = self.matcher.match_affiliation('Unregistered Private Laboratory, Czech Republic')
        self.assertEqual(result['countries'], ['Czechia'])
        self.assertEqual(result['institutions'], [])

    def test_two_institutions_are_retained(self):
        result = self.matcher.match_affiliation('Massachusetts General Hospital and Harvard Medical School, Boston, USA')
        self.assertEqual({r['name'] for r in result['institutions']},{'Massachusetts General Hospital','Harvard University'})
        harvard = next(r for r in result['institutions'] if r['name']=='Harvard University')
        self.assertEqual(harvard['method'],'reviewed_parent')

    def test_incompatible_country_does_not_get_fuzzy_institution(self):
        result = self.matcher.match_affiliation('University of Oxford, Paris, France')
        self.assertEqual(result['institutions'], [])
        self.assertEqual(result['countries'], ['France'])

    def test_email_city_and_unknown_do_not_become_institutions(self):
        for text in ['example@mit.edu','Cambridge, UK','Unverified Experimental Group']:
            with self.subTest(text=text):
                self.assertEqual(self.matcher.match_affiliation(text)['institutions'], [])

    def test_hong_kong_address_with_explicit_china_matches(self):
        result = self.matcher.match_affiliation('City University of Hong Kong, Hong Kong SAR 999077, China')
        self.assertIn('City University of Hong Kong',[r['name'] for r in result['institutions']])
        self.assertEqual(result['countries'],['China'])

    def test_country_is_independent_of_organization_in_batch(self):
        paper={'author_details':[{'name':'A','affiliation':'Unregistered Private Laboratory, Canada'}]}
        ror_refine_paper(paper,self.matcher)
        self.assertEqual(paper['author_details'][0]['ror_normalized_affiliation'],[])
        self.assertEqual(paper['author_details'][0]['ror_country'],['Canada'])
        parsed = parse_work_details(paper, {'domain':'域外局限'})
        self.assertEqual(parsed[2], [])
        self.assertIn('Canada', [c['name'] for c in parsed[3]])

    def test_basic_word_does_not_match_center_acronym(self):
        result = self.matcher.match_affiliation('School of Basic Medical Sciences, Tsinghua University, Beijing, China')
        self.assertEqual([r['name'] for r in result['institutions']],['Tsinghua University'])

    def test_illinois_campuses_remain_distinct(self):
        result=self.matcher.match_affiliation('University of Illinois Chicago, Chicago, IL, USA')
        self.assertEqual([r['name'] for r in result['institutions']],['University of Illinois Chicago'])

    def test_fuzzy_does_not_replace_distinctive_place_or_disease(self):
        for name in ['Affiliated Hospital of Xuzhou Medical University, Xuzhou, China',
                     'National Clinical Research Center for Eye Diseases, Shanghai, China',
                     'University of Southern Punjab, Multan, Pakistan',
                     'University of Texas San Antonio, San Antonio, USA']:
            with self.subTest(name=name):
                self.assertEqual(self.matcher.match_affiliation(name)['institutions'],[])

    def test_embedded_charity_is_not_independent_unit(self):
        result=self.matcher.match_affiliation('The Breast Cancer Now Toby Robins Research Centre, The Institute of Cancer Research, London, UK')
        self.assertEqual([r['name'] for r in result['institutions']],['Institute of Cancer Research'])

    def test_explicit_state_rejects_unrelated_generic_institute(self):
        result=self.matcher.match_affiliation('Cancer Research Institute, Beth Israel Deaconess Medical Center, Boston, MA, USA')
        self.assertNotIn('Cancer Research Institute',[r['name'] for r in result['institutions']])
        self.assertEqual(result['subregions'],['Massachusetts'])

    def test_exact_distinctive_organization_can_have_a_branch(self):
        result=self.matcher.match_affiliation('Howard Hughes Medical Institute, Massachusetts General Hospital, Boston, MA 02114, USA')
        self.assertIn('Howard Hughes Medical Institute',[r['name'] for r in result['institutions']])
        self.assertEqual(result['subregions'],['Massachusetts'])

    def test_structured_geography_is_not_zipped_to_flat_arrays(self):
        author={'affiliation_resolution':[{'input':'Original address','institutions':[
            {'name':'Unit A','country':'Canada'}, {'name':'Unit B','country':'France'}]}],
            'ror_normalized_affiliation':['Unit A','Unit B'], 'ror_country':['France','Canada']}
        self.assertEqual([(r['name'],r['country_name']) for r in resolved_author_institutions(author)],
                         [('Unit A','Canada'),('Unit B','France')])

    def test_empty_resolution_does_not_resurrect_old_guessed_unit(self):
        author={'affiliation_resolution':[], 'normalized_affiliation':['Wrong old organization']}
        self.assertEqual(resolved_author_institutions(author),[])

    def test_pubmed_cache_reuse_is_independent_of_batch_composition(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'tmps') as folder:
            path=Path(folder)
            (path/'pubmed_oldbatch.xml').write_text('<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>123</PMID><Article><ArticleTitle>Cached</ArticleTitle></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>')
            with patch('enrich_source_metadata.requests.get') as get:
                records=load_pubmed(['123'],path)
                self.assertEqual(records['123']['title'],'Cached')
                get.assert_not_called()

    def test_arxiv_optional_author_affiliation_is_preserved(self):
        ns={'atom':'http://www.w3.org/2005/Atom','arxiv':'http://arxiv.org/schemas/atom'}
        entry=ET.fromstring('<entry xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom"><id>http://arxiv.org/abs/2610.00001v1</id><title>Example</title><published>2026-10-01T00:00:00Z</published><author><name>A Researcher</name><arxiv:affiliation>University of Oxford</arxiv:affiliation></author></entry>')
        paper=parse_arxiv_entry(entry,ns)
        self.assertEqual(paper['author_details'][0]['affiliation'],'University of Oxford')

    def test_database_refresh_preserves_scores_and_shared_author_history(self):
        conn=sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        conn.executescript((Path(__file__).resolve().parents[1]/'sql_scripts/schema.sql').read_text(encoding='utf-8'))
        conn.executescript("""
            INSERT INTO articles(id,title,doi,score) VALUES(1,'Selected','10.test/a',7),(2,'Historical','10.test/b',8);
            INSERT INTO countries(id,standard_name,country_name) VALUES(1,'United States','United States');
            INSERT INTO institutions(id,name,country_id) VALUES(1,'Wrong old unit',1);
            INSERT INTO authors(id,name) VALUES(1,'Exclusive'),(2,'Shared');
            INSERT INTO article_authors(article_id,author_id) VALUES(1,1),(1,2),(2,2);
            INSERT INTO author_institutions(author_id,institution_id) VALUES(1,1),(2,1);
            INSERT INTO article_institutions(article_id,institution_id) VALUES(1,1),(2,1);
            INSERT INTO article_countries(article_id,country_id) VALUES(1,1),(2,1);
        """)
        paper={'title':'Selected','doi':'10.test/a','countries':['Canada'],'author_details':[
            {'name':n,'ror_country':['Canada'],'affiliation_resolution':[]} for n in ['Exclusive','Shared']]}
        result=refresh(conn,[paper],self.matcher)
        self.assertEqual(result['shared_historical_authors_preserved'],1)
        self.assertEqual(list(conn.execute('SELECT id,score FROM articles ORDER BY id')),[(1,7),(2,8)])
        self.assertEqual(list(conn.execute('SELECT article_id,institution_id FROM article_institutions')),[(2,1)])
        self.assertEqual(list(conn.execute('SELECT author_id,institution_id FROM author_institutions')),[(2,1)])
        self.assertEqual(list(conn.execute('SELECT c.standard_name FROM article_countries a JOIN countries c ON c.id=a.country_id WHERE a.article_id=1')),[('Canada',)])
        repeated=refresh(conn,[paper],self.matcher)
        self.assertEqual(repeated['statistics']['article_countries_removed'],0)
        self.assertEqual(repeated['statistics']['article_countries_added'],0)

    def test_all_initials_disambiguate_corresponding_author(self):
        self.assertTrue(author_name_matches('Orr, A. G.','Anna G Orr'))
        self.assertFalse(author_name_matches('Orr, A. L.','Anna G Orr'))
        self.assertTrue(author_name_matches('Saito, M. L.','Mitsuyoshi Luke Saito'))
        self.assertFalse(author_name_matches('Saito, M. R.','Mitsuyoshi Luke Saito'))

    def test_name_diacritics_match(self):
        self.assertTrue(author_name_matches('Pinol, R. A.','Ramón A. Piñol'))
        self.assertTrue(author_name_matches('Schröder, S.','Sylvia Schröder'))

    def test_compact_pubmed_initials_expand_without_merging_full_given_names(self):
        self.assertTrue(author_name_matches('Boyko JD','Jeremy D Boyko'))
        self.assertTrue(author_name_matches('Smith, John','John Smith'))
        self.assertFalse(author_name_matches('Smith, John','Jean Smith'))
        self.assertFalse(author_name_matches('John Smith','Jean Smith'))

    def test_publication_identifiers_override_title_variants_but_reject_conflicts(self):
        self.assertTrue(valid_source({'title':'Short listing title','doi':'10.test/a'}, {'title':'Full published title','doi':'10.test/a'}))
        self.assertFalse(valid_source({'title':'Same title','doi':'10.test/a'}, {'title':'Same title','doi':'10.test/b'}))

    def test_pubmed_source_orcid_and_all_author_affiliations(self):
        root=ET.fromstring('<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>12</PMID><Article><ArticleTitle>Study</ArticleTitle><AuthorList><Author><LastName>Smith</LastName><ForeName>Sarah A</ForeName><Identifier Source="ORCID">0000-0002-1825-0097</Identifier><AffiliationInfo><Affiliation>University of Oxford</Affiliation></AffiliationInfo></Author></AuthorList></Article></MedlineCitation><PubmedData><ArticleIdList><ArticleId IdType="doi">10.test/a</ArticleId></ArticleIdList></PubmedData></PubmedArticle></PubmedArticleSet>')
        record=parse_pubmed_root(root)['12']
        self.assertEqual(record['author_details'][0]['orcid'],'https://orcid.org/0000-0002-1825-0097')
        paper,audit=supplement_paper({'title':'Study','doi':'10.test/a','pmid':'12','authors':['Smith SA'],
                                    'author_details':[{'name':'Smith SA','affiliation':'Wrong current employer','source':'OpenAlex'}]},
                                   {'12':record},{},{})
        self.assertEqual(paper['authors'],['Sarah A Smith'])
        self.assertEqual(paper['author_details'][0]['affiliation'],'University of Oxford')
        self.assertTrue(audit['source_verified'])

    def test_arxiv_numeric_markers_assign_only_explicit_units(self):
        markup='<h1 class="ltx_title_document">Study</h1><div class="ltx_authors"><span class="ltx_personname"><b>Alice Smith<sup>1,2,*</sup> Bob Jones<sup>2</sup></b><sup>1</sup>University of Oxford<sup>2</sup>University of Cambridge<sup>*</sup>Equal contribution</span></div>'
        parsed=parse_arxiv_authors(markup,['Alice Smith','Bob Jones'],'https://arxiv.org/html/test')
        self.assertEqual(parsed['author_details'][0]['affiliation'],'University of Oxford; University of Cambridge')
        self.assertEqual(parsed['author_details'][1]['affiliation'],'University of Cambridge')

    def test_orcid_check_digit_is_checked(self):
        self.assertEqual(normalize_orcid('0000-0002-1825-0097'),'https://orcid.org/0000-0002-1825-0097')
        self.assertIsNone(normalize_orcid('0000-0002-1825-0098'))

    def test_identical_institution_names_have_distinct_ror_database_rows(self):
        conn=sqlite3.connect(':memory:');self.addCleanup(conn.close)
        conn.executescript((Path(__file__).resolve().parents[1]/'sql_scripts/schema.sql').read_text(encoding='utf-8'))
        conn.executescript("INSERT INTO articles(id,title,doi) VALUES(1,'UK study','10.test/uk'),(2,'CA study','10.test/ca');")
        papers=[]
        for ident,title,country,address in [(1,'UK study','United Kingdom','Institute of Cancer Research, London, UK'),(2,'CA study','Canada','Institute of Cancer Research, Calgary, Canada')]:
            paper={'title':title,'doi':'10.test/uk' if ident==1 else '10.test/ca','countries':[country],
                   'source_author_metadata_status':'verified publication record','author_details':[{'name':'Author '+str(ident),'affiliation':address}]}
            ror_refine_paper(paper,self.matcher);papers.append(paper)
        refresh(conn,papers,self.matcher)
        rows=list(conn.execute('SELECT name,ror_id FROM institutions'))
        self.assertEqual(len(rows),2);self.assertNotEqual(rows[0][1],rows[1][1])
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM article_author_institutions').fetchone()[0],2)
        refresh(conn,papers,self.matcher)
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM institutions').fetchone()[0],2)

    def test_pubmed_empty_affiliation_preserves_publisher_unit(self):
        old=[{'name':'Luppi, Andrea I.','affiliation':'University of Oxford','source':'Publisher'}]
        new=[{'name':'Andrea I Luppi','source':'PubMed XML'}]
        merged=merge_author_details(old,new)
        self.assertEqual(merged[0]['affiliation'],'University of Oxford')
        self.assertNotIn('affiliation',new[0])

    def test_country_name_variants_match_the_same_registry_country(self):
        for name in ['the Netherlands','Netherlands','The Netherlands']:
            result=self.matcher.match_affiliation('Radboud University, Nijmegen, '+name)
            self.assertIn('Radboud University Nijmegen',[r['name'] for r in result['institutions']])
            self.assertEqual(result['countries'],['The Netherlands'])
        self.assertEqual(self.matcher.canonical_country('Turkey'),'Türkiye')

    def test_reviewed_medical_school_parent_is_explicit(self):
        for address,parent in [('Yale School of Medicine, New Haven, CT, USA','Yale University'),
                               ('Stanford School of Medicine, Stanford, CA, USA','Stanford University'),
                               ('NYU Grossman School of Medicine, New York, NY, USA','New York University')]:
            result=self.matcher.match_affiliation(address)
            self.assertIn(parent,[r['name'] for r in result['institutions']])
            self.assertTrue(any(r['method']=='reviewed_parent' for r in result['institutions']))

    def test_legal_suffix_after_exact_company_name(self):
        result=self.matcher.match_affiliation('Genentech Inc., 1 DNA Way, South San Francisco, CA 94080, USA')
        self.assertEqual([r['name'] for r in result['institutions']],['Genentech'])

    def test_unverified_profile_does_not_replace_source_author_list_or_orcid(self):
        paper={'title':'Preprint','source':'bioRxiv','authors':['Smallwood, J.','Jefferies, E.'],
               'author_details':[{'name':'Smallwood, J.','source':'OpenAlex',
                                  'orcid':'https://orcid.org/0000-0002-3826-4330',
                                  'affiliation':'Current profile institution'}]}
        updated,audit=supplement_paper(paper,{},{},{})
        self.assertEqual([a['name'] for a in updated['author_details']],paper['authors'])
        self.assertNotIn('orcid',updated['author_details'][0])
        self.assertEqual(updated['author_details'][0]['legacy_profile_orcid'],paper['author_details'][0]['orcid'])
        self.assertEqual(audit['after_authors'],2)

    def test_indexed_preprint_orcid_does_not_require_an_affiliation(self):
        paper={'title':'Preprint','source':'bioRxiv','doi':'10.test/a','authors':['Smith, S.']}
        record={'title':'Preprint','source':'PPR','id':'PPR1','doi':'10.test/a','authorList':{'author':[
            {'firstName':'Sarah','lastName':'Smith','authorId':{'type':'ORCID','value':'0000-0002-1825-0097'}}]}}
        updated,audit=supplement_paper(paper,{},{},{'10.test/a':[record]})
        self.assertEqual(updated['author_details'][0]['orcid'],'https://orcid.org/0000-0002-1825-0097')
        self.assertEqual(audit['source_orcids'],1)
        self.assertFalse(updated['author_details'][0].get('affiliation'))


if __name__ == '__main__':
    unittest.main()
