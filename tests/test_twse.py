"""證交所 parse 的測試：全部使用離線 JSON 樣本。"""
import json

import pandas as pd
import pytest

from scrapers.errors import NoDataError, UnexpectedPageError
from scrapers.twse import parse
from tests.conftest import read_fixture


def _load(name):
    return json.loads(read_fixture(name))


def test_parse_returns_all_trading_days():
    df = parse(_load('twse_2330_202409.json'), '2330')
    assert len(df) == 20
    assert list(df.columns[:4]) == ['日期', '股票代號', '成交股數', '成交金額']


def test_parse_converts_roc_year_to_datetime():
    df = parse(_load('twse_2330_202409.json'), '2330')
    # 來源是民國 '113/09/02'
    assert df['日期'].dtype.kind == 'M'
    assert df['日期'].iloc[0] == pd.Timestamp('2024-09-02')


def test_parse_cleans_thousands_separator_and_sign():
    df = parse(_load('twse_2330_202409.json'), '2330')
    row = df.iloc[0]
    assert row['成交股數'] == 19272593      # 來源為 '19,272,593'
    assert row['漲跌價差'] == 4.0            # 來源為 '+4.00'
    assert row['收盤價'] == 948.0


def test_parse_adds_stock_number_as_text():
    df = parse(_load('twse_2330_202409.json'), '2330')
    assert set(df['股票代號']) == {'2330'}


def test_parse_raises_nodata_when_month_has_no_data():
    # 查詢未來月份時，API 只回傳 stat 與 total，沒有 data 鍵
    raw = _load('twse_2330_nodata.json')
    assert 'data' not in raw
    with pytest.raises(NoDataError):
        parse(raw, '2330')


def test_parse_raises_when_fields_change():
    raw = _load('twse_2330_202409.json')
    raw['fields'] = ['日期', '莫名其妙的欄位']
    raw['data'] = [['113/09/02', '1']]
    with pytest.raises(UnexpectedPageError, match='缺少'):
        parse(raw, '2330')
