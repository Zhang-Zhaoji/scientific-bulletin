from pyecharts.charts import Map, Pie
from pyecharts import options as opts
import datetime
import os
import re
import html
import json
import shutil
from collections import Counter
from pathlib import Path

import jsonlines

from dbapi import DBAPI

try:
    from snapshot_helper import take_screenshot
except Exception:
    def take_screenshot(*args, **kwargs):
        print("  [SKIP] Selenium not available, skipping screenshot")

# 本地 echarts/地图资源（assets.pyecharts.org CDN 可能不可达，改为引用本地文件）
_ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets')
_ECHARTS_LOCAL = '../vendor/echarts.min.js'
_WORLD_MAP_LOCAL = '../vendor/world.js'


def _use_local_assets(html_path: str):
    """将生成的 HTML 中的 CDN 引用替换为本地资源，避免网络不可达导致截图超时"""
    with open(html_path, encoding='utf-8') as f:
        html = f.read()
    html = html.replace('https://assets.pyecharts.org/assets/v6/echarts.min.js', _ECHARTS_LOCAL)
    html = html.replace('https://assets.pyecharts.org/assets/v6/maps/world.js', _WORLD_MAP_LOCAL)
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)

COUNTRY_ALIASES = {'USA': 'United States', 'United States of America': 'United States',
                   'UK': 'United Kingdom', 'United Kingdom of Great Britain and Northern Ireland': 'United Kingdom',
                   'The Netherlands': 'Netherlands', 'Türkiye': 'Turkey',
                   'Ivory Coast': "Côte d'Ivoire", 'North Macedonia': 'Macedonia',
                   'Solomon Islands': 'Solomon Is.', 'The Gambia': 'Gambia',
                   'Czechia': 'Czech Rep.', 'Laos': 'Lao PDR', "Lao People's Democratic Republic": 'Lao PDR',
                   'Eswatini': 'Swaziland', 'South Korea': 'Korea', 'North Korea': 'Dem. Rep. Korea',
                   'Czech Republic': 'Czech Rep.', 'Dominican Republic': 'Dominican Rep.',
                   'Bosnia and Herzegovina': 'Bosnia and Herz.', 'Equatorial Guinea': 'Eq. Guinea',
                   'Democratic Republic of the Congo': 'Dem. Rep. Congo', 'Republic of the Congo': 'Congo',
                   'Central African Republic': 'Central African Rep.', 'South Sudan': 'S. Sudan'}

def list_values(value):
    return [value] if isinstance(value, str) else (value or [])

def article_countries(article):
    countries = set(list_values(article.get('countries')))
    for author in article.get('author_details', article.get('authors_enriched', [])):
        countries.update(list_values(author.get('ror_country')))
    return {COUNTRY_ALIASES.get(str(c).strip(), str(c).strip()) for c in countries if c and str(c).strip()}

def portable_chart(chart, output_path, title, metadata):
    chart.render(output_path)
    _use_local_assets(output_path)
    path = Path(output_path)
    content = path.read_text(encoding='utf-8')
    content = content.replace('<body >', '<body>')
    details = f"日期：{metadata.get('date', '')} · 取得地区信息 {metadata.get('located', 0)}/{metadata.get('total', 0)} 篇"
    header = f'<header><strong>{html.escape(title)}</strong><span>{html.escape(details)}</span></header>'
    content = content.replace('<body>', '<body>' + header)
    css = '<style>html,body{margin:0;width:100%;height:100%;overflow:hidden;font:14px system-ui,"Microsoft YaHei",sans-serif;background:#fff;color:#182b3a}header{height:64px;box-sizing:border-box;padding:12px 16px}header strong,header span{display:block}header strong{font-size:17px}header span{font-size:12px;color:#627383;margin-top:4px}.chart-container{width:100%!important;height:calc(100vh - 64px)!important}</style>'
    content = content.replace('</head>', '<meta name="viewport" content="width=device-width, initial-scale=1">' + css + '</head>')
    script = '<script>window.addEventListener("resize",function(){document.querySelectorAll(".chart-container").forEach(function(el){var c=echarts.getInstanceByDom(el);if(c)c.resize();})});</script>'
    content = content.replace('</body>', script + '</body>')
    path.write_text(content, encoding='utf-8')


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
HEATMAP_ROOT_DIR = str(_PROJECT_ROOT / 'Imgs/visulize_img/globalHeatmap')
PIE_ROOT_DIR = str(_PROJECT_ROOT / 'Imgs/visulize_img/countryPie')

