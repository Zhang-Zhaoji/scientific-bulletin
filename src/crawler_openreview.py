"""
Crawler for OpenReview conference papers (ICLR, NeurIPS, ICML, etc.)

Uses Selenium to bypass Cloudflare challenge on api2.openreview.net.
Requires: selenium, beautifulsoup4, chromedriver
Environment: OPEN_REVIEW_USER_NAME, OPEN_REVIEW_USER_PASSWORD in .env
"""
import os
import json
import time
import argparse
import datetime
from typing import List, Dict, Optional
from pathlib import Path

import jsonlines


def _load_env(env_path: str = '.env') -> Dict[str, str]:
    """Load .env file into dict (handles BOM and various encodings)."""
    env = {}
    if not os.path.exists(env_path):
        return env
    with open(env_path, 'r', encoding='utf-8-sig') as f:
        for line in f:
            line = line.strip()
            if line and '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip()
    return env


class OpenReviewCrawler:
    """Crawl conference papers from OpenReview via Selenium."""

    BASE_URL = 'https://api2.openreview.net'
    WEB_URL = 'https://openreview.net'

    # Known venue IDs format: {Conference}.cc/{Year}/Conference
    VENUE_IDS = {
        'ICLR': 'ICLR.cc/{year}/Conference',
        'NeurIPS': 'NeurIPS.cc/{year}/Conference',
        'ICML': 'ICML.cc/{year}/Conference',
    }

    def __init__(self, headless: bool = True):
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options

        chrome_options = Options()
        if headless:
            chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument(
            '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
        )

        self.driver = webdriver.Chrome(options=chrome_options)
        self._logged_in = False

    def login(self, username: str, password: str) -> bool:
        """Login to OpenReview via web form to get auth cookies."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        self.driver.get(f'{self.WEB_URL}/login')

        # Wait for login form to render (React SPA, may take time)
        try:
            email_input = WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.ID, 'email-input'))
            )
        except Exception:
            print(f"[ERROR] Login form not found after 20s")
            return False

        pass_input = self.driver.find_element(By.ID, 'password-input')
        email_input.send_keys(username)
        pass_input.send_keys(password)

        login_btn = self.driver.find_element(
            By.XPATH, '//button[contains(text(), "Login")]'
        )
        login_btn.click()

        # Wait for redirect after login
        try:
            WebDriverWait(self.driver, 15).until(
                lambda d: 'login' not in d.current_url.lower()
            )
            self._logged_in = True
            print(f"[OK] OpenReview login successful")
            return True
        except Exception:
            print(f"[ERROR] Login failed - still on login page after 15s")
            return False

    def _api_get(self, endpoint: str, params: Optional[Dict] = None) -> Optional[dict]:
        """Call OpenReview API by navigating to the URL (bypasses Cloudflare)."""
        from selenium.webdriver.common.by import By

        url = f'{self.BASE_URL}/{endpoint}'
        if params:
            query = '&'.join(f'{k}={v}' for k, v in params.items())
            url = f'{url}?{query}'

        self.driver.get(url)
        time.sleep(2)

        try:
            body = self.driver.find_element(By.TAG_NAME, 'body').text
            if body and body.strip().startswith('{'):
                return json.loads(body)
        except Exception:
            pass
        return None

    def fetch_papers(
        self,
        venue: str,
        year: int,
        fetch_affiliations: bool = False,
        max_affiliations: int = 0,
    ) -> List[Dict]:
        """
        Fetch all accepted papers from a conference venue.

        Args:
            venue: 'ICLR', 'NeurIPS', 'ICML', etc.
            year: Conference year (e.g. 2025)
            fetch_affiliations: If True, fetch author profiles for affiliations
            max_affiliations: Max number of authors to fetch affiliations for
                             (0 = all, useful for rate limiting)

        Returns:
            List of paper dicts compatible with the project's format
        """
        venue_template = self.VENUE_IDS.get(venue)
        if not venue_template:
            # Try custom venue format
            venue_id = venue
        else:
            venue_id = venue_template.format(year=year)

        source_name = f'{venue} {year}'
        print(f"\n[{source_name}] Venue ID: {venue_id}")

        # Fetch all papers with pagination
        all_notes = []
        offset = 0
        page_size = 1000

        while True:
            data = self._api_get('notes', {
                'content.venueid': venue_id,
                'limit': str(page_size),
                'offset': str(offset),
            })

            if not data:
                print(f"  [WARN] No data at offset {offset}")
                break

            notes = data.get('notes', [])
            if not notes:
                break

            all_notes.extend(notes)
            print(f"  Batch at offset {offset}: {len(notes)} papers (total: {len(all_notes)})")

            offset += len(notes)
            if len(notes) < page_size:
                break

        print(f"  Total papers: {len(all_notes)}")

        # Parse papers into project format
        papers = []
        author_ids_to_fetch = set()

        for note in all_notes:
            paper = self._parse_note(note, source_name, venue_id)
            if paper:
                papers.append(paper)
                if fetch_affiliations:
                    for aid in paper.get('author_ids', []):
                        author_ids_to_fetch.add(aid)

        # Fetch author affiliations
        if fetch_affiliations and author_ids_to_fetch:
            affiliations = self._fetch_affiliations_batch(
                author_ids_to_fetch, max_affiliations
            )
            # Attach affiliations to papers
            for paper in papers:
                paper['author_affiliations'] = []
                for aid in paper.get('author_ids', []):
                    if aid in affiliations:
                        paper['author_affiliations'].append(affiliations[aid])
                    else:
                        paper['author_affiliations'].append([])

        return papers

    def _parse_note(self, note: dict, source_name: str, venue_id: str) -> Optional[Dict]:
        """Parse an OpenReview note into project paper format."""
        try:
            content = note.get('content', {})

            # Extract fields (OpenReview v2 wraps values in {'value': ...})
            def get_val(key):
                v = content.get(key, {})
                if isinstance(v, dict):
                    return v.get('value', '')
                return v

            title = get_val('title')
            authors = get_val('authors') or []
            author_ids = get_val('authorids') or []
            abstract = get_val('abstract') or ''
            keywords = get_val('keywords') or []
            pdf_path = get_val('pdf') or ''
            venue = get_val('venue') or source_name
            tldr = get_val('TLDR') or ''

            # Forum URL
            forum_id = note.get('id', '')
            forum_url = f'{self.WEB_URL}/forum?id={forum_id}' if forum_id else ''

            # PDF URL
            pdf_url = f'{self.WEB_URL}{pdf_path}' if pdf_path else ''

            # Clean abstract
            abstract = ' '.join(abstract.split())

            return {
                'type': 'Conference Paper',
                'title': title,
                'authors': authors,
                'date': str(source_name.split()[-1]),  # Year as string
                'url': forum_url,
                'abstract': abstract,
                'doi': '',
                'source': source_name,
                'author_ids': author_ids,
                'keywords': keywords,
                'pdf_url': pdf_url,
                'venue': venue,
                'venue_id': venue_id,
                'forum_id': forum_id,
                'tldr': tldr,
            }
        except Exception as e:
            print(f"  [WARN] Failed to parse note: {e}")
            return None

    def _fetch_affiliations_batch(
        self, author_ids: set, max_count: int = 0
    ) -> Dict[str, List[Dict]]:
        """Fetch author profiles for affiliations in batches."""
        # Filter out emails and empty IDs (only keep ~profile IDs)
        valid_ids = [aid for aid in author_ids if aid and aid.startswith('~')]

        if max_count > 0:
            valid_ids = valid_ids[:max_count]

        total = len(valid_ids)
        print(f"\n  Fetching affiliations for {total} authors (batch mode)...")

        result = {}
        batch_size = 50  # OpenReview accepts comma-separated IDs

        for start in range(0, total, batch_size):
            batch = valid_ids[start:start + batch_size]
            ids_param = ','.join(batch)

            data = self._api_get('profiles', {'ids': ids_param})
            if data:
                profiles = data.get('profiles', [])
                for profile in profiles:
                    pid = profile.get('id', '')
                    content = profile.get('content', {})
                    history = content.get('history', [])
                    if isinstance(history, dict):
                        history = history.get('value', [])

                    affiliations = []
                    for h in history:
                        inst = h.get('institution', {})
                        if isinstance(inst, dict):
                            affiliations.append({
                                'name': inst.get('name', ''),
                                'domain': inst.get('domain', ''),
                                'start': h.get('start', ''),
                                'end': h.get('end', 'present'),
                            })
                    result[pid] = affiliations

            done = min(start + batch_size, total)
            if done % 200 == 0 or done == total:
                print(f"    Progress: {done}/{total} ({len(result)} profiles found)")

            time.sleep(0.5)  # Be polite between batches

        print(f"    Done: {len(result)}/{total} profiles fetched")
        return result

    def download_pdf(self, paper: Dict, output_dir: str = 'getfiles/pdfs') -> bool:
        """Download PDF for a paper (optional)."""
        pdf_url = paper.get('pdf_url', '')
        if not pdf_url:
            return False

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        forum_id = paper.get('forum_id', 'unknown')
        filepath = Path(output_dir) / f'{forum_id}.pdf'

        if filepath.exists():
            return True  # Already downloaded

        try:
            # Navigate to PDF URL in browser
            self.driver.get(pdf_url)
            time.sleep(3)

            # Check if it's a PDF page
            # Chrome headless can't easily save PDFs, so we use requests
            # with the session cookies
            import requests
            session = requests.Session()
            for c in self.driver.get_cookies():
                session.cookies.set(c['name'], c['value'])

            r = session.get(pdf_url, timeout=60)
            if r.status_code == 200 and 'application/pdf' in r.headers.get('Content-Type', ''):
                with open(filepath, 'wb') as f:
                    f.write(r.content)
                return True
        except Exception as e:
            print(f"    [WARN] PDF download failed for {forum_id}: {e}")

        return False

    def close(self):
        """Close the browser."""
        self.driver.quit()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def save_papers_jsonl(papers: List[Dict], filepath: str):
    """Save papers to JSONL file."""
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    with jsonlines.open(filepath, mode='w') as writer:
        writer.write_all(papers)
    print(f"[OK] Saved {len(papers)} papers to {filepath}")


def crawl_conference(
    venue: str,
    year: int,
    output_file: str,
    fetch_affiliations: bool = False,
    max_affiliations: int = 0,
    headless: bool = True,
) -> List[Dict]:
    """
    Crawl a conference and save results.

    Args:
        venue: 'ICLR', 'NeurIPS', 'ICML', etc.
        year: Conference year
        output_file: Output JSONL file path
        fetch_affiliations: Whether to fetch author affiliations
        max_affiliations: Max authors to fetch (0 = all)
        headless: Run browser in headless mode
    """
    env = _load_env()
    username = env.get('OPEN_REVIEW_USER_NAME', '')
    password = env.get('OPEN_REVIEW_USER_PASSWORD', '')

    if not username or not password:
        print('[ERROR] OPEN_REVIEW_USER_NAME or OPEN_REVIEW_USER_PASSWORD not set in .env')
        return []

    with OpenReviewCrawler(headless=headless) as crawler:
        if not crawler.login(username, password):
            print('[ERROR] Login failed')
            return []

        papers = crawler.fetch_papers(
            venue=venue,
            year=year,
            fetch_affiliations=fetch_affiliations,
            max_affiliations=max_affiliations,
        )

        if papers:
            save_papers_jsonl(papers, output_file)

        return papers


def main():
    parser = argparse.ArgumentParser(
        description='Crawl conference papers from OpenReview'
    )
    parser.add_argument('venue', help='Conference venue (ICLR, NeurIPS, ICML)')
    parser.add_argument('year', type=int, help='Conference year (e.g. 2025)')
    parser.add_argument('-o', '--output', help='Output JSONL file path')
    parser.add_argument(
        '--affiliations', action='store_true',
        help='Fetch author affiliations (slower)'
    )
    parser.add_argument(
        '--max-affiliations', type=int, default=0,
        help='Max authors to fetch affiliations for (0 = all)'
    )
    parser.add_argument(
        '--no-headless', action='store_true',
        help='Show browser window (for debugging)'
    )

    args = parser.parse_args()

    if args.output:
        output_file = args.output
    else:
        output_file = f'getfiles/{args.venue.lower()}{args.year}_papers.jsonl'

    papers = crawl_conference(
        venue=args.venue,
        year=args.year,
        output_file=output_file,
        fetch_affiliations=args.affiliations,
        max_affiliations=args.max_affiliations,
        headless=not args.no_headless,
    )

    if papers:
        print(f"\n{'='*60}")
        print(f"Crawled {len(papers)} papers from {args.venue} {args.year}")
        print(f"Saved to: {output_file}")
        print(f"{'='*60}")

        # Print sample
        if papers:
            p = papers[0]
            print(f"\nSample paper:")
            print(f"  Title: {p['title'][:80]}")
            print(f"  Authors: {p['authors'][:3]}")
            print(f"  Abstract: {p['abstract'][:100]}...")
            print(f"  Keywords: {p.get('keywords', [])}")


if __name__ == '__main__':
    main()
