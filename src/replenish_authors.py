"""
作者信息补全工具

扫描所有 ror_refined 文件，找到关键作者（前2+后2）信息不完整的论文，
分批从 OpenAlex API 重新获取，受限于每日 1000 次的免费配额。
同时支持从 PubMed API 批量补充缺失的作者地址信息。

完整流水线: PubMed地址 → scan → OpenAlex → 更新enriched文件 → build_ror → build_sq

用法:
    # 完整流水线（推荐）
    python src/replenish_authors.py pipeline [--daily-limit 950]

    # 分步执行
    python src/replenish_authors.py fetch-affiliations   # 步骤1: 从PubMed补地址
    python src/replenish_authors.py scan                  # 步骤2: 扫描，导出列表
    python src/replenish_authors.py update                 # 步骤3: 调用OpenAlex+更新enriched
    python src/replenish_authors.py build                  # 步骤4: 运行build_ror+build_sq

输出:
    - getfiles/author_replenish_list.json     (扫描结果)
    - getfiles/author_replenish_progress.json  (进度跟踪)
    - getfiles/*_enriched.jsonl               (原地更新，不新建文件)
"""

import argparse
import json
import os
import sys
import time
import glob
import jsonlines
import requests
import subprocess
from datetime import datetime
from typing import List, Dict, Optional, Set, Tuple
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

load_dotenv()

# 添加路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from enrich_authors import (
    AuthorDatabase, get_database,
    classify_name, name_similarity,
    is_senior_researcher, SENIOR_RESEARCHER_THRESHOLD,
    HEADERS, fetch_with_retry,
    fetch_affiliations_batch,
    find_best_pmid_by_title,
    split_affiliation,
    normalize_affiliation,
    infer_country_from_affiliation,
)
from enrich_authors import (
    fetch_author_impact_strict,
    fetch_author_impact_loose,
)


# ── 常量 ──
DEFAULT_INPUT_DIR = "getfiles"
DEFAULT_OUTPUT_LIST = "getfiles/author_replenish_list.json"
DEFAULT_PROGRESS_FILE = "getfiles/author_replenish_progress.json"
DEFAULT_DAILY_LIMIT = 950  # 留50次余量
RATE_LIMIT_STATUS = 429


class RateLimitError(Exception):
    """OpenAlex API 每日配额用尽时抛出"""
    pass


# ── 工具函数 ──

def get_key_authors(authors: List[str]) -> List[Tuple[int, str]]:
    """获取关键作者：前2个 + 后2个（去重，保持顺序）"""
    if not authors:
        return []
    n = len(authors)
    indices = set()
    for i in range(min(2, n)):
        indices.add(i)
    for i in range(max(0, n - 2), n):
        indices.add(i)
    return [(i, authors[i]) for i in sorted(indices)]


def find_author_in_details(author_name: str, author_details: List[Dict]) -> Optional[Dict]:
    """在 author_details 列表中按名字查找作者"""
    for ad in author_details:
        if ad.get('name') == author_name:
            return ad
    return None


def is_author_incomplete(detail: Optional[Dict]) -> bool:
    """判断作者信息是否不完整（h_index 为 None 即视为不完整）"""
    if detail is None:
        return True
    return detail.get('h_index') is None


def find_ror_refined_files(input_dir: str) -> List[str]:
    """找到所有 enriched_ror_refined 文件（排除已 replenished 的）"""
    pattern = os.path.join(input_dir, 'all_papers_*_enriched_ror_refined.jsonl')
    files = sorted(glob.glob(pattern))
    # 排除已经 replenished 的文件
    files = [f for f in files if '_replenished' not in f]
    return files


def find_enriched_files(input_dir: str) -> List[str]:
    """找到所有 enriched 文件（排除 ror_refined 和 replenished 的）"""
    pattern = os.path.join(input_dir, 'all_papers_*_enriched.jsonl')
    files = sorted(glob.glob(pattern))
    files = [f for f in files if '_ror_refined' not in f and '_replenished' not in f]
    return files


# ── 带限流检测的 OpenAlex API 调用 ──

