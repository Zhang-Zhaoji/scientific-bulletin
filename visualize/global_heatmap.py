from pyecharts.charts import Map, Pie
from pyecharts import options as opts
import sqlite3
import datetime
import os

from dbapi import DBAPI

HEATMAP_ROOT_DIR = '../Imgs/visulize_img/globalHeatmap'
PIE_ROOT_DIR = '../Imgs/visulize_img/countryPie'

if not os.path.exists(HEATMAP_ROOT_DIR):
    HEATMAP_ROOT_DIR = 'Imgs/visulize_img/globalHeatmap'
if not os.path.exists(PIE_ROOT_DIR):
    PIE_ROOT_DIR = 'Imgs/visulize_img/countryPie'

class WorldHeatmap:
    def __init__(self, db_api: DBAPI):
        self.db_api = db_api
        self.HEATMAP_ROOT_DIR = HEATMAP_ROOT_DIR
        self.PIE_ROOT_DIR = PIE_ROOT_DIR
        
        os.makedirs(self.PIE_ROOT_DIR, exist_ok=True)

    def render_pie_chart(self, country_article_count: list[tuple[str, int]], top_n: int = 10):
        """
        渲染各国文章数量饼图，默认只显示文章数最多的前N个国家
        :param country_article_count: 国家-文章数量列表
        :param top_n: 显示前N个国家，其余合并为"其他"
        :return: None
        """
        filtered_data = [(name, count) for name, count in country_article_count if count > 0]
        sorted_data = sorted(filtered_data, key=lambda x: x[1], reverse=True)
        
        if len(sorted_data) > top_n:
            top_data = sorted_data[:top_n]
            other_count = sum(count for _, count in sorted_data[top_n:])
            top_data.append(("其他", other_count))
        else:
            top_data = sorted_data
        
        pie = (
            Pie()
            .add(
                "",
                top_data,
                radius=["30%", "75%"],
                center=["50%", "50%"],
            )
            .set_series_opts(
                label_opts=opts.LabelOpts(
                    formatter="{b}: {c} ({d}%)"
                )
            )
            .set_global_opts(
                title_opts=opts.TitleOpts(title="Country Publication Distribution"),
                legend_opts=opts.LegendOpts(orient="vertical", pos_left="0%", pos_top="15%")
            )
        )
        
        date = datetime.datetime.now().strftime("%Y-%m-%d")
        output_path = os.path.join(self.PIE_ROOT_DIR, f"{date}_pie.html")
        pie.render(output_path)

    def get_world_data(self, date_range)->list[tuple[str, int]]:
        """
        从数据库中获取全球文章数量
        :param date_range: 日期范围, 格式为 (start_date, end_date)
        :return: 国家-文章数量列表
        """
        start_date, end_date = date_range
        country_article_count = self.db_api.get_country_article_count(start_date, end_date)
        print(f"获取到 {start_date} 到 {end_date} 之间的文章数量: {len(country_article_count)} 个")
        print("国家-文章数量列表:")
        print("="*20)
        for name_count in country_article_count:
            print(name_count)
        print("="*20)
        return country_article_count

    def render_heatmap(self, country_article_count: list[tuple[str, int]]):
        """
        渲染全球热力图, 并保存到HTML文件
        :param country_article_count: 国家-文章数量列表
        :return: None
        """ 
        filtered_data = [(name, count) for name, count in country_article_count if count > 0]
        max_article_count = max([count for _, count in filtered_data])
        world_map = (
           Map()
           .add("", filtered_data, "world")
           .set_series_opts(
               label_opts=opts.LabelOpts(
                   is_show=False,
               )
           )
           .set_global_opts(
               title_opts=opts.TitleOpts(title="Publication Heatmap"),
               visualmap_opts=opts.VisualMapOpts(max_=max_article_count, min_=0, is_piecewise=False)
           )
        )
        date = datetime.datetime.now().strftime("%Y-%m-%d")
        output_path = os.path.join(self.HEATMAP_ROOT_DIR, f"{date}.html")
        world_map.render(output_path)


if __name__ == "__main__":
    db_api = DBAPI()
    world_heatmap = WorldHeatmap(db_api)
    country_article_count = world_heatmap.get_world_data(("2026-04-04", "2099-12-31"))
    world_heatmap.render_heatmap(country_article_count)
    world_heatmap.render_pie_chart(country_article_count, top_n=10)
    db_api.close()