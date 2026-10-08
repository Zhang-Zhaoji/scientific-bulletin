from thefuzz import process
from thefuzz import fuzz
import json    
import time
import tqdm
import re

STANDARD_NAME_JSON_PATH = 'data/RORStandardNameDict.json'
ALIAS_JSON_PATH = 'data/RORAliasNameDict.json'
LOC_JSON_PATH = 'data/RORLocInfo.json'
COUNTRY_JSON_PATH = 'data/CountryList.json' 
SUBREGION_JSON_PATH = 'data/CountrySubdivisionList.json' 
ABR2COUNTRY_JSON_PATH = 'data/abbr2country.json'
ALIAS_COUNTRY_JSON_PATH = 'data/aliasCountryName.json'

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

from affiliation_matcher import AffiliationMatcher


class ROR_Search(AffiliationMatcher):
    """Backward-compatible entry point for the evidence-aware local matcher."""
    pass


def check_affiliation_coverage():
    """
    统计所有 ror_refined 文件中作者地址信息的覆盖率。
    """
    import glob
    import jsonlines
    import os

    files = sorted(glob.glob('getfiles/all_papers_*_enriched_ror_refined.jsonl'))
    files = [f for f in files if '_replenished' not in f]

    total = 0
    has_affil = 0
    has_ror_country = 0
    has_ror_inst = 0

    print("\n" + "=" * 70)
    print("Affiliation Coverage Report")
    print("=" * 70)

    for fp in files:
        file_total = 0
        file_affil = 0
        file_country = 0
        file_inst = 0

        with jsonlines.open(fp) as r:
            for paper in r:
                total += 1
                file_total += 1
                details = paper.get('author_details', [])

                affil_found = any(d.get('affiliation') for d in details)
                country_found = any(d.get('ror_country') for d in details)
                inst_found = any(d.get('ror_normalized_affiliation') for d in details)

                if affil_found:
                    has_affil += 1
                    file_affil += 1
                if country_found:
                    has_ror_country += 1
                    file_country += 1
                if inst_found:
                    has_ror_inst += 1
                    file_inst += 1

        pct_a = file_affil / file_total * 100 if file_total else 0
        pct_c = file_country / file_total * 100 if file_total else 0
        print(f"  {os.path.basename(fp):55s} {file_total:4d} papers | affil {pct_a:5.1f}% | country {pct_c:5.1f}%")

    print("-" * 70)
    print(f"  {'TOTAL':55s} {total:4d} papers")
    print(f"  Has affiliation:        {has_affil:4d} ({has_affil/total*100:.1f}%)")
    print(f"  Has ROR country:        {has_ror_country:4d} ({has_ror_country/total*100:.1f}%)")
    print(f"  Has ROR institution:    {has_ror_inst:4d} ({has_ror_inst/total*100:.1f}%)")
    print("=" * 70)


if __name__ == '__main__':
    import sys

    if '--coverage' in sys.argv:
        check_affiliation_coverage()
        sys.exit(0)

    ror_search = ROR_Search(threshold=90)
    example_institute_path = "tmp_files/test_insts.json"
    
    with open(example_institute_path, 'r', encoding='utf-8') as f:
        examples = json.load(f)
    
    total = len(examples)
    found = 0
    not_found = []
    top_candidates = []
    
    start_time = time.time()
    
    for example in tqdm.tqdm(examples):
        affiliation = example['name']
        result, score, location_info = ror_search.extract_institute_info(affiliation)
        if location_info[0] is None:
            print(f"\n{affiliation} -> {result} (score: {score}) -> {location_info[0]}, {location_info[1]}")
            input()
        if result:
            found += 1
            top_candidates.append((result, score, location_info))
        elif result is None:
            not_found.append(affiliation)
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
        print(f"未找到 ({len(not_found)}/{total} 条):")
        for aff in not_found:
            print(f"  {aff}")
            print(ror_search.extract_institute_info(aff, threshold=0))
    
    if not_found:
        no_location = [aff for aff in not_found if aff[1] is None]
        print(f"未找到 ({len(no_location)}/{total}) 条 无位置信息:")
        input()
        for aff in no_location:
            print(f"  {aff}")
            print(ror_search.extract_institute_info(aff, threshold=0))
