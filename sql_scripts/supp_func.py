from fuzzywuzzy import process
from thefuzz import fuzz
import json    
import time
import tqdm

STANDARD_NAME_JSON_PATH = 'data/RORStandardNameDict.json'
ALIAS_JSON_PATH = 'data/RORAliasNameDict.json'
LOC_JSON_PATH = 'data/RORLocInfo.json'
COUNTRY_JSON_PATH = 'data/CountryList.json' 
SUBREGION_JSON_PATH = 'data/CountrySubdivisionList.json' 

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
        self.country_set, self.subregion_set = self.load_regions()
        self._build_index()
    
    def load_regions(self) -> tuple[set[str], set[str]]:
        """
        Load the regions from the ROR location info.
        """
        with open(COUNTRY_JSON_PATH, 'r', encoding='utf-8') as f:
            countries = json.load(f)
        with open(SUBREGION_JSON_PATH, 'r', encoding='utf-8') as f:
            subregions = json.load(f)
        return set[str](countries), set[str](subregions)
    
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

    def load_institute_info(self) -> tuple[list[str], dict[str, int], dict[str, list[dict[str,str|dict]]]]:
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
        else:
            return 0
    
    # @timer
    def split_affiliation_parts(self, affiliation: str) -> list[str]:
        """
        Split affiliation into parts by comma, clean each part.
        """
        parts = affiliation.split(',')
        cleaned_parts = []
        for part in parts:
            cleaned = part.strip()
            if len(cleaned) > 2 and not self.exclude(cleaned):
                cleaned_parts.append(cleaned)
        cleaned_parts.reverse()
        return cleaned_parts
    

    # @timer
    def extract_institute_info(self, affiliation: str, threshold: int|None = None) -> str|None:
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
        if threshold is None:
            threshold = self.threshold
        
        parts = self.split_affiliation_parts(affiliation)
        
        for part in parts:
            first_char = part[0].upper()
            candidates = self.standard_index.get(first_char, self.standard_name_dict)
            result = process.extract(part, candidates, limit=1, scorer=fuzz.ratio)
            standard_name, score = result[0]
            if score >= threshold:
                return standard_name, score
        
        for part in parts:
            first_char = part[0].upper()
            candidates = self.alias_index.get(first_char, self.alias_name_dict)
            result = process.extract(part, candidates, limit=1, scorer=fuzz.ratio)
            alias, score = result[0]
            if score >= threshold:
                return self.alias_name_dict[alias], score
        
        return None, None


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
