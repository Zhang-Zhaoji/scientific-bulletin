# extract texts from Springer Nature Journals
import requests
import datetime
import tqdm
from bs4 import BeautifulSoup
import jsonlines
from utils import normalize_url, select_articles
import time

start_day = '10/12/2025'

# if we want to extract texts from multiple pages, we need to add the page number to the url
# ?searchType=journalSearch&sort=PubDate&page=2

# for each article on the original page, the example information is that:
# '''
# <article class="u-full-height c-card c-card--flush" itemscope="" itemtype="http://schema.org/ScholarlyArticle">
# <div class="c-card__layout u-full-height">
# <div class="c-card__body u-display-flex u-flex-direction-column">
# <h3 class="c-card__title" itemprop="name headline">
# <a class="c-card__link u-link-inherit" data-track="click" data-track-action="view article" data-track-label="link" href="/articles/s41586-025-10031-z" itemprop="url">Mazdutide versus dulaglutide in Chinese adults with type 2 diabetes</a>   
# </h3>
# <ul class="app-author-list app-author-list--compact app-author-list--truncated" data-test="author-list">
# <li itemprop="creator" itemscope="" itemtype="http://schema.org/Person"><span itemprop="name">Lixin Guo</span></li><li itemprop="creator" itemscope="" itemtype="http://schema.org/Person"><span itemprop="name">Bo Zhang</span></li><li itemprop="creator" itemscope="" itemtype="http://schema.org/Person"><span itemprop="name">Wenying Yang</span></li>
# </ul>
# </div>
# </div>
# <div class="c-card__section c-meta">
# <span class="c-meta__item c-meta__item--block-at-lg" data-test="article.type"><span class="c-meta__type">Article</span></span><time class="c-meta__item c-meta__item--block-at-lg" datetime="2025-12-17" itemprop="datePublished">17 Dec 2025</time>
# </div>
# </article>
# '''

def extract_text(base_url:str):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
    }
    next_page = True
    page = 1
    article_infos = []
    while next_page:
        response = requests.get(base_url + f'?searchType=journalSearch&sort=PubDate&page={page}', headers=headers)
        print(f'page {page}')
        page += 1
        time.sleep(1)
        soup = BeautifulSoup(response.text, 'html.parser')
        all_artice_elements = soup.find_all('article')
        
        for article in all_artice_elements:
            title_element = article.find('h3', class_='c-card__title')
            title = title_element.text.strip() if title_element else 'No title'
            author_elements = article.find_all('li', itemprop='creator')
            authors = [author.text.strip() for author in author_elements] if author_elements else ['No author']
            date_element = article.find('time', itemprop='datePublished')
            date = date_element.text.strip() if date_element else 'No date'
            url_element = article.find('a', class_='c-card__link u-link-inherit')
            url = url_element['href'] if url_element else 'No url'
            article_type_element = article.find('span', class_='c-meta__type')
            article_type = article_type_element.text.strip() if article_type_element else 'No type'
            if article_type not in ['Article', 'Review Article']:
                continue 
            article_info = {
                'type': article_type,
                'title': title,
                'authors': authors,
                'date': date,
                'url': url,
            }
            article_infos.append(article_info)
        print(len(article_infos))
        next_page, article_infos = select_articles(article_infos, start_day)
        print(len(article_infos))
    return article_infos



def get_abstracts(url: str, href: str) -> str:
    target_url = normalize_url(url.strip(), href.strip())
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'
    }
    try:
        response = requests.get(target_url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"[ERROR] Failed to fetch {target_url}: {e}")
        return ""
    soup = BeautifulSoup(response.text, 'html.parser')
    abstract_section = soup.find('section', {'data-title': 'Abstract'})
    if abstract_section is None:
        print("[WARN] Abstract section not found.")
        return ""

    content_div = abstract_section.find('div', class_='c-article-section__content')
    paragraphs = content_div.find_all('p', recursive=True)
    if not paragraphs:
        print("[WARN] No <p> tags found in abstract section.")
        return ""

    cleaned_texts = []
    for p in paragraphs:
        for sup in p.find_all('sup'):
            citation_link = sup.find('a', {'data-test': 'citation-ref'})
            if citation_link:
                sup.decompose() 
        text = p.get_text(separator=' ', strip=True)
        if text:
            cleaned_texts.append(text)
    abstract = ' '.join(cleaned_texts)
    return abstract

def process_nature_article_infos(root_nature_url:str):
    print('get texts')
    article_infos = extract_text(root_nature_url)
    print('texts extracted \n get abstracts:\n')
    for idx, article_info in enumerate(tqdm.tqdm(article_infos,total=len(article_infos))):
        article_url = article_info['url']
        abstract = get_abstracts(root_nature_url, article_url)
        article_infos[idx]['abstract'] = abstract
    return article_infos  

if __name__ == '__main__':
    base_urls = ['https://www.nature.com/nature/research-articles',
            'https://www.nature.com/nature/reviews-and-analysis',
            'https://www.nature.com/natbiomedeng/research-articles',
            'https://www.nature.com/natbiomedeng/reviews-and-analysis',
            'https://www.nature.com/nmeth/research-articles',
            'https://www.nature.com/nmeth/reviews-and-analysis',
            'https://www.nature.com/neuro/research-articles',
            'https://www.nature.com/neuro/reviews-and-analysis',
            'https://www.nature.com/nathumbehav/research-articles',
            'https://www.nature.com/nathumbehav/reviews-and-analysis',
                # 'https://www.nature.com/subjects/biological-sciences/ncomms',
                # 'https://www.nature.com/subjects/health-sciences/ncomms'
                ]
    article_infos = []
    for idx, base_url in enumerate(base_urls):
        print(f'[{idx}/{len(base_urls)}], url = {base_url}')
        article_infos.extend(process_nature_article_infos(base_url))    
    
    with jsonlines.open(f'getfiles/{datetime.datetime.now().strftime("%Y-%m-%d")}.jsonl', 'w') as f:
        print('writing...')
        for article_info in article_infos:
            f.write(article_info)
        print('finished')