class WorldHeatmap:
    def __init__(self, db_api: DBAPI):
        self.db_api = db_api
        self.HEATMAP_ROOT_DIR = HEATMAP_ROOT_DIR
        self.PIE_ROOT_DIR = PIE_ROOT_DIR
        
        os.makedirs(self.HEATMAP_ROOT_DIR, exist_ok=True)
        os.makedirs(self.PIE_ROOT_DIR, exist_ok=True)
        vendor = Path(self.HEATMAP_ROOT_DIR).parent / 'vendor'
        vendor.mkdir(exist_ok=True)
        shutil.copy2(Path(_ASSET_DIR) / 'echarts.min.js', vendor / 'echarts.min.js')
        shutil.copy2(Path(_ASSET_DIR) / 'maps/world.js', vendor / 'world.js')
        self.metadata = {}
        self.skip_screenshots = False

    def render_pie_chart(self, country_article_count: list[tuple[str, int]], top_n: int = 10, output_date: str | None = None):
        """
        渲染各国文章数量饼图，默认只显示文章数最多的前N个国家
        :param country_article_count: 国家-文章数量列表
        :param top_n: 显示前N个国家，其余合并为"其他"
        :return: None
        """
        filtered_data = [(name, count) for name, count in country_article_count if count > 0]
        sorted_data = sorted(filtered_data, key=lambda x: x[1], reverse=True)
        
        top_data = sorted_data[:top_n]
        if len(sorted_data) > top_n:
            top_data.append(('其他', sum(count for _, count in sorted_data[top_n:])))
        pie = (Pie(init_opts=opts.InitOpts(width='100%', height='100%'))
               .add('', top_data or [('无地区信息', 0)], radius=['30%', '75%'], center=['50%', '50%'])
               .set_series_opts(label_opts=opts.LabelOpts(formatter='{b}: {c} ({d}%)'))
               .set_global_opts(legend_opts=opts.LegendOpts(orient='vertical', pos_left='0%', pos_top='15%')))
        if not top_data:
            pie.options['series'][0]['data'] = []
        
        date = output_date or datetime.datetime.now().strftime("%Y-%m-%d")
        output_path = os.path.join(self.PIE_ROOT_DIR, f"{date}_pie.html")
        self.metadata['date'] = date
        portable_chart(pie, output_path, 'Country Publication Distribution' if top_data else '本期未取得地区信息', self.metadata)
        if not self.skip_screenshots:
            take_screenshot(output_path, output_path.replace(".html", ".png"))

    def get_jsonl_country_data(self, jsonl_path: str) -> list[tuple[str, int]]:
        country_counter = Counter()
        total, located = 0, 0
        with jsonlines.open(jsonl_path) as reader:
            for article in reader:
                total += 1
                countries = article_countries(article)
                located += bool(countries)
                country_counter.update(countries)
        self.metadata = {'source': str(jsonl_path), 'total': total, 'located': located,
                         'counting_unit': 'one paper per country; countries can overlap',
                         'counts': dict(country_counter.most_common())}
        map_names = set(re.findall(r'"name"\s*:\s*"([^"]+)"', Path(_ASSET_DIR, 'maps/world.js').read_text(encoding='utf-8')))
        self.metadata['unmapped_countries'] = sorted(set(country_counter) - map_names)
        print(f'地区信息覆盖：{located}/{total} 篇；{len(country_counter)} 个地区')
        return country_counter.most_common()

    def get_world_data(self, start_date=None, end_date=None)->list[tuple[str, int]]:
        """
        从数据库中获取全球文章数量
        :param start_date: 起始日期 (YYYY-MM-DD)，None 表示自动推断
        :param end_date: 结束日期 (YYYY-MM-DD)，None 表示自动推断
        :return: 国家-文章数量列表
        """
        if end_date is None or start_date is None:
            # 查询数据库中有国家关联的最新和最旧日期
            self.db_api.cursor.execute("""
                SELECT MAX(a.pub_date), MIN(a.pub_date)
                FROM articles a
                JOIN article_countries ac ON a.id = ac.article_id
                JOIN countries c ON ac.country_id = c.id
                WHERE a.id NOT IN (SELECT article_id FROM article_themes WHERE theme_id = 1)
            """)
            max_date, min_date = self.db_api.cursor.fetchone()

            if end_date is None:
                if max_date:
                    end_date = max_date
                else:
                    end_date = datetime.datetime.now().strftime("%Y-%m-%d")

            if start_date is None:
                if max_date:
                    # 以有国家数据的最新日期为基准往前推7天，但不早于最早日期
                    from datetime import datetime as dt
                    end_dt = dt.strptime(end_date, "%Y-%m-%d")
                    start_dt = max(
                        end_dt - datetime.timedelta(days=7),
                        dt.strptime(min_date, "%Y-%m-%d") if min_date else end_dt - datetime.timedelta(days=7)
                    )
                    start_date = start_dt.strftime("%Y-%m-%d")
                else:
                    start_date = (datetime.datetime.now() - datetime.timedelta(days=7)).strftime("%Y-%m-%d")

        country_article_count = self.db_api.get_country_article_count(start_date, end_date)
        print(f"获取到 {start_date} 到 {end_date} 之间的文章数量: {len(country_article_count)} 个国家/地区")
        print("国家-文章数量列表:")
        print("="*20)
        for name_count in country_article_count:
            print(name_count)
        print("="*20)
        return country_article_count

    def render_heatmap(self, country_article_count: list[tuple[str, int]], output_date: str | None = None):
        """
        渲染全球热力图, 并保存到HTML文件
        :param country_article_count: 国家-文章数量列表
        :return: None
        """ 
        filtered_data = [(name, count) for name, count in country_article_count if count > 0]
        max_article_count = max([count for _, count in filtered_data], default=1)
        world_map = (
           Map(init_opts=opts.InitOpts(width='100%', height='100%'))
           .add("", filtered_data or [('__initialization_only__', None)], "world")
           .set_series_opts(
               label_opts=opts.LabelOpts(
                   is_show=False,
               )
           )
           .set_global_opts(
               legend_opts=opts.LegendOpts(is_show=False),
               tooltip_opts=opts.TooltipOpts(trigger='item'),
               visualmap_opts=opts.VisualMapOpts(max_=max_article_count, min_=0, is_piecewise=False,
                                                pos_left='left', pos_bottom='bottom', range_color=['#e3eef2', '#31869c', '#123e59'])
           )
        )
        date = output_date or datetime.datetime.now().strftime("%Y-%m-%d")
        output_path = os.path.join(self.HEATMAP_ROOT_DIR, f"{date}_heatmap.html")
        world_map.options['series'][0].update(roam=True, layoutCenter=['54%', '48%'], layoutSize='100%',
                                              showLegendSymbol=False,
                                              itemStyle={'areaColor': '#e7e9eb', 'borderColor': '#fff', 'borderWidth': .4})
        if not filtered_data:
            world_map.options['series'][0]['data'] = []
            world_map.options['visualMap'] = []
        self.metadata['date'] = date
        portable_chart(world_map, output_path, '全球论文地区分布' if filtered_data else '本期未取得地区信息', self.metadata)
        Path(output_path).with_suffix('.data.json').write_text(json.dumps(self.metadata, ensure_ascii=False, indent=2), encoding='utf-8')
        if not self.skip_screenshots:
            take_screenshot(output_path, output_path.replace(".html", ".png"))


