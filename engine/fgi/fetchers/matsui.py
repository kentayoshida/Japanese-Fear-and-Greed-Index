"""#6 信用評価損益率（買い方）を松井証券「投資指標（店内）」から取得。仕様 §2。

このページは値が生HTML・単独XHRに存在せず（Network検索で該当なし）、描画後の DOM に
のみ現れるため、ヘッドレスブラウザ（Playwright）でレンダリングして抽出する。
ToS 確認済み（前営業日更新分は利用制限なし・Ken確認）。取得は日次1回に限ること。

抽出対象：「信用残速報」テーブルの『買い残』行の『評価損益率(%)』セル（例 -3.856）。

JS描画が遅く wait_for_selector が時折 Timeout するため、試行ごとに新しいコンテキストで
待ち時間を延ばしながら数回リトライする（tier-1 の実測点＝較正の要のため取りこぼしを減らす）。
"""

from __future__ import annotations

import re
import time

from .base import FetchError

URL = "https://www.matsui.co.jp/market/stock/netstock-info/"

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _parse_pl(text: str | None) -> float:
    """『買い残』行の評価損益率セル文字列から数値(%)を取り出して検証する。"""
    if not text:
        raise FetchError("margin_pl: 評価損益率セルを取得できず")
    m = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    if not m:
        raise FetchError(f"margin_pl: 値を解釈できず '{text}'")
    value = float(m.group())
    if not (-60.0 <= value <= 60.0):  # 信用評価損益率の常識的レンジ
        raise FetchError(f"margin_pl: 想定外の値 {value}")
    return value


def _scrape_once(browser, selector_timeout_ms: int, goto_timeout_ms: int) -> float:
    """1回ぶんの取得。新規コンテキストで開いて『買い残』行の評価損益率(%)を返す。"""
    # ※ 松井ページは分析タグが常時通信し networkidle に到達しないため使わない。
    #   DOM 構築後にテーブル行の出現を明示的に待つ。
    context = browser.new_context(user_agent=_UA)
    try:
        page = context.new_page()
        page.goto(URL, wait_until="domcontentloaded", timeout=goto_timeout_ms)
        # 「買い残」を含む行（信用残速報テーブル）が描画されるまで待つ
        page.wait_for_selector("tr:has-text('買い残')", timeout=selector_timeout_ms)
        row = page.locator("tr", has_text="買い残").first
        # 買い残行の td: [0]=信用残(億円), [1]=評価損益率(%)
        text = row.locator("td").nth(1).inner_text()
        return _parse_pl(text)
    finally:
        context.close()


def fetch_margin_pl_buy(
    timeout_ms: int = 60000, attempts: int = 3, selector_timeout_ms: int = 45000
) -> float:
    """松井『投資指標(店内)』の信用評価損益率（買い方, %）を返す。

    attempts 回まで再試行し、試行ごとにセレクタ待ちを延長（描画遅延に頑健化）。
    すべて失敗したら最後のエラーを添えて FetchError を送出する。
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        raise FetchError(f"margin_pl: playwright 未導入（{exc}）") from exc

    last_err: Exception | None = None
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for attempt in range(1, attempts + 1):
                # 試行が進むごとに待ち時間を延長（例 45s → 60s → 75s）
                sel_timeout = selector_timeout_ms + (attempt - 1) * 15000
                try:
                    return _scrape_once(browser, sel_timeout, timeout_ms)
                except FetchError as exc:
                    last_err = exc
                except Exception as exc:  # noqa: BLE001  Timeout 等
                    last_err = exc
                if attempt < attempts:
                    time.sleep(2 * attempt)  # 2s, 4s のバックオフ
        finally:
            browser.close()

    raise FetchError(f"margin_pl: {attempts}回試行して取得失敗（最後のエラー: {last_err}）")
