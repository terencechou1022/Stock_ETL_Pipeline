"""期交所 每日行情（Selenium）。

技術選擇說明：這個頁面沒有公開 JSON API，查詢條件（日期、交易時段、契約）
必須透過表單送出，且交易時段的選項會由 JavaScript 依查詢日期重新產生，
因此需要真實瀏覽器。這是本專案唯一無法用 requests 取代的情況之一。

頁面兩個必須知道的行為：
1. MarketCode（交易時段）的選項取決於查詢日期。初次載入時預設日期是下一個
   交易日，只會有「盤後交易時段」；送出一次歷史日期查詢後，「一般交易時段」
   才會出現。因此 run() 開始前會先做一次暖機查詢。
2. 切換 MarketCode 會觸發 onChangMarketCode() 重新填充契約清單，所以順序
   必須是「先選時段、等清單重建、再選契約」。
"""
import logging
from io import StringIO
from pathlib import Path

import holidays
import pandas as pd
from lxml import html as lxml_html
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.ui import WebDriverWait

from scrapers.browser import DEFAULT_TIMEOUT, create_driver, submit_and_wait
from scrapers.clean import normalize_column, to_number
from scrapers.errors import NoDataError, ScraperError, UnexpectedPageError
from scrapers.retry import with_retry
from scrapers.storage import save_csv

log = logging.getLogger(__name__)

URL = 'https://www.taifex.com.tw/cht/3/futDailyMarketReport'

# MarketCode 的 value；用 value 而不是索引，索引會隨頁面狀態變動
SESSIONS = {'一般交易時段': '0', '盤後交易時段': '1'}

# 契約用代碼定位（TX = 臺股期貨）。原本的 select_by_index(19) 其實是
# 「英鎊兌美元期貨(XBF)」，和本專案的台股主題無關——這就是魔術索引的代價。
DEFAULT_CONTRACT = 'TX'

CORE_COLUMNS = ['契約', '到期月份(週別)', '開盤價', '最高價', '最低價', '最後成交價']
TEXT_COLUMNS = ['契約', '到期月份(週別)']
KEY = ['日期', '契約', '到期月份(週別)']


def trading_days(start, end):
    """產生候選交易日：排除週末與國定假日。

    holidays 套件不含颱風假、補行上班日，期交所也有自己的特殊休市，
    所以這裡只做粗篩。真正的判斷交給「查無資料就跳過」——以來源回傳的
    結果為準，比維護一份假日清單可靠得多。
    """
    tw_holidays = holidays.Taiwan()
    for day in pd.date_range(start, end):
        if day.weekday() >= 5:
            continue
        if day.date() in tw_holidays:
            continue
        yield day


def _page_date(page_html):
    """從頁面擷取資料日期，例如 '日期： 2024/09/02' -> '2024/09/02'。"""
    tree = lxml_html.fromstring(page_html)
    nodes = tree.xpath('//*[@id="printhere"]/p[1]')
    if not nodes:
        raise UnexpectedPageError('找不到頁面日期元素（#printhere > p[1]），來源可能已改版')
    text = nodes[0].text_content()
    if '：' not in text:
        raise UnexpectedPageError(f'頁面日期格式不符：{text!r}')
    return text.split('：')[1].strip()


def _select_session(driver, session_code):
    """選擇交易時段，回傳是否成功選到。

    切換 MarketCode 會觸發 onChangMarketCode()，以 AJAX 重建契約清單並把整個
    <select> 元素換掉。因此必須等舊元素變成 stale 才算重建完成——用「選項數量
    大於 N」當等待條件是錯的，舊清單本來就滿足，會拿到即將失效的參照。
    """
    market = Select(driver.find_element(By.ID, 'MarketCode'))
    if session_code not in [option.get_attribute('value') for option in market.options]:
        return False
    if market.first_selected_option.get_attribute('value') == session_code:
        return True

    old_commodity = driver.find_element(By.ID, 'commodity_idt')
    market.select_by_value(session_code)
    WebDriverWait(driver, DEFAULT_TIMEOUT).until(EC.staleness_of(old_commodity))
    return True


def _ensure_form_ready(driver):
    """確認查詢表單可用，必要時重新載入頁面。

    查無資料的結果頁會把契約選單清空。若沿用那個頁面繼續查下一天，就會
    因為「選不到契約」而誤判成該日也沒資料——真實交易日被靜默漏掉，
    這是資料管線最不能接受的錯誤，所以寧可多花一次頁面載入把表單復原。
    """
    if driver.find_elements(By.CSS_SELECTOR, '#commodity_idt option'):
        return
    log.debug('契約選單為空，重新載入查詢頁以復原表單')
    driver.get(URL)
    WebDriverWait(driver, DEFAULT_TIMEOUT).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, '#commodity_idt option')
    )


