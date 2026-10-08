"""Resolve source affiliations with normalized names and explicit geographic evidence.

Similarity is a retrieval score, not a probability. Missing or ambiguous source
information remains unresolved. Reviewed additions live outside the ROR snapshot.
"""
from collections import defaultdict
from functools import lru_cache
import json
from pathlib import Path
import re
import unicodedata
from thefuzz import fuzz, process

DATA = Path(__file__).resolve().parents[1] / 'data'
GENERIC = {'university', 'institute', 'center', 'centre', 'hospital', 'school', 'college',
           'department', 'laboratory', 'research', 'medicine', 'health', 'science',
           'sciences', 'national', 'medical', 'of', 'the', 'and', 'for', 'de', 'la', 'des'}
FUZZY_GENERIC = GENERIC | {'clinical', 'affiliated', 'foundation', 'system'}
GENERIC_NAME_WORDS = GENERIC | {'cancer', 'clinical', 'biological', 'molecular', 'life'}
UNIT_SUFFIXES = {'school', 'faculty', 'department', 'division', 'college', 'and', 'at',
                 'inc', 'incorporated', 'ltd', 'llc', 'gmbh', 'corp', 'corporation'}


def normalize(value):
    value = unicodedata.normalize('NFKD', str(value or ''))
    value = ''.join(c for c in value if not unicodedata.combining(c)).casefold()
    value = value.replace('&', ' and ').replace('’', "'").replace("'", '')
    return ' '.join(re.findall(r'\w+', value))


def clean_affiliation(value):
    value = re.sub(r'\b\S+@\S+\b|https?://\S+', ' ', str(value or ''))
    return re.sub(r'Electronic\s+address\s*:', ' ', value, flags=re.I)


