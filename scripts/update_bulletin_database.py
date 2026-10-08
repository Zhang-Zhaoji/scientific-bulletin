"""Backfill complete weekly outputs safely, preserving the bundled databases.

Example (read-only):
    python -B scripts/update_bulletin_database.py --through-date 2026-10-04 --dry-run

The update uses SQLite backups, a staged transaction, input/result reconciliation,
and integrity checks before replacing either published database. Existing nonempty
metadata and IDs are preserved. Explicit abstract rechecks and verified bioRxiv
revisions may refresh scores, with an audit. Conference datasets are excluded.
"""
from __future__ import annotations

import argparse
import collections
from contextlib import closing
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sql_scripts.build_sqlite import (  # noqa: E402
    align_list, as_list, clean_text, clean_text_list, is_missing_text, normalize_country_name,
    parse_work_details, resolved_author_institutions, ensure_affiliation_schema,
)
from sql_scripts.build_slim_db import build_slim_db, verify_slim_db  # noqa: E402

DOMAINS = {"核心域", "域外高影响", "域外局限"}
WEEK_FILE = re.compile(r"all_papers_(\d{4}-\d{2}-\d{2})_enriched_ror_refined\.jsonl$")
LINKS = {
    "article_authors": ("article_id", "author_id"),
    "author_institutions": ("author_id", "institution_id"),
    "article_institutions": ("article_id", "institution_id"),
    "article_countries": ("article_id", "country_id"),
    "article_themes": ("article_id", "theme_id"),
    "article_subthemes": ("article_id", "subtheme_id"),
    "article_crosstags": ("article_id", "tag_id"),
}


def readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def fingerprint(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalized_title(value) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("An input or LLM result has no title")
    return re.sub(r"\s+", "", value)


def normalized_doi(value) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", text)


def verify_same_article(existing: dict, incoming: dict, *, allow_url: bool = False) -> dict:
    """Require a shared stable identifier and reject contradictory identifiers."""
    old_doi, new_doi = normalized_doi(existing.get("doi")), normalized_doi(incoming.get("doi"))
    old_pmid, new_pmid = str(existing.get("pmid") or "").strip(), str(incoming.get("pmid") or "").strip()
    if (old_doi and new_doi and old_doi != new_doi) or (old_pmid and new_pmid and old_pmid != new_pmid):
        raise ValueError(f"Conflicting identifiers for title {incoming['title']!r}: "
                         f"existing DOI/PMID={old_doi}/{old_pmid}, incoming={new_doi}/{new_pmid}")
    matched = []
    if old_doi and old_doi == new_doi:
        matched.append("doi")
    if old_pmid and old_pmid == new_pmid:
        matched.append("pmid")
    if allow_url:
        normalize_url = lambda value: re.sub(r"^https?://", "", str(value or "").strip()).rstrip("/")
        old_url, new_url = normalize_url(existing.get("url")), normalize_url(incoming.get("url"))
        if old_url and old_url == new_url:
            matched.append("source_url")
    if not matched:
        raise ValueError(f"Cannot verify same-paper identity for {incoming['title']!r}; "
                         "a shared DOI or PMID is required for reevaluation")
    return {"matched_on": matched, "doi": new_doi or old_doi, "pmid": new_pmid or old_pmid}


def is_posted_revision(paper: dict) -> bool:
    evidence = paper.get("date_evidence") or {}
    try:
        version = int(paper.get("version") or evidence.get("version") or 0)
    except (ValueError, TypeError):
        return False
    return (str(paper.get("source", "")).lower() == "biorxiv" and version > 1
            and evidence.get("field") == "bioRxiv API record date"
            and evidence.get("value") == paper.get("date"))


def load_rechecks(path: Path | None) -> list[tuple[dict, dict]]:
    if path is None:
        return []
    results = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(results, list):
        raise ValueError("--rechecks must contain a list of complete LLM result records")
    pairs, seen = [], set()
    for result in results:
        paper = result.get("paper", {}).get("raw_data", {})
        title = normalized_title(paper.get("title"))
        score = result.get("total_score")
        if title in seen or result.get("domain") not in DOMAINS:
            raise ValueError("Duplicate or invalid LLM record in --rechecks")
        if not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 10:
            raise ValueError(f"Invalid recheck score: {score}")
        if result["domain"] == "核心域" and not clean_text(result.get("primary_category")):
            raise ValueError("Missing core category in --rechecks")
        if not normalized_doi(paper.get("doi")) and not paper.get("pmid"):
            raise ValueError(f"Recheck requires DOI or PMID: {paper['title']}")
        if is_missing_text(paper.get("abstract")) or len(str(paper["abstract"]).strip()) < 50:
            raise ValueError(f"Recheck has no recovered substantive abstract: {paper['title']}")
        seen.add(title)
        pairs.append((paper, result))
    return pairs


def snapshot(conn: sqlite3.Connection) -> dict:
    tables = [row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )]
    integrity = conn.execute("PRAGMA integrity_check").fetchall()
    foreign_keys = conn.execute("PRAGMA foreign_key_check").fetchall()
    if integrity != [("ok",)] or foreign_keys:
        raise RuntimeError(f"Database integrity failed: {integrity}; FK errors: {foreign_keys[:5]}")
    return {
        "counts": {table: conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                   for table in tables},
        "date_range": list(conn.execute("SELECT MIN(pub_date), MAX(pub_date) FROM articles").fetchone()),
        "integrity_check": "ok", "foreign_key_errors": 0,
    }


