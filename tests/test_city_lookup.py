from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from city_lookup import CityLookup
from affiliation_matcher import AffiliationMatcher


@unittest.skipUnless((ROOT/'data/world_cities.db').exists(),'Offline GeoNames index is not installed')
class CityLookupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lookup=CityLookup();cls.matcher=AffiliationMatcher()

    def test_leipzig_with_country_and_postcode(self):
        result=self.lookup.resolve_address('Institute for Applied Training Science, Leipzig 04109, Germany')
        self.assertEqual([(c['name'],c['region'],c['country_code']) for c in result['cities']],[('Leipzig','Saxony','DE')])
        self.assertEqual(result['warnings'],[])

    def test_powell_is_disambiguated_by_state(self):
        result=self.lookup.resolve_address('GNOME Diagnostics, Powell, OH 43065')
        self.assertEqual([(c['name'],c['region'],c['country_code']) for c in result['cities']],[('Powell','Ohio','US')])
        self.assertEqual(result['warnings'],[])

    def test_conflicting_postal_code_is_kept_as_a_review_issue(self):
        result=self.lookup.resolve_address('GNOME Diagnostics, Powell, OH 43081')
        self.assertEqual(result['status'],'matched_with_conflict')
        self.assertEqual(result['warnings'][0]['postal_code'],'43081')
        self.assertIn('Westerville',result['warnings'][0]['postal_places'])

    def test_malformed_postal_code_does_not_remove_city_state_evidence(self):
        result=self.matcher.match_affiliation('GNOME Diagnostics, Powell, OH 143081')
        self.assertEqual(result['countries'],['United States'])
        self.assertEqual(result['geography_warnings'][0]['type'],'invalid_postal_format')
        self.assertEqual(result['institutions'],[])

    def test_same_city_name_does_not_choose_the_largest_city(self):
        result=self.lookup.resolve_address('Unregistered Laboratory, Paris')
        self.assertEqual(result['cities'],[])
        self.assertGreater(result['ambiguous'][0]['candidate_count'],1)
        self.assertGreater(len({c['country_code'] for c in result['ambiguous'][0]['candidates']}),1)

    def test_city_embedded_in_institution_is_not_an_address(self):
        self.assertEqual(self.lookup.resolve_address('University of York')['cities'],[])
        self.assertEqual(self.lookup.resolve_address('New York University')['cities'],[])

    def test_state_abbreviation_is_not_used_as_a_country(self):
        result=self.lookup.resolve_address('Unknown Laboratory, Boston, MA')
        self.assertEqual(result['cities'][0]['country_code'],'US')
        result=self.lookup.resolve_address('Unknown Laboratory, Stanford, CA 94305')
        self.assertEqual(result['cities'][0]['country_code'],'US')

    def test_explicit_country_excludes_incompatible_city(self):
        result=self.lookup.resolve_address('Unknown Laboratory, Powell, Germany')
        self.assertEqual(result['cities'],[])

    def test_city_search_state_filter(self):
        rows,total=self.lookup.search('Powell',country='US',region='OH')
        self.assertEqual(total,1);self.assertEqual(rows[0]['region'],'Ohio')
        result=self.lookup.resolve_address('Powell',countries=('US',),regions=('OH',))
        self.assertEqual(result['cities'][0]['region'],'Ohio')

    def test_country_suffix_without_a_comma_constrains_city(self):
        result=self.lookup.resolve_address('Unknown Laboratory, Leipzig 04109 Germany')
        self.assertEqual(result['cities'][0]['country_code'],'DE')

    def test_same_city_name_in_another_postal_state_is_a_conflict(self):
        result=self.lookup.resolve_address('Unknown Laboratory, Powell, OH 82435')
        self.assertEqual(result['status'],'matched_with_conflict')
        self.assertIn('Wyoming',result['warnings'][0]['postal_regions'])

    def test_contact_and_corporate_fragments_are_not_cities(self):
        for address in ['NYU','phone: (503) 725-2435','Min Wu ( somebody@example.org )',
                        'Communication Science Laboratories, NTT, Inc.','Neuroscience Center Zurich, Uni']:
            with self.subTest(address=address):
                self.assertEqual(self.matcher.match_affiliation(address)['cities'],[])

    def test_street_square_does_not_override_institution_country(self):
        result=self.matcher.match_affiliation('Institute of Cognitive Neuroscience, UCL, 17 Queen Square, London WC1N 3AZ.')
        self.assertEqual(result['countries'],['United Kingdom'])
        self.assertEqual(result['cities'],[])

    def test_full_state_with_postcode_constrains_city_and_is_not_a_city(self):
        result=self.lookup.resolve_address('UM-MIND, University of Maryland School of Medicine, Baltimore, Maryland 21201.')
        self.assertEqual([(c['name'],c['country_code']) for c in result['cities']],[('Baltimore','US')])
        self.assertNotIn('Michigan Institute for Neurological Disorders',[i['name'] for i in self.matcher.match_affiliation('UM-MIND, University of Maryland School of Medicine, Baltimore, Maryland 21201.')['institutions']])

    def test_country_spelling_does_not_become_an_italian_city(self):
        result=self.matcher.match_affiliation('Université Hassan II de Casablanca, Casablanca, Marocco.')
        self.assertEqual(result['countries'],['Morocco'])

    def test_org_name_split_by_comma_does_not_supply_city(self):
        result=self.matcher.match_affiliation('Mind, Brain and Behavior Research Center (CIMCYC), University of Granada')
        self.assertEqual(result['countries'],['Spain'])
        self.assertEqual(result['cities'],[])

    def test_country_before_concatenated_units_and_notes_is_retained(self):
        result=self.matcher.match_affiliation('The University of Tokyo, Tokyo, Japan Nicolaus Copernicus University, Torun, Poland RIKEN AIP, Tokyo, Japan ORCID: 0000-0002-4259-4121')
        self.assertEqual(set(result['countries']),{'Japan','Poland'})

    def test_geographic_institution_prefix_is_not_an_address_country(self):
        for text in ['Wallace H. Coulter Department of Biomedical Engineering, Georgia Institute of Technology and Emory University School of Medicine, Atlanta, GA 30332.',
                     'Korea Institute for Advancement of Technology-Georgia Tech Semiconductor Electronics Center at the Institute for Matter and Systems, Georgia Institute of Technology, Atlanta, GA 30332.']:
            self.assertEqual(self.matcher.match_affiliation(text)['countries'],['United States'])

    def test_joint_unit_acronyms_keep_publication_identity_evidence(self):
        self.assertEqual(self.matcher.match_affiliation('Columbia University/NYSPI')['countries'],['United States'])
        self.assertIn('Chinese University of Hong Kong',[i['name'] for i in self.matcher.match_affiliation('KIZ-CUHK Joint Laboratory of B')['institutions']])

    def test_new_jersey_is_not_the_country_jersey(self):
        result=self.matcher.match_affiliation('Princeton Neuroscience Institute, Princeton, New Jersey, United States of America * Corresponding author: a@example.org')
        self.assertEqual(result['countries'],['United States'])

    def test_new_mexico_is_not_the_country_mexico(self):
        result=self.matcher.match_affiliation('New Mexico Alcohol Research Center, Albuquerque, New Mexico, 87131.')
        self.assertEqual(result['countries'],['United States'])
        self.assertEqual(result['cities'][0]['name'],'Albuquerque')


if __name__=='__main__':unittest.main()
