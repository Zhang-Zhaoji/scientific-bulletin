# extract texts from Science Journals
import requests
import datetime
import tqdm
from bs4 import BeautifulSoup
import jsonlines
from utils import normalize_url, select_articles
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

start_day = '10 Dec 2025'

# if we want to extract texts from multiple pages, we need to add the page number to the url
# ?searchType=journalSearch&sort=PubDate&page=2

# for each article on the original page, the example information is that:
'''
<div class="card-header">
      <div class="d-flex justify-content-between align-items-end">
         <div>
            <div class="d-flex align-items-center mb-2 "><span class="overline text-uppercase text-primary">Research Article</span></div><span class="hlFld-Title">
               <h2 class="article-title sans-serif text-deep-gray mb-1"><a href="/doi/10.1126/science.adu8264" class="text-reset animation-underline">Carbonated ultramafic igneous rocks in Jezero crater, Mars</a></h2></span></div>
         <div><a title="" name="bookmark" role="button" data-toggle="tooltip" data-offset="0,14px" class="ml-3 btn-bookmark p-2" data-original-title="ADD TO READING LIST" href="/personalize/addFavoritePublication?doi=10.1126%2Fscience.adu8264"><i aria-hidden="true" class="icon-bookmark"></i><span class="sr-only">Add to reading list</span></a></div>
      </div>
      <div class="card-meta align-middle mb-2 text-uppercase text-darker-gray">
         <div class="card-contribs authors d-inline mr-2 authors-truncate comma-separated" data-visible-items-sm="3" data-visible-items-md="5" data-visible-items="10" data-truncate-less="fewer" data-truncate-more="authors" data-truncate-dots="true"><span>by</span><ul class="list-inline comma-separated" title="list of authors">
               <li class="list-inline-item"><span class="hlFld-ContribAuthor">Kenneth H. Williford</span></li>
               <li class="list-inline-item"><span class="hlFld-ContribAuthor">Kenneth A. Farley</span></li>
               <li class="list-inline-item"><span class="hlFld-ContribAuthor">Briony H.N. Horgan</span></li>
               <li class="list-inline-item"><span class="hlFld-ContribAuthor">Brad Garczynski</span></li>
               <li class="list-inline-item"><span class="hlFld-ContribAuthor">Allan H. Treiman</span></li>
               <li class="list-inline-item d-none"><span class="hlFld-ContribAuthor">Sanjeev Gupta</span></li>
               # ...
               <li class="list-inline-item authors-truncate-to-hide "><a href="#" role="button" class="toggle truncation ml-1 d-inline-block">[...]</a></li><li class="list-inline-item"><span class="hlFld-ContribAuthor">R. Aileen Yingst</span></li>
<li class="list-inline-item authors-toggle  ">
    <button class="truncated btn btn-xs btn-outline-secondary btn-authors-truncate ml-1">+69 authors</button>
</li>
            </ul>
         </div><span class="card-meta__item bullet-left">Science</span><span class="card-meta__item bullet-left"><time>17 Dec 2025</time></span><span class="card-meta__item card-meta__access"></span></div>
   </div>
'''

