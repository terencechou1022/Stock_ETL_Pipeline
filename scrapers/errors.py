"""爬蟲共用的例外型別。"""


class ScraperError(Exception):
    """本套件所有預期內錯誤的基底類別。"""


class NoDataError(ScraperError):
    """查詢成功但該區間沒有資料（例如休市日、尚未公布）。

    這是預期會發生的情況，呼叫端應該跳過並繼續，而不是中斷整批作業。
    """


class UnexpectedPageError(ScraperError):
    """頁面結構與預期不符，通常代表來源網站改版了。

    刻意設計成帶著「實際看到什麼」的訊息拋出，避免安靜地解析到錯誤的表格。
    """


class SourceUnavailableError(ScraperError):
    """連不上來源，或來源回了根本無法使用的回應（被擋、超時、非預期格式）。

    與 UnexpectedPageError 的差別在於「是誰壞了」：這個是來源端或網路的狀況，
    重試也救不回來，但不代表本地程式有問題。排程碰到這種情形不該顯示紅燈，
    否則真正的程式錯誤會被淹沒在雲端 IP 被擋的雜訊裡。
    """
