"""Resume the 2026-09-21..27 bulletin through Nature, enrichment, ROR and DeepSeek."""
import collections
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
os.environ['PYTHONUTF8'] = '1'
sys.path.insert(0, str(ROOT / 'src'))
import main as crawler
from crawler_nature import extract_text, get_abstracts
from utils import ymd

RUN = ROOT / 'tmps/pipeline_20260927'
RUN.mkdir(parents=True, exist_ok=True)
STATUS = RUN / 'status.json'
RAW = ROOT / 'getfiles/all_papers_2026-09-27.jsonl'
ENRICHED = ROOT / 'getfiles/all_papers_2026-09-27_enriched.jsonl'
REFINED = ROOT / 'getfiles/all_papers_2026-09-27_enriched_ror_refined.jsonl'
RESULT = ROOT / 'LLM_Results/LLM_results_20260927.json'
START, END = dt.date(2026, 9, 21), dt.date(2026, 9, 27)
state = {'pid': os.getpid(), 'date_range': [str(START), str(END)], 'status': 'running', 'completed_stages': []}

def update(stage, **fields):
    state.update(stage=stage, updated_at=dt.datetime.now().isoformat(), **fields)
    temp = STATUS.with_suffix('.tmp')
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(STATUS)
    print(f"[{state['updated_at']}] {stage}", flush=True)

def read(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]

def write(path, papers):
    temp = path.with_suffix('.tmp')
    with temp.open('w', encoding='utf-8') as stream:
        for paper in papers:
            stream.write(json.dumps(paper, ensure_ascii=False) + '\n')
    temp.replace(path)

def command(stage, arguments):
    logfile = ROOT / f'logs/{stage}_20260927.log'
    update(stage, command=[sys.executable, '-u', '-B', *arguments], log=str(logfile))
    with logfile.open('a', encoding='utf-8') as log:
        subprocess.run([sys.executable, '-u', '-B', *arguments], stdout=log,
                       stderr=subprocess.STDOUT, check=True, cwd=ROOT)

def run():
    update('nature_supplement')
    backup = RUN / 'raw_before_nature.jsonl'
    if not backup.exists():
        shutil.copy2(RAW, backup)
    nature = []
    days = (dt.date.today() - START).days + 1
    with (ROOT / 'logs/nature_supplement_20260927.log').open('a', encoding='utf-8') as log:
        original_stdout = sys.stdout
        try:
            sys.stdout = log
            for idx, url in enumerate(crawler.NATURE_JOURNALS):
                checkpoint = RUN / f'nature_{idx:02d}.jsonl'
                if checkpoint.exists():
                    papers = read(checkpoint)
                else:
                    papers = crawler.filter_date_range(extract_text(url, days_back=days), START, END)
                    for paper in papers:
                        paper['date'] = ymd(paper['date'])
                        paper['abstract'] = get_abstracts(url, paper['url'])
                    write(checkpoint, papers)
                nature.extend(papers)
                log.flush()
        finally:
            sys.stdout = original_stdout
    primary = read(backup)
    papers = crawler.merge_papers(primary, [], nature, *[[] for _ in range(12)])
    assert len(crawler.filter_date_range(papers, START, END)) == len(papers)
    write(RAW, papers)
    summary_path = ROOT / 'getfiles/summary_2026-09-27.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    summary['sources']['nature'] = {'count': len(nature), 'date_range': {'min': min((p['date'] for p in nature), default=None), 'max': max((p['date'] for p in nature), default=None)}}
    summary['merged_count'] = len(papers)
    summary['source_counts_after_merge'] = dict(collections.Counter(p.get('source', 'unknown') for p in papers))
    summary['missing_abstract_count'] = sum(not crawler.has_meaningful_abstract(p) for p in papers)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    state['completed_stages'].append('nature_supplement')
    update('nature_complete', paper_count=len(papers), nature_count=len(nature))

    command('author_enrichment', ['src/enrich_source_metadata.py', str(RAW), '-o', str(ENRICHED), '--cache-dir', str(RUN / 'source_cache')])
    enriched = read(ENRICHED)
    assert len(enriched) == len(papers)
    state['completed_stages'].append('author_enrichment')
    state['authors_with_metrics'] = sum(a.get('h_index') is not None for p in enriched for a in p.get('author_details', []))
    state['authors_with_affiliation'] = sum(bool(a.get('affiliation')) for p in enriched for a in p.get('author_details', []))
    state['openalex_rate_limited'] = 'OpenAlex remains rate limited' in (ROOT / 'logs/author_enrichment_20260927.log').read_text(encoding='utf-8')

    command('ror_refine', ['src/ror_refine_batch.py', '--input', str(ENRICHED), '-o', str(REFINED)])
    refined = read(REFINED)
    assert len(refined) == len(papers)
    state['completed_stages'].append('ror_refine')
    state['authors_with_ror_match'] = sum(bool(a.get('ror_normalized_affiliation')) for p in refined for a in p.get('author_details', []))

    command('deepseek_eval', ['LLM_eval/main.py', '-i', str(REFINED), '-o', str(RESULT), '--platform', 'DeepSeek'])
    results = json.loads(RESULT.read_text(encoding='utf-8'))
    state['llm_result_count'] = len(results)
    if len(results) != len(refined):
        raise RuntimeError(f'LLM results incomplete: {len(results)}/{len(refined)}; see evaluation log')
    state['completed_stages'].append('deepseek_eval')
    command('summary', ['LLM_eval/Summary.py', '-i', str(RESULT)])
    state['completed_stages'].append('summary')
    update('complete', status='complete', result=str(RESULT), refined=str(REFINED))

if __name__ == '__main__':
    try:
        run()
    except BaseException as error:
        update(state.get('stage', 'startup'), status='failed', error=str(error))
        traceback.print_exc()
        sys.exit(1)
