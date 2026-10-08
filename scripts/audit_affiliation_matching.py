"""Profile affiliation-source coverage and local matcher failures for a weekly corpus."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from supp_func import ROR_Search

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--input', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
papers = [json.loads(l) for l in args.input.read_text(encoding='utf-8').splitlines() if l.strip()]
matcher = ROR_Search()
units, examples, by_source = Counter(), defaultdict(list), defaultdict(Counter)
profile = Counter(papers=len(papers))
for p in papers:
    source = p.get('source', 'unknown')
    by_source[source]['papers'] += 1
    details = p.get('author_details') or []
    profile['authors'] += len(details)
    present = False
    for a in details:
        affiliation = a.get('affiliation')
        if not affiliation:
            profile['authors_without_affiliation'] += 1
            by_source[source]['authors_without_affiliation'] += 1
            continue
        present = True
        profile['authors_with_affiliation'] += 1
        by_source[source]['authors_with_affiliation'] += 1
        values = affiliation.split(';') if isinstance(affiliation, str) else affiliation
        for value in values:
            value = value.strip()
            if not value:
                continue
            units[value] += 1
            if len(examples[value]) < 2:
                examples[value].append({'title': p['title'], 'author': a['name'], 'source': source})
    if present:
        profile['papers_with_affiliation'] += 1
        by_source[source]['papers_with_affiliation'] += 1
rows = []
for text, count in units.most_common():
    institution, score, location = matcher.extract_institute_info(text)
    row = {'affiliation': text, 'occurrences': count, 'institution': institution, 'score': score,
           'country': location[0], 'subregion': location[1], 'examples': examples[text]}
    if hasattr(matcher, 'match_affiliation'):
        row['resolution'] = matcher.match_affiliation(text)
    row['countries'] = row.get('resolution', {}).get('countries', [location[0]] if location[0] else [])
    rows.append(row)
    profile['affiliation_occurrences'] += count
    profile['institution_matched_occurrences'] += count * bool(institution)
    profile['country_matched_occurrences'] += count * bool(row['countries'])
profile['unique_affiliations'] = len(rows)
profile['unique_institution_matched'] = sum(bool(r['institution']) for r in rows)
profile['unique_country_matched'] = sum(bool(r['countries']) for r in rows)
report = {'input': str(args.input), 'profile': dict(profile), 'by_source': {k:dict(v) for k,v in by_source.items()},
          'unmatched_institutions': [r for r in rows if not r['institution']],
          'unmatched_countries': [r for r in rows if not r['countries']], 'all_affiliations': rows}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report['profile'], ensure_ascii=False, indent=2))
print('Top unmatched institutions:')
print(json.dumps(report['unmatched_institutions'][:18], ensure_ascii=False, indent=2))
print('Top unmatched countries:')
print(json.dumps(report['unmatched_countries'][:12], ensure_ascii=False, indent=2))
