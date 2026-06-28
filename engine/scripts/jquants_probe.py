#!/usr/bin/env python3
"""J-Quants v2 実レスポンスのスキーマ検証スクリプト（手元で1回だけ実行）。

目的：v2 実 API で、各エンドポイントのレスポンス・フィールド名（綴り）や
オプションの Put/Call 区分・出来高カラム、空売り比率のカラムを確認し、
#5/#7 の provider を「推測ではなく事実」に基づいて確定するため。
※ 秘密情報（APIキー）は出力しない。市場データのサンプルのみ表示する。

使い方（ローカル・オープンネットワーク環境）:
  cd engine
  pip install -r requirements.txt
  export JQUANTS_API_KEY='...'   # v2 ダッシュボード発行のAPIキー（JQUANTS_REFRESH_TOKEN でも可）
  python scripts/jquants_probe.py

出力（エンドポイントごとのカラム名・サンプル行・P/C計算例）をそのまま貼ってください。
それを基に #5/#7 の provider を確定します。
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ENGINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE_ROOT))

from fgi.fetchers.jquants import JQuantsClient  # noqa: E402


def _recent_business_date(days_back: int = 3) -> str:
    d = datetime.utcnow() + timedelta(hours=9)  # JST
    d = d - timedelta(days=days_back)
    while d.weekday() >= 5:  # 土日を避ける
        d -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def _hr(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def main() -> int:
    if not JQuantsClient.is_configured():
        print("ERROR: APIキー未設定。JQUANTS_API_KEY（または JQUANTS_REFRESH_TOKEN）を "
              "環境変数に設定してください。", file=sys.stderr)
        return 1

    client = JQuantsClient()
    print(f"ベースURL: {client.base_url}")
    print("認証: x-api-key（APIキーは表示しません）")

    probe_date = _recent_business_date()
    from_date = (datetime.utcnow() - timedelta(days=20)).strftime("%Y-%m-%d")

    # ---- #1 指数四本値（日経225 = code 0000） ----
    _hr("[#1] /indices/bars/daily  (code=0000, 日経225)")
    try:
        rows = client._get("/indices/bars/daily", {"code": "0000", "from": from_date})  # noqa: SLF001
        df = pd.DataFrame(rows)
        print(f"件数: {len(df)}  カラム: {list(df.columns)}")
        if len(df):
            print(df.tail(2).to_string())
    except Exception as exc:  # noqa: BLE001
        print(f"取得失敗: {exc}")

    # ---- #5 日経225オプション四本値 ----
    _hr(f"[#5] /derivatives/bars/daily/options/225  (date={probe_date})")
    try:
        rows = client._get("/derivatives/bars/daily/options/225", {"date": probe_date})  # noqa: SLF001
        df = pd.DataFrame(rows)
        print(f"件数: {len(df)}  カラム: {list(df.columns)}")
        if len(df):
            print("先頭1行（全カラム）:")
            print(df.head(1).to_string())
            # Put/Call 区分・出来高らしきカラムを推定表示
            for c in df.columns:
                lc = c.lower()
                if "put" in lc or "call" in lc or "division" in lc or "volume" in lc:
                    print(f"  候補カラム {c}: ユニーク値(先頭) {df[c].astype(str).unique()[:6]}")
    except Exception as exc:  # noqa: BLE001
        print(f"取得失敗: {exc}")

    # ---- #7 業種別空売り比率 ----
    _hr(f"[#7] /markets/short-ratio  (date={probe_date})")
    try:
        rows = client._get("/markets/short-ratio", {"date": probe_date})  # noqa: SLF001
        df = pd.DataFrame(rows)
        print(f"件数: {len(df)}  カラム: {list(df.columns)}")
        if len(df):
            print("先頭2行:")
            print(df.head(2).to_string())
    except Exception as exc:  # noqa: BLE001
        print(f"取得失敗: {exc}")

    _hr("完了")
    print("上記のカラム名・サンプル行をそのまま共有してください。#5/#7 を確定します。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
