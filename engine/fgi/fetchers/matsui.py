"""#6 信用評価損益率（買い方）を松井証券「投資指標（店内）」から取得。仕様 §2。

このページは値が生HTML・単独XHRに存在せず（Network検索で該当なし）、描画後の DOM に
のみ現れるため、ヘッドレスブラウザ（Playwright）でレンダリングして抽出する。
ToS 確認済み（前営業日更新分は利用制限なし・Ken確認）。取得は日次1回に限ること。

抽出対象：「信用残速報」テーブルの『買い残』行の『評価損益率(%)』セル（例 -3.856）。
"""

from __future__ import annotations

import re

from .base import FetchError

URL = "https://www.matsui.co.jp/market/stock/netstock-info/"


def fetch_margin_pl_buy(timeout_ms: int = 60000) -> float:
    """松井『投資指標(店内)』の信用評価損益率（買い方, %）を返す。"""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        raise FetchError(f"margin_pl: playwright 未導入（{exc}）") from exc

    text = None
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ))
            page.goto(URL, wait_until="networkidle", timeout=timeout_ms)
            # 「買い残」を含む行（信用残速報テーブル）が描画されるまで待つ
            page.wait_for_selector("tr:has-text('買い残')", timeout=30000)
            row = page.locator("tr", has_text="買い残").first
            # 買い残行の td: [0]=信用残(億円), [1]=評価損益率(%)
            text = row.locator("td").nth(1).inner_text()
        finally:
            browser.close()

    if not text:
        raise FetchError("margin_pl: 評価損益率セルを取得できず")
    m = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    if not m:
        raise FetchError(f"margin_pl: 値を解釈できず '{text}'")
    value = float(m.group())
    if not (-60.0 <= value <= 60.0):  # 信用評価損益率の常識的レンジ
        raise FetchError(f"margin_pl: 想定外の値 {value}")
    return value