def load_week(path: Path, results_path: Path, through_date: str) -> list[tuple[dict, dict]]:
    papers = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    results = json.loads(results_path.read_text(encoding="utf-8"))
    if not isinstance(results, list) or len(papers) != len(results) or not papers:
        raise ValueError(f"Incomplete input/result pair: {path.name}, {results_path.name}")
    result_map = {}
    for result in results:
        title = normalized_title(result.get("paper", {}).get("raw_data", {}).get("title"))
        if title in result_map:
            raise ValueError(f"Repeated LLM title in {results_path.name}: {title[:80]}")
        if result.get("domain") not in DOMAINS:
            raise ValueError(f"Invalid LLM domain in {results_path.name}: {result.get('domain')}")
        score = result.get("total_score")
        if not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 10:
            raise ValueError(f"Invalid LLM score in {results_path.name}: {score}")
        if result["domain"] == "核心域" and not clean_text(result.get("primary_category")):
            raise ValueError(f"Missing core category in {results_path.name}")
        result_map[title] = result
    pairs, seen = [], set()
    for paper in papers:
        title = normalized_title(paper.get("title"))
        if title in seen or title not in result_map:
            raise ValueError(f"Duplicate or unmatched input title in {path.name}: {title[:80]}")
        seen.add(title)
        result = result_map[title]
        article = parse_work_details(paper, result)[0]
        if article["pub_date"] and article["pub_date"] > through_date:
            raise ValueError(f"Future/out-of-range publication in {path.name}: {article['pub_date']}")
        pairs.append((paper, result))
    if seen != set(result_map):
        raise ValueError(f"Input/LLM title sets differ: {path.name}")
    return pairs


def discover(coverage: str | None, through_date: str) -> tuple[list[dict], list[str]]:
    weeks, warnings = [], []
    for path in sorted((ROOT / "getfiles").glob("all_papers_*_enriched_ror_refined.jsonl")):
        match = WEEK_FILE.fullmatch(path.name)
        if not match:
            continue
        date = match.group(1)
        if date > through_date or (coverage and date <= coverage and date != through_date):
            continue
        candidates = sorted((ROOT / "LLM_Results").glob(f"LLM_results_{date.replace('-', '')}*.json"))
        exact = ROOT / "LLM_Results" / f"LLM_results_{date.replace('-', '')}.json"
        candidates.sort(key=lambda item: (item == exact, item.name), reverse=True)
        pair = None
        failures = []
        for result_path in candidates:
            try:
                records = load_week(path, result_path, through_date)
                pair = {"date": date, "input": path, "results": result_path, "records": records}
                break
            except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
                failures.append(f"{result_path.name}: {error}")
        if pair is None:
            raise ValueError(f"No complete aligned results for {path.name}: {failures or 'no result file'}")
        weeks.append(pair)
        warnings.extend(failures)
    return weeks, warnings


