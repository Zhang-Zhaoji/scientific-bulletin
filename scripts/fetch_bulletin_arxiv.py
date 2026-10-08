"""Fetch the established arXiv categories into a date-bounded temporary checkpoint."""
import argparse
from datetime import date
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from main import fetch_all_arxiv_papers, filter_date_range

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--start-date', type=date.fromisoformat, required=True)
parser.add_argument('--end-date', type=date.fromisoformat, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
papers = fetch_all_arxiv_papers(days=(date.today() - args.start_date).days + 1, max_results=999)
papers = filter_date_range(papers, args.start_date, args.end_date)
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(''.join(json.dumps(p, ensure_ascii=False) + '\n' for p in papers), encoding='utf-8')
print(f'Saved {len(papers)} arXiv papers to {args.output}', flush=True)
