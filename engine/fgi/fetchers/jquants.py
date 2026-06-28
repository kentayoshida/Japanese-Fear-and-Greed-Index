"""J-Quants API クライアント（一次バックボーン）。仕様 §1-A / §2。

認証情報は環境変数 / GitHub Secrets で渡す（コードに直書きしない §6）：
  - JQUANTS_REFRESH_TOKEN を直接渡す、または
  - JQUANTS_MAIL_ADDRESS + JQUANTS_PASSWORD でログインして取得

提供エンドポイント（Phase 2/3 で使用）：
  - 日経225オプション四本値（出来高 → #5 Put/Call レシオ）
  - 業種別空売り比率（→ #7 空売り比率）
  - 指数四本値（→ #1 モメンタム等の指数価格、stooq の代替）

⚠ Phase 0 の確認事項：申込画面で「Standard プランで日経225オプション四本値が
   取得可能」であることを最終確認すること（プラン別対応は JPX 側で変わりうる）。
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pandas as pd
import requests

DEFAULT_BASE_URL = "https://api.jquants.com/v1"


class JQuantsError(RuntimeError):
    pass


class JQuantsClient:
    """軽量な J-Quants クライアント。idToken をメモリにキャッシュする。"""

    def __init__(self, base_url: str | None = None, timeout: int = 30) -> None:
        self.base_url = (base_url or os.environ.get("JQUANTS_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self._id_token: str | None = None

    # ----- 認証 -------------------------------------------------------------
    @staticmethod
    def is_configured() -> bool:
        """認証情報が環境変数に揃っているか。揃っていなければ呼び出し側で stale 扱い。"""
        if os.environ.get("JQUANTS_REFRESH_TOKEN"):
            return True
        return bool(os.environ.get("JQUANTS_MAIL_ADDRESS") and os.environ.get("JQUANTS_PASSWORD"))

    def _refresh_token(self) -> str:
        token = os.environ.get("JQUANTS_REFRESH_TOKEN")
        if token:
            return token
        mail = os.environ.get("JQUANTS_MAIL_ADDRESS")
        password = os.environ.get("JQUANTS_PASSWORD")
        if not (mail and password):
            raise JQuantsError(
                "J-Quants 認証情報が未設定（JQUANTS_REFRESH_TOKEN もしくは "
                "JQUANTS_MAIL_ADDRESS+JQUANTS_PASSWORD を設定してください）"
            )
        resp = requests.post(
            f"{self.base_url}/token/auth_user",
            json={"mailaddress": mail, "password": password},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()["refreshToken"]

    def _ensure_id_token(self) -> str:
        if self._id_token:
            return self._id_token
        refresh = self._refresh_token()
        resp = requests.post(
            f"{self.base_url}/token/auth_refresh",
            params={"refreshtoken": refresh},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        self._id_token = resp.json()["idToken"]
        return self._id_token

    def _get(self, path: str, params: dict | None = None) -> list[dict]:
        """ページネーション対応の GET。data 配列を連結して返す。"""
        token = self._ensure_id_token()
        headers = {"Authorization": f"Bearer {token}"}
        params = dict(params or {})
        out: list[dict] = []
        # J-Quants はレスポンスキーがエンドポイントごとに異なるため呼び出し側で抽出
        while True:
            resp = requests.get(
                f"{self.base_url}{path}", headers=headers, params=params, timeout=self.timeout
            )
            resp.raise_for_status()
            body = resp.json()
            # data 本体キー（最初に見つかった list 値）を抽出
            data_key = next((k for k, v in body.items() if isinstance(v, list)), None)
            if data_key is not None:
                out.extend(body[data_key])
            pagination = body.get("pagination_key")
            if not pagination:
                break
            params["pagination_key"] = pagination
        return out

    # ----- データ取得（Phase 2/3 実装ポイント） -----------------------------
    def index_ohlc(self, code: str = "0000", from_date: str | None = None) -> pd.DataFrame:
        """指数四本値。code='0000' は日経平均（TOPIX 等は別コード）。

        返り値: DatetimeIndex の DataFrame[Open, High, Low, Close]。
        ※ 実際のエンドポイント/コード体系は契約後の API ドキュメントで確認すること。
        """
        params = {"code": code}
        if from_date:
            params["from"] = from_date
        rows = self._get("/indices", params)
        if not rows:
            raise JQuantsError(f"index_ohlc: no data for code={code}")
        df = pd.DataFrame(rows)
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date").sort_index()
        rename = {"Open": "Open", "High": "High", "Low": "Low", "Close": "Close"}
        return df.rename(columns=rename)[["Open", "High", "Low", "Close"]].astype(float)

    def index_option_ohlc(self, date: str) -> pd.DataFrame:
        """日経225オプション四本値（指定日・全ストライク）。#5 Put/Call の素材。

        返り値: DataFrame（PutCallDivision/StrikePrice/Volume 等を含む）。
        ※ カラム名は契約後 API ドキュメントに合わせて調整すること。
        """
        rows = self._get("/option/index_option", {"date": date})
        if not rows:
            raise JQuantsError(f"index_option_ohlc: no data for date={date}")
        return pd.DataFrame(rows)

    def short_selling_ratio(self, from_date: str | None = None) -> pd.DataFrame:
        """業種別空売り比率。#7 空売り比率の素材。

        返り値: DatetimeIndex の DataFrame。市場全体値が必要なら集計するか
        東証集計で補完する（§2）。
        ※ カラム名は契約後 API ドキュメントに合わせて調整すること。
        """
        params = {}
        if from_date:
            params["from"] = from_date
        rows = self._get("/markets/short_selling", params)
        if not rows:
            raise JQuantsError("short_selling_ratio: no data")
        df = pd.DataFrame(rows)
        df["Date"] = pd.to_datetime(df["Date"])
        return df.set_index("Date").sort_index()


def now_jst_date() -> str:
    """JST の本日日付（YYYY-MM-DD）。cron 実行のデフォルト基準日に使う。"""
    jst = timezone.utc  # 実運用では ZoneInfo("Asia/Tokyo") を使用（CI の TZ 設定でも可）
    return datetime.now(jst).strftime("%Y-%m-%d")
