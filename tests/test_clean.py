"""欄位清理工具的測試。"""
import pandas as pd
import pytest

from scrapers.clean import normalize_column, roc_cjk_to_iso, roc_slash_to_iso, to_number


def test_roc_slash_to_iso():
    assert roc_slash_to_iso('113/09/02') == '2024-09-02'
    assert roc_slash_to_iso('99/1/5') == '2010-01-05'


def test_roc_cjk_to_iso():
    assert roc_cjk_to_iso('資料日期：115年08月21日') == '2026-08-21'
    assert roc_cjk_to_iso('113年1月5日') == '2024-01-05'


@pytest.mark.parametrize('bad', ['2024-09-02', '', '113/09'])
def test_roc_slash_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        roc_slash_to_iso(bad)


def test_normalize_column_removes_whitespace_and_footnote_star():
    assert normalize_column('到期 月份 (週別)') == '到期月份(週別)'
    assert normalize_column('*未沖銷契約量') == '未沖銷契約量'
    assert normalize_column('最後\n成交價') == '最後成交價'


def test_to_number_handles_twse_symbols():
    # 證交所 notes：「+/-/X表示漲/跌/不比價」，無成交日為 '--'
    result = to_number(pd.Series(['19,272,593', '+4.00', '-8.00', 'X0.00', '--']), '+X ')
    assert list(result[:4]) == [19272593.0, 4.0, -8.0, 0.0]
    assert pd.isna(result.iloc[4])


def test_to_number_handles_taifex_arrows():
    result = to_number(pd.Series(['▼-142', '▲+18', '▼-0.64%', '-']), '▲▼+ ')
    assert list(result[:3]) == [-142.0, 18.0, -0.64]
    assert pd.isna(result.iloc[3])