def fetch_author_with_rate_limit(
    author_name: str,
    pubmed_affiliation: str = "",
    delay: float = 0.15,
    max_retries: int = 3,
) -> Optional[Dict]:
    """
    调用 OpenAlex API 获取作者信息，带限流检测。

    - HTTP 429 → 抛出 RateLimitError
    - 网络错误 → 重试
    - 成功 → 返回作者信息 dict 或 None（未找到）
    """
    url = "https://api.openalex.org/authors"
    mode = classify_name(author_name)
    is_strict = mode == "strict"

    params = {'search': author_name, 'per-page': 10 if is_strict else 5}

    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, headers=HEADERS, timeout=15)

            # 限流检测
            if response.status_code == RATE_LIMIT_STATUS:
                raise RateLimitError(
                    f"OpenAlex API rate limit hit (HTTP 429) for author '{author_name}'"
                )

            response.raise_for_status()
            data = response.json()

            if not data or not data.get('results'):
                return None

            candidates = data['results']

            # 严格模式：名字相似度 > 0.9 + 机构匹配
            if is_strict:
                if not pubmed_affiliation:
                    return None

                name_matches = []
                for c in candidates:
                    sim = name_similarity(author_name, c.get('display_name', ''))
                    if sim > 0.9:
                        name_matches.append((c, sim))

                if not name_matches:
                    return None

                name_matches.sort(key=lambda x: -x[1])

                for candidate, sim in name_matches:
                    last_inst = candidate.get('last_known_institution')
                    cand_affil = last_inst.get('display_name', '') if last_inst else ''

                    if cand_affil and check_affiliation_match(pubmed_affiliation, cand_affil):
                        return _extract_metrics(candidate, cand_affil, 'high')

                return None
            else:
                # 宽松模式：取最相似的
                best = max(candidates,
                           key=lambda x: name_similarity(author_name, x.get('display_name', '')))
                sim = name_similarity(author_name, best.get('display_name', ''))
                if sim < 0.8:
                    return None

                last_inst = best.get('last_known_institution', {})
                cand_affil = last_inst.get('display_name', '') if last_inst else ''
                return _extract_metrics(best, cand_affil, 'medium')

        except RateLimitError:
            raise
        except requests.exceptions.Timeout:
            wait = delay * (2 ** attempt)
            print(f"      [RETRY {attempt+1}/{max_retries}] Timeout, waiting {wait:.1f}s...")
            time.sleep(wait)
        except requests.exceptions.RequestException as e:
            wait = delay * (2 ** attempt)
            print(f"      [RETRY {attempt+1}/{max_retries}] Request error: {e}")
            time.sleep(wait)

    print(f"      [FAIL] Max retries exceeded for '{author_name}'")
    return None


def _extract_metrics(candidate: Dict, affiliation: str, confidence: str) -> Dict:
    """从 OpenAlex 候选结果中提取关键指标"""
    citations = candidate.get('cited_by_count', 0) or 0
    result = {
        'name': candidate.get('display_name', ''),
        'h_index': candidate.get('summary_stats', {}).get('h_index', 0) or 0,
        'citations': citations,
        'works_count': candidate.get('works_count', 0) or 0,
        'i10_index': candidate.get('summary_stats', {}).get('i10_index', 0) or 0,
        'orcid': candidate.get('orcid'),
        'affiliation': affiliation,
        'match_confidence': confidence,
    }
    if citations > 200000:
        result['suspicious'] = True
    return result


def check_affiliation_match(pubmed_affil: str, openalex_affil: str) -> bool:
    """检查两个单位是否匹配（简化版，来自 enrich_authors.py）"""
    if not pubmed_affil or not openalex_affil:
        return False
    a1, a2 = pubmed_affil.lower(), openalex_affil.lower()
    if a1 in a2 or a2 in a1:
        return True
    import re
    from difflib import SequenceMatcher
    k1 = set(re.findall(r'\b[a-z]{4,}\b', a1))
    k2 = set(re.findall(r'\b[a-z]{4,}\b', a2))
    if k1 & k2:
        return True
    return SequenceMatcher(None, a1, a2).ratio() > 0.6


# ── Scan 命令 ──

def scan_command(args):
    """扫描所有 ror_refined 文件，导出需要补全的作者列表"""
    input_dir = args.input_dir
    output_file = args.output

    files = find_ror_refined_files(input_dir)
    if not files:
        print(f"[ERROR] No *_enriched_ror_refined.jsonl files found in {input_dir}")
        return

    print("=" * 70)
    print("Author Info Replenishment - SCAN")
    print("=" * 70)
    print(f"Found {len(files)} ror_refined files to scan\n")

    db = get_database()

    total_papers = 0
    papers_with_incomplete = 0
    total_key_authors_checked = 0
    total_incomplete = 0

    # author_name -> {papers: [...], pubmed_affiliations: set(), needs_fetch: bool}
    authors_map: Dict[str, Dict] = {}
    cache_hit_authors: Set[str] = set()

    for filepath in files:
        filename = os.path.basename(filepath)
        print(f"  Scanning: {filename} ...", end=" ")

        with jsonlines.open(filepath) as reader:
            papers = list(reader)

        file_incomplete = 0
        for paper_idx, paper in enumerate(papers):
            authors = paper.get('authors', [])
            author_details = paper.get('author_details', [])

            if not authors:
                continue

            total_papers += 1
            key_authors = get_key_authors(authors)
            paper_has_incomplete = False

            for position, author_name in key_authors:
                total_key_authors_checked += 1
                detail = find_author_in_details(author_name, author_details)

                if not is_author_incomplete(detail):
                    continue  # 已有完整信息

                paper_has_incomplete = True
                total_incomplete += 1

                # 收集 PubMed 机构信息（用于严格匹配）
                pubmed_affil = ""
                if detail:
                    pubmed_affil = detail.get('affiliation', '') or ""

                # 检查 DB 缓存
                cached = db.get_author(author_name)
                if cached and cached.get('h_index') is not None:
                    cache_hit_authors.add(author_name)
                    needs_fetch = False
                else:
                    needs_fetch = True

                # 记录
                if author_name not in authors_map:
                    authors_map[author_name] = {
                        'name': author_name,
                        'needs_fetch': needs_fetch,
                        'pubmed_affiliations': set(),
                        'papers': [],
                    }
                if pubmed_affil:
                    authors_map[author_name]['pubmed_affiliations'].add(pubmed_affil)

                authors_map[author_name]['papers'].append({
                    'file': filename,
                    'paper_idx': paper_idx,
                    'title': paper.get('title', '')[:80],
                    'date': paper.get('date', ''),
                    'doi': paper.get('doi', ''),
                    'pmid': paper.get('pmid', ''),
                    'author_position': position,
                })

                # 如果任何一个出现标记 needs_fetch，就保持
                if needs_fetch:
                    authors_map[author_name]['needs_fetch'] = True

            if paper_has_incomplete:
                papers_with_incomplete += 1
                file_incomplete += 1

        print(f"{len(papers)} papers, {file_incomplete} incomplete")

    # 构建导出数据
    authors_needing_fetch = []
    cache_only = []

    for author_name, info in sorted(authors_map.items(), key=lambda x: -len(x[1]['papers'])):
        entry = {
            'name': author_name,
            'needs_fetch': info['needs_fetch'],
            'occurrence_count': len(info['papers']),
            'pubmed_affiliations': list(info['pubmed_affiliations']) if info['pubmed_affiliations'] else [],
            'papers': info['papers'],
        }
        if info['needs_fetch']:
            authors_needing_fetch.append(entry)
        else:
            cache_only.append(author_name)

    result = {
        'scan_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'files_scanned': [os.path.basename(f) for f in files],
        'summary': {
            'total_papers': total_papers,
            'papers_with_incomplete_authors': papers_with_incomplete,
            'total_key_authors_checked': total_key_authors_checked,
            'total_incomplete_occurrences': total_incomplete,
            'unique_incomplete_authors': len(authors_map),
            'cache_hits': len(cache_only),
            'needs_api_call': len(authors_needing_fetch),
        },
        'authors_needing_fetch': authors_needing_fetch,
        'cache_only_authors': cache_only,
    }

    # 保存
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 打印摘要
    print("\n" + "=" * 70)
    print("SCAN COMPLETE")
    print("=" * 70)
    s = result['summary']
    print(f"  Total papers scanned:           {s['total_papers']}")
    print(f"  Papers with incomplete authors:  {s['papers_with_incomplete_authors']}")
    print(f"  Key author occurrences checked:  {s['total_key_authors_checked']}")
    print(f"  Incomplete occurrences:          {s['total_incomplete_occurrences']}")
    print(f"  Unique incomplete authors:       {s['unique_incomplete_authors']}")
    print(f"    - Available in DB cache:       {s['cache_hits']}")
    print(f"    - Need API call:               {s['needs_api_call']}")
    print(f"\n  Exported to: {output_file}")
    print(f"\n  Next step: review the list, then run:")
    print(f"    python src/replenish_authors.py update")


