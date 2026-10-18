"""Refresh PNG exports for the historical charts changed by abstract reassessment."""
import argparse
import base64
import json
from pathlib import Path
import re
import shutil

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait

from audit_bulletin_abstracts import ROOT, fingerprint
from recover_bulletin_abstracts import atomic_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    args = parser.parse_args()
    run = args.run_dir.resolve()
    manifest = json.loads((run / 'apply_manifest.json').read_text(encoding='utf-8'))
    options = Options()
    for argument in ['--headless', '--no-sandbox', '--disable-dev-shm-usage', '--window-size=1200,800']:
        options.add_argument(argument)
    driver = webdriver.Chrome(options=options)
    audits = []
    try:
        for issue in manifest['issues']:
            source_date = re.search(r'\d{4}-\d{2}-\d{2}', issue['source'])[0]
            for relative in [f'Imgs/visulize_img/globalHeatmap/{source_date}_heatmap.html', f'Imgs/visulize_img/countryPie/{source_date}_pie.html']:
                path = ROOT / relative
                target = path.with_suffix('.png')
                backup = run / 'source_backups' / target.relative_to(ROOT)
                before = fingerprint(target) if target.exists() else None
                if target.exists() and not backup.exists():
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, backup)
                    if fingerprint(backup) != before:
                        raise ValueError('Chart PNG backup failed')
                driver.get(path.resolve().as_uri())
                WebDriverWait(driver, 20).until(lambda browser: browser.execute_script('return !!window.echarts && !!document.querySelector("canvas");'))
                driver.execute_script('const chart=echarts.getInstanceByDom(document.querySelector(".chart-container")); chart.setOption({animation:false}); chart.resize();')
                data_url = driver.execute_script('return echarts.getInstanceByDom(document.querySelector(".chart-container")).getDataURL({type:"png",pixelRatio:2,backgroundColor:"#ffffff"});')
                target.write_bytes(base64.b64decode(data_url.split(',', 1)[1]))
                audits.append({'target': str(target.relative_to(ROOT)), 'before_sha256': before, 'after_sha256': fingerprint(target)})
            atomic_json(run / 'chart_png_exports.json', audits)
            print('RENDERED', source_date, flush=True)
    finally:
        driver.quit()


if __name__ == '__main__':
    main()
