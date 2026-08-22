"""with_retry 的重試與錯誤分類測試。

重點在於「重試耗盡後拋出什麼」：來源端與網路問題要能和程式壞掉區分開，
否則排程無法只對真正需要修的錯誤顯示紅燈。base_delay=0 讓測試不必真的等。
"""
import pytest

from scrapers.errors import (NoDataError, ScraperError, SourceUnavailableError,
                             UnexpectedPageError)
from scrapers.retry import with_retry


def _counter(exc=None, succeed_on=None):
    """回傳 (func, calls)：calls 是可變 list，長度即呼叫次數。"""
    calls = []

    def func():
        calls.append(1)
        if succeed_on is not None and len(calls) >= succeed_on:
            return 'ok'
        raise exc

    return func, calls


def test_returns_value_without_retrying_on_success():
    func, calls = _counter(succeed_on=1)
    assert with_retry(func, base_delay=0) == 'ok'
    assert len(calls) == 1


def test_retries_then_succeeds():
    func, calls = _counter(exc=ConnectionError('暫時斷線'), succeed_on=3)
    assert with_retry(func, attempts=3, base_delay=0) == 'ok'
    assert len(calls) == 3


def test_network_failure_becomes_source_unavailable():
    """連線類例外重試耗盡後包成 SourceUnavailableError，並保留原因。"""
    original = ConnectionError('連線被拒')
    func, calls = _counter(exc=original)

    with pytest.raises(SourceUnavailableError) as info:
        with_retry(func, attempts=3, base_delay=0, description='測試來源')

    assert len(calls) == 3
    assert info.value.__cause__ is original
    assert '測試來源' in str(info.value)


def test_no_data_error_is_not_retried_and_propagates_unchanged():
    """NoDataError 是「確定沒有資料」，再試也沒用，且不該被重新分類。"""
    func, calls = _counter(exc=NoDataError('休市'))

    with pytest.raises(NoDataError):
        with_retry(func, attempts=3, base_delay=0)

    assert len(calls) == 1


def test_unexpected_page_error_is_not_disguised_as_source_problem():
    """關鍵分界：期交所改了契約代碼會從 fetch 閉包拋 UnexpectedPageError。

    若被包成 SourceUnavailableError，排程會顯示綠燈，真正的破壞就被吃掉了。
    """
    func, calls = _counter(exc=UnexpectedPageError('找不到契約代碼'))

    with pytest.raises(UnexpectedPageError):
        with_retry(func, attempts=3, base_delay=0)

    assert len(calls) == 3


def test_source_unavailable_is_a_scraper_error():
    """呼叫端若只想攔「預期內的錯誤」，仍然只需要接 ScraperError。"""
    assert issubclass(SourceUnavailableError, ScraperError)
