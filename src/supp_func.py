from thefuzz import process
from thefuzz import fuzz
import json    
import time
import tqdm

STANDARD_NAME_JSON_PATH = 'data/RORStandardNameDict.json'
ALIAS_JSON_PATH = 'data/RORAliasNameDict.json'
LOC_JSON_PATH = 'data/RORLocInfo.json'
COUNTRY_JSON_PATH = 'data/CountryList.json' 
SUBREGION_JSON_PATH = 'data/CountrySubdivisionList.json' 
ABR2COUNTRY_JSON_PATH = 'data/abbr2country.json'

# example affiliation string:
'''
"Department Of Physiology And Neuroscience, Keck School Of Medicine, University Of Southern California, Los Angeles, Ca 90033, Usa"
'''
def timer(func):
    def wrapper(*args, **kwargs):
        """
        Measure the time cost of the function.
        """
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        print(f"[DEBUG]: {func.__name__} cost {end_time - start_time:.2f} seconds")
        return result
    return wrapper

class ROR_Search():
    def __init__(self, threshold: int = 90):
        self.threshold = threshold
        self.standard_name_dict, self.alias_name_dict, self.loc_info = self.load_institute_info()
        self.key_words = ['@', 'Electronic', 'Department Of', 'Key Laboratory', 'School Of']
        self.country_set, self.subregion_set, self.abbr2country = self.load_regions()
        self._build_index()
        self.trans = str.maketrans('', '', '0123456789')
    
    def load_regions(self) -> tuple[set[str], set[str], dict[str, str]]:
        """
        Load the regions from the ROR location info.
        """
        with open(COUNTRY_JSON_PATH, 'r', encoding='utf-8') as f:
            countries = json.load(f)
        with open(SUBREGION_JSON_PATH, 'r', encoding='utf-8') as f:
            subregions = json.load(f)
        with open(ABR2COUNTRY_JSON_PATH, 'r', encoding='utf-8') as f:
            abbr2country = json.load(f)
        return set[str](countries), set[str](subregions), abbr2country
    
    def _build_index(self):
        """
        Build first character index to reduce candidate search space.
        """
        self.standard_index = {}
        for name in self.standard_name_dict:
            if not name:
                continue
            first_char = name[0].upper()
            if first_char not in self.standard_index:
                self.standard_index[first_char] = []
            self.standard_index[first_char].append(name)
        
        self.alias_index = {}
        for alias in self.alias_name_dict.keys():
            if not alias:
                continue
            first_char = alias[0].upper()
            if first_char not in self.alias_index:
                self.alias_index[first_char] = []
            self.alias_index[first_char].append(alias)

    def load_institute_info(self) -> tuple[list[str], dict[str, str], dict[str, list[dict]]]:
        """
        Load the ROR standard name dict, alias name dict, and location info.
        """
        with open(STANDARD_NAME_JSON_PATH, 'r', encoding='utf-8') as f:
            standard_name_dict = json.load(f)
        with open(ALIAS_JSON_PATH, 'r', encoding='utf-8') as f:
            alias_name_dict = json.load(f)
        with open(LOC_JSON_PATH, 'r', encoding='utf-8') as f:
            loc_info = json.load(f)
        return standard_name_dict, alias_name_dict, loc_info
    

    def exclude(self, part:str) -> bool:
        """
        Exclude parts that are not valid institute names.
        """
        # email
        
        if any(keyword in part for keyword in self.key_words):
            return 1
        elif part in self.country_set:
            return 2
        elif part in self.subregion_set:
            return 3
        elif part.lower() in self.abbr2country.keys():
            return 4
        else:
            return 0
    
    # @timer
    def split_affiliation_parts(self, affiliation: str) -> list[str]:
        """
        Split affiliation into parts by comma, clean each part.
        """
        location_info = [None, None]
        parts = affiliation.split(',')
        parts = [part.replace('.', '').translate(self.trans).strip() for part in parts]
        kinds = [self.exclude(part) for part in parts]
        parts = parts[::-1]
        kinds = kinds[::-1]
        cleaned_parts = [part for i, part in enumerate(parts) if kinds[i] == 0]
        country = next((part for i, part in enumerate(parts) if kinds[i] == 2), None)
        subregion = next((part for i, part in enumerate(parts) if kinds[i] == 3), None)
        abbr = next((part for i, part in enumerate(parts) if kinds[i] == 4), None)
        if abbr:
            country = self.abbr2country[abbr.lower().strip()]
        if country:
            location_info[0] = country
        if subregion:
            location_info[1] = subregion
        return cleaned_parts, location_info
    

    # @timer
    def extract_institute_info(self, affiliation: str, threshold: int|None = None) -> tuple[str|None, int|None, list]:
        """
        Search the institute name in the ROR standard name dict.
        Strategy:
        1. Split affiliation by comma, reverse order (start from country/city/university)
        2. Try to match each part until we find one above threshold
        3. Check standard names first, then aliases
        Return:
        1. institute name
        2. score
        3. location info(country, subdivision)
        """
        standard_name, score, location_info = None, 0, [None, None]
        if threshold is None:
            threshold = self.threshold
            
        parts, location_info = self.split_affiliation_parts(affiliation)
        
        tmp_standard_name = None
        tmp_score = 0
        for part in parts:
            if not part:
                continue
            first_char = part[0].upper()
            candidates = self.standard_index.get(first_char, self.standard_name_dict)
            result = process.extract(part, candidates, limit=1, scorer=fuzz.ratio)
            candidate_name, candidate_score = result[0]
            if candidate_score > tmp_score:
                tmp_standard_name = candidate_name
                tmp_score = candidate_score
            if candidate_score >= threshold:
                standard_name = candidate_name
                score = candidate_score
                break
        if score < threshold:
            # not pass strict, continue        
            for part in parts:
                if not part:
                    continue
                first_char = part[0].upper()
                candidates = self.alias_index.get(first_char, self.alias_name_dict.keys())
                result = process.extract(part, candidates, limit=1, scorer=fuzz.ratio)
                alias, alias_score = result[0]
                if alias_score >= tmp_score:
                    alias_standard_name = self.alias_name_dict[alias]
                    tmp_standard_name = alias_standard_name
                    tmp_score = alias_score
                    if alias_score >= threshold:
                        standard_name = tmp_standard_name
                        score = alias_score
                        break
        if standard_name is not None and standard_name in self.loc_info:
            loc_entry = self.loc_info[standard_name][0]
            score_related_country = loc_entry['geonames_details']['country_name']
            score_related_subregion = loc_entry['geonames_details'].get('country_subdivision_name')
            if location_info[0] is None:
                location_info[0] = score_related_country
            if location_info[0] == score_related_country and location_info[1] is None and score_related_subregion:
                location_info[1] = score_related_subregion

        return standard_name, score, location_info


