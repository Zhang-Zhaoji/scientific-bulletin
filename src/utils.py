from dateutil import parser
from datetime import datetime, date

from urllib.parse import urljoin, urlparse, urlunparse

def normalize_url(base_url: str, href: str) -> str:
    if not href or not isinstance(href, str):
        raise ValueError("href must be a non-empty string")
    if not base_url or not isinstance(base_url, str):
        raise ValueError("base_url must be a non-empty string")
    resolved = urljoin(base_url.strip(), href.strip())
    parsed = urlparse(resolved)
    
    netloc = parsed.netloc
    if parsed.scheme == 'http' and netloc.endswith(':80'):
        netloc = netloc[:-3]
    elif parsed.scheme == 'https' and netloc.endswith(':443'):
        netloc = netloc[:-4]
    scheme = parsed.scheme.lower()
    netloc = netloc.lower()

    path = parsed.path
    normalized = urlunparse((
        scheme,
        netloc,
        path,
        parsed.params,
        parsed.query,     
        parsed.fragment
    ))
    return normalized

def ymd(d: str) -> str:
    return parser.parse(d, dayfirst=True).strftime('%Y-%m-%d')

def days(d1: str, d2: str) -> int:
    ''' d2 is later than d1. Both d1 and d2 should be in YYYY-MM-DD format.'''
    return (datetime.fromisoformat(d2) - datetime.fromisoformat(d1)).days


def select_articles(articles: list[dict], start_date: str=datetime.now().strftime('%Y-%m-%d'), end_date: str = '3000-01-01') -> tuple[bool, list[dict]]:
    ''' Select articles published between start_date and end_date, and return if process the next page'''
    articles.sort(key=lambda x: ymd(x['date']),reverse=True)
    for idx, article in enumerate(articles):
        date = ymd(article['date'])
        print(idx, date)
        if not (days(start_date, date) >= 0 and days(date, end_date) >= 0):
            # later than end_date or earlier than start_date, 
            # by the way, there should be no articles later than end_date
            return False, articles[:idx]
    return True, articles