"""集保 parse 的測試：全部使用離線 HTML 樣本。"""
import pandas as pd
import pytest

from scrapers.errors import UnexpectedPageError
from scrapers.tdcc import parse
from tests.conftest import read_fixture

FIXTURE = 'tdcc_2330_20260821.html'


def test_parse_returns_all_holding_levels():
    df = parse(read_fixture(FIXTURE), '2330')
    assert len(df) == 17          # 15 個級距 + 差異數調整 + 合計
    assert df['持股/單位數分級'].iloc[0] == '1-999'


def test_parse_converts_cjk_roc_date():
    df = parse(read_fixture(FIXTURE), '2330')
    # 來源是「資料日期：115年08月21日」，和證交所的 '113/09/02' 格式不同
    assert set(df['日期']) == {pd.Timestamp('2026-08-21')}


def test_parse_extracts_major_holder_ratio():
    df = parse(read_fixture(FIXTURE), '2330')
    major = df[df['持股/單位數分級'] == '1,000,001以上'].iloc[0]
    assert major['占集保庫存數比例(%)'] == 84.71
    assert major['股數/單位數'] == 21968307511


def test_parse_finds_table_by_column_not_by_index():
    html = read_fixture(FIXTURE)
    # 在前面插入一個無關表格：若沿用寫死的 table[1] 就會抓錯資料
    injected = html.replace('<body>', '<body><table><tr><th>干擾</th></tr></table>', 1)
    assert parse(injected, '2330').equals(parse(html, '2330'))


def test_parse_raises_when_target_table_missing():
    with pytest.raises(UnexpectedPageError, match='持股/單位數分級'):
        parse('<html><body><table><tr><td>無關</td></tr></table></body></html>', '2330')