if __name__ == '__main__':

    
    ror_search = ROR_Search(threshold=90)
    example_institute_path = 'data/example_institutions.json'
    
    with open(example_institute_path, 'r', encoding='utf-8') as f:
        examples = json.load(f)
    
    total = len(examples)
    found = 0
    not_found = []
    top_candidates = []
    
    start_time = time.time()
    
    for example in tqdm.tqdm(examples):
        result, score, location_info = ror_search.extract_institute_info(example)
        if result:
            found += 1
            top_candidates.append((result, score, location_info))
        elif result is None:
            not_found.append(example)
            top_candidates.append((result, score, location_info))
    
    elapsed = time.time() - start_time
    
    print(f"总测试条数: {total}")
    print(f"成功匹配: {found}")
    print(f"匹配率: {found/total*100:.1f}%")
    print(f"总耗时: {elapsed:.2f} 秒")
    print(f"平均每条耗时: {elapsed/total*1000:.2f} 毫秒")
    print()
    # for inst, candidate in zip(examples, top_candidates):
    #     print(f"  {inst} -> {candidate[0]} (score: {candidate[1]})")
    #     input()
    
    if not_found:
        print(f"未找到 ({len(not_found)} 条):")
        for aff in not_found:
            print(f"  {aff}")
            print(ror_search.extract_institute_info(aff, threshold=0))