# ── Update 命令 ──

def load_progress(progress_file: str) -> Dict:
    """加载进度文件"""
    if os.path.exists(progress_file):
        with open(progress_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'last_run': None, 'total_api_calls_today': 0, 'authors': {}}


def save_progress(progress: Dict, progress_file: str):
    """保存进度文件"""
    os.makedirs(os.path.dirname(progress_file), exist_ok=True)
    with open(progress_file, 'w', encoding='utf-8') as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def update_command(args):
    """调用 OpenAlex API 补全作者信息，然后生成更新后的 JSONL 文件"""
    input_file = args.input
    progress_file = args.progress
    daily_limit = args.daily_limit

    if not os.path.exists(input_file):
        print(f"[ERROR] Scan result not found: {input_file}")
        print("  Run 'python src/replenish_authors.py scan' first.")
        return

    with open(input_file, 'r', encoding='utf-8') as f:
        scan_data = json.load(f)

    # 检查是否是新的一天，重置计数
    today = datetime.now().strftime('%Y-%m-%d')
    progress = load_progress(progress_file)
    if progress.get('last_run') != today:
        progress = {'last_run': today, 'total_api_calls_today': 0, 'authors': {}}

    authors_to_fetch = scan_data.get('authors_needing_fetch', [])
    if not authors_to_fetch:
        print("[INFO] No authors need API calls. Applying cache hits only...")
        _apply_updates(scan_data)
        return

    # 过滤掉今天已经尝试过的作者
    today_attempted = set()
    for name, info in progress.get('authors', {}).items():
        if info.get('last_attempt') == today:
            today_attempted.add(name)

    pending = [a for a in authors_to_fetch if a['name'] not in today_attempted]
    skipped = len(authors_to_fetch) - len(pending)

    print("=" * 70)
    print("Author Info Replenishment - UPDATE")
    print("=" * 70)
    print(f"  Authors needing API call:  {len(authors_to_fetch)}")
    if skipped:
        print(f"  Already attempted today:   {skipped}")
    print(f"  Pending:                   {len(pending)}")
    print(f"  API calls used today:      {progress['total_api_calls_today']}")
    print(f"  Daily limit:               {daily_limit}")
    remaining = daily_limit - progress['total_api_calls_today']
    print(f"  Remaining quota:           {remaining}")
    print()

    if remaining <= 0:
        print("[STOP] Daily API quota exhausted. Applying cache hits only...")
        _apply_updates(scan_data)
        return

    if not pending:
        print("[INFO] All pending authors already attempted today.")
        print("  Applying updates from cache + previous fetches...")
        _apply_updates(scan_data)
        return

    # 初始化 DB
    db = get_database()
    api_calls_made = 0
    fetched_count = 0
    not_found_count = 0
    rate_limited = False

    for i, author_entry in enumerate(pending, 1):
        author_name = author_entry['name']

        # 检查配额
        if progress['total_api_calls_today'] + api_calls_made >= daily_limit:
            print(f"\n[STOP] Daily limit reached ({daily_limit}). Try again tomorrow.")
            rate_limited = True
            break

        # 获取最佳 PubMed 机构信息（用于严格匹配）
        pubmed_affils = author_entry.get('pubmed_affiliations', [])
        best_affil = pubmed_affils[0] if pubmed_affils else ""

        print(f"  [{i}/{len(pending)}] {author_name}", end="")

        try:
            metrics = fetch_author_with_rate_limit(author_name, best_affil)
            api_calls_made += 1

            if metrics:
                # 更新 DB
                info = {
                    'name': author_name,
                    'h_index': metrics.get('h_index'),
                    'citations': metrics.get('citations'),
                    'works_count': metrics.get('works_count'),
                    'i10_index': metrics.get('i10_index'),
                    'orcid': metrics.get('orcid'),
                    'is_senior_researcher': is_senior_researcher(metrics),
                }
                db.update_author_metrics(author_name, info)
                fetched_count += 1
                status = "SENIOR" if info['is_senior_researcher'] else "OK"
                print(f" -> {status} (h={info['h_index']}, cites={info['citations']})")
            else:
                not_found_count += 1
                progress['authors'][author_name] = {
                    'status': 'not_found',
                    'last_attempt': today,
                }
                print(f" -> not found")

        except RateLimitError as e:
            print(f"\n  [RATE LIMITED] {e}")
            print(f"  API calls made so far: {api_calls_made}")
            rate_limited = True
            break

        # 记录进度
        progress['authors'][author_name] = {
            'status': 'fetched' if metrics else 'not_found',
            'last_attempt': today,
        }

        # 每处理10个作者保存一次进度
        if i % 10 == 0:
            progress['total_api_calls_today'] += api_calls_made
            save_progress(progress, progress_file)
            api_calls_made = 0

        # OpenAlex 速率限制：10 req/sec
        time.sleep(0.12)

    # 保存最终进度
    progress['total_api_calls_today'] += api_calls_made
    save_progress(progress, progress_file)

    # 打印摘要
    print("\n" + "=" * 70)
    print("FETCH PHASE COMPLETE")
    print("=" * 70)
    print(f"  Authors fetched:    {fetched_count}")
    print(f"  Not found:          {not_found_count}")
    print(f"  API calls made:     {progress['total_api_calls_today']}")
    if rate_limited:
        print(f"  [RATE LIMITED] Remaining authors will be processed next run.")
    print()

    # 应用更新到 JSONL 文件
    print("Applying updates to JSONL files...")
    _apply_updates(scan_data)

    print("\n[OK] Done!")