def extract_text(base_url:str, headless=True):
    # 设置Chrome选项
    chrome_options = Options()
    
    # 根据参数决定是否使用无头模式
    if headless:
        chrome_options.add_argument('--headless')  # 无头模式
        print("Using headless Chrome mode")
    else:
        print("Using regular Chrome mode")
        
    # 添加实验性选项，禁用自动化特征检测
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    # 添加浏览器指纹信息，模拟真实用户
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    chrome_options.add_argument('--accept-language=en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7')
    chrome_options.add_argument('--referer=https://www.google.com/')
    chrome_options.add_argument('--start-maximized')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--ignore-certificate-errors')
    chrome_options.add_argument('--allow-running-insecure-content')
    chrome_options.add_argument('--disable-web-security')
    chrome_options.add_argument('--disable-features=site-per-process')
    
    # 创建WebDriver实例
    driver = webdriver.Chrome(options=chrome_options)
    # 设置窗口大小
    driver.set_window_size(1920, 1080)
    # 设置页面加载策略为正常
    driver.set_page_load_timeout(30)
    
    page = 0
    article_infos = []
    
    try:
        target_url = base_url + f'?startPage={page}&pageSize=100' # get 100 articles for the first page, which is enough for most problems
        
        print(f"Page {page}, URL: {target_url}")
        
        # 访问目标URL
        driver.get(target_url)
        
        # 等待页面加载
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.TAG_NAME, 'body'))
        )
        
        # 等待一段时间模拟真实用户行为
        time.sleep(2)
        
        # 获取页面内容
        response_text = driver.page_source
        
        # 使用BeautifulSoup解析页面
        soup = BeautifulSoup(response_text, 'html.parser')
        all_artice_elements = soup.find_all('div', attrs={'class': "card-header"})
        
        # 打印找到的文章数量
        print(f"Found {len(all_artice_elements)} articles on page {page}")
        
        # 如果没有找到文章，可能是因为反爬或页面结构变化
        if len(all_artice_elements) == 0:
            print("No articles found, checking if we're blocked...")
            
            # 检查页面内容中是否包含验证码相关关键词
            response_text_lower = response_text.lower()
            captcha_keywords = ['captcha', 'challenge', 'verify', 'human', 'turnstile', '完成以下操作', '验证您是真人', '请稍候', 'cloudflare']
            
            blocked = False
            for keyword in captcha_keywords:
                if keyword in response_text_lower:
                    print(f"Detected blocking keyword: '{keyword}'")
                    blocked = True
                    break
            
            # 检查是否被重定向到验证码页面
            if 'captcha' in driver.current_url.lower() or blocked:
                print("We're being asked for verification!")
                print(f"Current URL: {driver.current_url}")
                print("Please complete the captcha in the browser window.")
                print("After completing the captcha, press Enter to continue...")
                
                # 等待用户完成验证码
                input("Press Enter to continue after solving the captcha...")
                
                # 重新加载页面内容
                response_text = driver.page_source
                soup = BeautifulSoup(response_text, 'html.parser')
                all_artice_elements = soup.find_all('div', attrs={'class': "card-header"})
                
                if len(all_artice_elements) > 0:
                    print("Success! Captcha solved, found articles.")
                else:
                    print("Still no articles found after captcha attempt.")
            
            print(f"Found {len(all_artice_elements)} articles on page {page}")
        
        page += 1
    
        for article in all_artice_elements:
            title_element = article.find('a', class_='text-reset animation-underline')
            title = title_element.text.strip() if title_element else 'No title'
            author_elements = article.find_all('span', class_='hlFld-ContribAuthor')
            authors = [author.text.strip() for author in author_elements] if author_elements else ['No author']
            date_element = article.find('time')
            date = date_element.text.strip() if date_element else 'No date'
            url_element = article.find('a', class_='text-reset animation-underline')
            url = url_element['href'] if url_element else 'No url'
            article_type_element = article.find('span', class_='overline text-uppercase text-primary')
            article_type = article_type_element.text.strip() if article_type_element else 'No type'
            if article_type not in ['Research Article', 'Review Article']:
                continue 
            article_info = {
                'type': article_type,
                'title': title,
                'authors': authors,
                'date': date,
                'url': url,
            }
            article_infos.append(article_info)
        print(f"Total articles collected so far: {len(article_infos)}")
        
        _, article_infos = select_articles(article_infos, start_day)
        print(f"After filtering, articles left: {len(article_infos)}")
    except Exception as e:
        print(f"Error during extraction: {e}")
        # 发生错误时关闭浏览器
        driver.quit()
        print("Browser closed due to error")
        return article_infos, None
    
    # 不关闭浏览器，将其返回给调用者
    print("Browser kept open for abstract fetching")
    return article_infos, driver

