"""Validate a weekly corpus and write its canonical source-backed report.

Example:
  python -B scripts/finalize_bulletin_report.py --date 2026-10-04 \
    --start-date 2026-09-28 --issue 30 --theme-line1 "研究对象或方法" \
    --theme-line2 "主要发现" --run-dir tmps/pipeline_20261004

This is local postprocessing: no model API or historical database is queried.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
from datetime import date, datetime
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
TIERS = ("头条推荐", "深度解读", "简要提及", "域外高影响", "不推送", "错误")


def normalized_title(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def publication_date(value) -> str:
    text = str(value or "").strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}(?:$|[T\s])", text):
        return date.fromisoformat(text[:10]).isoformat()
    if not text:
        raise ValueError("A paper has no publication date")
    from dateutil import parser as date_parser
    return date_parser.parse(text, dayfirst=False).date().isoformat()


def paper_key(paper: dict) -> tuple[str, str]:
    title = normalized_title(str(paper.get("title") or ""))
    if not title:
        raise ValueError("A paper has no title")
    return title, publication_date(paper.get("date"))


def comparable_metadata(paper: dict) -> dict:
    comparable = copy.deepcopy(paper)
    comparable["title"], comparable["date"] = paper_key(paper)
    return comparable


def missing_abstract(paper: dict) -> bool:
    abstract = str(paper.get("abstract") or "").strip()
    return len(abstract) < 50 or abstract.casefold() in {"none", "null", "n/a", "not available"}


def load_and_validate(refined_path: Path, result_path: Path,
                      start_date: date, end_date: date) -> tuple[list[dict], list[dict]]:
    papers = [json.loads(line) for line in refined_path.read_text(encoding="utf-8").splitlines()
              if line.strip()]
    results = json.loads(result_path.read_text(encoding="utf-8"))
    if not papers or not isinstance(results, list) or len(results) != len(papers):
        raise ValueError(f"Incomplete evaluation: {len(results) if isinstance(results, list) else 'invalid'} "
                         f"results for {len(papers)} papers")
    source_by_key = {paper_key(paper): paper for paper in papers}
    if len(source_by_key) != len(papers):
        raise ValueError("Duplicate source titles/dates: resolve corpus duplicates before finalizing")
    result_keys = [paper_key(result.get("paper") or {}) for result in results]
    if Counter(result_keys) != Counter(source_by_key.keys()):
        missing = sorted(set(source_by_key) - set(result_keys))
        unexpected = sorted(set(result_keys) - set(source_by_key))
        raise ValueError(f"Result/title coverage mismatch; missing={missing[:3]}, unexpected={unexpected[:3]}")
    for result, key in zip(results, result_keys):
        source = source_by_key[key]
        if not start_date <= date.fromisoformat(key[1]) <= end_date:
            raise ValueError(f"Paper date outside the requested interval: {key}")
        paper = result["paper"]
        raw_data = paper.get("raw_data") or {}
        if paper_key(raw_data) != key:
            raise ValueError(f"Raw metadata title/date differs from the evaluated paper: {key}")
        for field in ("authors", "abstract"):
            expected = source.get(field, [] if field == "authors" else "")
            for data in (paper, raw_data):
                if data.get(field, [] if field == "authors" else "") != expected:
                    raise ValueError(f"Stale evaluation {field}: {key}")
        if comparable_metadata(raw_data) != comparable_metadata(source):
            raise ValueError(f"Evaluation contains stale source metadata: {key}")
        if result.get("recommendation_tier") not in TIERS:
            raise ValueError(f"Unknown recommendation tier: {result.get('recommendation_tier')}")
        score = float(result.get("total_score", 0))
        if not math.isfinite(score) or not 0 <= score <= 10:
            raise ValueError(f"Invalid score {score}: {key}")
        if missing_abstract(source):
            result["input_quality_warning"] = (
                "Source abstract unavailable or too short; assessment based on limited metadata."
            )
        # Canonicalize dates only in the temporary report input, not source files.
        paper["date"] = raw_data["date"] = key[1]
    return papers, results


def preserve_existing(path: Path, run_dir: Path) -> None:
    if path.exists():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
        backup = run_dir / "previous" / f"{path.stem}_{digest}{path.suffix}"
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            shutil.copy2(path, backup)


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def finalize(args: argparse.Namespace, root: Path = ROOT) -> dict:
    root = root.resolve()
    end_date = date.fromisoformat(args.date)
    start_date = date.fromisoformat(args.start_date)
    if start_date > end_date or not 1 <= args.issue <= 999:
        raise ValueError("Invalid publication interval or three-digit issue number")
    theme_lines = [str(args.theme_line1).strip(), str(args.theme_line2).strip()]
    if any(not line or any(char in line for char in "\r\n《》") for line in theme_lines):
        raise ValueError("Each theme line must be nonempty and contain no newlines or title brackets")
    compact_date = end_date.strftime("%Y%m%d")
    refined = root / "getfiles" / f"all_papers_{end_date}_enriched_ror_refined.jsonl"
    result_path = root / "LLM_Results" / f"LLM_results_{compact_date}.json"
    papers, results = load_and_validate(refined, result_path, start_date, end_date)
    run_dir = Path(args.run_dir) if args.run_dir else Path("tmps") / f"pipeline_{compact_date}"
    if not run_dir.is_absolute():
        run_dir = root / run_dir
    run_dir.mkdir(parents=True, exist_ok=True)
    report_input = run_dir / "report_input.json"
    atomic_text(report_input, json.dumps(results, ensure_ascii=False, indent=2))

    # Import the established local renderer, without its optional API title step.
    sys.path.insert(0, str(ROOT / "LLM_eval"))
    sys.path.insert(0, str(ROOT / "scripts"))
    from Summary import ReportGenerator
    from generate_score_histograms import score_distribution, render_histogram

    distribution = score_distribution(results)
    scored_count = sum(result.get("domain") != "域外局限" for result in results)
    if sum(count for _, count in distribution) != scored_count:
        raise ValueError("Histogram bins omit scored papers; check scores including the 10.0 endpoint")
    draft_dir = run_dir / "report"
    draft_dir.mkdir(parents=True, exist_ok=True)
    generated = ReportGenerator(str(draft_dir)).generate_from_json(
        str(report_input), source_statistics=True, render_histogram=False,
    )
    if generated["statistics"]["total"] != len(papers) or not generated["statistics_text"]:
        raise ValueError("Report generation did not produce complete source statistics")
    expected_tiers = Counter(result["recommendation_tier"] for result in results)
    if generated["tiers"] != {tier: expected_tiers[tier] for tier in TIERS}:
        raise ValueError("Report tier counts do not match the evaluation")

    missing_count = sum(missing_abstract(paper) for paper in papers)
    located_count = sum(any(author.get("ror_country") for author in paper.get("author_details", []))
                        for paper in papers)
    note = (f"> 第 {args.issue:03d} 期 · 文献日期：{start_date}—{end_date}（含首尾）。"
            f"共检索并评估 {len(papers)} 篇；作者与机构信息来自原始来源及 ROR 匹配。"
            f"{missing_count} 篇未取得足够摘要，相关条目已标注为仅供初筛；"
            f"{located_count} 篇取得地区信息。作者指标未参与本期来源统计。")
    rechecks_path = run_dir / "historical_rechecks.json"
    if rechecks_path.exists():
        recheck_count = len(json.loads(rechecks_path.read_text(encoding="utf-8")))
        note += (f"\n\n> 本期日期包括预印本版本发布日；另有 {recheck_count} 篇历史期刊论文补全了摘要，"
                 "单独用于数据库更新。地区图与评分统计排除域外局限条目。")
    overview = "## 📊 本周概览\n\n"
    markdown = Path(generated["markdown_path"]).read_text(encoding="utf-8")
    if markdown.count(overview) != 1:
        raise ValueError("Expected exactly one overview section in the generated report")
    markdown = f"《{''.join(theme_lines)}》\n\n" + markdown.replace(overview, overview + note + "\n\n", 1)
    selected_count = sum(expected_tiers[tier] for tier in TIERS[:4])
    entries = re.findall(r"^### (?!🌍|🏢|📊)(.+)$", markdown, flags=re.MULTILINE)
    selected_titles = Counter(normalized_title(result["paper"]["title"])
                              for result in results if result["recommendation_tier"] in TIERS[:4])
    # Domain headings also use ###; count only headings matching corpus titles.
    corpus_titles = source_by_title(papers)
    report_titles = Counter(normalized_title(title) for title in entries
                            if normalized_title(title) in corpus_titles)
    if report_titles != selected_titles or sum(report_titles.values()) != selected_count:
        raise ValueError("Selected paper title/count mismatch in Markdown")

    report_target = root / "LLM_Results" / f"report_{compact_date}.md"
    histogram_target = root / "Imgs" / "visulize_img" / "statistics" / f"{end_date}_score_histogram.png"
    histogram_draft = run_dir / f"{end_date}_score_histogram.png"
    render_histogram(distribution, histogram_draft)
    if not histogram_draft.exists() or histogram_draft.stat().st_size == 0:
        raise ValueError("Dated histogram was not generated")
    for target in (report_target, histogram_target):
        preserve_existing(target, run_dir)
    atomic_text(report_target, markdown)
    histogram_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(histogram_draft, histogram_target)
    audit = {
        "issue": args.issue, "date": str(end_date), "start_date": str(start_date),
        "theme_lines": theme_lines, "papers": len(papers), "selected_papers": selected_count,
        "missing_abstracts": missing_count, "papers_with_country": located_count,
        "recommendation_distribution": dict(expected_tiers), "scored_papers": scored_count,
        "score_distribution": dict(distribution), "report": str(report_target),
        "histogram": str(histogram_target), "result": str(result_path), "refined": str(refined),
        "completed_at": datetime.now().isoformat(),
    }
    atomic_text(run_dir / "report_finalization.json", json.dumps(audit, ensure_ascii=False, indent=2))
    return audit


def source_by_title(papers: list[dict]) -> set[str]:
    return {normalized_title(paper["title"]) for paper in papers}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--date", required=True, help="Issue date/end date, YYYY-MM-DD")
    parser.add_argument("--start-date", required=True, help="Inclusive publication start date, YYYY-MM-DD")
    parser.add_argument("--issue", required=True, type=int)
    parser.add_argument("--theme-line1", required=True)
    parser.add_argument("--theme-line2", required=True)
    parser.add_argument("--run-dir", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(finalize(args), ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(1, f"Report finalization failed: {error}\n")


if __name__ == "__main__":
    main()
