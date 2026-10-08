"""Refresh author/unit/geography sections from staged source data; retain editorial text."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ROOT/'visualize'))
from affiliation_matcher import normalize
from global_heatmap import WorldHeatmap


def institution_labels(paper,raw_fallback=True):
    labels=[]
    for author in paper.get('author_details',[]):
        for resolution in author.get('affiliation_resolution',[]):
            for row in resolution.get('institutions',[]):
                name=row['name']
                if row.get('ambiguous_display_name_resolved') and row.get('country'):name+=' ('+row['country']+')'
                if name not in labels:labels.append(name)
    if not labels and raw_fallback:
        labels=list(dict.fromkeys(' '.join(v.split()) for v in paper.get('affiliations',[])))
    return labels


def refresh_metadata(markdown,papers):
    by_title={normalize(p['title']):p for p in papers}
    pieces=re.split(r'(?m)(^### .+$)',markdown)
    updated=0
    for index in range(1,len(pieces),2):
        title=pieces[index].removeprefix('### ').strip();paper=by_title.get(normalize(title))
        if paper is None:continue
        body=pieces[index+1]
        authors=paper.get('authors') or [a['name'] for a in paper.get('author_details',[])]
        line='**作者**: '+', '.join(authors[:3])+(' et al.' if len(authors)>3 else '')
        body=re.sub(r'(?m)^\*\*作者\*\*:.*$',lambda _:line,body)
        body=re.sub(r'(?m)^\*\*(单位|研究地区|资深研究者)\*\*:.*\n?', '',body)
        labels=institution_labels(paper)
        additions=''
        if labels:additions+='\n\n**单位**: '+'; '.join(labels[:3])+(' 等' if len(labels)>3 else '')
        if paper.get('countries'):additions+='\n\n**研究地区**: '+', '.join(paper['countries'])
        body=body.replace(line,line+additions,1)
        pieces[index+1]=body;updated+=1
    return ''.join(pieces),updated


def geography_statistics(results):
    countries=Counter();institutions=Counter();cohort=[]
    for result in results:
        if result.get('domain')=='域外局限':continue
        paper=result['paper']['raw_data'];cohort.append(paper)
        countries.update(set(paper.get('countries') or []));institutions.update(set(institution_labels(paper,raw_fallback=False)))
    text=('> 作者、单位和地区信息已于 2026-10-08 按原始发表记录、ROR 和城市地址规则重新处理。'
          '单位与地区分别统计；跨地区合作可重复计入。下列统计仅含本期非“域外局限”条目，'
          '覆盖率不代表完整机构排名。原有评分与推荐保持不变。\n\n')
    for heading,counts,label in [('🌍 国家/地区分布 TOP 10',countries,'国家/地区'),('🏢 研究机构 TOP 10',institutions,'机构')]:
        text+='### '+heading+'\n\n| 排名 | '+label+' | 文章数量 |\n|------|------|----------|\n'
        for rank,(name,count) in enumerate(counts.most_common(10),1):text+=f'| {rank} | {name} | {count} |\n'
        if counts is countries:text+=f'\n**地区计次合计**: {sum(counts.values())} 次；取得地区信息 {sum(bool(p.get("countries")) for p in cohort)}/{len(cohort)} 篇\n'
        text+='\n'
    return text,cohort


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',type=Path,required=True)
    args=parser.parse_args();run=args.run_dir
    manifest=json.loads((run/'author_backfill.json').read_text(encoding='utf-8'))
    report_paths=[p for p in (ROOT/'LLM_Results').glob('report_*.md') if not any(w in p.name for w in ['wechat','specialissue','.raw','.deprecated'])]
    available={p:set(normalize(h) for h in re.findall(r'^### (.+)$',p.read_text(encoding='utf-8'),re.M)) for p in report_paths}
    audits=[];used_reports=set()
    for week in manifest['weeks']:
        refined=next(Path(p) for p,t in week['staged_outputs'] if '_enriched_ror_refined.jsonl' in p)
        result_path=next(Path(t) for p,t in week['staged_outputs'] if Path(t).name.startswith('LLM_results_'))
        results=json.loads(result_path.read_text(encoding='utf-8'));papers=[r['paper']['raw_data'] for r in results]
        selected={normalize(p['title']) for p in papers}
        overlap=sorted(((len(selected&titles),str(p),p) for p,titles in available.items()),reverse=True)
        report=overlap[0][2]
        if overlap[0][0]<1:raise ValueError('No aligned historical report for '+week['week'])
        if report in used_reports:raise ValueError('Multiple weeks aligned to '+report.name)
        used_reports.add(report)
        backup=run/'source_backups'/report.relative_to(ROOT)
        original=(backup if backup.exists() else report).read_text(encoding='utf-8')
        updated,count=refresh_metadata(original,papers)
        stats,cohort=geography_statistics(results)
        start=updated.find('### 🌍 国家/地区分布');end=updated.find('### 📊 评分分布',start)
        if start>=0:
            if end<start:end=updated.find('## 📈 各领域文章分布',start)
            if end<start:raise ValueError('Historical overview section missing after geography: '+report.name)
            # Replace this workflow's previous note as well as older source notes.
            for prefix in ['\n> 地区与机构按','\n> 作者、单位和地区信息已于']:
                note=updated.rfind(prefix,0,start)
                if note>=0:start=note+1
            updated=updated[:start]+stats+updated[end:]
        else:
            # Early issues did not have geographic tables. Add them within the
            # overview, before its existing score table or domain section.
            position=updated.find('### 📊 评分分布')
            if position<0:position=updated.find('## 📈 各领域文章分布')
            if position<0:raise ValueError('No overview insertion point: '+report.name)
            updated=updated[:position]+stats+updated[position:]
        located=sum(bool(p.get('countries')) for p in papers)
        updated=re.sub(r'\d+ 篇取得地区信息',str(located)+' 篇取得地区信息',updated)
        audit_note=f'> 作者信息回填：本期 {len(papers)} 条评估记录中，{sum(bool(p.get("affiliations")) for p in papers)} 条取得作者单位文本，{located} 条取得地区信息。来源与未解决项保存在数据核验记录中。'
        marker='## 📊 本周概览\n\n'
        updated=re.sub(r'(?m)^> 作者信息回填：.*\n\n','',updated)
        updated=updated.replace(marker,marker+audit_note+'\n\n',1)
        backup.parent.mkdir(parents=True,exist_ok=True)
        if not backup.exists():shutil.copy2(report,backup)
        staged_report=run/'staged_reports'/report.name;staged_report.parent.mkdir(exist_ok=True)
        staged_report.write_text(updated,encoding='utf-8');os.replace(staged_report,report)
        geography=run/'geography';geography.mkdir(exist_ok=True)
        path=geography/(week['week']+'.jsonl');path.write_text(''.join(json.dumps(p,ensure_ascii=False)+'\n' for p in cohort),encoding='utf-8')
        chart=WorldHeatmap(None);chart.skip_screenshots=True
        data=chart.get_jsonl_country_data(str(path));chart.render_heatmap(data,week['week']);chart.render_pie_chart(data,output_date=week['week'])
        audits.append({'week':week['week'],'report':str(report),'article_metadata_blocks_updated':count,
                       'evaluated':len(results),'geography_eligible':len(cohort),'located':located})
        print(week['week'],'report',report.name,'metadata blocks',count,flush=True)
    (run/'historical_reports_refresh.json').write_text(json.dumps(audits,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
