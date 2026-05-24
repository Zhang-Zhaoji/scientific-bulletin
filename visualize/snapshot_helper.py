import os
import time
import base64
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def take_screenshot(html_path: str, output_png_path: str, width: int = 1200, height: int = 800):
    """
    使用 Selenium 打开本地 HTML 文件并截图，等待 echarts 渲染完成。
    """
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument(f"--window-size={width},{height}")
    chrome_options.add_argument("--hide-scrollbars")
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("--ignore-certificate-errors-spki-list")
    chrome_options.add_argument("--allow-insecure-localhost")

    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        file_url = "file:///" + os.path.abspath(html_path).replace("\\", "/")
        driver.get(file_url)
        
        # 等待页面加载和 echarts 渲染完成
        WebDriverWait(driver, 30).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        # 等待 canvas 元素出现
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located(("tag name", "canvas"))
        )
        # 再额外等待确保渲染完成（包括地图数据加载）
        time.sleep(3)
        
        data_url = driver.execute_script("""
            const canvases = Array.from(document.querySelectorAll('canvas'));
            if (!canvases.length) {
                return null;
            }
            const chartDom = canvases[0].closest('.chart-container') || canvases[0].parentElement;
            const chart = window.echarts && echarts.getInstanceByDom(chartDom);
            if (!chart) {
                return null;
            }
            return chart.getDataURL({
                type: 'png',
                pixelRatio: 2,
                backgroundColor: 'rgba(0,0,0,0)'
            });
        """)
        if data_url:
            _, encoded_png = data_url.split(",", 1)
            with open(output_png_path, "wb") as f:
                f.write(base64.b64decode(encoded_png))
            print(f"Canvas image saved: {output_png_path}")
        else:
            driver.save_screenshot(output_png_path)
            print(f"Screenshot saved: {output_png_path}")
    finally:
        driver.quit()
