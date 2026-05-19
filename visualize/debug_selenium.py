from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import os

chrome_options = Options()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--window-size=1200,800')

driver = webdriver.Chrome(options=chrome_options)
try:
    html_path = 'D:/工作/scientific bulletin/Imgs/visulize_img/globalHeatmap/2026-05-17_heatmap.html'
    file_url = 'file:///' + os.path.abspath(html_path).replace('\\', '/')
    driver.get(file_url)

    # 获取浏览器日志
    logs = driver.get_log('browser')
    for log in logs:
        print(log)

    # 检查echarts实例是否存在
    chart_exists = driver.execute_script('return typeof chart_d9370b78bfc245379f33151017a7f8e6 !== "undefined"')
    print('Chart exists:', chart_exists)

    # 检查div内容
    div_html = driver.execute_script('return document.getElementById("d9370b78bfc245379f33151017a7f8e6").innerHTML')
    print('Div HTML:', div_html[:500])

    # 尝试手动初始化看看echarts是否会报错
    error_msg = driver.execute_script('''
        try {
            var chart = echarts.init(document.getElementById("d9370b78bfc245379f33151017a7f8e6"));
            return "init ok";
        } catch(e) {
            return e.message;
        }
    ''')
    print('Manual init result:', error_msg)
finally:
    driver.quit()