def _ror_refined_to_enriched(filename: str) -> str:
    """将 ror_refined 文件名转换为对应的 enriched 文件名"""
    return filename.replace('_enriched_ror_refined.jsonl', '_enriched.jsonl')


def _apply_updates(scan_data: Dict):
    """
    用 DB 中的最新数据更新 enriched 文件的 author_details。

    流程:
    1. 读取原始 enriched 文件
    2. 从 DB 更新 author_details
    3. 写入临时文件
    4. 验证数据完整性（论文数、标题、作者列表不变）
    5. 验证通过后覆盖原始 enriched 文件
    """
    db = get_database()
    files_scanned = scan_data.get('files_scanned', [])
    input_dir = DEFAULT_INPUT_DIR

    # 收集需要更新的 enriched 文件
    enriched_files = []
    for ror_filename in files_scanned:
        enriched_filename = _ror_refined_to_enriched(ror_filename)
        enriched_filepath = os.path.join(input_dir, enriched_filename)
        if os.path.exists(enriched_filepath):
            enriched_files.append(enriched_filepath)
        else:
            print(f"  [WARN] Enriched file not found: {enriched_filename}")

    if not enriched_files:
        print("[WARN] No enriched files to update.")
        return

    total_updated = 0
    total_papers = 0

    for enriched_filepath in enriched_files:
        filename = os.path.basename(enriched_filepath)
        temp_filepath = enriched_filepath + '.tmp'

        print(f"  Processing: {filename}")

        # 1. 读取原始 enriched 文件
        with jsonlines.open(enriched_filepath) as reader:
            original_papers = list(reader)

        # 2. 更新 author_details
        updated_papers = []
        file_updated = 0

        for paper in original_papers:
            updated_paper = _update_paper_authors(paper, db)
            updated_papers.append(updated_paper)

            # 检查是否有作者被更新
            old_details = paper.get('author_details', [])
            new_details = updated_paper.get('author_details', [])
            for old, new in zip(old_details, new_details):
                if old.get('h_index') is None and new.get('h_index') is not None:
                    file_updated += 1
                    break

        # 3. 写入临时文件
        with jsonlines.open(temp_filepath, 'w') as f:
            for paper in updated_papers:
                f.write(paper)

        # 4. 验证数据完整性
        if not _verify_integrity(original_papers, updated_papers, filename):
            print(f"    [ERROR] Verification failed! Temp file kept: {temp_filepath}")
            continue

        # 5. 验证通过，覆盖原始文件
        os.replace(temp_filepath, enriched_filepath)

        total_papers += len(updated_papers)
        total_updated += file_updated
        print(f"    -> {len(updated_papers)} papers, {file_updated} updated [VERIFIED]")

    print(f"\n  Total: {total_papers} papers processed, {total_updated} papers had authors updated")


