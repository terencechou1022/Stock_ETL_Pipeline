"""測試共用設定。

這裡刻意封鎖所有網路連線：parse 層是純函式，測試若不小心碰到網路就該失敗。
這也是「fetch 與 parse 分離」這個設計的驗證方式——整套測試離線可跑。
"""
import socket
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / 'fixtures'


def read_fixture(name):
    return (FIXTURES / name).read_text(encoding='utf-8')


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def _blocked(*args, **kwargs):
        raise RuntimeError('測試不應該連線網路：parse 層必須是純函式')

    monkeypatch.setattr(socket, 'socket', _blocked)
    monkeypatch.setattr(socket, 'create_connection', _blocked)
