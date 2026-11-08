"""Real-browser checks for the single-issue explorer, with independent corpus totals."""
import argparse
from collections import Counter
import json
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--page', type=Path, default=Path('tmps/issue_explorer_preview/report_20261107.html'))
    parser.add_argument('--driver', required=True)
    parser.add_argument('--evidence-dir', type=Path, default=Path('tmps/issue_explorer_preview'))
    args = parser.parse_args()
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    options = Options()
    for option in ('--headless', '--no-sandbox', '--disable-dev-shm-usage', '--window-size=1600,1100'):
        options.add_argument(option)
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    browser = webdriver.Chrome(service=Service(args.driver), options=options)
    evidence = {}
    try:
        browser.get(args.page.resolve().as_uri())
        WebDriverWait(browser, 7).until(lambda b: b.execute_script('return document.querySelectorAll(".issue-chart svg").length === 2'))
        script = browser.execute_script
        script('document.documentElement.style.scrollBehavior="auto"')
        payload = script('return JSON.parse(document.getElementById("issue-explorer-data").textContent)')
        assert not script('return document.getElementById("issue-reading-results").open')
        assert not browser.find_element('id', 'issue-result-list').is_displayed()
        script('document.querySelector("#issue-reading-results summary").click()')
        assert browser.find_element('id', 'issue-result-list').is_displayed()
        script('document.querySelector("#issue-reading-results summary").click()')
        assert not browser.find_element('id', 'issue-result-list').is_displayed()
        evidence['index_default_collapsed_and_toggle'] = 'passed'
        original = json.loads((Path('LLM_Results') / payload['source']).read_text(encoding='utf-8'))
        scoped = [r for r in original if r.get('domain') != '域外局限']
        assert len(scoped) == len(payload['rows'])
        assert script('return document.getElementById("issue-result-count").textContent') == f'{len(scoped)} / {len(scoped)} 篇'
        totals = script('return ["score", "field"].map(k=>echarts.getInstanceByDom(document.getElementById("issue-"+k+"-chart")).getOption().series.reduce((n,s)=>n+s.data.reduce((a,b)=>a+b,0),0))')
        assert totals == [len(scoped)] * 2, totals
        evidence['all_scope'] = {'papers': len(scoped), 'chart_totals': totals}
        script('document.getElementById("issue-explorer").scrollIntoView({behavior:"instant"})')
        browser.save_screenshot(str(args.evidence_dir / 'desktop.png'))
        script('document.getElementById("issue-topic-cloud").scrollIntoView({behavior:"instant",block:"start"})')
        browser.save_screenshot(str(args.evidence_dir / 'reading_index.png'))
        # ECharts click handler selects an exact field/score segment.
        script('''var ch=echarts.getInstanceByDom(document.getElementById('issue-field-chart'));
          var opt=ch.getOption(); var si=opt.series.findIndex(s=>s.data.some(n=>n>0)); var di=opt.series[si].data.findIndex(n=>n>0);
          ch.trigger('click',{componentType:'series',seriesName:opt.series[si].name,name:opt.yAxis[0].data[di],value:opt.series[si].data[di]});''')
        field = script('return document.getElementById("issue-field").value')
        band = int(script('return document.getElementById("issue-score").value.split(":")[1]'))
        def band_of(row):
            s = row.get('total_score')
            return 3 if s is None else 2 if s > 9 else 1 if s > 7 else 0
        expected = sum((r.get('primary_category') or ('域外高影响（未分领域）' if r.get('domain') == '域外高影响' else '未分领域')) == field and band_of(r) == band for r in scoped)
        actual = script('return document.getElementById("issue-result-count").textContent')
        assert script('return document.getElementById("issue-reading-results").open')
        assert actual == f'{expected} / {len(scoped)} 篇', (actual, expected)
        evidence['chart_filter'] = {'field': field, 'band': band, 'count': expected}
        evidence['filter_auto_expands_index'] = 'passed'
        script('document.getElementById("issue-reset").click(); document.querySelector("#issue-topic-cloud button").click()')
        tag = script('return document.querySelector("#issue-topic-cloud button[aria-pressed=true]").dataset.tag')
        expected = sum(tag in (r.get('cross_tags') or []) for r in scoped)
        assert script('return document.getElementById("issue-result-count").textContent') == f'{expected} / {len(scoped)} 篇'
        evidence['topic_filter'] = {'tag': tag, 'count': expected}
        script('document.getElementById("issue-reset").click(); document.getElementById("issue-query").value="unlikely-no-such-paper-xyz"; document.getElementById("issue-query").dispatchEvent(new Event("input"))')
        assert script('return document.getElementById("issue-result-count").textContent').startswith('0 /')
        script('document.getElementById("issue-reset").click(); var s=document.getElementById("issue-scope"); s.value="expanded"; s.dispatchEvent(new Event("change"));')
        expanded = sum(r['expanded'] for r in payload['rows'])
        assert script('return document.getElementById("issue-result-count").textContent') == f'{expanded} / {expanded} 篇'
        totals = script('return ["score", "field"].map(k=>echarts.getInstanceByDom(document.getElementById("issue-"+k+"-chart")).getOption().series.reduce((n,s)=>n+s.data.reduce((a,b)=>a+b,0),0))')
        assert totals == [expanded] * 2
        evidence['expanded_scope'] = {'papers': expanded, 'chart_totals': totals}
        script('document.getElementById("issue-next").click()')
        assert script('return document.getElementById("issue-page").textContent').startswith('2 /')
        first_link = browser.find_element('css selector', '#issue-result-list a')
        target = first_link.get_attribute('href').split('#')[-1]
        assert script('return !!document.getElementById(arguments[0])', target)
        script('arguments[0].scrollIntoView({behavior:"instant",block:"center"})', first_link)
        first_link.click()
        assert browser.current_url.endswith('#' + target)
        evidence['navigation_and_pagination'] = 'passed'
        browser.execute_cdp_cmd('Emulation.setDeviceMetricsOverride', {'width': 390, 'height': 900, 'deviceScaleFactor': 1, 'mobile': True})
        script('document.getElementById("issue-explorer").scrollIntoView({behavior:"instant"})')
        evidence['mobile_overflow'] = script('return document.documentElement.scrollWidth > innerWidth')
        evidence['mobile_width'] = script('return innerWidth')
        browser.save_screenshot(str(args.evidence_dir / 'mobile.png'))
        assert not evidence['mobile_overflow']
        errors = [entry for entry in browser.get_log('browser') if entry['level'] == 'SEVERE']
        evidence['browser_errors'] = errors
        assert not errors, errors
        (args.evidence_dir / 'browser_checks.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
    finally:
        browser.quit()


if __name__ == '__main__':
    main()