def _verify_integrity(original: List[Dict], updated: List[Dict], filename: str, allow_pmid_update: bool = True) -> bool:
    """
    验证更新后的数据完整性:
    - 论文数量一致
    - 每篇论文的标题、作者列表、DOI、abstract、url 不变
    - PMID 通常不变，但允许从 None/空 更新为有效值（标题搜索找到新 PMID）
    - author_details 作者数量一致、作者名不变
    """
    if len(original) != len(updated):
        print(f"    [FAIL] Paper count mismatch: {len(original)} vs {len(updated)}")
        return False

    for i, (orig, updt) in enumerate(zip(original, updated)):
        # 检查核心字段不变
        for field in ['title', 'authors', 'doi', 'abstract', 'url']:
            orig_val = orig.get(field)
            updt_val = updt.get(field)
            if orig_val != updt_val:
                print(f"    [FAIL] Field '{field}' changed in paper {i}: "
                      f"{str(orig_val)[:50]} -> {str(updt_val)[:50]}")
                return False

        # PMID: 允许从 None/空 更新为有效值
        orig_pmid = orig.get('pmid')
        updt_pmid = updt.get('pmid')
        if orig_pmid != updt_pmid:
            if not allow_pmid_update:
                print(f"    [FAIL] Field 'pmid' changed in paper {i}: {orig_pmid} -> {updt_pmid}")
                return False
            if orig_pmid:
                print(f"    [FAIL] Field 'pmid' changed from non-empty value in paper {i}: "
                      f"{orig_pmid} -> {updt_pmid}")
                return False
            # orig_pmid is None/empty and updt_pmid is set: allowed

        # 检查 author_details 作者数量一致
        orig_ad = orig.get('author_details', [])
        updt_ad = updt.get('author_details', [])
        if len(orig_ad) != len(updt_ad):
            print(f"    [FAIL] author_details count changed in paper {i}: "
                  f"{len(orig_ad)} -> {len(updt_ad)}")
            return False

        # 检查 author_details 中的作者名不变
        for j, (oa, ua) in enumerate(zip(orig_ad, updt_ad)):
            if oa.get('name') != ua.get('name'):
                print(f"    [FAIL] Author name changed at paper {i}, author {j}: "
                      f"{oa.get('name')} -> {ua.get('name')}")
                return False

    return True


def _update_paper_authors(paper: Dict, db: AuthorDatabase) -> Dict:
    """
    用 DB 中的最新数据更新单篇论文的 author_details。
    只更新 OpenAlex 来源的字段（h_index, citations, works_count, i10_index, orcid, is_senior_researcher）。
    不触碰 affiliation 和 ror_* 字段。
    """
    updated = paper.copy()
    author_details = paper.get('author_details', [])

    if not author_details:
        return updated

    new_details = []
    for detail in author_details:
        new_detail = dict(detail)  # 浅拷贝，保留原有字段
        author_name = detail.get('name', '')

        if not author_name:
            new_details.append(new_detail)
            continue

        # 只更新关键作者（前2+后2），其他作者保持原样
        authors_list = paper.get('authors', [])
        key_author_names = {name for _, name in get_key_authors(authors_list)}

        if author_name not in key_author_names:
            new_details.append(new_detail)
            continue

        # 从 DB 获取最新数据
        cached = db.get_author(author_name)
        if cached and cached.get('h_index') is not None:
            # 更新 OpenAlex 来源的字段
            new_detail['h_index'] = cached['h_index']
            new_detail['citations'] = cached.get('citations')
            new_detail['works_count'] = cached.get('works_count')
            new_detail['i10_index'] = cached.get('i10_index')
            new_detail['orcid'] = cached.get('orcid')
            new_detail['is_senior_researcher'] = cached.get('is_senior_researcher', False)
            new_detail['source'] = 'OpenAlex'

        new_details.append(new_detail)

    updated['author_details'] = new_details

    # 重新计算 senior_authors
    senior_authors = []
    for detail in new_details:
        if detail.get('is_senior_researcher'):
            senior_info = {
                'name': detail.get('name', ''),
                'h_index': detail.get('h_index'),
                'citations': detail.get('citations'),
                'works_count': detail.get('works_count'),
                'institution': detail.get('normalized_affiliation') or detail.get('affiliation', 'N/A'),
            }
            senior_authors.append(senior_info)

    updated['senior_authors'] = senior_authors
    updated['senior_author_names'] = [s['name'] for s in senior_authors]
    updated['senior_author_count'] = len(senior_authors)
    updated['has_senior_researcher'] = len(senior_authors) > 0

    return updated


# ── Fetch Affiliations 命令（从 PubMed 补充地址）──

def _normalize_author_name(name: str) -> str:
    """标准化作者名用于匹配：去除点号、多余空格、统一大小写"""
    import re
    name = str(name).strip()
    name = re.sub(r'\.', '', name)  # 去掉点号（如 G. -> G）
    name = re.sub(r'\s+', ' ', name)  # 合并连续空格
    return name.strip()


