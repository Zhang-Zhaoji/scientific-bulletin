"""Evaluate only recovered abstracts, resuming per-paper model checkpoints."""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys

from audit_bulletin_abstracts import ROOT, substantive
from recover_bulletin_abstracts import atomic_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=20)
    args = parser.parse_args()
    run = args.run_dir.resolve()
    targets = {target['key']: target for target in json.loads((run / 'targets.json').read_text(encoding='utf-8'))}
    recovered = {row['key']: row for row in json.loads((run / 'recovery.json').read_text(encoding='utf-8')) if row['status'] == 'recovered'}
    evaluated = {}
    for path in sorted(run.glob('evaluation_attempt_*.json')):
        for result in json.loads(path.read_text(encoding='utf-8')):
            key = result['paper']['raw_data']['abstract_recovery_key']
            if key not in recovered or not substantive(result['paper'].get('abstract')):
                raise ValueError('Unexpected evaluation checkpoint identity')
            evaluated[key] = result
    first = max([int(path.stem.rsplit('_', 1)[-1]) for path in run.glob('evaluation_attempt_*.json')] or [0]) + 1
    for attempt in range(first, first + 3):
        pending = []
        for key in sorted(recovered, key=lambda key: (not targets[key]['selected'], key)):
            if key in evaluated:
                continue
            paper = copy.deepcopy(targets[key]['paper'])
            record = recovered[key]
            paper.update(abstract=record['abstract'], abstract_source=record['abstract_source'],
                         abstract_source_url=record.get('abstract_source_url'), abstract_recovery_key=key)
            pending.append(paper)
        if not pending:
            break
        source = run / f'evaluation_pending_{attempt}.jsonl'
        source.write_text(''.join(json.dumps(paper, ensure_ascii=False) + '\n' for paper in pending), encoding='utf-8')
        output = run / f'evaluation_attempt_{attempt}.json'
        print('EVALUATING', len(pending), 'ALREADY', len(evaluated), flush=True)
        with (run / f'evaluation_attempt_{attempt}.log').open('a', encoding='utf-8') as stream:
            subprocess.run([sys.executable, '-u', '-B', str(ROOT / 'LLM_eval/main.py'), '-i', str(source), '-o', str(output), '--platform', 'DeepSeek', '--model', 'deepseek-flash', '-w', str(args.workers)], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, check=True)
        for result in json.loads(output.read_text(encoding='utf-8')):
            key = result['paper']['raw_data']['abstract_recovery_key']
            if key not in recovered or result['paper']['abstract'] != recovered[key]['abstract']:
                raise ValueError('Model output changed source abstract identity')
            evaluated[key] = result
        atomic_json(run / 'reevaluated.json', evaluated)
    if set(evaluated) != set(recovered):
        raise ValueError(f'Incomplete reevaluation: {len(evaluated)}/{len(recovered)}')
    atomic_json(run / 'reevaluated.json', evaluated)
    print('COMPLETE', len(evaluated), flush=True)


if __name__ == '__main__':
    main()