def fetch_day(driver, day, contract, session_code):
    """填表送出單一交易日的查詢，回傳頁面 HTML。只做 I/O。"""

    def _submit():
        _ensure_form_ready(driver)

        date_input = driver.find_element(By.ID, 'queryDate')
        date_input.clear()
        date_input.send_keys(day.strftime('%Y/%m/%d'))

        if not _select_session(driver, session_code):
            log.debug('%s 沒有時段代碼 %s 可選，使用頁面預設值', day.date(), session_code)

        commodity = Select(driver.find_element(By.ID, 'commodity_idt'))
        codes = [option.get_attribute('value') for option in commodity.options]
        if not codes:
            # 進入時 _ensure_form_ready 已保證選單非空，所以此處的空清單來自
            # 本次日期／時段變更觸發的 AJAX，代表這一天真的沒有契約可查（休市）。
            # 注意順序很重要：若沒有先復原表單就這樣判斷，讀到的會是上一次查詢
            # 殘留的空選單，真實交易日會被靜默漏掉。
            raise NoDataError(f'{day:%Y-%m-%d} 沒有可查詢的契約，應為休市日')
        if contract not in codes:
            raise UnexpectedPageError(f'找不到契約代碼 {contract!r}；可用代碼：{codes}')
        commodity.select_by_value(contract)

        submit_and_wait(driver, driver.find_element(By.ID, 'button'))
        return driver.page_source

    return with_retry(_submit, description=f'期交所 {contract} {day:%Y-%m-%d}')


def parse(page_html):
    """把行情頁面轉成 DataFrame。純函式，可用離線 HTML 測試。

    欄位集合會隨交易時段變動（盤後只有「成交量」，一般時段拆成盤後／一般／
    合計三欄），因此只驗證核心欄位存在，其餘欄位照來源保留。
    """
    # 休市日的結果頁只有「查無資料」四個字，沒有任何表格。這是「查無資料」
    # 而不是「來源改版」，必須讓上層跳過該日繼續跑。
    # flavor='lxml' 是必要的：不指定時 pandas 找不到表格會退回 bs4/html5lib，
    # 拋出的是 ImportError（抱怨缺 html5lib）而不是 ValueError，攔不到。
    try:
        tables = pd.read_html(StringIO(page_html), flavor='lxml')
    except ValueError as exc:
        raise NoDataError(f'頁面沒有表格，應為休市日（{exc}）') from exc
    if not tables:
        # 實測兩種形式都會發生：離線片段會拋 ValueError，完整頁面則是回傳空清單。
        raise NoDataError('頁面沒有表格，應為休市日')

    df = tables[0]
    df.columns = [normalize_column(column) for column in df.columns]

    missing = [column for column in CORE_COLUMNS if column not in df.columns]
    if missing:
        raise UnexpectedPageError(
            f'行情表欄位與預期不符，缺少 {missing}；實際欄位：{list(df.columns)}'
        )

    # 表格最後一列是「小計」，契約欄為空值
    label = df['契約'].astype(str).str.strip()
    df = df[df['契約'].notna() & ~label.str.contains('小計|合計|總計', na=False)].copy()
    if df.empty:
        raise NoDataError('查無資料（可能為休市日）')

    df['到期月份(週別)'] = (
        df['到期月份(週別)'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    )
    df['契約'] = df['契約'].astype(str).str.strip()

    for column in df.columns:
        if column not in TEXT_COLUMNS:
            # 漲跌欄位帶 ▲▼ 箭頭，未成交欄位是 '-'
            df[column] = to_number(df[column], strip_chars='▲▼+ ')

    df['日期'] = pd.to_datetime(_page_date(page_html))

    ordered = KEY + [c for c in df.columns if c not in KEY]
    return df[ordered].reset_index(drop=True)


def run(start, end, contract=DEFAULT_CONTRACT, session='一般交易時段',
        out_dir='data', headless=False):
    """抓取 [start, end] 期間的每日行情並寫入 CSV，回傳輸出路徑。"""
    if session not in SESSIONS:
        raise ValueError(f'session 必須是 {list(SESSIONS)} 之一，收到 {session!r}')
    session_code = SESSIONS[session]

    days = list(trading_days(start, end))
    if not days:
        raise NoDataError(f'{start}～{end} 之間沒有候選交易日')

    driver = create_driver(headless)
    frames = []
    try:
        driver.get(URL)
        WebDriverWait(driver, DEFAULT_TIMEOUT).until(
            lambda d: d.find_element(By.ID, 'queryDate')
        )

        # 暖機：先送出一次查詢，「一般交易時段」選項才會出現（見模組說明）。
        # 暖機失敗不致命——例如首日剛好休市，後續日期照樣能抓。
        log.info('暖機查詢中……')
        try:
            fetch_day(driver, days[0], contract, session_code)
        except ScraperError as exc:
            log.debug('暖機查詢未成功（%s），繼續進行', exc)

        for day in days:
            try:
                frames.append(parse(fetch_day(driver, day, contract, session_code)))
                log.info('已取得 %s', day.date())
            except NoDataError as exc:
                log.info('%s 無資料，略過（%s）', day.date(), exc)
    finally:
        driver.quit()

    if not frames:
        raise NoDataError(f'{contract} 在 {start}～{end} 沒有取得任何資料')

    df = pd.concat(frames, ignore_index=True)
    path = Path(out_dir) / f'taifex_{contract}.csv'
    save_csv(df, path, KEY)
    return path
