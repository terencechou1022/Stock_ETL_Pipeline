"""多標的累積報酬比較（yfinance + matplotlib）。

這支腳本是課堂原本兩支分析程式（台股／美股報酬率分析）的重寫版，
修掉三個在新版套件下會直接壞掉或算錯的地方：

1. yfinance 0.2.51 起 auto_adjust 預設為 True，回傳已無 'Adj Close' 欄，
   原本的 data['Adj Close'] 會 KeyError。已調整後的收盤價就在 'Close'。
2. 原本逐檔 yf.download() 再 concat；新版一次傳入多個代號即可，
   回傳 MultiIndex 欄位（Price × Ticker），少一半程式碼也少一次對齊錯誤。
3. 原本把 price / price.shift(1) 稱作「日報酬」，那其實是毛比率（在 1.0 附近
   震盪），畫出來看不出東西。這裡改成真正的日報酬率與累積報酬倍數。

圖檔輸出到檔案而非 plt.show()，才能在沒有視窗的環境（CI）跑。
"""
import argparse
import sys
from pathlib import Path

import matplotlib
import pandas as pd
import yfinance as yf

matplotlib.use('Agg')          # 必須在 pyplot 匯入前設定
import matplotlib.pyplot as plt   # noqa: E402

# 沿用課堂原本的兩組標的
MARKETS = {
    'tw': {
        '2330.TW': 'TSMC',
        '2454.TW': 'MediaTek',
        '2303.TW': 'UMC',
        '2317.TW': 'Foxconn',
        '2382.TW': 'Quanta',
        '3231.TW': 'Wistron',
    },
    'us': {
        'AAPL': 'Apple',
        'NVDA': 'NVIDIA',
        'AMD': 'AMD',
        'MSFT': 'Microsoft',
        'INTC': 'Intel',
    },
}


def load_prices(tickers, start, end=None):
    """下載並回傳已調整收盤價（欄名換成好讀的公司名）。"""
    raw = yf.download(list(tickers), start=start, end=end,
                      auto_adjust=True, progress=False)
    if raw.empty:
        raise SystemExit('下載不到任何資料，請確認代號與日期區間')

    close = raw['Close']            # auto_adjust=True，這已經是調整後價格
    return close.rename(columns=tickers).dropna(how='all')


def cumulative_return(prices):
    """累積報酬倍數：以區間第一天為 1.0。"""
    return prices / prices.iloc[0]


def plot(frame, title, ylabel, path):
    axes = frame.plot(figsize=(11, 6), linewidth=1.2)
    axes.set_title(title)
    axes.set_ylabel(ylabel)
    axes.set_xlabel('')
    axes.grid(alpha=0.3)
    axes.legend(loc='upper left', fontsize=9)
    axes.figure.tight_layout()
    axes.figure.savefig(path, dpi=120)
    plt.close(axes.figure)
    print(f'已輸出 {path}')


def main():
    # Windows 終端機預設 cp950，中文摘要會亂碼
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')

    parser = argparse.ArgumentParser(description='多標的累積報酬比較')
    parser.add_argument('--market', choices=sorted(MARKETS), default='tw',
                        help='tw=台股半導體/代工，us=美股半導體（預設：tw）')
    parser.add_argument('--start', default='2020-01-01', help='起始日期')
    parser.add_argument('--end', default=None, help='結束日期（預設：至今）')
    parser.add_argument('--out', default='analysis/output', help='圖檔輸出目錄')
    args = parser.parse_args()

    tickers = MARKETS[args.market]
    prices = load_prices(tickers, args.start, args.end)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    label = args.market.upper()
    span = f'{prices.index[0]:%Y-%m-%d} ~ {prices.index[-1]:%Y-%m-%d}'

    plot(prices, f'{label} Adjusted Close ({span})', 'Price',
         out_dir / f'{args.market}_price.png')
    plot(cumulative_return(prices), f'{label} Cumulative Return ({span})',
         'Growth of 1.0', out_dir / f'{args.market}_cumulative_return.png')

    summary = pd.DataFrame({
        '累積報酬倍數': cumulative_return(prices).iloc[-1].round(3),
        '年化波動度': (prices.pct_change().std() * (252 ** 0.5)).round(3),
    }).sort_values('累積報酬倍數', ascending=False)
    print(f'\n區間 {span}')
    print(summary.to_string())


if __name__ == '__main__':
    main()
