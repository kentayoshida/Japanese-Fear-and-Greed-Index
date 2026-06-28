#!/usr/bin/env python3
"""J-Quants 実レスポンスのスキーマ検証スクリプト（手元で1回だけ実行）。

目的：契約後の実 API で、エンドポイント名・カラム名・PutCallDivision の値などを
確認し、providers の結線を「推測ではなく事実」に基づいて確定するため。
※ 秘密情報（トークン/パスワード）は出力しない。市場データのサンプルのみ表示する。

使い方（ローカル・オープンネットワーク環境）:
  cd engine
  pip install -r requirements.txt
  # いずれかの認証情報を環境変数で
  export JQUANTS_MAIL_ADDRESS='...'      # 推奨（cron でも durable）
  export JQUANTS_PASSWORD='...'
  #   または
  export JQUANTS_REFRESH_TOKEN='...'
  python scripts/jquants_probe.py

出力（エンドポイントごとのカラム名・サンプル行・計算例）をそのまま貼ってください。
それを基に #1/#5/#7 の provider を確定します。
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
    """直近の平日（祝日は考慮しないので数日戻す）。"""
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
        print("ERROR: 認証情報が未設定です。JQUANTS_MAIL_ADDRESS+JQUANTS_PASSWORD "
              "もしくは JQUANTS_REFRESH_TOKEN を環境変数に設定してください。", file=sys.stderr)
        return 1

    client = JQuantsClient()
    try:
        client._ensure_id_token()  # noqa: SLF001
        print("認証 OK（idToken を取得しました。トークンは表示しません）")
    except Exception as exc:  # noqa: BLE001
        print(f"認証 失敗: {exc}", file=sys.stderr)
        return 1

    probe_date = _recent_business_date()
    from_date = (datetime.utcnow() - timedelta(days=20)).strftime("%Y-%m-%d")

    # ---- #1 指数四本値（日経225 = code 0000） ----
    _hr("[#1] /indices  (日経225 指数四本値, code=0000)")
    try:
        rows = client._get("/indices", {"code": "0000", "from": from_date})  # noqa: SLF001
        df = pd.DataFrame(rows)
        print(f"件数: {len(df)}  カラム: {list(df.columns)}")
        if len(df):
            print("末尾2行:")
            print(df.tail(2).to_string())
    except Exception as exc:  # noqa: BLE001
        print(f"取得失敗: {exc}")

    # ---- #5 日経225オプション四本値（出来高 → Put/Call） ----
    _hr(f"[#5] /option/index_option  (date={probe_date})")
    try:
        rows = client._get("/option/index_option", {"date": probe_date})  # noqa: SLF001
        df = pd.DataFrame(rows)
        print(f"件数: {len(df)}  カラム: {list(df.columns)}")
        if len(df):
            print("先頭1行（全カラム）:")
            print(df.head(1).to_string())
            for col in ("PutCallDivision", "Volume", "WholeDayVolume"):
                if col in df.columns:
                    print(f"  {col} のユニーク値（先頭）: {df[col].astype(str).unique()[:8]}")
            # P/C 計算例（PutCallDivision 1=Put,2=Call と仮定）
            if "PutCallDivision" in df.columns:
                vol_col = "Volume" if "Volume" in df.columns else (
                    "WholeDayVolume" if "WholeDayVolume" in df.columns else None)
                if vol_col:
                    v = pd.to_numeric(df[vol_col], errors="coerce").fillna(0)
                    pcd = df["PutCallDivision"].astype(str)
                    put = v[pcd == "1"].sum()
                    call = v[pcd == "2"].sum()
                    print(f"  仮定(1=Put,2=Call) put_vol={put} call_vol={call} "
                          f"P/C={put/call if call else float('nan'):.4f}  (vol_col={vol_col})")
    except Exception as exc:  # noqa: BLE001
        print(f"取得失敗: {exc}")

    # ---- #7 業種別空売り比率 ----
    _hr(f"[#7] /markets/short_selling  (from={from_date})")
    try:
        rows = client._get("/markets/short_selling", {"from": from_date})  # noqa: SLF001
        df = pd.DataFrame(rows)
        print(f"件数: {len(df)}  カラム: {list(df.columns)}")
        if len(df):
            print("先頭1行:")
            print(df.head(1).to_string())
            print(f"  Date のユニーク数: {df['Date'].nunique() if 'Date' in df.columns else 'N/A'}")
    except Exception as exc:  # noqa: BLE001
        print(f"取得失敗: {exc}")

    _hr("完了")
    print("上記の出力（カラム名・サンプル行・P/C計算例）をそのまま共有してください。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