'''
<section id="editor-abstract" property="abstract" typeof="Text" role="doc-abstract">
<h2 property="name">Editor’s summary</h2>
<div role="paragraph">The transition from a liquid to a solid state generally introduces a discontinuity in ionic conductivity. In the liquid phase, the ionic conductivity follows the Arrhenius relation. However, a sharp phase change such as freezing will cause a drop in ionic conductivity at the transition temperature because the ions are much less mobile in a solid than in a liquid. Barclay <i>et al</i>. designed an organic electrolyte based on cyclopropenium salts that does not show a sharp drop in the ionic conductivity at the liquid-to-solid phase change boundary. This attribute is achieved by bridging the liquid and solid phase regions by a liquid crystal phase region. Key aspects are the weak cation-anion interactions and considerable structural freedom. —Marc S. Lavine</div>
</section>

<section id="abstract" property="abstract" typeof="Text" role="doc-abstract">
<h2 property="name">Abstract</h2>
<div role="paragraph">Liquids lend themselves to high ionic conductivities because of their molecular-level positional and orientational disorder, which enables the free movement of ions. However, there is an unavoidable steep drop in ionic conductivity upon phase transition from a fluid state to the more ordered solid state. Here, we describe organic salts that maintain the same ionic conductivity mechanism across transitions between three states of matter, from an initial isotropic liquid to a liquid crystalline state and then to a crystalline solid. We achieved this property by minimizing the ion-pairing interactions between mobile ions and highly diffuse counterions that assemble in a stepwise manner to preserve conformational flexibility across phase transitions. This state-independent ionic conductivity opens up opportunities to exploit liquid-like ionic conductivity in organic solids.</div>
</section>
'''

def get_abstracts(url: str, href: str, driver) -> str:
    target_url = normalize_url(url.strip(), href.strip())
    
    try:
        # 使用相同的Selenium driver访问文章页面，共享会话状态
        # 增加随机延迟，模拟真实用户行为
        import random
        random_delay = random.uniform(2, 5)
        print(f"\nWaiting {random_delay:.1f} seconds before accessing next article...")
        time.sleep(random_delay)
        
        driver.get(target_url)
        
        # 等待页面加载完成
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, 'body'))
        )
        
        # 模拟滚动行为
        driver.execute_script("window.scrollTo(0, 200)")
        time.sleep(1)
        driver.execute_script("window.scrollTo(0, 400)")
        time.sleep(1)
        
        # 获取页面内容
        response_text = driver.page_source
        soup = BeautifulSoup(response_text, 'html.parser')
        
        # 检查是否遇到验证码（更精确的检测）
        blocked = False
        response_text_lower = response_text.lower()
        captcha_keywords = ['captcha', 'challenge', 'verify', 'human', 'turnstile', '完成以下操作', '验证您是真人', '请稍候', 'cloudflare']
        
        # 检查页面标题和内容
        if 'access denied' in response_text_lower or 'forbidden' in response_text_lower:
            blocked = True
        else:
            for keyword in captcha_keywords:
                if keyword in response_text_lower:
                    blocked = True
                    break
        
        if blocked:
            print(f"\n[WARNING] Access blocked or captcha detected when fetching abstract for {target_url}")
            print("Please complete the captcha or solve the access issue in the browser window.")
            print("After resolving the issue, press Enter to continue...")
            input("Press Enter to continue after solving the issue...")
            
            # 重新获取页面内容
            response_text = driver.page_source
            soup = BeautifulSoup(response_text, 'html.parser')
        
        # 查找并提取摘要（多种方式）
        abstract_content = ""
        
        # 方式1: 查找Editor's summary和Abstract
        editor_summary = ""
        abstract = ""
        
        editor_summary_section = soup.find('section', {'id': 'editor-abstract'})
        if editor_summary_section:
            editor_paragraph = editor_summary_section.find('div', {'role': 'paragraph'})
            if editor_paragraph:
                editor_summary = editor_paragraph.get_text(separator=' ', strip=True)
        
        abstract_section = soup.find('section', {'id': 'abstract'})
        if abstract_section:
            abstract_paragraph = abstract_section.find('div', {'role': 'paragraph'})
            if abstract_paragraph:
                abstract = abstract_paragraph.get_text(separator=' ', strip=True)
        
        # 合并结果
        if editor_summary and abstract:
            abstract_content = f"Editor's summary: {editor_summary} Abstract: {abstract}"
        elif abstract:
            abstract_content = abstract
        elif editor_summary:
            abstract_content = editor_summary
        else:
            # 方式2: 查找带有data-title="Abstract"的section
            abstract_section = soup.find('section', {'data-title': 'Abstract'})
            if abstract_section:
                content_div = abstract_section.find('div', class_='c-article-section__content')
                if content_div:
                    paragraphs = content_div.find_all('p')
                    if paragraphs:
                        abstract_content = ' '.join([p.get_text(strip=True) for p in paragraphs])
            
            # 方式3: 直接查找所有段落，寻找包含"Abstract"的内容
            if not abstract_content:
                all_paragraphs = soup.find_all('p')
                for p in all_paragraphs:
                    text = p.get_text(strip=True)
                    if text.lower().startswith('abstract'):
                        abstract_content = text
                        break
        
        if not abstract_content:
            print(f"[WARN] Abstract content not found for {target_url}")
        
        return abstract_content
    except Exception as e:
        print(f"[ERROR] Failed to fetch abstract for {target_url}: {e}")
        return ""

