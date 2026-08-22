"""CSV 落地層：把 DataFrame 併入既有檔案，去重後寫回。

刻意做成「可重複執行」（idempotent）：同一個區間跑兩次不會產生重複列，
這樣排程重跑或手動補抓都不需要先清檔案。
"""
import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

# utf-8-sig 讓 Excel 直接雙擊開啟不會亂碼（純 utf-8 在 Excel 會變成亂碼）
ENCODING = 'utf-8-sig'


def _dates_to_iso(df):
    """把 datetime 欄位轉成 YYYY-MM-DD 字串。

    落地格式統一用字串，讀回來才不會出現「字串 vs datetime 比不出相等」
    導致去重失效的問題。
    """
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].dt.strftime('%Y-%m-%d')
    return out


def save_csv(df, path, key):
    """把 df 併入 path 的既有 CSV，依 key 去重後寫回。

    參數
        df   : 要寫入的資料
        path : 目標 CSV 路徑
        key  : 用來判斷「同一筆」的欄位清單，重複時保留新抓到的

    回傳 (總列數, 新增列數)
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = _dates_to_iso(df)

    if path.exists():
        old = pd.read_csv(path, encoding=ENCODING, dtype=str)
        before = len(old)
        merged = pd.concat([old.astype(str), new.astype(str)], ignore_index=True)
    else:
        before = 0
        merged = new.astype(str)

    merged = merged.drop_duplicates(subset=key, keep='last')
    merged = merged.sort_values(key, ignore_index=True)
    merged.to_csv(path, index=False, encoding=ENCODING)

    added = len(merged) - before
    log.info('已寫入 %s：共 %d 列（新增 %d 列）', path, len(merged), added)
    return len(merged), added