def _update_paper_affiliations(paper: Dict, pmid_affiliations: Dict[str, Dict[str, str]], pmid: Optional[str] = None) -> Dict:
    """
    用 PubMed 获取的地址信息更新单篇论文的 author_details、affiliations 和 countries。
    如果传入 pmid 参数，会同时更新论文的 pmid 字段（用于标题搜索找到的新 PMID）。
    """
    updated = paper.copy()
    if pmid is None:
        pmid = paper.get('pmid') or paper.get('PMID')
    if not pmid or pmid not in pmid_affiliations:
        return updated

    pubmed_affils = pmid_affiliations[pmid]
    details = paper.get('author_details', [])
    if not details:
        return updated

    # 构建标准化后的 PubMed 名字查找表
    normalized_affils = {_normalize_author_name(k): v for k, v in pubmed_affils.items()}

    new_details = []
    all_affiliations = list(paper.get('affiliations', []))
    all_countries = list(paper.get('countries', []))

    for detail in details:
        new_detail = dict(detail)
        author_name = detail.get('name', '')
        normalized_name = _normalize_author_name(author_name)

        affiliation = normalized_affils.get(normalized_name)
        if affiliation:
            new_detail['affiliation'] = affiliation
            new_detail['normalized_affiliation'] = normalize_affiliation(affiliation)

            # 更新 paper-level affiliations/countries
            split_affils = split_affiliation(affiliation)
            for affil in split_affils:
                norm_affil = normalize_affiliation(affil)
                if norm_affil and norm_affil not in all_affiliations:
                    all_affiliations.append(norm_affil)
                country = infer_country_from_affiliation(affil)
                if country and country not in all_countries:
                    all_countries.append(country)

        new_details.append(new_detail)

    updated['author_details'] = new_details
    updated['affiliations'] = all_affiliations
    updated['countries'] = all_countries

    # 如果 PMID 是通过标题搜索新找到的，更新论文的 PMID 字段
    if pmid and not (paper.get('pmid') or paper.get('PMID')):
        updated['pmid'] = pmid

    return updated


def fetch_affiliations_command(args):
    """从 PubMed API 批量补充 enriched 文件中缺失的作者地址信息"""
    input_dir = args.input_dir
    search_by_title = getattr(args, 'search_by_title', False)
    files = find_enriched_files(input_dir)

    if not files:
        print(f"[ERROR] No enriched files found in {input_dir}")
        return

    print("=" * 70)
    print("Author Affiliation Replenishment - PubMed efetch")
    if search_by_title:
        print("  [Title search enabled: papers without PMID will be searched by title]")
    print("=" * 70)
    print(f"Found {len(files)} enriched files\n")

    total_papers = 0
    papers_with_pmid = 0
    papers_without_pmid = 0
    papers_with_affil = 0
    papers_needing = []

    # 1. 扫描需要补充地址的论文
    for filepath in files:
        filename = os.path.basename(filepath)
        file_total = 0
        file_pmid = 0
        file_no_pmid = 0
        file_needing = 0
        file_has_affil = 0

        with jsonlines.open(filepath) as reader:
            papers = list(reader)

        for paper_idx, paper in enumerate(papers):
            total_papers += 1
            file_total += 1
            pmid = paper.get('pmid') or paper.get('PMID')
            title = paper.get('title', '')
            authors = paper.get('authors', [])
            details = paper.get('author_details', [])
            key_authors = get_key_authors(authors)

            has_missing = any(
                not find_author_in_details(name, details).get('affiliation')
                for _, name in key_authors
            )

            if not has_missing:
                papers_with_affil += 1
                file_has_affil += 1
                continue

            if pmid:
                papers_with_pmid += 1
                file_pmid += 1
                papers_needing.append({
                    'file': filepath,
                    'paper_idx': paper_idx,
                    'pmid': str(pmid).strip(),
                    'title': title[:80],
                })
                file_needing += 1
            elif search_by_title:
                papers_without_pmid += 1
                file_no_pmid += 1
                papers_needing.append({
                    'file': filepath,
                    'paper_idx': paper_idx,
                    'pmid': None,
                    'title': title[:80],
                })
                file_needing += 1

        print(f"  {filename}: {file_total} papers | {file_pmid} with PMID need affil | {file_no_pmid} no-PMID need affil | {file_has_affil} already have")

    # 2. 对无 PMID 的论文按标题搜索 PMID（4线程并行，共享 token bucket 限速）
    title_searched = 0
    title_found = 0
    if search_by_title:
        no_pmid_entries = [p for p in papers_needing if p['pmid'] is None]
        if no_pmid_entries:
            print("\nSearching PubMed by title for papers without PMID...")
            print("  (Using 4 threads with shared rate limiter)")

            def _search_one_title(args):
                idx, entry = args
                found_pmid = find_best_pmid_by_title(entry['title'])
                return idx, found_pmid

            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(_search_one_title, (i, e)): i
                           for i, e in enumerate(no_pmid_entries)}
                for future in as_completed(futures):
                    i, found_pmid = future.result()
                    title_searched += 1
                    if found_pmid:
                        no_pmid_entries[i]['pmid'] = found_pmid
                        title_found += 1
                    if title_searched % 100 == 0 or title_searched == len(no_pmid_entries):
                        print(f"  Progress: {title_searched}/{len(no_pmid_entries)} titles searched, {title_found} PMIDs found")

            print(f"  Titles searched: {title_searched}, PMIDs found: {title_found}")

    unique_pmids = list({p['pmid'] for p in papers_needing if p['pmid']})

    print("\n" + "-" * 70)
    print(f"  Total papers:              {total_papers}")
    print(f"  With PMID needing affil:   {papers_with_pmid}")
    if search_by_title:
        print(f"  No PMID searched by title: {papers_without_pmid} (found {title_found})")
    print(f"  Already have affil:        {papers_with_affil}")
    print(f"  Need PubMed fetch:         {len(papers_needing)} ({len(unique_pmids)} unique PMIDs)")
    print("-" * 70)

    if not unique_pmids:
        print("\n[INFO] No PMIDs available to fetch affiliations.")
        return

    # 3. 从 PubMed 批量获取地址
    print("\nFetching affiliations from PubMed...")
    pmid_affiliations = fetch_affiliations_batch(unique_pmids)

    if not pmid_affiliations:
        print("[WARN] No affiliations returned from PubMed.")
        return

    fetched_pmids = len(pmid_affiliations)
    print(f"  PubMed returned affiliations for {fetched_pmids}/{len(unique_pmids)} PMIDs")

    # 4. 应用更新到 enriched 文件
    print("\nApplying updates to enriched files...")
    file_to_papers = defaultdict(list)
    for p in papers_needing:
        file_to_papers[p['file']].append(p)

    total_updated_papers = 0
    for filepath, paper_list in file_to_papers.items():
        filename = os.path.basename(filepath)
        temp_filepath = filepath + '.tmp'

        with jsonlines.open(filepath) as reader:
            original_papers = list(reader)

        # 快速索引需要更新的论文
        paper_idx_to_pmid = {p['paper_idx']: p['pmid'] for p in paper_list if p['pmid']}

        updated_papers = []
        file_updated = 0
        for idx, paper in enumerate(original_papers):
            pmid = paper_idx_to_pmid.get(idx)
            updated_paper = _update_paper_affiliations(paper, pmid_affiliations, pmid=pmid)
            updated_papers.append(updated_paper)

            old_details = paper.get('author_details', [])
            new_details = updated_paper.get('author_details', [])
            for old, new in zip(old_details, new_details):
                if not old.get('affiliation') and new.get('affiliation'):
                    file_updated += 1
                    break

        if not _verify_integrity(original_papers, updated_papers, filename):
            print(f"  [ERROR] Verification failed for {filename}, temp kept: {temp_filepath}")
            continue

        with jsonlines.open(temp_filepath, 'w') as f:
            for paper in updated_papers:
                f.write(paper)
        os.replace(temp_filepath, filepath)

        total_updated_papers += file_updated
        print(f"  {filename}: {file_updated} papers updated [VERIFIED]")

    print("\n" + "=" * 70)
    print("PUBMED AFFILIATION FETCH COMPLETE")
    print("=" * 70)
    print(f"  Papers updated: {total_updated_papers}")
    print(f"  PMIDs fetched:  {fetched_pmids}")
    if search_by_title:
        print(f"  PMIDs found by title search: {title_found}/{title_searched}")
    print(f"\n  Next step: run 'python src/replenish_authors.py build' to regenerate ror_refined + database")


