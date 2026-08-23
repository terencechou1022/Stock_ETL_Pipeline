"""fetch 層的重試機制。

只在真正碰外部資源的地方使用；parse 是純函式，失敗重試沒有意義。
"""
import logging
import time

log = logging.getLogger(__name__)


def with_retry(func, attempts=3, base_delay=2, description='請求'):
    """執行 func，失敗時以遞增間隔重試。

    NoDataError 不重試——那是「確定沒有資料」，再試也不會變出來。

    重試耗盡後依「是誰壞了」分類：已經是 ScraperError 的原樣往上拋（那是來源
    結構或程式的問題），其餘（連線、超時、driver 異常）包成 SourceUnavailableError。
    分類刻意放在最後一次失敗才做，重試次數與行為完全不變。
    """
    from scrapers.errors import NoDataError, ScraperError, SourceUnavailableError

    for attempt in range(1, attempts + 1):
        try:
            return func()
        except NoDataError:
            raise
        except Exception as exc:
            if attempt == attempts:
                log.error('%s 重試 %d 次後仍失敗：%s', description, attempts, exc)
                if isinstance(exc, ScraperError):
                    raise
                raise SourceUnavailableError(
                    f'{description} 重試 {attempts} 次後仍失敗：{exc}') from exc
            delay = base_delay * attempt
            log.warning('%s 第 %d 次失敗（%s），%d 秒後重試', description, attempt, exc, delay)
            time.sleep(delay)