def date_from_path(path: str) -> str | None:
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", path)
    if match:
        return match.group(0)
    match = re.search(r"(\d{4})(\d{2})(\d{2})", path)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Render country heatmap and pie chart.")
    parser.add_argument("--jsonl", help="Use a weekly JSONL file instead of querying the database.")
    parser.add_argument("--date", help="Output date label, for example 2026-05-23.")
    parser.add_argument("--start-date", help="Database start date, YYYY-MM-DD.")
    parser.add_argument("--end-date", help="Database end date, YYYY-MM-DD.")
    parser.add_argument('--skip-screenshots', action='store_true')
    args = parser.parse_args()

    db_api = None if args.jsonl else DBAPI()
    world_heatmap = WorldHeatmap(db_api)
    world_heatmap.skip_screenshots = args.skip_screenshots
    if args.jsonl:
        country_article_count = world_heatmap.get_jsonl_country_data(args.jsonl)
        output_date = args.date or date_from_path(args.jsonl)
    else:
        country_article_count = world_heatmap.get_world_data(args.start_date, args.end_date)
        output_date = args.date or args.end_date
    world_heatmap.render_heatmap(country_article_count, output_date)
    world_heatmap.render_pie_chart(country_article_count, top_n=10, output_date=output_date)
    if db_api:
        db_api.close()
    if os.path.exists('render.html'):
        os.remove('render.html')
