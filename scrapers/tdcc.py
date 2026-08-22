"""集保結算所 股權分散表（Selenium）。

技術選擇說明：這個頁面同樣沒有公開 API，且查詢週別是下拉選單（value 就是
西元日期 YYYYMMDD），必須送出表單才能取得該週資料，因此使用瀏覽器自動化。

股權分散表是籌碼分析的核心：把「1,000,001 股以上」這一級的占比拉出時間序列，
就是常說的「大戶持股比例」。
"""
import logging
from io import StringIO
from pathlib import Path

import pandas as pd
from lxml import html as lxml_html
from selenium.webdriver.common.by import By
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.ui import WebDriverWait

from scrapers.browser import DEFAULT_TIMEOUT, create_driver, submit_and_wait
from scrapers.clean import normalize_column, roc_cjk_to_iso, to_number
from scrapers.errors import NoDataError, UnexpectedPageError
from scrapers.retry import with_retry
from scrapers.storage import save_csv

log = logging.getLogger(__name__)

URL = 'https://www.tdcc.com.tw/portal/zh/smWeb/qryStock'

# 用「表格是否含這個欄位」來辨識目標表格，取代寫死的 table[1]
TARGET_COLUMN = '持股/單位數分級'
CORE_COLUMNS = ['序', TARGET_COLUMN, '人數', '股數/單位數']
TEXT_COLUMNS = [TARGET_COLUMN]
KEY = ['日期', '股票代號', TARGET_COLUMN]


def _page_date(page_html):
    """從「資料日期：115年08月21日」擷取並轉成西元 ISO 日期。"""
    tree = lxml_html.fromstring(page_html)
    for node in tree.xpath('//*[contains(text(), "資料日期")]'):
        try:
            return roc_cjk_to_iso(node.text_content())
        except ValueError:
            continue
    raise UnexpectedPageError('找不到「資料日期」文字，來源可能已改版')


def _pick_table(tables):
    """挑出股權分散表本體。

    原本寫死 table[1]，只要頁面多一個表格就會安靜地拿到錯的資料；
    改成用欄位特徵辨識，並在找不到時明確報錯。
    """
    for table in tables:
        columns = [normalize_column(column) for column in table.columns]
        if TARGET_COLUMN in columns:
            picked = table.copy()
            picked.columns = columns
            return picked
    found = [list(table.columns) for table in tables]
    raise UnexpectedPageError(f'找不到含「{TARGET_COLUMN}」的表格；頁面表格欄位：{found}')


def available_weeks(driver):
    """回傳下拉選單提供的所有週別（西元 YYYYMMDD，最新在前）。"""
    select = Select(driver.find_element(By.ID, 'scaDate'))
    return [option.get_attribute('value') for option in select.options]


def fetch_week(driver, stock_no, week_index):
    """查詢單一週別的股權分散表，回傳頁面 HTML。只做 I/O。"""

    def _submit():
        Select(driver.find_element(By.ID, 'scaDate')).select_by_index(week_index)

        stock_input = driver.find_element(By.ID, 'StockNo')
        stock_input.clear()
        stock_input.send_keys(str(stock_no))

        # 原本用絕對 XPath //*[@id="form1"]/table/tbody/tr[4]/td/input 定位送出鈕，
        # 只要表格多一列就會失效；改用按鈕本身的 value 定位。
        submit = driver.find_element(By.CSS_SELECTOR, 'input[value="查詢"]')
        submit_and_wait(driver, submit)
        return driver.page_source

    return with_retry(_submit, description=f'集保 {stock_no} 第 {week_index + 1} 週')


def parse(page_html, stock_no):
    """把股權分散表頁面轉成 DataFrame。純函式，可用離線 HTML 測試。"""
    # flavor='lxml' 讓「找不到表格」穩定拋 ValueError；不指定時 pandas 會退回
    # bs4/html5lib，拋出的是 ImportError，攔不到也看不懂。
    try:
        tables = pd.read_html(StringIO(page_html), flavor='lxml')
    except ValueError as exc:
        raise NoDataError(f'頁面沒有表格（{exc}）') from exc
    if not tables:
        # 實測兩種形式都會發生：離線片段會拋 ValueError，完整頁面則是回傳空清單。
        raise NoDataError('頁面沒有表格')
    df = _pick_table(tables)

    missing = [column for column in CORE_COLUMNS if column not in df.columns]
    if missing:
        raise UnexpectedPageError(
            f'股權分散表欄位與預期不符，缺少 {missing}；實際欄位：{list(df.columns)}'
        )

    df = df[df[TARGET_COLUMN].notna()].copy()
    if df.empty:
        raise NoDataError('查無資料（可能是尚未公布或代號錯誤）')

    df[TARGET_COLUMN] = df[TARGET_COLUMN].astype(str).str.strip()
    for column in df.columns:
        if column not in TEXT_COLUMNS:
            df[column] = to_number(df[column])

    df['日期'] = pd.to_datetime(_page_date(page_html))
    df['股票代號'] = str(stock_no)

    ordered = KEY + [c for c in df.columns if c not in KEY]
    return df[ordered].reset_index(drop=True)


def run(stock_no, weeks=5, out_dir='data', headless=False):
    """抓取最近 weeks 週的股權分散表並寫入 CSV，回傳輸出路徑。"""
    driver = create_driver(headless)
    frames = []
    try:
        driver.get(URL)
        WebDriverWait(driver, DEFAULT_TIMEOUT).until(
            lambda d: d.find_element(By.ID, 'scaDate')
        )

        weeks_available = available_weeks(driver)
        if weeks > len(weeks_available):
            raise ValueError(
                f'只提供最近 {len(weeks_available)} 週（{weeks_available[-1]}～'
                f'{weeks_available[0]}），無法取得 {weeks} 週'
            )

        for index in range(weeks):
            try:
                frames.append(parse(fetch_week(driver, stock_no, index), stock_no))
                log.info('已取得 %s', weeks_available[index])
            except NoDataError as exc:
                log.info('%s 無資料，略過（%s）', weeks_available[index], exc)
    finally:
        driver.quit()

    if not frames:
        raise NoDataError(f'{stock_no} 沒有取得任何股權分散資料')

    df = pd.concat(frames, ignore_index=True)
    path = Path(out_dir) / f'tdcc_{stock_no}.csv'
    save_csv(df, path, KEY)
    return path
