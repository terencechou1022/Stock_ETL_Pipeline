"""證交所 個股每日成交資訊（requests + 官方 JSON API）。

技術選擇說明：證交所提供 STOCK_DAY 這支 JSON API，一次回傳一整個月的日成交
資料，因此完全不需要瀏覽器自動化。能打 API 就不要開瀏覽器——快上兩個數量級、
不依賴 DOM 結構、也不會因為網站改版就壞掉。

API 端點：https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY
    date     該月任一日（YYYYMMDD）
    stockNo  股票代號
    response json
"""
import logging
import time
from pathlib import Path

import pandas as pd
import requests

from scrapers.clean import roc_slash_to_iso, to_number
from scrapers.errors import NoDataError, UnexpectedPageError
from scrapers.retry import with_retry
from scrapers.storage import save_csv

log = logging.getLogger(__name__)

API_URL = 'https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY'

# 證交所有流量限制，連續請求之間需要間隔，否則會被暫時擋掉
REQUEST_INTERVAL = 3

# 依 API notes：「+/-/X表示漲/跌/不比價」，另外無成交的日子會是 '--'
PRICE_COLUMNS = ['開盤價', '最高價', '最低價', '收盤價', '漲跌價差']
VOLUME_COLUMNS = ['成交股數', '成交金額', '成交筆數']
REQUIRED_FIELDS = ['日期'] + VOLUME_COLUMNS + PRICE_COLUMNS

KEY = ['日期', '股票代號']


def fetch_month(stock_no, month, session=None):
    """取得單月的原始 JSON。month 為該月任一日期。

    只做 I/O，不做任何解析——回傳原封不動的 dict。
    """
    getter = session.get if session is not None else requests.get
    params = {
        'date': month.strftime('%Y%m01'),
        'stockNo': stock_no,
        'response': 'json',
    }

    def _get():
        response = getter(API_URL, params=params, timeout=15)
        response.raise_for_status()
        return response.json()

    return with_retry(_get, description=f'證交所 {stock_no} {month:%Y-%m}')


def parse(raw, stock_no):
    """把 STOCK_DAY 的 JSON 轉成 DataFrame。

    純函式：不碰網路，可以直接餵離線樣本測試。
    """
    stat = raw.get('stat')
    if stat != 'OK':
        # 查詢未來月份時，回應只有 stat 與 total 兩個欄位，沒有 data。
        # 原本的寫法直接取 raw['data'] 會在這裡 KeyError。
        raise NoDataError(stat or '回應中沒有 stat 欄位')

    if 'data' not in raw or 'fields' not in raw:
        raise UnexpectedPageError(f'回應缺少 data/fields，實際鍵值：{sorted(raw)}')

    df = pd.DataFrame(raw['data'], columns=raw['fields'])

    missing = [column for column in REQUIRED_FIELDS if column not in df.columns]
    if missing:
        raise UnexpectedPageError(
            f'API 欄位與預期不符，缺少 {missing}；實際欄位：{list(df.columns)}'
        )

    for column in VOLUME_COLUMNS + PRICE_COLUMNS:
        df[column] = to_number(df[column], strip_chars='+X ')

    df['日期'] = pd.to_datetime(df['日期'].map(roc_slash_to_iso))
    df['股票代號'] = str(stock_no)

    ordered = KEY + [c for c in df.columns if c not in KEY]
    return df[ordered]


def run(stock_no, start, end, out_dir='data'):
    """抓取 [start, end] 期間的日成交資料並寫入 CSV，回傳輸出路徑。"""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    # API 以月為單位，因此先把區間對齊到月初再逐月抓，最後才裁切回實際區間。
    # 注意：pandas 3.0 已移除 freq='M'，月初要用 'MS'。
    months = pd.date_range(
        start.to_period('M').to_timestamp(),
        end.to_period('M').to_timestamp(),
        freq='MS',
    )

    frames = []
    with requests.Session() as session:
        for index, month in enumerate(months):
            if index:
                time.sleep(REQUEST_INTERVAL)
            try:
                frames.append(parse(fetch_month(stock_no, month, session), stock_no))
                log.info('已取得 %s', month.strftime('%Y-%m'))
            except NoDataError as exc:
                log.info('%s 無資料，略過（%s）', month.strftime('%Y-%m'), exc)

    if not frames:
        raise NoDataError(f'{stock_no} 在 {start:%Y-%m-%d}～{end:%Y-%m-%d} 沒有取得任何資料')

    df = pd.concat(frames, ignore_index=True)
    df = df[(df['日期'] >= start) & (df['日期'] <= end)]

    path = Path(out_dir) / f'twse_{stock_no}.csv'
    save_csv(df, path, KEY)
    return path
