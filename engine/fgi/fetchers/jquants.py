"""J-Quants API v2 クライアント（一次バックボーン）。仕様 §1-A / §2。

v2 認証（2026/6/1 に v1 廃止）：
  - ダッシュボード発行の **APIキー**を `x-api-key` ヘッダーに載せる（1段階・トークン交換不要）
  - APIキー自体に有効期限なし（無人運用に適する）
  - ベースURL: https://api.jquants.com/v2

認証情報は環境変数 / GitHub Secrets で渡す（コードに直書きしない §6）：
  - 推奨: JQUANTS_API_KEY
  - 後方互換: JQUANTS_REFRESH_TOKEN（v1 時代の名前。値が APIキーならこちらでも動く）

提供エンドポイント（Phase 2/3 で使用）：
  - 指数四本値        : /indices/bars/daily              （→ #1 モメンタムの指数価格）
  - 日経225オプション : /derivatives/bars/daily/options/225（出来高 → #5 Put/Call）
  - 業種別空売り比率  : /markets/short-ratio             （→ #7 空売り比率）

レスポンスは {"data": [...], "pagination_key": "..."} 形式。pagination_key で続きを取得。
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pandas as pd
import requests

DEFAULT_BASE_URL = "https://api.jquants.com/v2"


class JQuantsError(RuntimeError):
    pass


def _api_key() -> str | None:
    return os.environ.get("JQUANTS_API_KEY") or os.environ.get("JQUANTS_REFRESH_TOKEN")


class JQuantsClient:
    """J-Quants v2 クライアント。APIキーを x-api-key ヘッダーで送るだけ。"""

    def __init__(self, base_url: str | None = None, timeout: int = 30) -> None:
        self.base_url = (base_url or os.environ.get("JQUANTS_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.api_key = _api_key()

    @staticmethod
    def is_configured() -> bool:
        """APIキーが環境変数にあるか。無ければ呼び出し側で stale 扱い。"""
        return bool(_api_key())

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise JQuantsError(
                "J-Quants APIキー未設定（JQUANTS_API_KEY もしくは JQUANTS_REFRESH_TOKEN を設定）"
            )
        return {"x-api-key": self.api_key}

    def _get(self, path: str, params: dict | None = None) -> list[dict]:
        """data 配列をページネーション対応で取得して連結する。"""
        headers = self._headers()
        params = {k: v for k, v in (params or {}).items() if v is not None}
        out: list[dict] = []
        while True:
            resp = requests.get(
                f"{self.base_url}{path}", headers=headers, params=params, timeout=self.timeout
            )
            resp.raise_for_status()
            body = resp.json()
            data = body.get("data")
            if data is None:
                # 念のため：最初に見つかった list 値を data とみなす
                data = next((v for v in body.values() if isinstance(v, list)), [])
            out.extend(data)
            pagination = body.get("pagination_key")
            if not pagination:
                break
            params["pagination_key"] = pagination
        return out

    # ----- データ取得 -------------------------------------------------------
    @staticmethod
    def _find_col(columns, *candidates: str) -> str | None:
        """候補名（完全一致→小文字一致→部分一致）でカラムを探す。v2 の表記揺れに頑健化。"""
        cols = list(columns)
        lower = {c.lower(): c for c in cols}
        for cand in candidates:
            if cand in cols:
                return cand
            if cand.lower() in lower:
                return lower[cand.lower()]
        for cand in candidates:
            for c in cols:
                if cand.lower() in c.lower():
                    return c
        return None

    def index_close(self, code: str = "0000", from_date: str | None = None,
                    to_date: str | None = None) -> pd.Series:
        """指数終値系列。code='0000' は日経平均（#1 モメンタムの素材）。

        /indices/bars/daily から取得。Date と Close を頑健に検出して Series を返す。
        """
        rows = self._get("/indices/bars/daily", {"code": code, "from": from_date, "to": to_date})
        if not rows:
            raise JQuantsError(f"index_close: no data for code={code}")
        df = pd.DataFrame(rows)
        date_col = self._find_col(df.columns, "Date")
        # v2 の指数四本値は OHLC が略記（O/H/L/C）。Close/C/AdjustmentClose の順で検出。
        close_col = self._find_col(df.columns, "Close", "C", "AdjustmentClose")
        if not date_col or not close_col:
            raise JQuantsError(
                f"index_close: Date/Close 列が見つからない columns={list(df.columns)}"
            )
        s = pd.Series(
            pd.to_numeric(df[close_col], errors="coerce").values,
            index=pd.to_datetime(df[date_col]),
        ).dropna().sort_index()
        return s

    def equity_adj_close(self, code: str, from_date: str | None = None,
                         to_date: str | None = None) -> pd.Series:
        """個別銘柄/ETF の調整後終値（AdjC）系列。#8 の債券レッグ（国債ETF）等に使う。

        /equities/bars/daily から取得。調整後終値はトータルリターン近似（分配・分割調整済み）。
        """
        rows = self._get("/equities/bars/daily", {"code": code, "from": from_date, "to": to_date})
        if not rows:
            raise JQuantsError(f"equity_adj_close: no data for code={code}")
        df = pd.DataFrame(rows)
        date_col = self._find_col(df.columns, "Date")
        # 調整後終値を優先（AdjC）。無ければ素の終値。
        close_col = self._find_col(df.columns, "AdjC", "AdjustmentClose", "Close", "C")
        if not date_col or not close_col:
            raise JQuantsError(
                f"equity_adj_close: Date/AdjC 列が見つからない columns={list(df.columns)}"
            )
        s = pd.Series(
            pd.to_numeric(df[close_col], errors="coerce").values,
            index=pd.to_datetime(df[date_col]),
        ).dropna().sort_index()
        return s

    def index_option_chain(self, date: str) -> pd.DataFrame:
        """日経225オプション四本値（指定日・全ストライク）。#5 Put/Call の素材。

        /derivatives/bars/daily/options/225 から取得。
        ※ 出来高カラム名・PutCallDivision の値は実レスポンスで確認のうえ derive 側で扱う。
        """
        rows = self._get("/derivatives/bars/daily/options/225", {"date": date})
        if not rows:
            raise JQuantsError(f"index_option_chain: no data for date={date}")
        return pd.DataFrame(rows)

    def _discover_short_sectors(self) -> list[str]:
        """直近の営業日から空売り比率の業種コード(S33)一覧を取得する。"""
        from datetime import datetime, timedelta, timezone as _tz

        jst_now = datetime.now(_tz.utc) + timedelta(hours=9)
        for back in range(1, 10):
            day = jst_now - timedelta(days=back)
            if day.weekday() >= 5:
                continue
            rows = self._get("/markets/short-ratio", {"date": day.strftime("%Y-%m-%d")})
            if rows:
                return sorted({str(r["S33"]) for r in rows if "S33" in r})
        raise JQuantsError("short-ratio: 業種コードの探索に失敗")

    def short_ratio_market_df(self, from_date: str, to_date: str | None = None) -> pd.DataFrame:
        """市場全体の空売り比率算出用に、全業種×期間レンジの行を取得して連結する。

        /markets/short-ratio は from/to を s33 指定時のみ受け付けるため、業種ごとに
        レンジ取得して縦結合する（業種数ぶんの呼び出し＝約34回）。
        """
        sectors = self._discover_short_sectors()
        frames: list[pd.DataFrame] = []
        for s33 in sectors:
            rows = self._get("/markets/short-ratio", {"s33": s33, "from": from_date, "to": to_date})
            if rows:
                frames.append(pd.DataFrame(rows))
        if not frames:
            raise JQuantsError("short_ratio_market_df: no data")
        return pd.concat(frames, ignore_index=True)


def now_jst_date() -> str:
    """JST の本日日付（YYYY-MM-DD）。"""
    return datetime.now(timezone.utc).astimezone(timezone(__import__("datetime").timedelta(hours=9))).strftime("%Y-%m-%d")
