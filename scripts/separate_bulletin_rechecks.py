"""Separate verified historical journal reappearances from a newly curated week."""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--date', required=True)
parser.add_argument('--manifest', type=Path, required=True)
parser.add_argument('--run-dir', type=Path, required=True)
args = parser.parse_args()
manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
start = manifest['date_range'][0]
historical = {r['title']: r for r in manifest['records']
              if r['source'] in ('Journal of Neuroscience', 'Journal of Cognitive Neuroscience')
              and not r['new_version_signal'] and r['earliest_recorded_date'] < start}
if not historical:
    raise ValueError('No verified prior-publication records in manifest')
stamp = args.date.replace('-', '')
result_path = ROOT / 'LLM_Results' / f'LLM_results_{stamp}.json'
results = json.loads(result_path.read_text(encoding='utf-8'))
rechecks = [r for r in results if r['paper']['title'] in historical]
kept = [r for r in results if r['paper']['title'] not in historical]
if len(rechecks) != len(historical):
    raise ValueError('Historical manifest and evaluation do not match one-to-one')
for result in rechecks:
    evidence = historical[result['paper']['title']]
    result['historical_recheck'] = {'earlier_date': evidence['earliest_recorded_date'],
                                  'reason': 'Previously indexed journal paper reappeared with a later issue date.',
                                  'manifest': str(args.manifest), 'doi': evidence['doi'], 'pmid': evidence['pmid']}
backup = args.run_dir / 'before_historical_separation'
backup.mkdir(parents=True, exist_ok=True)

def preserve(path):
    token = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    target = backup / f'{path.stem}_{token}{path.suffix}'
    if not target.exists():
        shutil.copy2(path, target)

def write(path, data):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(data, encoding='utf-8')
    temporary.replace(path)

recheck_path = args.run_dir / 'historical_rechecks.json'
write(recheck_path, json.dumps(rechecks, ensure_ascii=False, indent=2))
for suffix in ('', '_enriched', '_enriched_ror_refined'):
    path = ROOT / 'getfiles' / f'all_papers_{args.date}{suffix}.jsonl'
    papers = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    if len(papers) != len(results):
        raise ValueError(f'Corpus/evaluation count differs for {path}')
    preserve(path)
    write(path, ''.join(json.dumps(p, ensure_ascii=False) + '\n' for p in papers if p['title'] not in historical))
preserve(result_path)
write(result_path, json.dumps(kept, ensure_ascii=False, indent=2))
refined = [r['paper']['raw_data'] for r in kept]
counts = dict(Counter(p['source'] for p in refined))
for path in (ROOT / 'getfiles' / f'quality_{args.date}.json',
             ROOT / 'getfiles' / f'summary_{args.date}.json',
             args.run_dir / 'processing_status.json'):
    data = json.loads(path.read_text(encoding='utf-8'))
    preserve(path)
    data.update(papers=len(kept), paper_count=len(kept), llm_result_count=len(kept), merged_count=len(kept),
                historical_recheck_count=len(rechecks), historical_rechecks=str(recheck_path),
                initial_evaluated_count=len(results), source_counts=counts, source_counts_after_merge=counts,
                recommendation_distribution=dict(Counter(r['recommendation_tier'] for r in kept)),
                missing_abstracts=sum(bool(r.get('input_quality_warning')) for r in kept),
                papers_with_affiliation=sum(bool(p.get('affiliations')) for p in refined),
                papers_with_ror=sum(any(a.get('ror_normalized_affiliation') for a in p.get('author_details', [])) for p in refined),
                updated_at=datetime.now().isoformat())
    if 'sources' in data:
        data['sources'] = {name: {'count': count} for name, count in counts.items()}
    write(path, json.dumps(data, ensure_ascii=False, indent=2))
print(json.dumps({'weekly_papers': len(kept), 'historical_rechecks': len(rechecks),
                  'rechecks': str(recheck_path)}, ensure_ascii=False, indent=2))
