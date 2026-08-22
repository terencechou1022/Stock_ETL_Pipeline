"""台股籌碼儀表板（Streamlit）。

把三個資料源放在同一頁：股價（證交所）、期貨未平倉（期交所）、
大戶持股比例（集保）。這三條線合起來才看得出「價格在動的時候，
籌碼是往集中還是往分散走」——單看任何一個都看不出來。

啟動方式：
    streamlit run app.py
"""
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

# 以腳本位置為基準而不是工作目錄：從任何路徑啟動都能找到資料
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'data'
SAMPLE_DIR = BASE_DIR / 'sample_data'  # 納入版控的展示快照，供雲端部署使用
MAJOR_LEVEL = '1,000,001以上'          # 集保級距中的「大戶」
TOTAL_LEVEL = '合　計'                  # 注意是全形空白

st.set_page_config(page_title='台股籌碼儀表板', layout='wide')


@st.cache_data
def load(path):
    return pd.read_csv(path, encoding='utf-8-sig', parse_dates=['日期'])


def resolve_data_dir():
    """優先使用本機抓取結果，沒有才退回 repo 內的展示快照。

    data/ 不納入版本控制，所以雲端部署時只有 sample_data/ 可用；
    本機跑過爬蟲之後會自動改用最新資料，不必改任何設定。
    """
    if DATA_DIR.exists() and any(DATA_DIR.glob('*.csv')):
        return DATA_DIR, False
    return SAMPLE_DIR, True


ACTIVE_DIR, USING_SAMPLE = resolve_data_dir()


def find(pattern):
    return sorted(ACTIVE_DIR.glob(pattern))


def line_chart(wide, value_title, height=280):
    """折線圖。

    y 軸刻意不從 0 起算（`zero=False`）：大戶持股比例在 84.6～84.7% 之間變動，
    若從 0 畫起會被壓成一條直線，等於什麼都沒表達。股價同理。
    """
    # value_name 用中性名稱：若直接用 value_title，遇到同名欄位（例如「收盤價」）
    # pandas 的 melt 會因為名稱衝突而拋 ValueError。軸標題另外指定即可。
    tidy = wide.reset_index().melt('日期', var_name='項目', value_name='數值')
    encoding = {
        'x': alt.X('日期:T', title=None),
        'y': alt.Y('數值:Q', scale=alt.Scale(zero=False), title=value_title),
        'tooltip': ['日期:T', '項目:N', '數值:Q'],
    }
    if wide.shape[1] > 1:
        encoding['color'] = alt.Color('項目:N', title=None)
    return alt.Chart(tidy).mark_line().encode(**encoding).properties(height=height)


def date_range_caption(frame, label):
    return f'{label}：{frame["日期"].min():%Y-%m-%d} ～ {frame["日期"].max():%Y-%m-%d}（{len(frame)} 列）'


st.title('台股籌碼儀表板')
st.caption('資料來源：臺灣證券交易所、臺灣期貨交易所、臺灣集中保管結算所（僅供學習研究，非投資建議）')

if USING_SAMPLE:
    st.info(
        '目前顯示的是 repo 內的**展示快照**（`sample_data/`）。'
        '在本機執行爬蟲後，儀表板會自動改用 `data/` 的最新資料。',
        icon='📁',
    )

twse_files = find('twse_*.csv')
taifex_files = find('taifex_*.csv')
tdcc_files = find('tdcc_*.csv')

if not (twse_files or taifex_files or tdcc_files):
    st.warning('`data/` 目錄還沒有任何 CSV。請先執行爬蟲：')
    st.code(
        'python main.py twse   --stock 2330 --start 2024-01 --end 2024-12\n'
        'python main.py taifex --start 2024-09-01 --end 2024-09-30 --headless\n'
        'python main.py tdcc   --stock 2330 --weeks 12 --headless',
        language='bash',
    )
    st.stop()

# ── 摘要 ──────────────────────────────────────────────────────────────
columns = st.columns(3)

price = None
if twse_files:
    price = load(twse_files[0]).sort_values('日期')
    latest = price.iloc[-1]
    previous = price.iloc[-2] if len(price) > 1 else latest
    columns[0].metric(
        f'收盤價（{latest["日期"]:%Y-%m-%d}）',
        f'{latest["收盤價"]:,.1f}',
        f'{latest["收盤價"] - previous["收盤價"]:+.1f}',
    )

futures = None
if taifex_files:
    futures = load(taifex_files[0])
    open_interest = (futures.groupby('日期')['未沖銷契約量'].sum().sort_index())
    if len(open_interest):
        change = open_interest.iloc[-1] - (open_interest.iloc[-2] if len(open_interest) > 1
                                           else open_interest.iloc[-1])
        columns[1].metric(
            f'未平倉合計（{open_interest.index[-1]:%Y-%m-%d}）',
            f'{open_interest.iloc[-1]:,.0f}',
            f'{change:+,.0f}',
        )

holders = None
if tdcc_files:
    holders = load(tdcc_files[0])
    major = (holders[holders['持股/單位數分級'] == MAJOR_LEVEL]
             .set_index('日期')['占集保庫存數比例(%)'].sort_index())
    if len(major):
        change = major.iloc[-1] - (major.iloc[-2] if len(major) > 1 else major.iloc[-1])
        columns[2].metric(
            f'大戶持股比例（{major.index[-1]:%Y-%m-%d}）',
            f'{major.iloc[-1]:.2f}%',
            f'{change:+.2f} pp',
        )

# ── 圖表 ──────────────────────────────────────────────────────────────
if price is not None:
    st.subheader('股價與成交量')
    st.caption(date_range_caption(price, '證交所'))
    left, right = st.columns([2, 1])
    left.altair_chart(line_chart(price.set_index('日期')[['收盤價']], '收盤價'),
                      use_container_width=True)
    right.bar_chart(price.set_index('日期')[['成交股數']], height=280)

if futures is not None:
    st.subheader('期貨未平倉量')
    st.caption(date_range_caption(futures, '期交所') +
               '　｜　未平倉上升代表新資金進場，下降代表部位了結')
    expiries = sorted(futures['到期月份(週別)'].astype(str).unique())
    picked = st.multiselect('到期月份', expiries, default=expiries[:1])
    if picked:
        pivot = (futures[futures['到期月份(週別)'].astype(str).isin(picked)]
                 .pivot_table(index='日期', columns='到期月份(週別)',
                              values='未沖銷契約量', aggfunc='sum'))
        st.altair_chart(line_chart(pivot, '未沖銷契約量'), use_container_width=True)

if holders is not None:
    st.subheader('股權分散：大戶 vs 散戶')
    st.caption(date_range_caption(holders, '集保') +
               '　｜　大戶比例上升＝籌碼集中，通常視為籌碼面轉強')
    st.altair_chart(line_chart(major.to_frame('大戶持股比例(%)'), '大戶持股比例(%)'),
                    use_container_width=True)

    with st.expander('最新一週完整級距分布'):
        newest = holders[holders['日期'] == holders['日期'].max()]
        detail = newest[~newest['持股/單位數分級'].isin([TOTAL_LEVEL])]
        st.dataframe(
            detail[['持股/單位數分級', '人數', '股數/單位數', '占集保庫存數比例(%)']],
            hide_index=True, use_container_width=True,
        )
