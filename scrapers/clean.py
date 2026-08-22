"""欄位清理工具：三個資料源共用。

政府網站的表格都是給人看的，數值帶千分位、漲跌帶箭頭、日期用民國年，
這裡集中處理這些轉換，讓各 parse() 專注在自己的表格結構上。
"""
import re

import pandas as pd


def to_number(series, strip_chars=''):
    """把人類可讀的數值文字轉成數值，無法解析的一律變成 NaN。

    strip_chars 指定該來源特有的前後綴字元，例如證交所的 '+'／'X'
    （notes 寫明「+/-/X表示漲/跌/不比價」）或期交所的 '▲'／'▼'。
    """
    text = (
        series.astype(str)
        .str.replace(',', '', regex=False)
        .str.replace('%', '', regex=False)
    )
    if strip_chars:
        text = text.str.strip(strip_chars)
    return pd.to_numeric(text.str.strip(), errors='coerce')


def roc_slash_to_iso(text):
    """民國年斜線格式轉西元：'113/09/02' -> '2024-09-02'（證交所）。"""
    parts = str(text).strip().split('/')
    if len(parts) != 3:
        raise ValueError(f'非預期的民國日期格式：{text!r}')
    return f'{int(parts[0]) + 1911:04d}-{int(parts[1]):02d}-{int(parts[2]):02d}'


def roc_cjk_to_iso(text):
    """民國年中文格式轉西元：'115年08月21日' -> '2026-08-21'（集保）。"""
    match = re.search(r'(\d+)\s*年\s*(\d+)\s*月\s*(\d+)\s*日', str(text))
    if not match:
        raise ValueError(f'非預期的民國日期格式：{text!r}')
    year, month, day = (int(g) for g in match.groups())
    return f'{year + 1911:04d}-{month:02d}-{day:02d}'


def normalize_column(name):
    """統一欄位名稱：去掉所有空白與換行，並移除註腳用的星號。

    來源表頭常有換行（'到期 月份 (週別)'）或註腳星號（'*未沖銷契約量'），
    正規化後才能穩定地驗證欄位與寫成 CSV 標頭。
    """
    return re.sub(r'\s+', '', str(name)).lstrip('*')
