#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Merge two JSONL files, deduplicating by title.

Files merged:
  - getfiles/tmp/all_papers_2026-07-04_enriched.jsonl  (read first, generally richer)
  - getfiles/all_papers_2026-07-04_enriched.jsonl

On duplicate title the more-enriched record is kept, scored by:
  1. has_senior_researcher == True
  2. senior_author_count (higher is better)
  3. number of author_details entries with non-null h_index
Ties keep the first-seen record (tmp is read first).
"""
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
TMP_FILE = os.path.join(BASE, "getfiles", "tmp", "all_papers_2026-07-04_enriched.jsonl")
MAIN_FILE = os.path.join(BASE, "getfiles", "all_papers_2026-07-04_enriched.jsonl")
OUT_FILE = os.path.join(BASE, "getfiles", "all_papers_2026-07-04_enriched_merged.jsonl")


def norm_title(t):
    # strip surrounding whitespace, lowercase, and drop a trailing period
    # (the two sources inconsistently add/remove a final ".")
    return (t or "").strip().lower().rstrip(".").rstrip()


def enrichment_score(rec):
    """Higher means better enriched."""
    score = 0
    if rec.get("has_senior_researcher"):
        score += 1000
    score += int(rec.get("senior_author_count") or 0) * 10
    for a in rec.get("author_details") or []:
        if a.get("h_index") is not None:
            score += 1
    return score


def read_jsonl(path):
    recs = []
    if not os.path.exists(path):
        print(f"[warn] not found: {path}")
        return recs
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"[warn] bad json at {path}:{i} -> {e}")
    return recs


def main():
    tmp_recs = read_jsonl(TMP_FILE)
    main_recs = read_jsonl(MAIN_FILE)
    print(f"tmp  : {len(tmp_recs)} records")
    print(f"main : {len(main_recs)} records")

    seen = {}   # norm_title -> index in order
    order = []  # output records, first-seen order
    dup_count = 0

    def add(rec):
        nonlocal dup_count
        key = norm_title(rec.get("title"))
        if not key:
            # No title: cannot dedup, keep as-is.
            order.append(rec)
            return
        if key not in seen:
            seen[key] = len(order)
            order.append(rec)
        else:
            dup_count += 1
            idx = seen[key]
            if enrichment_score(rec) > enrichment_score(order[idx]):
                order[idx] = rec  # replace with richer record

    for r in tmp_recs:
        add(r)
    for r in main_recs:
        add(r)

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        for rec in order:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"duplicates resolved: {dup_count}")
    print(f"output: {OUT_FILE}")
    print(f"total : {len(order)} records")


if __name__ == "__main__":
    main()
