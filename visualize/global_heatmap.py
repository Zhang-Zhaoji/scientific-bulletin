from pyecharts.charts import Map, Pie
from pyecharts import options as opts
import datetime
import os

from dbapi import DBAPI
from snapshot_helper import take_screenshot

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
        
        os.makedirs(self.HEATMAP_ROOT_DIR, exist_ok=True)
        os.makedirs(self.PIE_ROOT_DIR, exist_ok=True)

    def render_pie_chart(self, country_article_count: list[tuple[str, int]], top_n: int = 10):
        """
        渲染各国文章数量饼图，默认只显示文章数最多的前N个国家
        :param country_article_count: 国家-文章数量列表
        :param top_n: 显示前N个国家，其余合并为"其他"
        :return: None
        """
        filtered_data = [(name, count) for name, count in country_article_count if count > 0]
        if not filtered_data:
            print("没有数据可供渲染饼图")
            return
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
        take_screenshot(output_path, output_path.replace(".html", ".png"))

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

    def render_heatmap(self, country_article_count: list[tuple[str, int]]):
        """
        渲染全球热力图, 并保存到HTML文件
        :param country_article_count: 国家-文章数量列表
        :return: None
        """ 
        filtered_data = [(name, count) for name, count in country_article_count if count > 0]
        if not filtered_data:
            print("没有数据可供渲染热力图")
            return
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
        output_path = os.path.join(self.HEATMAP_ROOT_DIR, f"{date}_heatmap.html")
        world_map.render(output_path)
        take_screenshot(output_path, output_path.replace(".html", ".png"))
        


if __name__ == "__main__":
    db_api = DBAPI()
    world_heatmap = WorldHeatmap(db_api)
    country_article_count = world_heatmap.get_world_data()
    world_heatmap.render_heatmap(country_article_count)
    world_heatmap.render_pie_chart(country_article_count, top_n=10)
    db_api.close()
    if os.path.exists('render.html'):
        os.remove('render.html')
