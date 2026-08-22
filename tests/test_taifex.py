"""期交所 parse 的測試：全部使用離線 HTML 樣本。"""
import pandas as pd
import pytest

from scrapers.errors import NoDataError, UnexpectedPageError
from scrapers.taifex import parse, trading_days
from tests.conftest import read_fixture

GENERAL = 'taifex_TX_general_20240903.html'
AFTER_HOURS = 'taifex_TX_afterhours_20240902.html'
HOLIDAY = 'taifex_TX_holiday_20240228.html'


def test_parse_drops_subtotal_row():
    df = parse(read_fixture(GENERAL))
    # 頁面上有 6 個到期月份加 1 列「小計」
    assert len(df) == 6
    assert not df['契約'].isna().any()


def test_parse_extracts_date_from_page():
    df = parse(read_fixture(GENERAL))
    assert set(df['日期']) == {pd.Timestamp('2024-09-03')}


def test_parse_keeps_expiry_month_as_text():
    df = parse(read_fixture(GENERAL))
    # read_html 會把 202409 讀成 float，若不處理會變成 '202409.0'
    assert df['到期月份(週別)'].iloc[0] == '202409'


def test_parse_strips_updown_arrows():
    df = parse(read_fixture(GENERAL))
    assert df['漲跌價'].iloc[0] == -142.0      # 來源為 '▼-142'
    assert df['漲跌%'].iloc[0] == -0.64        # 來源為 '▼-0.64%'


def test_parse_handles_general_session_columns():
    df = parse(read_fixture(GENERAL))
    # 一般交易時段把成交量拆成三欄，並提供未沖銷契約量（籌碼分析的關鍵欄位）
    assert {'盤後交易時段成交量', '一般交易時段成交量', '合計成交量'} <= set(df.columns)
    assert df['未沖銷契約量'].iloc[0] == 82306


def test_parse_handles_after_hours_session_columns():
    df = parse(read_fixture(AFTER_HOURS))
    # 盤後時段只有單一「成交量」欄，parse 不應該假設固定欄位集合
    assert '成交量' in df.columns
    assert '合計成交量' not in df.columns
    assert set(df['日期']) == {pd.Timestamp('2024-09-02')}


def test_parse_raises_when_table_structure_changes():
    with pytest.raises(UnexpectedPageError):
        parse('<html><body><table><tr><td>無關表格</td></tr></table></body></html>')


def test_parse_raises_nodata_for_real_market_holiday():
    # 真實休市日頁面（2024-02-28 和平紀念日）只有「查無資料」，沒有任何表格。
    # 這必須是 NoDataError 而不是結構錯誤，否則整批作業會因為一天休市中斷。
    with pytest.raises(NoDataError):
        parse(read_fixture(HOLIDAY))


def test_trading_days_skips_weekends():
    days = list(trading_days('2024-09-06', '2024-09-09'))
    assert [d.strftime('%Y-%m-%d') for d in days] == ['2024-09-06', '2024-09-09']


def test_trading_days_skips_public_holiday():
    # 2024-02-28 和平紀念日
    days = [d.strftime('%Y-%m-%d') for d in trading_days('2024-02-27', '2024-02-29')]
    assert '2024-02-28' not in days
    assert days == ['2024-02-27', '2024-02-29']
