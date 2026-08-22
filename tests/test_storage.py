"""CSV 落地層的測試：重點在「可重複執行」。"""
import pandas as pd

from scrapers.storage import ENCODING, save_csv


def _frame(dates, value):
    return pd.DataFrame({
        '日期': pd.to_datetime(dates),
        '股票代號': ['2330'] * len(dates),
        '收盤價': [value] * len(dates),
    })


def test_save_csv_writes_iso_dates(tmp_path):
    path = tmp_path / 'out.csv'
    total, added = save_csv(_frame(['2024-01-02'], 593.0), path, ['日期', '股票代號'])

    assert (total, added) == (1, 1)
    assert path.read_text(encoding=ENCODING).splitlines()[1].startswith('2024-01-02')


def test_save_csv_is_idempotent(tmp_path):
    path = tmp_path / 'out.csv'
    frame = _frame(['2024-01-02', '2024-01-03'], 593.0)

    save_csv(frame, path, ['日期', '股票代號'])
    total, added = save_csv(frame, path, ['日期', '股票代號'])

    # 同一批資料寫兩次不應該產生重複列
    assert (total, added) == (2, 0)


def test_save_csv_merges_and_keeps_latest_value(tmp_path):
    path = tmp_path / 'out.csv'
    save_csv(_frame(['2024-01-02'], 593.0), path, ['日期', '股票代號'])
    save_csv(_frame(['2024-01-02'], 600.0), path, ['日期', '股票代號'])

    result = pd.read_csv(path, encoding=ENCODING)
    assert len(result) == 1
    assert float(result.loc[0, '收盤價']) == 600.0   # keep='last'


def test_save_csv_appends_new_dates_in_order(tmp_path):
    path = tmp_path / 'out.csv'
    save_csv(_frame(['2024-01-03'], 578.0), path, ['日期', '股票代號'])
    total, added = save_csv(_frame(['2024-01-02'], 593.0), path, ['日期', '股票代號'])

    result = pd.read_csv(path, encoding=ENCODING)
    assert (total, added) == (2, 1)
    assert list(result['日期']) == ['2024-01-02', '2024-01-03']   # 依 key 排序
