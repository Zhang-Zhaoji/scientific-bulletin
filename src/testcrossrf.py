import requests
import re
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from difflib import SequenceMatcher

def is_similar_title(title1: str, title2: str, threshold: float = 0.85) -> bool:
    """计算标题相似度，容忍标点符号的细微差异"""
    if not title1 or not title2:
        return False
    return SequenceMatcher(None, title1.lower(), title2.lower()).ratio() >= threshold

def extract_last_names(authors: List[str]) -> set:
    """提取作者姓氏用于交叉验证"""
    last_names = set()
    for author in authors:
        parts = author.split()
        if parts:
            last_names.add(parts[-1].lower().strip(','))
    return last_names

def clean_abstract(raw_abstract: str) -> str:
    """清除摘要中的 XML/HTML 标签 (例如 <jats:p>)"""
    if not raw_abstract:
        return ""
    # 用正则表达式移除所有 <...> 标签
    clean_text = re.sub(r'<[^>]+>', '', raw_abstract)
    # 移除可能残留的 "Abstract" 标题字样并去除首尾空格
    if clean_text.lower().startswith("abstract"):
        clean_text = clean_text[8:].strip()
    return clean_text

def search_biorxiv_preprint(title: str, authors: List[str], days: int = 730) -> Optional[Dict]:
    cutoff_date = datetime.now() - timedelta(days=days)
    target_last_names = extract_last_names(authors)
    
    crossref_url = "https://api.crossref.org/works"
    
    params = {
        "query.title": title,
        "filter": "type:posted-content", # 限制搜索范围为预印本
        "rows": 5
    }
    
    headers = {"User-Agent": "PreprintTracker/1.0 (mailto:zhang-zj@stu.pku.edu.cn)"}
    
    try:
        response = requests.get(crossref_url, params=params, headers=headers, timeout=10)
        
        if response.status_code == 200:
            items = response.json().get("message", {}).get("items", [])
            for item in items:
                publisher = item.get("publisher", "").lower()
                
                # 兼容不同结构的机构名
                institutions = item.get("institution", [])
                institution_name = institutions[0].get("name", "").lower() if institutions else ""
                
                # 确认是 bioRxiv 或 medRxiv
                if "biorxiv" in publisher or "biorxiv" in institution_name or "medrxiv" in institution_name:
                    found_title = item.get("title", [""])[0]
                    
                    if is_similar_title(title, found_title):
                        date_info = item.get("posted", item.get("accepted", item.get("issued", {})))
                        date_parts = date_info.get("date-parts", [[1970, 1, 1]])[0]
                        
                        if len(date_parts) == 3:
                            post_date = datetime(date_parts[0], date_parts[1], date_parts[2])
                            
                            # 验证时间窗口
                            if post_date >= cutoff_date:
                                found_authors = [a.get("family", "") for a in item.get("author", [])]
                                found_last_names = set(a.lower() for a in found_authors)
                                
                                # 验证作者姓氏是否有交集
                                if target_last_names & found_last_names or not authors:
                                    server_name = "bioRxiv" if "biorxiv" in institution_name or "biorxiv" in publisher else "medRxiv"
                                    
                                    # 【新增提取与清洗摘要的代码】
                                    raw_abstract = item.get("abstract", "")
                                    abstract_text = clean_abstract(raw_abstract)
                                    
                                    return {
                                        "server": server_name,
                                        "title": found_title,
                                        "doi": item.get("DOI"),
                                        "url": item.get("URL", [None])[0] if isinstance(item.get("URL"), list) else item.get("URL"),
                                        "date": post_date.strftime("%Y-%m-%d"),
                                        "abstract": abstract_text # <--- 这里返回摘要
                                    }
        else:
            print(f"API Error {response.status_code}: {response.text}")
            
    except Exception as e:
        print(f"Error searching bioRxiv via Crossref: {e}")

    return None

# ====================
# Colab 测试代码
# ====================
if __name__ == "__main__":
    # 使用你的文章测试
    test_title = "Decoding Covert Human Attention in Multidimensional Environments"
    test_authors = ["Christina Maher", "Ignacio Saez", "Angela Radulescu"]
    
    print(f"Searching for: '{test_title}'...\n")
    
    # 设为 730 天确保能覆盖 2023 年的文章
    result = search_biorxiv_preprint(test_title, test_authors, days=730)
    
    if result:
        print("✅ Found Preprint!\n")
        print(f"Server  : {result['server']}")
        print(f"Title   : {result['title']}")
        print(f"Date    : {result['date']}")
        print(f"DOI     : {result['doi']}")
        print("-" * 60)
        # 打印前 500 个字符的摘要看看效果
        print(f"Abstract: {result['abstract'][:500]} ... [truncated]")
    else:
        print("❌ No preprint found within the specified days.")