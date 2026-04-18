import matplotlib.pyplot as plt
import datetime
import os
import json

plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

from dbapi import DBAPI

STATS_ROOT_DIR = './Imgs/visulize_img/statistics'

class StatisticsVisualizer:
    def __init__(self, db_api: DBAPI):
        self.db_api = db_api
        self.STATS_ROOT_DIR = STATS_ROOT_DIR
        os.makedirs(self.STATS_ROOT_DIR, exist_ok=True)
    
    def get_score_distribution(self, results: list) -> list[tuple[str, int]]:
        """
        统计评分分布
        :param results: LLM处理后的结果列表
        :return: [(score_range, count), ...]
        """
        bins = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7), (7, 8), (8, 9), (9, 10)]
        counts = [0] * len(bins)
        
        for result in results:
            score = result.get('total_score', 0)
            for i, (low, high) in enumerate(bins):
                if low <= score < high:
                    counts[i] += 1
                    break
        
        return [(f"{low}-{high}", count) for (low, high), count in zip(bins, counts) if count > 0]
    
    def get_institution_topn(self, start_date=None, end_date=None, top_n: int = 10) -> list[tuple[str, int]]:
        """
        获取机构发表文章TOP N
        :param start_date: 起始日期
        :param end_date: 结束日期
        :param top_n: 返回前N个
        :return: [(institution_name, count), ...]
        """
        query = """
        SELECT i.name, COUNT(DISTINCT a.id) as article_count
        FROM institutions i
        JOIN article_institutions ai ON i.id = ai.institution_id
        JOIN articles a ON ai.article_id = a.id
        WHERE 1=1
        """
        params = []
        
        if start_date:
            query += " AND a.pub_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND a.pub_date <= ?"
            params.append(end_date)
        
        query += """
        GROUP BY i.id, i.name
        ORDER BY article_count DESC
        LIMIT ?
        """
        params.append(top_n)
        
        self.db_api.cursor.execute(query, params)
        results = self.db_api.cursor.fetchall()
        
        return [(row[0], row[1]) for row in results]
    
    def render_score_histogram(self, score_distribution: list[tuple[str, int]]):
        """
        渲染评分分布直方图
        :param score_distribution: [(score_range, count), ...]
        :return: None
        """
        x_data = [x[0] for x in score_distribution]
        y_data = [x[1] for x in score_distribution]
        
        plt.figure(figsize=(10, 6))
        bars = plt.bar(x_data, y_data, color='skyblue')
        
        plt.title("评分分布", fontsize=14)
        plt.xlabel("评分区间", fontsize=12)
        plt.ylabel("文章数量", fontsize=12)
        
        for bar in bars:
            height = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2., height,
                    f'{int(height)}',
                    ha='center', va='bottom')
        
        plt.tight_layout()
        
        date = datetime.datetime.now().strftime("%Y-%m-%d")
        output_path = os.path.join(self.STATS_ROOT_DIR, f"{date}_score_histogram.png")
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"评分分布直方图已保存到: {output_path}")
    
    def get_statistics_text(self, country_stats: list[tuple[str, int]], institution_stats: list[tuple[str, int]], score_stats: list[tuple[str, int]]) -> str:
        """
        生成统计文字信息，用于插入到Markdown报告中
        """
        text = ""
        
        if country_stats:
            text += "### 🌍 国家/地区分布 TOP 10\n\n"
            text += "| 排名 | 国家 | 文章数量 |\n"
            text += "|------|------|----------|\n"
            for i, (name, count) in enumerate(country_stats[:10], 1):
                text += f"| {i} | {name} | {count} |\n"
            text += f"\n**总计**: {sum(count for _, count in country_stats)} 篇文章\n\n"
        
        if institution_stats:
            text += "### 🏢 研究机构 TOP 10\n\n"
            text += "| 排名 | 机构 | 文章数量 |\n"
            text += "|------|------|----------|\n"
            for i, (name, count) in enumerate(institution_stats[:10], 1):
                short_name = name if len(name) < 30 else name[:27] + "..."
                text += f"| {i} | {short_name} | {count} |\n"
            text += "\n"
        
        if score_stats:
            text += "### 📊 评分分布\n\n"
            text += "| 评分区间 | 文章数量 |\n"
            text += "|----------|----------|\n"
            for score_range, count in score_stats:
                text += f"| {score_range} | {count} |\n"
            text += f"\n**总计**: {sum(count for _, count in score_stats)} 篇评分文章\n\n"
        
        return text


if __name__ == "__main__":
    import sys
    db_api = DBAPI()
    stats_vis = StatisticsVisualizer(db_api)
    
    if len(sys.argv) > 1:
        result_file = sys.argv[1]
        # 如果是相对路径，相对于项目根目录（当前工作目录）
        if not os.path.isabs(result_file):
            result_file = os.path.join(os.getcwd(), result_file)
        with open(result_file, 'r', encoding='utf-8') as f:
            results = json.load(f)
        
        score_dist = stats_vis.get_score_distribution(results)
        stats_vis.render_score_histogram(score_dist)
        
        print("\n统计完成！")
        print(f"评分分布: {score_dist}")
    
    db_api.close()
