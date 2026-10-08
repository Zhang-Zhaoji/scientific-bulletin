"""Offline city lookup; address evidence is independent of institution identity."""
from functools import lru_cache
import json
from pathlib import Path
import re
import sqlite3
import unicodedata

DATA=Path(__file__).resolve().parents[1]/'data/world_cities.db'
UNIT_WORDS=re.compile(r'\b(university|institute|institut|department|division|laboratory|laboratories|hospital|school|college|centre|center|diagnostics|sciences?|research|street|road|avenue|building|faculty|square|lane|boulevard|parkway|drive|inc|ltd|llc|gmbh|phone|telephone|fax|orcid)\b',re.I)
CONTACT_NOTE=re.compile(r'\b(?:ORCID|Correspondence|Corresponding\s+author|E-?mail)\s*:|[*†‡]|\\dagger',re.I)


def fold(value):
    value=unicodedata.normalize('NFKD',str(value or ''))
    value=''.join(c for c in value if not unicodedata.combining(c)).casefold().replace('’',"'").replace("'",'')
    return ' '.join(re.findall(r'\w+',value))


class CityLookup:
    def __init__(self,path=DATA):
        self.conn=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,check_same_thread=False)
        self.conn.row_factory=sqlite3.Row
        self.countries={r['code']:r['name'] for r in self.conn.execute('SELECT * FROM countries')}
        self.country_names={fold(n):c for c,n in self.countries.items()}
        for r in self.conn.execute('SELECT * FROM countries'):
            self.country_names[fold(r['code'])]=r['code'];self.country_names[fold(r['iso3'])]=r['code']
        self.country_names.update({'the netherlands':'NL','south korea':'KR','republic of korea':'KR',
            'turkiye':'TR','turkey':'TR','united states of america':'US','uk':'GB','england':'GB','scotland':'GB','wales':'GB','czech republic':'CZ',"peoples republic of china":'CN','pr china':'CN','marocco':'MA'})
        self.regions={r['code']:r['name'] for r in self.conn.execute('SELECT * FROM regions')}
        self.region_names={}
        for code,name in self.regions.items():self.region_names.setdefault(fold(name),[]).append(code)
        self.country_labels=sorted(self.country_names,key=len,reverse=True)
        self.us_states={code.split('.')[1]:name for code,name in self.regions.items() if code.startswith('US.')}
        self.us_state_names={fold(n) for n in self.us_states.values()}
        self.postal_countries={r[0] for r in self.conn.execute('SELECT DISTINCT country_code FROM postcodes')}
        self.manifest=json.loads(self.conn.execute('SELECT value FROM metadata WHERE key="manifest"').fetchone()[0])

    def country_codes(self,countries):
        return {self.country_names[fold(c)] for c in countries if fold(c) in self.country_names}

    @lru_cache(maxsize=50000)
    def named(self,name):
        sql='''SELECT c.*,r.name AS region FROM city_aliases a JOIN cities c ON c.id=a.city_id
               LEFT JOIN regions r ON r.code=c.region_code WHERE a.alias=? ORDER BY c.population DESC,c.id'''
        return tuple(dict(r) for r in self.conn.execute(sql,(fold(name),)))

    def search(self,query,country=None,region=None,limit=25):
        rows=list(self.named(query));codes=self.country_codes([country]) if country else set()
        if codes:rows=[r for r in rows if r['country_code'] in codes]
        if region:rows=[r for r in rows if fold(r.get('region'))==fold(region) or r['region_code'].split('.')[-1].casefold()==region.casefold()]
        return [self.decorate(r) for r in rows[:limit]],len(rows)

    def decorate(self,row):
        return {**row,'country':self.countries.get(row['country_code'],row['country_code']),
                'source_url':'https://www.geonames.org/'+str(row['id'])}

    @lru_cache(maxsize=50000)
    def resolve_address(self,address,countries=(),regions=()):
        clean=CONTACT_NOTE.split(address,maxsplit=1)[0]
        clean=re.sub(r'\b\S+@\S+\b|https?://\S+',' ',clean)
        components=[x.strip().rstrip('.') for x in re.split('[,;]',clean) if x.strip()]
        codes=self.country_codes(countries)
        # Infer explicit long country labels; short codes remain restricted to a tail.
        for i,component in enumerate(components):
            key=fold(component)
            short_country_tail=(i==len(components)-1 and component.upper() not in self.us_states)
            if key in self.country_names and (len(key)>3 or short_country_tail):codes.add(self.country_names[key])
            if not UNIT_WORDS.search(component):
                key=fold(re.sub(r'\b\d[\w-]*\b',' ',component))
                if key in self.us_state_names and key not in self.country_names:continue
                for label in self.country_labels:
                    safe_short=i==len(components)-1 and label.upper() not in self.us_states
                    if key.endswith(' '+label) and (len(label)>3 or safe_short):
                        codes.add(self.country_names[label]);break
        state_codes=set()
        for component in components:
            m=re.fullmatch(r'([A-Z]{2})(?:\s+\d[\w-]*)?',component)
            if m and m[1] in self.us_states and (not codes or 'US' in codes):state_codes.add('US.'+m[1])
            region_text=re.sub(r'\b\d[\w-]*\b',' ',component)
            for key in self.region_names.get(fold(region_text),[]):
                if not codes or key[:2] in codes:state_codes.add(key)
        if regions:
            state_codes.update(k for r in regions for k in self.region_names.get(fold(r),[]) if not codes or k[:2] in codes)
            state_codes.update(k for r in regions for k in self.regions if k.split('.')[-1].casefold()==r.casefold() and (not codes or k[:2] in codes))
        matches=[];ambiguities=[];warnings=[]
        first_unit=next((i for i,c in enumerate(components) if UNIT_WORDS.search(c)),None)
        contact_only='@' in address and len(components)==1 and first_unit is None
        for i,component in enumerate(components):
            # Leading comma fragments can be parts of an organization name, e.g.
            # "Mind, Brain and Behavior Research Center", rather than addresses.
            if contact_only or (first_unit is not None and i<first_unit):continue
            if UNIT_WORDS.search(component):continue
            region_text=fold(re.sub(r'\b\d[\w-]*\b',' ',component))
            if region_text in self.us_state_names and (re.search(r'\d',component) or i==len(components)-1):continue
            token=re.sub(r'\b\d[\w-]*\b',' ',component)
            token=re.sub(r'\b[A-Z]{2}\b',' ',token)
            key=fold(token)
            if key in self.country_names or not key:continue
            # Airport codes, institution acronyms and short historical aliases
            # need independently supplied country/state evidence.
            if len(key.replace(' ',''))<=3 and not codes and not state_codes:continue
            # A city followed by a long country label can occur without commas.
            for label in self.country_labels:
                if len(label)>3 and key.endswith(' '+label):key=key[:-(len(label)+1)];break
            candidates=list(self.named(key))
            if codes:candidates=[r for r in candidates if r['country_code'] in codes]
            if state_codes:candidates=[r for r in candidates if r['region_code'] in state_codes]
            if len(candidates)==1:
                city=self.decorate(candidates[0]);city['matched_text']=component;city['method']='exact_address_city'
                if city['id'] not in {m['id'] for m in matches}:matches.append(city)
            elif candidates:
                ambiguities.append({'text':component,'candidate_count':len(candidates),'candidates':[self.decorate(r) for r in candidates[:12]]})
        for city in matches:
            country=city['country_code']
            if country not in self.postal_countries:continue
            postal_pattern=r'\b(?:'+ '|'.join(self.us_states)+r')\s+(\d[\w-]*)\b' if country=='US' else r'\b(\d{5})\b'
            postals=re.findall(postal_pattern,clean)
            for code in postals:
                canonical=code.split('-')[0]
                if country=='US' and not re.fullmatch(r'\d{5}(?:-\d{4})?',code):
                    warnings.append({'type':'invalid_postal_format','value':code,'country_code':country});continue
                rows=[dict(r) for r in self.conn.execute('SELECT * FROM postcodes WHERE country_code=? AND code=?',(country,canonical))]
                if not rows:
                    warnings.append({'type':'postal_code_not_in_index','value':code,'country_code':country});continue
                aliases={r[0] for r in self.conn.execute('SELECT alias FROM city_aliases WHERE city_id=?',(city['id'],))}
                if not any(r['place_key'] in aliases and (country!='US' or r['region_code']==city['region_code']) for r in rows):
                    warnings.append({'type':'city_postal_conflict','city':city['name'],'postal_code':code,
                                     'postal_places':sorted({r['place'] for r in rows}),
                                     'postal_regions':sorted({self.regions.get(r['region_code'],r['region_code']) for r in rows}),
                                     'country_code':country})
        return {'cities':matches,'ambiguous':ambiguities,'warnings':warnings,
                'status':'matched_with_conflict' if matches and warnings else ('matched' if matches else ('ambiguous' if ambiguities else 'unresolved')),
                'source':'GeoNames cities500; postal checks cover '+', '.join(sorted(self.postal_countries))}
