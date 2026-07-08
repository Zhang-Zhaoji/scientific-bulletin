"""Orchestrate visualization generation for weekly reports and conference special issues.

Generates:
1. Score histograms from LLM result JSONs  (scripts/generate_score_histograms.py)
2. Weekly heatmap + pie HTMLs from JSONLs  (visualize/global_heatmap.py)
3. Conference treemaps / pies / wordcloud   (visualize/visualize_conf.py)

Usage:
  python scripts/visualize_pipeline.py                     # generate all, skip existing
  python scripts/visualize_pipeline.py --overwrite         # regenerate everything
  python scripts/visualize_pipeline.py --only histograms   # just score histograms
  python scripts/visualize_pipeline.py --only weekly       # just weekly charts
  python scripts/visualize_pipeline.py --only conference   # just conference charts
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VIZ_DIR = PROJECT_ROOT / "visualize"


SEP = "=" * 60


def _run(cmd: list[str], *, env_extra: dict[str, str] | None = None) -> bool:
    """Run a subprocess, return True on success."""
    env = {**os.environ, **(env_extra or {})}
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env, capture_output=True, text=True)
    if result.stdout.strip():
        print(result.stdout.rstrip())
    if result.returncode != 0:
        print(f"  [WARN] Command failed: {' '.join(cmd)}")
        if result.stderr.strip():
            print(f"  {result.stderr.rstrip()[:500]}")
        return False
    return True


# ── Score histograms ──

def generate_histograms(overwrite: bool = False) -> None:
    print(f"\n{SEP}")
    print("Generating score histograms")
    print(SEP)
    cmd = [sys.executable, "scripts/generate_score_histograms.py"]
    if overwrite:
        cmd.append("--overwrite")
    _run(cmd)


# ── Weekly heatmap + pie ──

def _extract_date(filename: str) -> str | None:
    m = re.search(r"(\d{4}-\d{2}-\d{2})", filename)
    return m.group(1) if m else None


def generate_weekly_charts(overwrite: bool = False) -> None:
    print(f"\n{SEP}")
    print("Generating weekly heatmap + pie charts")
    print(SEP)

    jsonl_dir = PROJECT_ROOT / "getfiles"
    jsonl_files = sorted(jsonl_dir.glob("all_papers_*_enriched_ror_refined.jsonl"))

    if not jsonl_files:
        print("  No enriched JSONL files found in getfiles/")
        return

    skipped = 0
    generated = 0
    for jsonl in jsonl_files:
        date = _extract_date(jsonl.name)
        if not date:
            continue

        heatmap = PROJECT_ROOT / "Imgs" / "visulize_img" / "globalHeatmap" / f"{date}_heatmap.html"
        pie = PROJECT_ROOT / "Imgs" / "visulize_img" / "countryPie" / f"{date}_pie.html"

        if not overwrite and heatmap.exists() and pie.exists():
            skipped += 1
            continue

        print(f"\n  [{date}] {jsonl.name}")
        env = {"PYTHONPATH": str(VIZ_DIR)}
        ok = _run(
            [sys.executable, "visualize/global_heatmap.py",
             "--jsonl", str(jsonl), "--date", date],
            env_extra=env,
        )
        generated += 1 if ok else 0

    print(f"\n  Summary: {generated} generated, {skipped} skipped")


# ── Conference visualizations ──

def generate_conference_charts(overwrite: bool = False) -> None:
    print(f"\n{SEP}")
    print("Generating conference visualizations")
    print(SEP)

    llm_files = sorted((PROJECT_ROOT / "LLM_Results").glob("LLM_results_ic*.json"))
    if not llm_files:
        print("  No conference LLM result files found (LLM_results_ic*.json)")
        return

    for llm in llm_files:
        # derive conference key, e.g. iclr2025 -> iclr2025_papers.jsonl
        stem = llm.stem.replace("LLM_results_", "")  # iclr2025, icml2025
        papers = PROJECT_ROOT / "getfiles" / f"{stem}_papers.jsonl"
        if not papers.exists():
            print(f"\n  [SKIP] {llm.name}: papers file not found ({papers.name})")
            continue

        # check if output already exists
        conf_key = stem.replace("2025", "_2025").replace("2026", "_2026")
        treemap = PROJECT_ROOT / "Imgs" / "conf_visualization" / conf_key / "all" / "institutions_treemap.png"
        if not overwrite and treemap.exists():
            print(f"\n  [SKIP] {stem}: visualizations already exist (use --overwrite to regenerate)")
            continue

        print(f"\n  [{stem}] LLM: {llm.name}, Papers: {papers.name}")
        _run(
            [sys.executable, "visualize/visualize_conf.py",
             "--llm", str(llm), "--papers", str(papers)],
        )

    # Conferences without LLM results (e.g. 2026) – can't regenerate, just note
    for papers in sorted((PROJECT_ROOT / "getfiles").glob("ic*_papers.jsonl")):
        stem = papers.stem.replace("_papers", "")
        llm = PROJECT_ROOT / "LLM_Results" / f"LLM_results_{stem}.json"
        if not llm.exists():
            print(f"\n  [NOTE] {stem}: no LLM results file ({llm.name}), skipping")


# ── Main ──

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate all visualization assets.")
    parser.add_argument("--overwrite", action="store_true", help="Regenerate existing visualizations.")
    parser.add_argument("--only", choices=["histograms", "weekly", "conference"],
                        help="Run only a specific visualization type.")
    args = parser.parse_args(argv)

    tasks = {
        "histograms": generate_histograms,
        "weekly": generate_weekly_charts,
        "conference": generate_conference_charts,
    }

    if args.only:
        tasks[args.only](overwrite=args.overwrite)
    else:
        for task in tasks.values():
            task(overwrite=args.overwrite)

    print("\nVisualization pipeline complete.")


if __name__ == "__main__":
    main()
