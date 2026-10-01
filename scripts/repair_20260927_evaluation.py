"""Replace source metadata and reevaluate only papers with newly recovered abstracts."""
import collections
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
RUN = ROOT / 'tmps/pipeline_20260927'
STATUS = RUN / 'status.json'
ENRICHED = ROOT / 'getfiles/all_papers_2026-09-27_enriched.jsonl'
REFINED = ROOT / 'getfiles/all_papers_2026-09-27_enriched_ror_refined.jsonl'
RESULT = ROOT / 'LLM_Results/LLM_results_20260927.json'
state = json.loads(STATUS.read_text(encoding='utf-8'))
state.update(pid=os.getpid(), status='running', metadata_mode='source metadata; no OpenAlex')

def update(stage, **fields):
    state.update(stage=stage, updated_at=datetime.datetime.now().isoformat(), **fields)
    STATUS.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    print(stage, flush=True)

def read(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]

def key(paper):
    return paper['title'].strip().lower()

def command(stage, args):
    update(stage)
    with (ROOT / f'logs/{stage}_20260927.log').open('w', encoding='utf-8') as log:
        subprocess.run([sys.executable, '-u', '-B', *args], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)

def run():
    originals = json.loads(RESULT.read_text(encoding='utf-8'))
    assert len(originals) == state['paper_count']
    for path in (ENRICHED, REFINED, RESULT):
        backup = RUN / (path.stem + '_initial' + path.suffix)
        if not backup.exists():
            shutil.copy2(path, backup)
    baseline = json.loads((RUN / (RESULT.stem + '_initial' + RESULT.suffix)).read_text(encoding='utf-8'))
    baseline_by_title = {key(r['paper']): r for r in baseline}
    shutil.copy2(RUN / 'source_enriched.jsonl', ENRICHED)
    command('ror_source_refine', ['src/ror_refine_batch.py', '--input', str(ENRICHED), '-o', str(REFINED)])
    refined = read(REFINED)
    assert len(refined) == len(originals)
    old = {key(r['paper']): r for r in originals}
    assert len(old) == len(originals), 'Duplicate titles require a stronger join'
    assert {key(p) for p in refined} == set(old)
    changed = [p for p in refined if (p.get('abstract') or '').strip() != (old[key(p)]['paper'].get('abstract') or '').strip()]
    subset = RUN / 'abstract_recovered_ror_refined.jsonl'
    subset.write_text(''.join(json.dumps(p, ensure_ascii=False) + '\n' for p in changed), encoding='utf-8')
    replacements = {}
    if changed:
        output = RUN / 'LLM_results_abstract_recovered.json'
        command('deepseek_repaired_abstracts', ['LLM_eval/main.py', '-i', str(subset), '-o', str(output), '--platform', 'DeepSeek'])
        rows = json.loads(output.read_text(encoding='utf-8'))
        replacements = {key(r['paper']): r for r in rows}
        assert set(replacements) == {key(p) for p in changed}, 'Incomplete reevaluation'
    final = []
    for p in refined:
        result = replacements.get(key(p), old[key(p)])
        result['paper'].update(raw_data=p, authors=p['authors'], abstract=p.get('abstract', ''), date=p['date'])
        if len(p.get('abstract') or '') < 50:
            result['input_quality_warning'] = 'Source abstract unavailable; assessment based on limited metadata.'
        final.append(result)
    RESULT.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding='utf-8')
    report_dir = RUN / 'source_report'
    report_dir.mkdir(exist_ok=True)
    command('summary_source', ['LLM_eval/Summary.py', '-i', str(RESULT), '-o', str(report_dir)])
    report = sorted(report_dir.glob('report_*.md'))[-1]
    report_target = ROOT / 'LLM_Results/report_20260927.md'
    report_target.write_text('> 文献日期：2026-09-21 至 2026-09-27。作者和机构取自原始来源；本次未查询 OpenAlex 作者指标。\n\n' + report.read_text(encoding='utf-8'), encoding='utf-8')
    audit = json.loads((RUN / 'source_enriched.audit.json').read_text(encoding='utf-8'))
    audit.update(reevaluated_count=sum((p.get('abstract') or '').strip() != (baseline_by_title[key(p)]['paper'].get('abstract') or '').strip() for p in refined), llm_result_count=len(final),
                 recommendation_distribution=dict(collections.Counter(r['recommendation_tier'] for r in final)),
                 initial_distribution=dict(collections.Counter(r['recommendation_tier'] for r in baseline)),
                 tier_changed_count=sum(r['recommendation_tier'] != baseline_by_title[key(r['paper'])]['recommendation_tier'] for r in final),
                 authors_with_ror_match=sum(bool(a.get('ror_normalized_affiliation')) for p in refined for a in p.get('author_details', [])))
    (ROOT / 'getfiles/quality_2026-09-27.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    update('complete', status='complete', **audit, report=str(report_target))
    print(json.dumps(audit, ensure_ascii=False, indent=2), flush=True)

if __name__ == '__main__':
    try:
        run()
    except BaseException as error:
        update(state.get('stage', 'startup'), status='failed', error=str(error))
        traceback.print_exc()
        sys.exit(1)