def scalar(value):
    if isinstance(value, (list, tuple)):
        return "; ".join(str(item) for item in value if item is not None) or None
    return value


class Importer:
    """Use stable keys and explicit link sets; never match unrelated NULL keys."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        ensure_affiliation_schema(conn)
        self.stats = collections.Counter()
        self.score_updates = []
        self.reevaluations = []
        self.recheck_links = []
        self.target_links = []
        self.title_aliases = []
        self.tables = {}
        for table, keys in {"articles": ("title",), "countries": ("standard_name",),
                            "institutions": ("ror_id", "normalized_name", "name"),
                            "themes": ("name",), "subthemes": ("name",), "crosstags": ("name",)}.items():
            self.tables[table] = {key: {value: ident for ident, value in conn.execute(
                f'SELECT id, "{key}" FROM "{table}" WHERE "{key}" IS NOT NULL')}
                for key in keys}
        self.author_records = {row[0]: dict(zip(
            ("id", "name", "orcid", "h_index", "citations", "is_senior_researcher"), row))
            for row in conn.execute("SELECT id,name,orcid,h_index,citations,is_senior_researcher FROM authors")}
        self.author_orcids = {row["orcid"]: ident for ident, row in self.author_records.items() if row["orcid"]}
        self.author_names = collections.defaultdict(list)
        for ident, row in self.author_records.items():
            self.author_names[row["name"]].append(ident)
        self.links = {table: set(conn.execute(f'SELECT {a},{b} FROM "{table}"'))
                      for table, (a, b) in LINKS.items()}
        self.author_institutions = collections.defaultdict(set)
        self.article_authors = collections.defaultdict(set)
        for author, institution in self.links["author_institutions"]:
            self.author_institutions[author].add(institution)
        for article, author in self.links["article_authors"]:
            self.article_authors[article].add(author)

    def fill(self, table: str, ident: int, values: dict):
        values = {key: scalar(value) for key, value in values.items() if value is not None}
        for key, value in values.items():
            self.conn.execute(f'UPDATE "{table}" SET "{key}"=? '
                              f'WHERE id=? AND ("{key}" IS NULL OR "{key}"=\'\')', (value, ident))

    def entity(self, table: str, values: dict, preferred_key: str | None = None) -> int:
        indexes = self.tables[table]
        ordered = ([preferred_key] if preferred_key else []) + [key for key in indexes if key != preferred_key]
        ident = next((indexes[key].get(values.get(key)) for key in ordered
                      if key in indexes and values.get(key) and indexes[key].get(values[key])), None)
        if table=='institutions' and values.get('ror_id'):
            ident=indexes['ror_id'].get(values['ror_id'])
            if ident is None:
                for key in ('normalized_name','name'):
                    candidate=indexes[key].get(values.get(key))
                    if candidate is None:continue
                    old_id,old_country=self.conn.execute('SELECT ror_id,country_id FROM institutions WHERE id=?',(candidate,)).fetchone()
                    if old_id is None and (old_country is None or old_country==values.get('country_id')):
                        ident=candidate;break
            if ident is None and values.get('normalized_name') in indexes['normalized_name']:
                values=dict(values,normalized_name=None)
            elif ident is not None and values.get('normalized_name') and indexes['normalized_name'].get(values['normalized_name']) not in (None,ident):
                values=dict(values,normalized_name=None)
        if ident is None:
            keys = list(values)
            cursor = self.conn.execute(
                f'INSERT INTO "{table}" ({",".join(keys)}) VALUES ({",".join("?" for _ in keys)})',
                [scalar(values[key]) for key in keys],
            )
            ident = cursor.lastrowid
            self.stats[f"{table}_inserted"] += 1
        else:
            self.fill(table, ident, values)
            self.stats[f"{table}_reused"] += 1
        for key in indexes:
            if values.get(key):
                indexes[key][values[key]] = ident
        return ident

    def link(self, table: str, left: int, right: int):
        pair = (left, right)
        if pair not in self.links[table]:
            a, b = LINKS[table]
            self.conn.execute(f'INSERT INTO "{table}" ({a},{b}) VALUES (?,?)', pair)
            self.links[table].add(pair)
            self.stats[f"{table}_inserted"] += 1
            if table == "author_institutions":
                self.author_institutions[left].add(right)
            elif table == "article_authors":
                self.article_authors[left].add(right)

    def country(self, value) -> int | None:
        if is_missing_text(value):
            return None
        name = normalize_country_name(value)
        if not name:
            return None
        return self.entity("countries", {"standard_name": name, "country_name": name})

    def author(self, article: int, info: dict, institution_ids: set[int], preferred_id: int | None = None) -> int:
        name = clean_text(info.get("name"))
        orcid = clean_text(info.get("orcid"))
        compatible = lambda ident: not (orcid and self.author_records[ident]["orcid"]
                                       and orcid != self.author_records[ident]["orcid"])
        ident = self.author_orcids.get(orcid) if orcid else None
        if ident is None and preferred_id is not None and compatible(preferred_id):
            ident=preferred_id
        if ident is None:
            ident = next((candidate for candidate in self.article_authors[article]
                          if self.author_records[candidate]["name"] == name and compatible(candidate)), None)
        if ident is None and institution_ids:
            ident = next((candidate for candidate in self.author_names[name]
                          if compatible(candidate) and self.author_institutions[candidate] & institution_ids), None)
        values = {key: info.get(key) for key in ("h_index", "citations", "is_senior_researcher")}
        values.update(name=name, orcid=orcid)
        if ident is None:
            ident = self.conn.execute(
                "INSERT INTO authors(name,orcid,h_index,citations,is_senior_researcher) VALUES (?,?,?,?,?)",
                tuple(values[key] for key in ("name", "orcid", "h_index", "citations", "is_senior_researcher")),
            ).lastrowid
            self.author_records[ident] = dict(values, id=ident)
            self.author_names[name].append(ident)
            self.stats["authors_inserted"] += 1
        else:
            self.fill("authors", ident, values)
            self.stats["authors_reused"] += 1
        if orcid:
            self.author_orcids[orcid] = ident
            self.author_records[ident]["orcid"] = orcid
        self.link("article_authors", article, ident)
        for institution in institution_ids:
            self.link("author_institutions", ident, institution)
        return ident

    def resolve_existing_article(self, paper: dict, *, recheck: bool) -> dict | None:
        fields = ("id", "title", "doi", "pmid", "pub_date", "score", "url")
        row = self.conn.execute("SELECT id,title,doi,pmid,pub_date,score,url FROM articles WHERE title=?",
                                (paper["title"],)).fetchone()
        if row is not None:
            return dict(zip(fields, row))
        if not recheck:
            return None
        clauses, parameters = [], []
        if normalized_doi(paper.get("doi")):
            clauses.append("LOWER(TRIM(doi))=?")
            parameters.append(normalized_doi(paper["doi"]))
        if paper.get("pmid"):
            clauses.append("CAST(pmid AS TEXT)=?")
            parameters.append(str(paper["pmid"]).strip())
        rows = self.conn.execute("SELECT id,title,doi,pmid,pub_date,score,url FROM articles WHERE "
                                 + " OR ".join(clauses), parameters).fetchall()
        if not rows:
            return None
        if len(rows) != 1:
            raise ValueError(f"Recheck must identify exactly one existing article: {paper['title']!r}; "
                             f"matched {len(rows)} rows")
        return dict(zip(fields, rows[0]))

    def ingest(self, paper: dict, result: dict, *, target: bool = False, recheck: bool = False):
        article_info, _, _, countries, themes, subthemes, tags = parse_work_details(paper, result)
        revision = target and is_posted_revision(paper)
        existing = self.resolve_existing_article(paper, recheck=recheck or revision) if target or recheck else None
        identity = verify_same_article(existing, paper, allow_url=not (recheck or revision)) if existing is not None else None
        if recheck and existing is None:
            raise ValueError(f"No previously stored article identified for recheck: {paper['title']}")
        if existing is not None and (recheck or revision):
            # A punctuation/name variant must use the existing record's ID and title.
            article_info["title"] = existing["title"]
        article = self.entity("articles", article_info)
        if existing is not None and existing["title"] != paper["title"]:
            self.title_aliases.append({"article_id": article, "source_title": paper["title"],
                                       "stored_title": existing["title"], "identity": identity,
                                       "reason": "historical_abstract_recheck" if recheck else "posted_biorxiv_revision"})
            self.tables["articles"]["title"][paper["title"]] = article
        if target:
            self.target_links.append((paper, result, article))
        reevaluate = recheck or revision
        if reevaluate and existing is not None:
            audit = {"article_id": article, "source_title": paper["title"], "stored_title": existing["title"],
                     "reason": "historical_abstract_recheck" if recheck else "posted_biorxiv_revision",
                     "identity": identity, "preserved_pub_date": existing["pub_date"],
                     "source_date": paper.get("date"), "version": paper.get("version"),
                     "old_score": existing["score"], "new_score": result["total_score"]}
            self.reevaluations.append(audit)
            if existing["score"] is None or not math.isclose(existing["score"], result["total_score"],
                                                             rel_tol=0, abs_tol=1e-9):
                self.conn.execute("UPDATE articles SET score=? WHERE id=?", (result["total_score"], article))
                self.score_updates.append(audit)
                self.stats["article_scores_updated"] += 1
            if recheck:
                self.recheck_links.append((paper, result, article))
        for country in countries:
            country_id = self.country(country["name"])
            if country_id:
                self.link("article_countries", article, country_id)
        details = [dict(info) for info in as_list(paper.get("author_details")) if isinstance(info, dict)]
        represented = {clean_text(info.get("name")) for info in details}
        for author in as_list(paper.get("authors")):
            name = clean_text(author.get("name") if isinstance(author, dict) else author)
            if name and name not in represented:
                details.append({"name": name})
                represented.add(name)
        for info in details:
            if not clean_text(info.get("name")):
                continue
            institution_ids = set()
            source_evidence=collections.defaultdict(list)
            for row in resolved_author_institutions(info):
                name = row['name']
                country_id = self.country(row['country_name'])
                institution = self.entity("institutions", {
                    "name": name, "normalized_name": row['normalized_name'],
                    "raw_affiliation": scalar(row['raw_affiliation']), "country_id": country_id,
                    "ror_id":row.get('ror_id'),
                }, preferred_key="ror_id" if row.get('ror_id') else "normalized_name")
                institution_ids.add(institution)
                source_evidence[institution].append({'affiliation':row['raw_affiliation'],'source':info.get('source'),
                                                    'source_url':info.get('source_url') or paper.get('url'),
                                                    'ror_id':row.get('ror_id')})
                self.link("article_institutions", article, institution)
                if country_id:
                    self.link("article_countries", article, country_id)
            author=self.author(article, info, institution_ids)
            for institution in institution_ids:
                self.conn.execute('''INSERT INTO article_author_institutions(article_id,author_id,institution_id,evidence_json)
                                     VALUES(?,?,?,?) ON CONFLICT(article_id,author_id,institution_id)
                                     DO UPDATE SET evidence_json=excluded.evidence_json''',
                                  (article,author,institution,json.dumps(source_evidence[institution],ensure_ascii=False,separators=(',',':'))))
        for entities, entity_table, link_table in (
            (themes, "themes", "article_themes"),
            (subthemes, "subthemes", "article_subthemes"),
            (tags, "crosstags", "article_crosstags"),
        ):
            for entity in entities:
                if clean_text(entity.get("name")):
                    self.link(link_table, article, self.entity(entity_table, entity))


def backup_database(source: Path, destination: Path):
    with closing(readonly(source)) as original, closing(sqlite3.connect(destination)) as copied:
        original.backup(copied)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--through-date", required=True, type=dt.date.fromisoformat)
    parser.add_argument("--dry-run", action="store_true", help="Validate and print plan; write nothing")
    parser.add_argument("--run-dir", type=Path, help="Logs, staged DBs, and database_backup directory")
    parser.add_argument("--rechecks", type=Path, help="Complete LLM records for explicit historical abstract rechecks")
    args = parser.parse_args()
    os.chdir(ROOT)
    through_date = args.through_date.isoformat()
    run_dir = (args.run_dir or ROOT / "tmps" / f"pipeline_{args.through_date:%Y%m%d}").resolve()
    if not run_dir.is_relative_to(ROOT):
        raise ValueError("--run-dir must be inside this repository")
    full = ROOT / "data/literature.db"
    slim = ROOT / "docs/assets/data/literature_slim.db"
    if not full.exists():
        raise FileNotFoundError(full)
    with closing(readonly(full)) as original:
        before = snapshot(original)
        titles_before = {row[0] for row in original.execute("SELECT title FROM articles")}
        cursor = original.execute("SELECT * FROM articles")
        score_column = [column[0] for column in cursor.description].index("score")
        old_articles = {row[0]: row for row in cursor}
    coverage = before["date_range"][1]
    weeks, warnings = discover(coverage, through_date)
    rechecks = load_rechecks(args.rechecks)
    unseen = set()
    week_summaries = []
    for week in weeks:
        missing = {paper["title"] for paper, _ in week["records"]} - titles_before
        week_summaries.append({"date": week["date"], "input": str(week["input"]),
                               "results": str(week["results"]), "records": len(week["records"]),
                               "missing_existing_titles": len(missing),
                               "new_unique_titles": len(missing - unseen)})
        unseen.update(missing)
    target_ready = any(week["date"] == through_date for week in weeks)
    plan = {"through_date": through_date, "before": before, "weeks": week_summaries,
            "expected_new_articles": len(unseen), "target_ready": target_ready, "warnings": warnings,
            "backups_directory": str(run_dir / "database_backup"), "dry_run": args.dry_run,
            "rechecks_file": str(args.rechecks) if args.rechecks else None, "historical_rechecks": len(rechecks)}
    print(json.dumps(plan, ensure_ascii=False, indent=2), flush=True)
    if args.dry_run:
        return 0
    if not target_ready:
        raise RuntimeError(f"Target week {through_date} is missing or incomplete; no databases changed")
    for database in (full, slim):
        for suffix in ("-wal", "-journal"):
            sidecar = Path(str(database) + suffix)
            if sidecar.exists() and sidecar.stat().st_size:
                raise RuntimeError(f"Active SQLite sidecar exists; close database writers first: {sidecar}")
    run_dir.mkdir(parents=True, exist_ok=True)
    backup_dir = run_dir / "database_backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    token = dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    full_backup = backup_dir / f"literature_{token}.db"
    slim_backup = backup_dir / f"literature_slim_{token}.db"
    staged_full = run_dir / f"literature_updated_{token}.db"
    staged_slim = run_dir / f"literature_slim_updated_{token}.db"
    initial_fingerprints = (fingerprint(full), fingerprint(slim))
    backup_database(full, full_backup)
    if slim.exists():
        backup_database(slim, slim_backup)
    shutil.copy2(full_backup, staged_full)
    with closing(sqlite3.connect(staged_full)) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        importer = Importer(conn)
        for week in weeks:
            for paper, result in week["records"]:
                importer.ingest(paper, result, target=week["date"] == through_date)
            print(f"Imported {week['date']}: {len(week['records'])} reconciled records", flush=True)
        for paper, result in rechecks:
            importer.ingest(paper, result, recheck=True)
        # Verify each old nonempty article value and stable article IDs before commit.
        current = {row[0]: row for row in conn.execute("SELECT * FROM articles")}
        allowed_score_changes = {audit["article_id"]: audit["new_score"] for audit in importer.score_updates}
        for ident, row in old_articles.items():
            def allowed(column, value):
                return (column == score_column and ident in allowed_score_changes
                        and value == allowed_score_changes[ident])
            if ident not in current or any(value not in (None, "") and value != current[ident][column]
                                           and not allowed(column, current[ident][column])
                                           for column, value in enumerate(row)):
                raise RuntimeError(f"An existing article changed unexpectedly: id={ident}")
        after = snapshot(conn)
        aliased_new_titles = {alias["source_title"] for alias in importer.title_aliases} & unseen
        expected_new_articles = len(unseen) - len(aliased_new_titles)
        if after["counts"]["articles"] != before["counts"]["articles"] + expected_new_articles:
            raise RuntimeError("Article-count reconciliation failed")
        for table, count in before["counts"].items():
            if after["counts"].get(table, 0) < count:
                raise RuntimeError(f"Existing rows were removed from {table}")
        for week in weeks:
            missing = [paper["title"] for paper, _ in week["records"]
                       if paper["title"] not in importer.tables["articles"]["title"]]
            if missing:
                raise RuntimeError(f"Database coverage failed for {week['date']}: {len(missing)} missing")
        if len({ident for _, _, ident in importer.target_links}) != len(importer.target_links):
            raise RuntimeError("Target corpus contains multiple records resolving to the same article ID")
        for paper, result, ident in importer.target_links:
            row = conn.execute("SELECT title,doi,pmid,score FROM articles WHERE id=?", (ident,)).fetchone()
            if row is None or (row[0] != paper["title"] and not verify_same_article(
                    {"doi": row[1], "pmid": row[2]}, paper)) or row[3] is None or not math.isclose(
                    row[3], result["total_score"], rel_tol=0, abs_tol=1e-9):
                raise RuntimeError(f"Target title/score reconciliation failed: {paper['title'][:100]}")
        for paper, result, ident in importer.recheck_links:
            current_row = conn.execute("SELECT doi,pmid,abstract,score FROM articles WHERE id=?", (ident,)).fetchone()
            verify_same_article({"doi": current_row[0], "pmid": current_row[1]}, paper)
            if len(str(current_row[2] or "").strip()) < 50 or not math.isclose(
                    current_row[3], result["total_score"], rel_tol=0, abs_tol=1e-9):
                raise RuntimeError(f"Historical abstract/score recheck failed: {paper['title']}")
        conn.commit()
    build_slim_db(staged_full, staged_slim)
    if not verify_slim_db(staged_full, staged_slim):
        raise RuntimeError("Staged slim database verification failed")
    with closing(readonly(staged_slim)) as conn:
        slim_after = snapshot(conn)
    if slim_after["counts"] != after["counts"]:
        raise RuntimeError("Full/slim table counts differ")
    if (fingerprint(full), fingerprint(slim)) != initial_fingerprints:
        raise RuntimeError("An original database changed concurrently; staged results retained, originals untouched")
    try:
        os.replace(staged_full, full)
        os.replace(staged_slim, slim)
    except BaseException:
        restore_full = run_dir / f"restore_full_{token}.db"
        shutil.copy2(full_backup, restore_full)
        os.replace(restore_full, full)
        if slim_backup.exists():
            restore_slim = run_dir / f"restore_slim_{token}.db"
            shutil.copy2(slim_backup, restore_slim)
            os.replace(restore_slim, slim)
        raise
    plan.update(status="complete", after=after, slim_after=slim_after,
                import_counts=dict(importer.stats), backups=[str(full_backup), str(slim_backup)],
                score_updates=importer.score_updates, reevaluations=importer.reevaluations,
                historical_rechecks_reconciled=len(importer.recheck_links), title_aliases=importer.title_aliases,
                reconciled_new_articles=expected_new_articles)
    plan["target_reconciliation"] = {"title_matches": next(len(week["records"]) for week in weeks
                                                           if week["date"] == through_date),
                                     "score_matches": next(len(week["records"]) for week in weeks
                                                           if week["date"] == through_date)}
    report = run_dir / "database_update.json"
    report.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Database update complete: {report}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
