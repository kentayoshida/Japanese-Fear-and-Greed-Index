#!/usr/bin/env python3
"""松井証券「投資指標（店内）」ページの構造確認プローブ（#6 信用評価損益率）。

ToS 確認済み（前営業日更新分は利用制限なし）。ページの HTML/テキスト構造を把握して
信用評価損益率（買い方）の値の在り処を特定し、パーサを確定するための一時スクリプト。
秘密情報は扱わない。

使い方（CI もしくは手元のオープンネットワーク）:
  python scripts/matsui_probe.py
"""

from __future__ import annotations

import re
import sys

import requests

URL = "https://www.matsui.co.jp/market/stock/netstock-info/"


def main() -> int:
    try:
        resp = requests.get(URL, timeout=30, headers={"User-Agent": "Mozilla/5.0 (fgi-probe)"})
        print(f"HTTP {resp.status_code}  bytes={len(resp.content)}  url={resp.url}")
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"取得失敗: {exc}", file=sys.stderr)
        return 1

    text = resp.text

    # 「評価損益率」周辺の抜粋を表示（前後 200 文字）
    print("\n=== '評価損益率' 周辺の抜粋 ===")
    hits = [m.start() for m in re.finditer("評価損益率", text)]
    if not hits:
        print("（『評価損益率』の文字列が HTML に見つからない → JS描画/別API の可能性）")
    for i, pos in enumerate(hits[:5]):
        snippet = text[max(0, pos - 200): pos + 200]
        snippet = re.sub(r"\s+", " ", snippet)
        print(f"[{i}] …{snippet}…")

    # パーセント値らしき箇所（-?数字.数字%）を抽出
    print("\n=== パーセント値候補（先頭20件） ===")
    for m in re.findall(r"-?\d{1,2}\.\d{1,2}\s*%", text)[:20]:
        print("  ", m)

    # JSON/APIらしきURLの手がかり
    print("\n=== data/api らしき URL 断片（先頭10件） ===")
    for m in re.findall(r"[\"']([^\"']*(?:api|\.json|data)[^\"']*)[\"']", text)[:10]:
        print("  ", m)

    # 参考：<title> と最初の1500文字
    print("\n=== 先頭1500文字（構造把握用） ===")
    print(re.sub(r"\s+", " ", text[:1500]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
