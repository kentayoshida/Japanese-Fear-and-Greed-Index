"""データプロバイダ：各指標の生値系列（IndicatorSeries）を組み立てる。

2モード：
  - real : 実ソースから取得（GitHub Actions 上で実行）。取得不能な指標は
           FetchError を送出し、呼び出し側で stale 扱い（中立値で埋めない §8）。
  - demo : 決定論的な合成データ。フロント表示と E2E 動作確認用。

実ソースの結線状況（2026-06 時点）：
  #1 momentum_125dma   : 指数価格（J-Quants 指数四本値 / stooq）から計算。←Phase1で結線可
  #2 advance_decline_25: 東証 値上がり/値下がり銘柄数。←要ソース確認（株探/日経/ToS）
  #3 new_high_low      : 東証 新高値/新安値銘柄数。←要ソース確認
  #4 nikkei_vi         : JPX/大阪取引所 公式。←要ソース確認（公式CSV/Excel）
  #5 put_call_ratio    : J-Quants 日経225オプション四本値。←J-Quants 契約後
  #6 margin_pl_ratio   : 松井証券「投資指標（店内）」日次。←要ToS確認
  #7 short_selling     : J-Quants 業種別空売り比率。←J-Quants 契約後
  #8 safe_haven        : 指数価格 + 10年JGBトータルリターン。←債券系列ソース要確認

未結線の指標は FetchError("要確認: ...") を送出する。実装者が各ソースを
確認・結線したら、その指標の provider を実データに差し替えること。
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

from .config import Config
from .fetchers.base import FetchError, IndicatorSeries, validate_series
from .fetchers.derive import momentum_125dma


# =============================================================================
# real プロバイダ
# =============================================================================
def _nikkei_close_real(config: Config) -> pd.Series:
    """日経225終値系列。J-Quants が使えればそれを、なければ stooq を試す。

    どちらも到達できなければ FetchError。
    """
    # 1) J-Quants v2（一次データ優先）
    from datetime import datetime, timedelta

    from .fetchers.jquants import JQuantsClient

    if JQuantsClient.is_configured():
        try:
            client = JQuantsClient(base_url=config.sources.get("jquants", {}).get("base_url"))
            # 125日移動平均＋252日パーセンタイルに十分な履歴（約2.5年）を取得
            from_date = (datetime.utcnow() - timedelta(days=900)).strftime("%Y-%m-%d")
            return client.index_close(code="0000", from_date=from_date)  # 日経平均
        except Exception as exc:  # noqa: BLE001
            raise FetchError(f"nikkei_close(J-Quants): {exc}") from exc

    # 2) stooq フォールバック（無料・日次CSV）
    import requests

    symbol = config.sources.get("stooq", {}).get("nikkei_symbol", "^nkx")
    url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        from io import StringIO

        df = pd.read_csv(StringIO(resp.text))
        if "Close" not in df.columns or "Date" not in df.columns:
            raise FetchError(f"nikkei_close(stooq): unexpected columns {list(df.columns)}")
        s = pd.Series(df["Close"].values, index=pd.to_datetime(df["Date"]))
        return s.sort_index()
    except FetchError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise FetchError(f"nikkei_close(stooq): {exc}") from exc


def _provide_real(config: Config) -> dict[str, IndicatorSeries]:
    series: dict[str, IndicatorSeries] = {}
    errors: dict[str, str] = {}

    # ---- #1 モメンタム（指数価格から計算）----
    try:
        close = _nikkei_close_real(config)
        close = validate_series(close, indicator_id="nikkei_close", min_value=1000, max_value=200000,
                                min_points=130)
        dev = momentum_125dma(close)
        series["momentum_125dma"] = IndicatorSeries("momentum_125dma", dev, "jquants_or_stooq")
    except FetchError as exc:
        errors["momentum_125dma"] = str(exc)

    # ---- #2〜#8 未結線：要ソース確認 / J-Quants 契約後 ----
    # それぞれ実ソースを確認・結線したら下記を実データ取得に差し替える。
    pending = {
        "advance_decline_25": "東証 値上がり/値下がり銘柄数のソース確認（株探/日経・ToS）が必要",
        "new_high_low": "東証 新高値/新安値銘柄数のソース確認が必要",
        "nikkei_vi": "日経VI 公式ソース（JPX/大阪取引所 CSV/Excel）の結線が必要",
        "put_call_ratio": "J-Quants 日経225オプション四本値（契約・APIキー発行）が必要",
        "margin_pl_ratio": "松井証券『投資指標（店内）』日次値のToS確認・結線が必要",
        "short_selling_ratio": "J-Quants 業種別空売り比率（契約・APIキー発行）が必要",
        "safe_haven": "10年JGBトータルリターン系列のソース確認・結線が必要",
    }
    for ind_id, reason in pending.items():
        errors[ind_id] = f"要確認: {reason}"

    if errors:
        # ログ用に保持（呼び出し側が表示）。系列が無い指標は自動的に stale になる。
        _provide_real.last_errors = errors  # type: ignore[attr-defined]
    return series


# =============================================================================
# demo プロバイダ（決定論的合成データ）
# =============================================================================
def _mean_reverting(rng, n, mean, vol, theta=0.05, clip=None):
    x = np.zeros(n)
    x[0] = mean
    for i in range(1, n):
        x[i] = x[i - 1] + theta * (mean - x[i - 1]) + rng.normal(0, vol)
    if clip:
        x = np.clip(x, *clip)
    return x


def _provide_demo(config: Config, n_days: int = 420, seed: int = 20260628) -> dict[str, IndicatorSeries]:
    rng = np.random.default_rng(seed)
    end = pd.Timestamp("2026-06-26")
    dates = pd.bdate_range(end=end, periods=n_days)

    # 共通の市場「気分」ファクタ（指標間に緩い相関を持たせる）
    mood = _mean_reverting(rng, n_days, mean=0.0, vol=0.6, theta=0.03, clip=(-3, 3))

    specs = {
        # id: (mean, vol, clip, mood_beta)  raw値レンジを現実的に
        "momentum_125dma":     (1.0, 0.8, (-10, 10), 2.0),
        "advance_decline_25":  (100, 4.0, (60, 145), 8.0),
        "new_high_low":        (0.0, 30.0, (-400, 400), 80.0),
        "nikkei_vi":           (22, 1.0, (12, 45), -3.0),    # 不安時に上昇（moodと逆）
        "put_call_ratio":      (1.05, 0.05, (0.6, 1.8), -0.12),
        "margin_pl_ratio":     (-10, 1.2, (-28, 6), 4.0),
        "short_selling_ratio": (43, 0.8, (35, 52), -2.0),
        "safe_haven":          (1.0, 1.5, (-12, 12), 3.0),
    }
    series: dict[str, IndicatorSeries] = {}
    for ind in config.indicators:
        mean, vol, clip, beta = specs[ind.id]
        base = _mean_reverting(rng, n_days, mean=mean, vol=vol, clip=None)
        vals = base + beta * mood
        vals = np.clip(vals, *clip)
        series[ind.id] = IndicatorSeries(ind.id, pd.Series(vals, index=dates), "demo")
    return series


# =============================================================================
# 公開エントリ
# =============================================================================
def provide(config: Config, mode: str = "real") -> tuple[dict[str, IndicatorSeries], dict[str, str]]:
    """mode に応じて生値系列を返す。

    返り値: (raw_series, errors)。errors は取得失敗した指標 id → 理由。
    """
    if mode == "demo":
        return _provide_demo(config), {}
    if mode == "real":
        series = _provide_real(config)
        errors = getattr(_provide_real, "last_errors", {})
        return series, dict(errors)
    raise ValueError(f"unknown provider mode: {mode}")
