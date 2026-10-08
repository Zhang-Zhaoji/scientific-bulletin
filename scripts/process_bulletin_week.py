"""Resume source enrichment, ROR normalization and complete LLM curation for a week.

The crawler and optional supplements run separately. This helper validates their
date bounds, preserves checkpoints, and retries only missing evaluation records.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from main import filter_date_range, merge_papers, normalize_title


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def write_jsonl(path, rows):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(''.join(json.dumps(p, ensure_ascii=False) + '\n' for p in rows), encoding='utf-8')
    temporary.replace(path)


def paper_key(paper):
    return normalize_title(paper['title'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start-date', type=date.fromisoformat, required=True)
    parser.add_argument('--date', type=date.fromisoformat, required=True)
    parser.add_argument('--supplement', type=Path)
    parser.add_argument('--workers', type=int, default=20)
    parser.add_argument('--model', default='deepseek-flash')
    args = parser.parse_args()
    os.chdir(ROOT)
    os.environ['PYTHONUTF8'] = '1'
    stamp = args.date.strftime('%Y%m%d')
    run = ROOT / 'tmps' / f'pipeline_{stamp}'
    run.mkdir(parents=True, exist_ok=True)
    status = run / 'processing_status.json'
    state = json.loads(status.read_text(encoding='utf-8')) if status.exists() else {'completed_stages': []}
    state.update(pid=os.getpid(), status='running', date_range=[str(args.start_date), str(args.date)])

    def update(stage, **fields):
        state.update(stage=stage, updated_at=datetime.now().isoformat(), **fields)
        write_json(status, state)
        print(f'{stage}: {fields}', flush=True)

    def command(stage, arguments):
        log_path = ROOT / 'logs' / f'{stage}_{stamp}.log'
        update(stage, log=str(log_path))
        with log_path.open('a', encoding='utf-8') as stream:
            subprocess.run([sys.executable, '-u', '-B', *arguments], cwd=ROOT,
                           stdout=stream, stderr=subprocess.STDOUT, check=True)

    def validate(rows, name):
        if not rows:
            raise ValueError(f'{name} is empty')
        if len(filter_date_range(rows, args.start_date, args.date)) != len(rows):
            raise ValueError(f'{name} has out-of-range or unknown publication dates')
        keys = [paper_key(p) for p in rows]
        if len(set(keys)) != len(keys):
            raise ValueError(f'{name} contains duplicate normalized titles')
        return keys

    raw = ROOT / 'getfiles' / f'all_papers_{args.date}.jsonl'
    enriched = raw.with_name(raw.stem + '_enriched.jsonl')
    refined = raw.with_name(raw.stem + '_enriched_ror_refined.jsonl')
    result_path = ROOT / 'LLM_Results' / f'LLM_results_{stamp}.json'
    try:
        papers = read_jsonl(raw)
        if args.supplement and 'supplement' not in state['completed_stages']:
            shutil.copy2(raw, run / 'raw_before_supplement.jsonl')
            extra = read_jsonl(args.supplement)
            if len(filter_date_range(extra, args.start_date, args.date)) != len(extra):
                raise ValueError('Supplement has unknown or out-of-range publication dates')
            papers = merge_papers(papers, extra, *[[] for _ in range(13)])
            write_jsonl(raw, papers)
            state['completed_stages'].append('supplement')
        keys = validate(papers, 'raw')
        summary_path = ROOT / 'getfiles' / f'summary_{args.date}.json'
        if summary_path.exists():
            summary = json.loads(summary_path.read_text(encoding='utf-8'))
            summary.update(merged_count=len(papers), date_range=[str(args.start_date), str(args.date)],
                           source_counts_after_merge=dict(Counter(p.get('source') for p in papers)))
            if args.supplement:
                summary['supplement_file'] = str(args.supplement)
            write_json(summary_path, summary)
        update('raw_validated', paper_count=len(papers), source_counts=dict(Counter(p.get('source') for p in papers)))
        if 'source_enrichment' not in state['completed_stages']:
            command('source_enrichment', ['src/enrich_source_metadata.py', str(raw), '-o', str(enriched),
                                         '--cache-dir', str(run / 'source_cache')])
        enriched_rows = read_jsonl(enriched)
        if validate(enriched_rows, 'enriched') != keys:
            raise ValueError('Source enrichment changed paper identity or ordering')
        if 'source_enrichment' not in state['completed_stages']:
            state['completed_stages'].append('source_enrichment')
        if 'ror_refine' not in state['completed_stages']:
            command('ror_refine', ['src/ror_refine_batch.py', '--input', str(enriched), '-o', str(refined)])
        refined_rows = read_jsonl(refined)
        if validate(refined_rows, 'refined') != keys:
            raise ValueError('ROR refinement changed paper identity or ordering')
        if 'ror_refine' not in state['completed_stages']:
            state['completed_stages'].append('ror_refine')

        evaluations = json.loads(result_path.read_text(encoding='utf-8')) if result_path.exists() else []
        evaluated = {paper_key(r['paper']): r for r in evaluations}
        if len(evaluated) != len(evaluations) or not set(evaluated).issubset(keys):
            raise ValueError('Existing evaluation contains duplicate or unexpected papers')
        checkpoint_paths = sorted(run.glob('evaluation_attempt_*.json'))
        rechecks_path = run / 'historical_rechecks.json'
        excluded_keys = {paper_key(r['paper']) for r in json.loads(rechecks_path.read_text(encoding='utf-8'))} if rechecks_path.exists() else set()
        for checkpoint in checkpoint_paths:
            try:
                checkpoint_rows = json.loads(checkpoint.read_text(encoding='utf-8'))
            except json.JSONDecodeError:
                print(f'Ignoring incomplete JSON checkpoint: {checkpoint}', flush=True)
                continue
            for row in checkpoint_rows:
                key = paper_key(row['paper'])
                if key in excluded_keys:
                    continue
                if key not in keys:
                    raise ValueError('Checkpoint contains an unexpected paper')
                evaluated.setdefault(key, row)
        if evaluated:
            write_json(result_path, [evaluated[k] for k in keys if k in evaluated])
        first_attempt = max([int(p.stem.rsplit('_', 1)[-1]) for p in checkpoint_paths] or [0]) + 1
        for attempt in range(first_attempt, first_attempt + 3):
            missing = [p for p in refined_rows if paper_key(p) not in evaluated]
            if not missing:
                break
            subset = run / f'evaluation_pending_{attempt}.jsonl'
            output = run / f'evaluation_attempt_{attempt}.json'
            write_jsonl(subset, missing)
            update('deepseek_eval', evaluated=len(evaluated), pending=len(missing), attempt=attempt)
            command(f'deepseek_eval_{attempt}', ['LLM_eval/main.py', '-i', str(subset), '-o', str(output),
                                                '--platform', 'DeepSeek', '--model', args.model, '-w', str(args.workers)])
            rows = json.loads(output.read_text(encoding='utf-8')) if output.exists() else []
            pending_keys = {paper_key(p) for p in missing}
            for row in rows:
                key = paper_key(row['paper'])
                if key not in pending_keys:
                    raise ValueError('Evaluation returned an unexpected paper')
                evaluated[key] = row
            write_json(result_path, [evaluated[k] for k in keys if k in evaluated])
        if set(evaluated) != set(keys):
            raise ValueError(f'Incomplete evaluation: {len(evaluated)}/{len(keys)}')
        final = []
        for p in refined_rows:
            row = evaluated[paper_key(p)]
            row['paper'].update(raw_data=p, title=p['title'], authors=p.get('authors', []),
                                abstract=p.get('abstract', ''), date=p['date'])
            if len((p.get('abstract') or '').strip()) < 50:
                row['input_quality_warning'] = 'Source abstract unavailable; assessment based on limited metadata.'
            final.append(row)
        write_json(result_path, final)
        audit = {'date_range': [str(args.start_date), str(args.date)], 'papers': len(papers),
                 'llm_result_count': len(final), 'source_counts': dict(Counter(p.get('source') for p in papers)),
                 'missing_abstracts': sum(bool(r.get('input_quality_warning')) for r in final),
                 'papers_with_affiliation': sum(bool(p.get('affiliations')) for p in refined_rows),
                 'papers_with_ror': sum(any(a.get('ror_normalized_affiliation') for a in p.get('author_details', [])) for p in refined_rows),
                 'author_metrics_status': 'not requested; source metadata only',
                 'model_requested': args.model,
                 'recommendation_distribution': dict(Counter(r['recommendation_tier'] for r in final))}
        if rechecks_path.exists():
            audit.update(historical_recheck_count=len(excluded_keys), historical_rechecks=str(rechecks_path),
                         initial_evaluated_count=len(final) + len(excluded_keys))
        write_json(ROOT / 'getfiles' / f'quality_{args.date}.json', audit)
        state['completed_stages'].append('deepseek_eval')
        update('complete', status='complete', **audit, result=str(result_path))
    except BaseException as error:
        update(state.get('stage', 'startup'), status='failed', error=str(error))
        raise


if __name__ == '__main__':
    main()
