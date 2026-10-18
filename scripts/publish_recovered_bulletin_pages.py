"""Build historical repair pages in staging and promote only verified differences."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys

from audit_bulletin_abstracts import ROOT, fingerprint
from recover_bulletin_abstracts import atomic_json

sys.path.insert(0, str(ROOT))
from sql_scripts.build_slim_db import verify_slim_db


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True, type=Path)
    args = parser.parse_args()
    run = args.run_dir.resolve()
    staged = run / 'site'
    subprocess.run([sys.executable, '-u', '-B', str(ROOT / 'scripts/build_pages.py'), '--input-dir', str(ROOT / 'LLM_Results'), '--output-dir', str(staged)], cwd=ROOT, check=True)
    if not verify_slim_db(ROOT / 'data/literature.db', ROOT / 'docs/assets/data/literature_slim.db'):
        raise ValueError('Existing repaired database pair is not reconciled')
    changed = []
    for source in sorted(staged.rglob('*')):
        if not source.is_file():
            continue
        relative = source.relative_to(staged)
        target = ROOT / 'docs' / relative
        before = fingerprint(target) if target.exists() else None
        after = fingerprint(source)
        if before == after:
            continue
        backup = run / 'web_backups' / relative
        if target.exists() and not backup.exists():
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
            if fingerprint(backup) != before:
                raise ValueError('Web asset backup failed')
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + '.abstract-recovery.tmp')
        shutil.copy2(source, temporary)
        temporary.replace(target)
        if fingerprint(target) != after:
            raise ValueError('Published web asset differs from stage')
        changed.append({'target': str(target.relative_to(ROOT)), 'before_sha256': before, 'after_sha256': after})
    atomic_json(run / 'web_publication.json', {'status': 'complete', 'changed_files': changed, 'full_slim_verified': True})
    print('PUBLISHED WEB FILES', len(changed), flush=True)


if __name__ == '__main__':
    main()
