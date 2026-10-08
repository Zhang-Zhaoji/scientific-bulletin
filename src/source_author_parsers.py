"""Read explicitly assigned author affiliations from original publisher/HTML text."""
from bs4 import BeautifulSoup, Tag
import re
from enrich_source_metadata import author_name_matches
from affiliation_matcher import normalize


def parse_arxiv_authors(markup,stored_names,url):
    soup=BeautifulSoup(markup,'html.parser')
    title=soup.select_one('.ltx_title_document') or soup.find('title')
    result={'title':title.get_text(' ',strip=True) if title else '', 'author_details':[]}
    block=soup.select_one('.ltx_authors')
    if not block:return result
    links={};definitions={}
    for sup in block.find_all('sup'):
        refs=re.findall(r'(?<!\d)\d{1,2}(?!\d)',sup.get_text(' ',strip=True))
        if not refs:continue
        preceding=[]
        for node in sup.previous_siblings:
            if isinstance(node,Tag) and node.name in {'sup','br'}:break
            preceding.insert(0,node.get_text(' ',strip=True) if isinstance(node,Tag) else str(node))
        left=normalize(' '.join(preceding))
        candidates=[name for name in stored_names if left==normalize(name) or left.endswith(' '+normalize(name))]
        if len(candidates)==1:
            links.setdefault(candidates[0],set()).update(refs)
            continue
        if len(refs)!=1:continue
        following=[]
        for node in sup.next_siblings:
            if isinstance(node,Tag) and node.name in {'sup','br'}:break
            following.append(node.get_text(' ',strip=True) if isinstance(node,Tag) else str(node))
        value=' '.join(' '.join(following).split()).strip(' ,;')
        if re.search(r'\b(equal|contribut|correspond|email|current address|present address)\w*\b',value,re.I):continue
        if re.search(r'\b(university|institute|laboratory|school|department|center|centre|hospital|research|college|academy)\b',value,re.I):
            definitions[refs[0]]=value
    by_name={}
    for name,refs in links.items():
        units=[definitions[r] for r in sorted(refs) if r in definitions]
        if units:by_name[name]=units
    # A creator wrapper explicitly groups people with its affiliation role.
    for creator in block.select('.ltx_creator.ltx_role_author'):
        contacts=[n.get_text(' ',strip=True) for n in creator.select('.ltx_contact.ltx_role_affiliation')]
        if not contacts:continue
        person=creator.select_one('.ltx_personname')
        if person:
            person=BeautifulSoup(str(person),'html.parser')
            for sup in person.find_all('sup'):sup.decompose()
            named=person.get_text(' ',strip=True)
            matches=[n for n in stored_names if author_name_matches(n,named)]
            if len(matches)==1:by_name.setdefault(matches[0],[]).extend(contacts)
    for name,units in by_name.items():
        result['author_details'].append({'name':name,'affiliation':'; '.join(dict.fromkeys(units)),
                                        'source':'arXiv original HTML affiliation markers','source_url':url})
    return result