# ── Build 命令（运行 build_ror + build_sq）──

def _run_build_ror():
    """运行 build_ror.bat，重新生成所有 ror_refined 文件"""
    script_path = os.path.join('bashScripts', 'build_ror.bat')
    if not os.path.exists(script_path):
        print(f"[ERROR] build_ror.bat not found: {script_path}")
        return False

    print("\n" + "=" * 70)
    print("Running build_ror.bat (ROR refinement)...")
    print("=" * 70)

    try:
        result = subprocess.run(
            [script_path],
            shell=True,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        if result.returncode != 0:
            print(f"[WARN] build_ror.bat exited with code {result.returncode}")
            return False
        print("[OK] build_ror.bat completed")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to run build_ror.bat: {e}")
        return False


def _run_build_sq():
    """运行 build_sq.bat，重建 SQLite 数据库"""
    script_path = os.path.join('bashScripts', 'build_sq.bat')
    if not os.path.exists(script_path):
        print(f"[ERROR] build_sq.bat not found: {script_path}")
        return False

    print("\n" + "=" * 70)
    print("Running build_sq.bat (SQLite database rebuild)...")
    print("=" * 70)

    try:
        result = subprocess.run(
            [script_path],
            shell=True,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        if result.returncode != 0:
            print(f"[WARN] build_sq.bat exited with code {result.returncode}")
            return False
        print("[OK] build_sq.bat completed")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to run build_sq.bat: {e}")
        return False


def build_command(args):
    """运行 build_ror.bat + build_sq.bat 重建 ror_refined 文件和数据库"""
    print("=" * 70)
    print("Author Info Replenishment - BUILD")
    print("=" * 70)

    success = True
    if not _run_build_ror():
        success = False
    if not _run_build_sq():
        success = False

    if success:
        print("\n[OK] Build complete! ROR refined files and database updated.")
    else:
        print("\n[WARN] Build completed with warnings. Check output above.")


# ── Pipeline 命令（完整流水线）──

def pipeline_command(args):
    """
    完整流水线: PubMed地址 → scan → OpenAlex → 更新enriched文件 → build_ror → build_sq
    """
    # Step 1: Fetch PubMed affiliations
    print("\n" + "#" * 70)
    print("# STEP 1/5: FETCH PUBMED AFFILIATIONS")
    print("#" * 70)
    fetch_affiliations_args = argparse.Namespace(
        input_dir=args.input_dir,
        search_by_title=args.search_by_title,
    )
    fetch_affiliations_command(fetch_affiliations_args)

    # Step 2: Scan
    print("\n" + "#" * 70)
    print("# STEP 2/5: SCAN")
    print("#" * 70)
    scan_args = argparse.Namespace(
        input_dir=args.input_dir,
        output=args.output,
    )
    scan_command(scan_args)

    # Step 3: Update (API + apply to enriched files)
    print("\n" + "#" * 70)
    print("# STEP 3/5: UPDATE (OpenAlex API calls + update enriched files)")
    print("#" * 70 + "\n")
    update_command(args)

    # Step 4: Build ROR
    print("\n" + "#" * 70)
    print("# STEP 4/5: BUILD ROR")
    print("#" * 70)
    _run_build_ror()

    # Step 5: Build SQ
    print("\n" + "#" * 70)
    print("# STEP 5/5: BUILD DATABASE")
    print("#" * 70)
    _run_build_sq()

    print("\n" + "=" * 70)
    print("PIPELINE COMPLETE!")
    print("=" * 70)
    print("  All enriched files updated, ror_refined files regenerated,")
    print("  and database rebuilt with latest author information.")


# ── 主入口 ──

def main():
    parser = argparse.ArgumentParser(
        description='作者信息补全工具 - 找到不完整的作者信息并从 OpenAlex 重新获取',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python src/replenish_authors.py pipeline                         # 完整流水线
  python src/replenish_authors.py pipeline --daily-limit 950        # 指定每日限额
  python src/replenish_authors.py fetch-affiliations                # 从PubMed补地址
  python src/replenish_authors.py scan                              # 仅扫描
  python src/replenish_authors.py update                            # 仅更新
  python src/replenish_authors.py build                             # 仅重建ror+数据库
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # scan 子命令
    scan_parser = subparsers.add_parser('scan', help='扫描文件，导出需要补全的作者列表')
    scan_parser.add_argument('--input-dir', default=DEFAULT_INPUT_DIR,
                             help=f'输入目录 (default: {DEFAULT_INPUT_DIR})')
    scan_parser.add_argument('--output', default=DEFAULT_OUTPUT_LIST,
                             help=f'输出列表文件 (default: {DEFAULT_OUTPUT_LIST})')

    # update 子命令
    update_parser = subparsers.add_parser('update', help='调用API补全并更新enriched文件')
    update_parser.add_argument('--input', default=DEFAULT_OUTPUT_LIST,
                               help=f'扫描结果文件 (default: {DEFAULT_OUTPUT_LIST})')
    update_parser.add_argument('--progress', default=DEFAULT_PROGRESS_FILE,
                               help=f'进度文件 (default: {DEFAULT_PROGRESS_FILE})')
    update_parser.add_argument('--daily-limit', type=int, default=DEFAULT_DAILY_LIMIT,
                               help=f'每日API调用上限 (default: {DEFAULT_DAILY_LIMIT})')
    update_parser.add_argument('--input-dir', default=DEFAULT_INPUT_DIR,
                               help=f'输入目录 (default: {DEFAULT_INPUT_DIR})')
    update_parser.add_argument('--output', default=DEFAULT_OUTPUT_LIST,
                               help=argparse.SUPPRESS)

    # build 子命令
    build_parser = subparsers.add_parser('build', help='运行 build_ror.bat + build_sq.bat')

    # fetch-affiliations 子命令
    fetch_affil_parser = subparsers.add_parser('fetch-affiliations', help='从PubMed efetch补充缺失的作者地址')
    fetch_affil_parser.add_argument('--input-dir', default=DEFAULT_INPUT_DIR,
                                    help=f'输入目录 (default: {DEFAULT_INPUT_DIR})')
    fetch_affil_parser.add_argument('--search-by-title', action='store_true',
                                    help='对没有 PMID 的论文通过标题搜索 PubMed（较慢但更全面）')

    # pipeline 子命令（完整流水线）
    pipeline_parser = subparsers.add_parser('pipeline', help='完整流水线: fetch-affiliations+scan+update+build_ror+build_sq')
    pipeline_parser.add_argument('--input-dir', default=DEFAULT_INPUT_DIR,
                                 help=f'输入目录 (default: {DEFAULT_INPUT_DIR})')
    pipeline_parser.add_argument('--output', default=DEFAULT_OUTPUT_LIST,
                                 help=f'输出列表文件 (default: {DEFAULT_OUTPUT_LIST})')
    pipeline_parser.add_argument('--progress', default=DEFAULT_PROGRESS_FILE,
                                 help=f'进度文件 (default: {DEFAULT_PROGRESS_FILE})')
    pipeline_parser.add_argument('--daily-limit', type=int, default=DEFAULT_DAILY_LIMIT,
                                 help=f'每日API调用上限 (default: {DEFAULT_DAILY_LIMIT})')
    pipeline_parser.add_argument('--input', default=DEFAULT_OUTPUT_LIST,
                                 help=argparse.SUPPRESS)
    pipeline_parser.add_argument('--search-by-title', action='store_true',
                                 help='对没有 PMID 的论文通过标题搜索 PubMed')

    args = parser.parse_args()

    if args.command == 'scan':
        scan_command(args)
    elif args.command == 'update':
        update_command(args)
    elif args.command == 'build':
        build_command(args)
    elif args.command == 'fetch-affiliations':
        fetch_affiliations_command(args)
    elif args.command == 'pipeline':
        pipeline_command(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
