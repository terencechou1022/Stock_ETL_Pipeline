"""台股市場資料爬蟲 CLI。

三個資料源各自一個子命令：

    python main.py twse   --stock 2330 --start 2024-01 --end 2024-03
    python main.py taifex --start 2024-09-01 --end 2024-09-10 --contract TX
    python main.py tdcc   --stock 2330 --weeks 5
"""
import argparse
import logging
import re
import sys

import pandas as pd

from scrapers import taifex, tdcc, twse
from scrapers.errors import ScraperError

MONTH_PATTERN = re.compile(r'^\d{4}-\d{2}$')
LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR']


def _use_utf8_output():
    """Windows 終端機預設是 cp950，中文與 ▲▼ 等符號會亂碼或直接拋錯。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')


def parse_date(text, is_end=False):
    """接受 YYYY-MM 或 YYYY-MM-DD。

    只給到月份時，起始日視為月初、結束日視為月底——否則 `--end 2024-03`
    會被當成 3/1，整個 3 月的資料都被裁掉。
    """
    timestamp = pd.Timestamp(text)
    if is_end and MONTH_PATTERN.match(text.strip()):
        return timestamp + pd.offsets.MonthEnd(0)
    return timestamp


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--out', default='data', help='CSV 輸出目錄（預設：data）')
    common.add_argument('--log-level', default='INFO', choices=LOG_LEVELS,
                        help='紀錄層級（預設：INFO）')

    parser = argparse.ArgumentParser(
        prog='main.py',
        description='台股市場資料爬蟲：證交所股價、期交所籌碼、集保股權分散',
    )
    sources = parser.add_subparsers(dest='source', required=True, metavar='來源')

    p_twse = sources.add_parser('twse', parents=[common],
                                help='證交所 個股每日成交資訊（requests + JSON API）')
    p_twse.add_argument('--stock', default='2330', help='股票代號（預設：2330）')
    p_twse.add_argument('--start', required=True, help='起始 YYYY-MM 或 YYYY-MM-DD')
    p_twse.add_argument('--end', required=True, help='結束 YYYY-MM 或 YYYY-MM-DD')

    p_taifex = sources.add_parser('taifex', parents=[common],
                                  help='期交所 每日行情（Selenium）')
    p_taifex.add_argument('--start', required=True, help='起始 YYYY-MM-DD')
    p_taifex.add_argument('--end', required=True, help='結束 YYYY-MM-DD')
    p_taifex.add_argument('--contract', default=taifex.DEFAULT_CONTRACT,
                          help='契約代碼，TX=臺股期貨（預設：TX）')
    p_taifex.add_argument('--session', default='一般交易時段',
                          choices=list(taifex.SESSIONS), help='交易時段')
    p_taifex.add_argument('--headless', action='store_true', help='不開啟瀏覽器視窗')

    p_tdcc = sources.add_parser('tdcc', parents=[common],
                                help='集保 股權分散表（Selenium）')
    p_tdcc.add_argument('--stock', default='2330', help='股票代號（預設：2330）')
    p_tdcc.add_argument('--weeks', type=int, default=5, help='往回抓幾週（預設：5）')
    p_tdcc.add_argument('--headless', action='store_true', help='不開啟瀏覽器視窗')

    return parser


def main(argv=None):
    _use_utf8_output()
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=args.log_level,
        format='%(asctime)s %(levelname)-7s %(message)s',
        datefmt='%H:%M:%S',
    )

    try:
        if args.source == 'twse':
            path = twse.run(args.stock, parse_date(args.start),
                            parse_date(args.end, is_end=True), args.out)
        elif args.source == 'taifex':
            path = taifex.run(parse_date(args.start), parse_date(args.end, is_end=True),
                              contract=args.contract, session=args.session,
                              out_dir=args.out, headless=args.headless)
        else:
            path = tdcc.run(args.stock, weeks=args.weeks, out_dir=args.out,
                            headless=args.headless)
    except (ScraperError, ValueError) as exc:
        logging.error('抓取失敗：%s', exc)
        return 1

    print(f'完成：{path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
