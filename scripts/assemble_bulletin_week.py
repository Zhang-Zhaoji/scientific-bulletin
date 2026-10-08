"""Assemble validated date-bounded source checkpoints with cross-issue deduplication."""
import argparse
from collections import Counter
from datetime import date
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from main import filter_date_range, load_historical_identifiers, merge_papers

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--start-date', type=date.fromisoformat, required=True)
parser.add_argument('--end-date', type=date.fromisoformat, required=True)
parser.add_argument('--inputs', type=Path, nargs='+', required=True)
parser.add_argument('--source-audit', type=Path)
args = parser.parse_args()
groups = []
for path in args.inputs:
    rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    if len(filter_date_range(rows, args.start_date, args.end_date)) != len(rows):
        raise ValueError(f'Unknown or out-of-range dates in {path}')
    groups.append(rows)
if len(groups) > 15:
    raise ValueError('At most fifteen input groups are supported')
groups.extend([[] for _ in range(15 - len(groups))])
identifiers = load_historical_identifiers(str(ROOT / 'getfiles'), max_weeks=1)
papers = merge_papers(*groups, historical_dois=identifiers[0], historical_pmids=identifiers[1],
                      historical_titles=identifiers[2], recheck_dois=identifiers[3],
                      recheck_pmids=identifiers[4], recheck_titles=identifiers[5])
if not papers:
    raise ValueError('The merged corpus is empty')
counts = Counter(p.get('source', 'unknown') for p in papers)
output = ROOT / 'getfiles' / f'all_papers_{args.end_date}.jsonl'
if output.exists():
    raise FileExistsError(f'Preserve/review the existing corpus before assembling again: {output}')
output.write_text(''.join(json.dumps(p, ensure_ascii=False) + '\n' for p in papers), encoding='utf-8')
summary = {'date': str(args.end_date), 'date_range': [str(args.start_date), str(args.end_date)],
           'merged_count': len(papers), 'source_counts_after_merge': dict(counts),
           'input_counts': {str(path): len(rows) for path, rows in zip(args.inputs, groups)},
           'sources': {source: {'count': count} for source, count in counts.items()},
           'missing_abstract_count': sum(len((p.get('abstract') or '').strip()) < 50 for p in papers)}
if args.source_audit:
    audit = json.loads(args.source_audit.read_text(encoding='utf-8'))
    destination = ROOT / 'getfiles' / f'source_audit_{args.end_date}.json'
    destination.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    summary['source_audit'] = str(destination)
(ROOT / 'getfiles' / f'summary_{args.end_date}.json').write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