def process_Science_article_infos(root_Science_url:str, headless=True):
    print('get texts')
    article_infos, driver = extract_text(root_Science_url, headless=headless)
    
    # 如果driver为None，说明在提取文章信息时发生了错误
    if driver is None:
        print('Failed to get driver, cannot fetch abstracts.')
        return article_infos
    
    print('texts extracted \n get abstracts:\n')
    
    # 增加全局等待时间，减少被检测的风险
    print("\n[INFO] Starting to fetch abstracts...")
    print("[INFO] A random delay will be added between each article to avoid detection.")
    print("[INFO] If you encounter captcha, please solve it in the browser window.")
    
    try:
        for idx, article_info in enumerate(tqdm.tqdm(article_infos,total=len(article_infos))):
            print(f"\nProcessing article {idx+1}/{len(article_infos)}: {article_info['url']}")
            article_url = article_info['url']
            abstract = get_abstracts(root_Science_url, article_url, driver)
            article_infos[idx]['abstract'] = abstract
            
            # 保存进度
            if (idx + 1) % 5 == 0:
                print(f"[INFO] Progress: {idx + 1}/{len(article_infos)} articles processed")
    except KeyboardInterrupt:
        print("\n[INFO] Process interrupted by user. Saving current progress...")
    finally:
        # 确保浏览器在完成后关闭
        try:
            driver.quit()
            print("Browser closed successfully")
        except Exception as e:
            print(f"[WARNING] Error closing browser: {e}")
    
    return article_infos  

if __name__ == '__main__':
    import argparse
    
    # 设置命令行参数
    parser = argparse.ArgumentParser(description='Science.org crawler with headless option')
    parser.add_argument('--headless', action='store_true', default=False, help='Use headless Chrome mode (default: False, meaning we use regular Chrome)')
    args = parser.parse_args()
    
    print(f"Headless mode: {args.headless}")
    print(f"Browser mode: {'Headless Chrome' if args.headless else 'Regular Chrome (with UI)'} ")
    
    base_urls = ['https://www.science.org/journal/science/research'
                ]
    article_infos = []
    for idx, base_url in enumerate(base_urls):
        print(f'[{idx}/{len(base_urls)}], url = {base_url}')
        article_infos.extend(process_Science_article_infos(base_url, headless=args.headless))    
    
    with jsonlines.open(f'getfiles/science-{datetime.datetime.now().strftime("%Y-%m-%d")}.jsonl', 'w') as f:
        print('writing...')
        for article_info in article_infos:
            f.write(article_info)
        print('finished')