class AffiliationMatcher:
    def __init__(self, threshold=90, use_city_index=True):
        self.threshold = threshold
        self.city_lookup=None
        if use_city_index and (DATA/'world_cities.db').exists():
            from city_lookup import CityLookup
            self.city_lookup=CityLookup()
        load = lambda name: json.loads((DATA / name).read_text(encoding='utf-8'))
        self.standard_name_dict = load('RORStandardNameDict.json')
        self.alias_name_dict = load('RORAliasNameDict.json')
        self.loc_info = load('RORLocInfo.json')
        self.identities = load('RORIdentityDict.json') if (DATA/'RORIdentityDict.json').exists() else {}
        ambiguous_aliases = load('RORAmbiguousAliasDict.json') if (DATA/'RORAmbiguousAliasDict.json').exists() else {}
        self.country_set = set(load('CountryList.json'))
        self.subregion_set = set(load('CountrySubdivisionList.json'))
        self.abbr2country = load('abbr2country.json')
        self.alias_country = load('aliasCountryName.json')
        patch = DATA / 'affiliation_overrides.json'
        self.overrides = load(patch.name) if patch.exists() else {}
        self.country_aliases = {normalize(k):v for k,v in self.overrides.get('country_aliases', {}).items()}
        self.reviewed = {}
        self.reviewed_aliases = set()
        self.ror_ids = {}
        for name, entries in self.identities.items():
            if len(entries)==1:
                self.ror_ids[name]=entries[0]['ror_id']
        self.parent_aliases = set()
        self.names = defaultdict(set)
        self.name_methods = {}
        self.acronyms = defaultdict(set)
        for row in self.overrides.get('institutions', []):
            name = row['name']
            self.reviewed[name] = row
            self.ror_ids[name] = row.get('ror_id')
            if name not in self.loc_info:
                self.standard_name_dict.append(name)
            self.loc_info[name] = row['locations']
            for alias in [name, *row.get('aliases', [])]:
                key = normalize(alias)
                self.reviewed_aliases.add(key)
                self.names[key].add(name)
                self.name_methods[(key, name)] = 'reviewed_exact'
                if alias.isupper() and ' ' not in alias:
                    self.acronyms[(key,name)].add(alias)
            for alias in row.get('parent_aliases', []):
                key = normalize(alias)
                self.parent_aliases.add((key,name))
                self.name_methods[(key,name)] = 'reviewed_parent'
        self.country_names = {}
        for name in self.country_set:
            self.country_names[normalize(name)] = self.canonical_country(name)
        for alias, country in self.alias_country.items():
            self.country_names[normalize(alias)] = self.canonical_country(country)
        for alias, country in self.country_aliases.items():
            self.country_names[alias] = self.canonical_country(country)
        self.region_countries = defaultdict(set)
        self.region_names = {}
        self.us_states = {}
        self.geographic_codes={normalize(k) for k in self.abbr2country}
        self.geographic_code_countries=defaultdict(set)
        cities = set()
        for entries in self.loc_info.values():
            for location in entries:
                details = location.get('geonames_details', {})
                country = self.canonical_country(details.get('country_name'))
                region = details.get('country_subdivision_name')
                cities.add(normalize(details.get('name')))
                if region and country:
                    self.region_names[normalize(region)] = region
                    self.region_countries[normalize(region)].add(country)
                    code=details.get('country_subdivision_code')
                    if code:self.geographic_code_countries[normalize(code)].add(country)
                if details.get('country_code') == 'US' and details.get('country_subdivision_code'):
                    self.us_states[details['country_subdivision_code']] = region
        for name in self.standard_name_dict:
            key = normalize(name)
            if key and key not in GENERIC and key not in self.country_names and key not in cities and key not in self.region_names:
                self.names[key].add(name)
                self.name_methods.setdefault((key, name), 'normalized_exact')
        for alias, name in self.alias_name_dict.items():
            key = normalize(alias)
            if not key or key in GENERIC or key in self.country_names or key in cities or key in self.region_names:
                continue
            if len(key.replace(' ', '')) <= 3 and key not in self.reviewed_aliases and not alias.isupper():
                continue
            if key in self.geographic_codes:continue
            self.names[key].add(name)
            self.name_methods.setdefault((key, name), 'alias_exact')
            if alias.isupper() and ' ' not in alias:
                self.acronyms[(key,name)].add(alias)
        for alias, names in ambiguous_aliases.items():
            key=normalize(alias)
            if not key or key in GENERIC or key in self.country_names or key in cities or key in self.region_names:
                continue
            if len(key.replace(' ',''))<=3 and key not in self.reviewed_aliases and not alias.isupper():
                continue
            if key in self.geographic_codes:continue
            for name in names:
                self.names[key].add(name)
                self.name_methods.setdefault((key,name),'alias_exact')
                if alias.isupper() and ' ' not in alias:self.acronyms[(key,name)].add(alias)
        self.trie = {}
        self.city_names=cities
        self.city_first_tokens={key.split()[0] for key in cities if key}
        self.region_first_token=defaultdict(list)
        for key,name in self.region_names.items():
            self.region_first_token[key.split()[0]].append((key,name))
        self.first_token = defaultdict(list)
        for key, names in self.names.items():
            if len(key.replace(' ', '')) < 4 and key not in self.reviewed_aliases and not any(self.acronyms.get((key,n)) for n in names):
                continue
            tokens = key.split()
            node = self.trie
            for token in tokens:
                node = node.setdefault(token, {})
            node.setdefault('', []).extend((name, key) for name in names)
            self.first_token[tokens[0]].append(key)

    def canonical_country(self, value):
        if not value:
            return None
        return self.country_aliases.get(normalize(value), value)

    def geography(self, affiliation):
        clean = clean_affiliation(affiliation)
        countries = []
        # Address components, not every word in an institution's name. Otherwise
        # Beth Israel in Boston spuriously produces the country Israel.
        components=re.split(r'[,;]',clean)
        for component_index,component in enumerate(components):
            component=re.split(r'\b(?:ORCID|Correspondence|Corresponding\s+author|E-?mail)\s*:|[*†‡]|\\dagger',component,maxsplit=1,flags=re.I)[0]
            part = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', component)
            part = re.sub(r'\b\d[\w-]*\b', ' ', part)
            key = normalize(part)
            if key in self.country_names:
                countries.append(self.country_names[key])
            elif key not in self.names and key.removeprefix('the ') not in self.names and key not in self.region_names:
                for name in sorted(self.country_names, key=len, reverse=True):
                    if key.endswith(' '+name):
                        countries.append(self.country_names[name]);break
                    # Concatenated source units can begin with the previous
                    # address's country, e.g. "Poland RIKEN AIP".
                    if (component_index>0 and normalize(components[component_index-1]) in self.city_names
                            and len(name)>3 and key.startswith(name+' ')
                            and re.search(r'\b(university|institute|research|riken|inc)\b',key[len(name):])):
                        countries.append(self.country_names[name]);break
        countries = list(dict.fromkeys(countries))
        regions = []
        postal = re.search(r'\b([A-Z]{2})\s+\d{5}(?:-\d{4})?\b', clean)
        if postal and postal[1] in self.us_states:
            countries = countries or ['United States']
            if 'United States' in countries:
                regions.append(self.us_states[postal[1]])
        # Restrict bare country codes to known unambiguous tail forms. In/CA/MA
        # in departments and US addresses must not become India/Canada/Morocco.
        tail = re.split(r'[,;]', clean)[-1].strip().rstrip('.')
        key = re.sub(r'[.\s]', '', tail).upper()
        safe_codes = self.overrides.get('country_codes', {})
        if key in safe_codes:
            countries.append(self.canonical_country(safe_codes[key]))
        countries = list(dict.fromkeys(countries))
        if 'United States' in countries:
            for component in re.split(r'[,;]', clean):
                state = component.strip().rstrip('.')
                if state in self.us_states:
                    regions.append(self.us_states[state])
        # Georgia is a US state when an explicit USA address is present.
        countries = [c for c in countries if not (normalize(c) in self.region_countries and
                     any(other != c and other in self.region_countries[normalize(c)] for other in countries))]
        text = ' ' + normalize(clean) + ' '
        for token in set(text.split()):
            for key,name in self.region_first_token.get(token,[]):
                if ' ' + key + ' ' in text and any(c in self.region_countries[key] for c in countries):
                    regions.append(name)
        return countries, list(dict.fromkeys(r for r in regions if r))

    def locations(self, name):
        return [e.get('geonames_details', {}) for e in self.loc_info.get(name, [])]

    def identity_candidates(self,name,countries,regions,affiliation=''):
        if name in self.reviewed:
            return [{'ror_id':self.ror_ids[name],'status':self.reviewed[name].get('status'),
                     'locations':self.loc_info.get(name,[])}]
        entries=self.identities.get(name,[])
        if len(entries)<=1:return entries
        def compatible(entry):
            actual={self.canonical_country(d.get('geonames_details',{}).get('country_name')) for d in entry['locations']} - {None}
            if 'China' in countries and actual.intersection({'Hong Kong','Macao'}):actual.add('China')
            return not countries or bool(actual.intersection(countries))
        entries=[entry for entry in entries if compatible(entry)]
        if len(entries)>1 and regions:
            narrowed=[e for e in entries if any(d.get('geonames_details',{}).get('country_subdivision_name') in regions for d in e['locations'])]
            if narrowed:entries=narrowed
        if len(entries)>1 and affiliation:
            components=[normalize(re.sub(r'\b\d[\w-]*\b',' ',p)) for p in re.split(r'[,;]',affiliation)
                        if not re.search(r'\b(university|institute|hospital|school|department|center|centre)\b',p,re.I)]
            narrowed=[e for e in entries if any(city and any(p==city or p.endswith(' '+city) or p==city+' city' for p in components)
                       for city in [normalize(d.get('geonames_details',{}).get('name')) for d in e['locations']])]
            if narrowed:entries=narrowed
        return entries

    def compatible(self, name, countries, regions=()):
        actual = {self.canonical_country(d.get('country_name')) for d in self.locations(name)} - {None}
        if 'China' in countries:
            actual = actual | ({'China'} if actual.intersection({'Hong Kong','Macao'}) else set())
        if countries and actual and not actual.intersection(countries):
            return False
        actual_regions = {d.get('country_subdivision_name') for d in self.locations(name)} - {None}
        return not regions or not actual_regions or bool(actual_regions.intersection(regions))

    @staticmethod
    def distinctive_words_match(left, right):
        """Long generic names must not hide a different place or disease word."""
        qualifiers = {'health', 'medical', 'hospital', 'school', 'college'}
        if set(left.split()) & qualifiers != set(right.split()) & qualifiers:
            return False
        a = [w for w in left.split() if w not in FUZZY_GENERIC]
        b = [w for w in right.split() if w not in FUZZY_GENERIC]
        return bool(a and b) and all(max(fuzz.ratio(w, v) for v in other) >= 90
                                   for words,other in ((a,b),(b,a)) for w in words)

    @lru_cache(maxsize=50000)
    def match_affiliation(self, affiliation, threshold=None):
        threshold = self.threshold if threshold is None else threshold
        clean = clean_affiliation(affiliation)
        countries, regions = self.geography(clean)
        explicit_geography=bool(countries)
        city_evidence=(self.city_lookup.resolve_address(str(affiliation or ''),tuple(countries),tuple(regions))
                       if self.city_lookup else {'cities':[],'ambiguous':[],'warnings':[],'status':'unavailable'})
        city_countries=list(dict.fromkeys(self.canonical_country(c['country']) for c in city_evidence['cities']))
        if not countries:countries=city_countries
        if not regions:regions=list(dict.fromkeys(c['region'] for c in city_evidence['cities'] if c.get('region')))
        name_text = re.sub(r'(?<=\w)\s*\([A-Z][A-Z0-9&/-]{1,12}\)', ' ', clean)
        tokens = normalize(name_text).split()
        component_ends = []
        offset = 0
        for component in re.split(r'[,;]', name_text):
            offset += len(normalize(component).split())
            component_ends.append(offset)
        candidates = []
        for start in range(len(tokens)):
            node = self.trie
            for end in range(start, len(tokens)):
                node = node.get(tokens[end])
                if node is None:
                    break
                for name, key in node.get('', []):
                    if len(key.replace(' ','')) <= 3 and not countries:
                        continue
                    if self.geographic_code_countries.get(key,set()).intersection(countries):continue
                    # BASIC inside "Basic Medical Sciences" is an ordinary word,
                    # not the Beijing center's acronym. Preserve acronym casing.
                    forms = self.acronyms.get((key,name))
                    if forms and key != normalize(name) and not any(re.search(r'\b'+re.escape(v)+r'\b',clean) for v in forms):
                        continue
                    boundary = next((b for b in component_ends if b >= end+1),len(tokens))
                    if end+1 < boundary and tokens[end+1] not in UNIT_SUFFIXES and tokens[end+1] not in self.city_first_tokens and tokens[end+1] not in self.country_names:
                        continue
                    # Registry locations can be a headquarters address rather
                    # than the author's branch. State conflicts reject generic
                    # names, not a distinctive exact organization such as HHMI.
                    embedded_short_acronym=(len(key.replace(' ',''))<=4 and forms
                                            and any(re.search(r'\w[-/]'+re.escape(v)+r'\b',clean) for v in forms))
                    constrain_regions = regions if embedded_short_acronym or all(w in GENERIC_NAME_WORDS for w in key.split()) else ()
                    if self.compatible(name, countries, constrain_regions):
                        candidates.append((start,end+1,name,key,100,self.name_methods[(key,name)]))
        # Longer named entities take precedence over parent names contained in
        # them; independent institutions in the same affiliation are retained.
        candidates.sort(key=lambda c: (-(c[1]-c[0]), c[0], c[2]))
        accepted = []
        ambiguity = []
        for candidate in candidates:
            start,end,name,key,score,method = candidate
            same_span = {c[2] for c in candidates if c[:2] == (start,end)}
            if len(same_span) > 1:
                ambiguity.append({'text':key,'candidates':sorted(same_span)})
                continue
            if any(start < b and end > a for a,b,*_ in accepted):
                continue
            accepted.append(candidate)
        if not accepted:
            for raw in re.split(r'[,;]', clean):
                part = normalize(re.sub(r'\([^)]*\)', ' ', raw)).removeprefix('the ')
                words = part.split()
                if len(words) < 2 or not any(w not in GENERIC for w in words) or re.match(r'^(department|division|laboratory)\b', part):
                    continue
                pool = self.first_token.get(words[0], [])
                proposals = process.extract(part, pool, scorer=fuzz.ratio, limit=6)
                resolved = []
                for key,score in proposals:
                    for name in self.names[key]:
                        if self.compatible(name, countries, regions) and self.distinctive_words_match(part,key):
                            resolved.append((score,name,key))
                resolved.sort(reverse=True)
                if not resolved or resolved[0][0] < threshold:
                    continue
                best = resolved[0]
                runner = next((r for r in resolved[1:] if r[1] != best[1]), None)
                if runner and best[0]-runner[0] < 5:
                    ambiguity.append({'text':part,'candidates':[best[1],runner[1]]})
                    continue
                accepted.append((0,0,best[1],best[2],best[0],'fuzzy_with_margin'))
        results = []
        for start,end,name,key,score,method in sorted(accepted, key=lambda c:c[0]):
            identities=self.identity_candidates(name,countries,regions,clean)
            if len(self.identities.get(name,[]))>1 and len(identities)!=1:
                ambiguity.append({'text':key,'reason':'identical display name identifies multiple ROR organizations',
                                  'candidate_ror_ids':[e['ror_id'] for e in self.identities[name]]})
                continue
            if any(r['name'] == name for r in results):
                continue
            available_locations=[d.get('geonames_details',{}) for d in identities[0]['locations']] if len(identities)==1 else self.locations(name)
            locations = [d for d in available_locations if not countries or self.canonical_country(d.get('country_name')) in countries]
            inferred = {self.canonical_country(d.get('country_name')) for d in locations} - {None}
            country = countries[0] if len(countries)==1 else (next(iter(inferred)) if len(inferred)==1 else None)
            state_set = {d.get('country_subdivision_name') for d in locations if d.get('country_subdivision_name')}
            region = regions[0] if len(regions)==1 else (next(iter(state_set)) if len(state_set)==1 else None)
            results.append({'name':name,'ror_id':identities[0]['ror_id'] if len(identities)==1 else self.ror_ids.get(name),'score':score,'method':method,
                            'matched_text':key,'country':country,'subregion':region,
                            'registry_region_conflict':bool(regions and state_set and not state_set.intersection(regions)),
                            'registry_status':identities[0].get('status') if len(identities)==1 else None,
                            'ambiguous_display_name_resolved':len(self.identities.get(name,[]))>1})
        if not countries:
            countries = list(dict.fromkeys(r['country'] for r in results if r['country']))
        if not regions:
            regions = list(dict.fromkeys(r['subregion'] for r in results if r['subregion']))
        return {'institutions':results,'countries':countries,'subregions':regions,'ambiguous':ambiguity,
                'cities':city_evidence['cities'],'city_ambiguities':city_evidence['ambiguous'],
                'geography_warnings':city_evidence['warnings'],'city_status':city_evidence['status'],
                'status':'matched' if results else ('ambiguous' if ambiguity else 'unresolved'),
                'geography_source':'explicit_address' if explicit_geography else ('city_address' if city_countries else ('institution_registry' if countries else 'unavailable'))}

    def extract_institute_info(self, affiliation, threshold=None):
        result = self.match_affiliation(affiliation, threshold)
        primary = result['institutions'][0] if result['institutions'] else None
        return (primary['name'] if primary else None, primary['score'] if primary else 0,
                [result['countries'][0] if len(result['countries'])==1 else None,
                 result['subregions'][0] if len(result['subregions'])==1 else None])

    def split_affiliation_parts(self, affiliation):
        countries,regions = self.geography(affiliation)
        return [normalize(v) for v in re.split(r'[,;]', clean_affiliation(affiliation))], [countries[0] if len(countries)==1 else None,regions[0] if len(regions)==1 else None]
