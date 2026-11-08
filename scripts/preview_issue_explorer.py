"""Render regular issue pages without rebuilding the database or special issues."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from page_builder.issue_explorer import explorer_payload
from page_builder.reports import (assign_covers, discover_reports, is_special_issue,
                                 render_report_page, write_site_assets)
from page_builder.sources import build_article_url_map


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, default=Path('LLM_Results'))
    parser.add_argument('--output-dir', type=Path, default=Path('tmps/issue_explorer_preview'))
    parser.add_argument('--report', help='One Markdown filename; omit to render all aligned regular issues.')
    args = parser.parse_args()
    reports = [p for p in discover_reports(args.input_dir) if not is_special_issue(p)
               and not any(s in p.name for s in ('.raw', '.deprecated'))]
    numbers = {p: i for i, p in enumerate(reports, 1)}
    covers = assign_covers(reports)
    write_site_assets(args.output_dir)
    world = args.output_dir / 'assets/vendor/world.js'
    shutil.copy2('docs/assets/vendor/world.js', world)
    audit = []
    for report in reports:
        if args.report and report.name != args.report:
            continue
        data = explorer_payload(args.input_dir, report, report.read_text(encoding='utf-8'))
        if data is None:
            audit.append({'report': report.name, 'status': 'skipped: no unambiguous identity-aligned evaluations'})
            continue
        urls = build_article_url_map(args.input_dir / data['source'])
        result = render_report_page(args.input_dir, args.output_dir, report, numbers, {}, {report: urls}, covers.get(report))
        audit.append({'report': report.name, 'page': result.page_name, 'status': 'rendered',
                      'source': data['source'], 'evaluated': data['evaluated'], 'statistical': len(data['rows']),
                      'expanded': sum(r['expanded'] for r in data['rows'])})
        print(result.page_name, len(data['rows']))
    (args.output_dir / 'issue_explorer_audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
