import json
from fuzzywuzzy import process

def normalize_country_name(name: str) -> str:
    """
    Normalize country name:
    - Remove content in parentheses
    - Strip whitespace
    """
    import re
    name = re.sub(r'\(.*?\)', '', name)
    return name.strip()

def build_mapping(abbr2country_path: str, country_list_path: str, threshold: int = 80) -> dict:
    """
    Build mapping from abbr2country values to CountryList standard names.
    """
    with open(abbr2country_path, 'r', encoding='utf-8') as f:
        abbr2country = json.load(f)
    
    with open(country_list_path, 'r', encoding='utf-8') as f:
        country_list = json.load(f)
    
    normalized_country_list = [normalize_country_name(c) for c in country_list]
    
    mapping = {}
    unmatched = []
    
    for abbr, full_name in abbr2country.items():
        normalized = normalize_country_name(full_name)
        result = process.extractOne(normalized, normalized_country_list)
        if result:
            match, score = result
            if score >= threshold:
                idx = normalized_country_list.index(match)
                standard_name = country_list[idx]
                mapping[abbr] = standard_name
            else:
                unmatched.append((abbr, normalized, match, score))
                mapping[abbr] = None
        else:
            unmatched.append((abbr, normalized, None, 0))
            mapping[abbr] = None
    
    return mapping, unmatched

def main():
    abbr2country_path = 'data/abbr2country.json'
    country_list_path = 'data/CountryList.json'
    output_path = 'data/normalized_country_map.json'
    
    mapping, unmatched = build_mapping(abbr2country_path, country_list_path, threshold=80)
    
    matched_count = sum(1 for v in mapping.values() if v is not None)
    total_count = len(mapping)
    
    print(f"Total entries: {total_count}")
    print(f"Matched: {matched_count}")
    print(f"Unmatched: {len(unmatched)}")
    print(f"Match rate: {matched_count/total_count*100:.1f}%")
    print()
    
    if unmatched:
        print("Unmatched entries:")
        for abbr, full_name, match, score in unmatched:
            print(f"  {abbr}: {full_name}")
            if match:
                print(f"    Closest: {match} (score: {score})")
        print()
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, indent=2, ensure_ascii=False)
    
    print(f"Mapping saved to {output_path}")

if __name__ == '__main__':
    main()
