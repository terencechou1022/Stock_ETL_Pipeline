"""Selenium 瀏覽器共用工具（taifex 與 tdcc 共用）。

只放兩支爬蟲都會用到的東西：driver 建立與「等待頁面重新載入」。
"""
import logging

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 20


def create_driver(headless=False):
    """建立 Edge driver。

    Selenium 4.6+ 內建 Selenium Manager，會自動下載相符版本的 msedgedriver，
    因此不需要手動管理 driver 執行檔。
    """
    options = webdriver.EdgeOptions()
    if headless:
        options.add_argument('--headless=new')
        options.add_argument('--window-size=1920,1080')
    driver = webdriver.Edge(options=options)
    driver.set_page_load_timeout(60)
    return driver


def submit_and_wait(driver, submit_element, timeout=DEFAULT_TIMEOUT):
    """按下送出，並等到新頁面真的載入完成才回傳。

    這裡取代原本的 time.sleep(5)：兩個來源網站送出表單都是整頁重新載入，
    所以先確認舊頁面的 <body> 已經 stale，再等 readyState 變成 complete。
    比固定秒數快，也不會在網路慢的時候抓到上一頁的資料。

    刻意用 <body> 而不是結果表格當錨點：休市日或查無資料時，頁面連一個
    表格都沒有，拿表格當錨點或當完成條件會在這些日子直接爆掉。
    """
    body = driver.find_element(By.TAG_NAME, 'body')
    submit_element.click()
    wait = WebDriverWait(driver, timeout)
    wait.until(EC.staleness_of(body))
    wait.until(lambda d: d.execute_script('return document.readyState') == 'complete')


def option_texts(select):
    """回傳下拉選單所有選項的文字，用於錯誤訊息與參數驗證。"""
    return [option.text.strip() for option in select.options]
