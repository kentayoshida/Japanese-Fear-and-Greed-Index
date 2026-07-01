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


# ---- 生値系列のローカルキャッシュ（CSV）。再取得コスト・レート制限を抑える ----
def _series_cache_path(config: Config, name: str):
    from pathlib import Path

    engine_root = Path(__file__).resolve().parents[1]
    latest = config.output.get("latest_path", "../web/public/data/latest.json")
    base = (engine_root / latest).resolve().parent / "series"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{name}.csv"


def _load_series_cache(path) -> pd.Series:
    if path.exists():
        df = pd.read_csv(path)
        s = pd.Series(pd.to_numeric(df["value"], errors="coerce").values,
                      index=pd.to_datetime(df["date"]))
        return s.dropna().sort_index()
    return pd.Series(dtype="float64")


def _save_series_cache(path, s: pd.Series) -> None:
    out = pd.DataFrame({"date": pd.DatetimeIndex(s.index).strftime("%Y-%m-%d"),
                        "value": s.values})
    out.to_csv(path, index=False)


def _provide_put_call(config: Config, client, series: dict, errors: dict) -> None:
    """#5 P/Cレシオ：日次のオプション四本値からP/Cを算出し、CSVに増分キャッシュ。

    オプション四本値は日付単位（1日約1万行）でしかレンジ取得できないため、
    過去ぶんは1回の実行で一定数だけ取得して積み増す（レート制限・時間を考慮）。
    """
    from datetime import datetime, timedelta

    from .fetchers.derive import put_call_ratio

    try:
        path = _series_cache_path(config, "put_call_ratio")
        cached = _load_series_cache(path)
        jst_today = (datetime.utcnow() + timedelta(hours=9)).date()
        start = jst_today - timedelta(days=int(config.lookback_days * 1.6) + 10)
        target = pd.bdate_range(start=start, end=jst_today)
        have = {d.normalize() for d in cached.index}
        missing = [d for d in target if d.normalize() not in have]
        max_new = int(os.environ.get("JQUANTS_PC_MAX_FETCH", "40"))
        new: dict[pd.Timestamp, float] = {}
        for d in missing[-max_new:]:  # 直近の未取得日から積み増す
            try:
                chain = client.index_option_chain(d.strftime("%Y-%m-%d"))
            except Exception:  # noqa: BLE001  休場日などはスキップ
                continue
            r = put_call_ratio(chain)
            if len(r):
                new[pd.Timestamp(d.date())] = float(r.iloc[-1])
        merged = cached
        if new:
            merged = pd.concat([cached, pd.Series(new)]).sort_index()
            merged = merged[~merged.index.duplicated(keep="last")]
            _save_series_cache(path, merged)
        if len(merged) == 0:
            raise FetchError("put_call_ratio: データ未取得（キャッシュ空・初回は数回の実行で積み増し）")
        series["put_call_ratio"] = IndicatorSeries("put_call_ratio", merged, "jquants_v2")
    except FetchError as exc:
        errors["put_call_ratio"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        errors["put_call_ratio"] = f"put_call_ratio: {exc}"


def _provide_short_ratio(config: Config, client, series: dict, errors: dict) -> None:
    """#7 空売り比率：業種別レンジを集計して市場全体比率の系列を作る。"""
    from datetime import datetime, timedelta

    from .fetchers.derive import short_selling_market_ratio

    try:
        start = (datetime.utcnow() + timedelta(hours=9)
                 - timedelta(days=int(config.lookback_days * 1.6) + 10)).strftime("%Y-%m-%d")
        df = client.short_ratio_market_df(start)
        ratio = short_selling_market_ratio(df)
        ratio = validate_series(ratio, indicator_id="short_selling_ratio",
                                min_value=0, max_value=100, min_points=20)
        series["short_selling_ratio"] = IndicatorSeries("short_selling_ratio", ratio, "jquants_v2")
    except FetchError as exc:
        errors["short_selling_ratio"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        errors["short_selling_ratio"] = f"short_selling_ratio: {exc}"


def _stooq_close(symbol: str) -> pd.Series:
    """stooq の日次CSVから終値系列を取得する（CIのオープンネットワークで実行）。"""
    import requests
    from io import StringIO

    url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    df = pd.read_csv(StringIO(resp.text))
    if "Close" not in df.columns or "Date" not in df.columns:
        raise FetchError(f"stooq({symbol}): unexpected columns {list(df.columns)}")
    return pd.Series(
        pd.to_numeric(df["Close"], errors="coerce").values, index=pd.to_datetime(df["Date"])
    ).dropna().sort_index()


def _nikkei_vi_official_csv(url: str, encoding: str = "cp932") -> pd.Series:
    """日経公式の日経VI日次CSV（Shift_JIS）を取得して終値系列を返す。

    先頭のタイトル行・末尾の注記行が混在するため、日付として解釈できる行だけを拾い、
    ヘッダから『終値』列位置を特定してパースする（列順の揺れに頑健化）。
    """
    import requests

    resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0 (fgi)"})
    resp.raise_for_status()
    text = resp.content.decode(encoding, errors="replace")

    close_idx = 1  # 既定：日付の次を終値とみなす（日経指数CSVの標準）
    header_found = False
    dates: list = []
    values: list = []
    for line in text.splitlines():
        parts = [p.strip().strip('"') for p in line.split(",")]
        if not header_found:
            if any(("データ日付" in p) or (p == "日付") for p in parts):
                for i, p in enumerate(parts):
                    if "終値" in p:
                        close_idx = i
                header_found = True
            continue
        if len(parts) <= close_idx:
            continue
        try:
            d = pd.to_datetime(parts[0])
        except Exception:  # noqa: BLE001
            continue
        try:
            v = float(parts[close_idx].replace(",", ""))
        except Exception:  # noqa: BLE001
            continue
        dates.append(d)
        values.append(v)
    if not values:
        raise FetchError(f"nikkei_vi(official csv): 行を解釈できず url={url}")
    return pd.Series(values, index=pd.DatetimeIndex(dates)).sort_index()


def _provide_nikkei_vi(config: Config, series: dict, errors: dict) -> None:
    """#4 日経VI：J-Quants/stooq に無いため日経公式の日次CSVを使用（Ken決定）。yfinance不使用。"""
    try:
        cfg = config.sources.get("nikkei_vi", {})
        url = cfg.get("csv_url")
        if not url:
            raise FetchError("nikkei_vi: config の csv_url 未設定")
        s = _nikkei_vi_official_csv(url, cfg.get("encoding", "cp932"))
        s = validate_series(s, indicator_id="nikkei_vi", min_value=5, max_value=200, min_points=60)
        series["nikkei_vi"] = IndicatorSeries("nikkei_vi", s, "nikkei_official")
    except FetchError as exc:
        errors["nikkei_vi"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        errors["nikkei_vi"] = f"nikkei_vi(official): {exc}"


def _provide_safe_haven(config: Config, client, series: dict, errors: dict) -> None:
    """#8 セーフヘイブン：株式(TOPIX) − 債券(国債ETF調整後終値) の20日リターン差。"""
    from datetime import datetime, timedelta

    from .fetchers.derive import safe_haven

    try:
        jq = config.sources.get("jquants", {})
        eq_code = jq.get("equity_index_code", "0000")
        bond_code = jq.get("bond_etf_code", "2510")
        from_date = (datetime.utcnow() + timedelta(hours=9)
                     - timedelta(days=int(config.lookback_days * 1.6) + 40)).strftime("%Y-%m-%d")
        eq = client.index_close(code=eq_code, from_date=from_date)      # TOPIX 現物
        bond = client.equity_adj_close(bond_code, from_date=from_date)  # 国債ETF 調整後終値
        sh = safe_haven(eq, bond, window=20)
        if len(sh) == 0:
            raise FetchError("safe_haven: 系列が空（株式/債券の重なり日数不足）")
        series["safe_haven"] = IndicatorSeries("safe_haven", sh, "jquants_v2")
    except FetchError as exc:
        errors["safe_haven"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        errors["safe_haven"] = f"safe_haven: {exc}"


def _provide_advance_decline(config: Config, client, series: dict, errors: dict) -> None:
    """#2 騰落レシオ（東証プライム・25日）：全銘柄 AdjC の前日比で日次の値上がり/値下がり
    銘柄数を集計し、25日累積で騰落レシオを算出。日次 adv/dec を CSV に増分キャッシュ。"""
    from datetime import datetime, timedelta

    from .fetchers.derive import advance_decline_ratio

    try:
        path = _series_cache_path(config, "advance_decline")
        # 既存キャッシュ（date, adv, dec）
        if path.exists():
            cdf = pd.read_csv(path)
            cdf["date"] = pd.to_datetime(cdf["date"])
            cache = cdf.set_index("date")[["adv", "dec"]].sort_index()
        else:
            cache = pd.DataFrame(columns=["adv", "dec"], dtype="float64")

        jst_today = (datetime.utcnow() + timedelta(hours=9)).date()
        start = jst_today - timedelta(days=int(config.lookback_days * 1.6) + 40)
        target = pd.bdate_range(start=start, end=jst_today)
        have = {d.normalize() for d in cache.index}
        missing = [d for d in target if d.normalize() not in have]
        max_new = int(os.environ.get("JQUANTS_AD_MAX_FETCH", "25"))
        # 前日比のため、対象バッチ＋その1営業日前から連続取得する
        batch = missing[-max_new:]
        if batch:
            prime = client.listed_codes_by_market("プライム")
            fetch_dates = list(pd.bdate_range(end=batch[-1], periods=len(batch) + 1))
            fetch_dates = [d for d in fetch_dates if d >= (batch[0] - pd.Timedelta(days=7))]
            prev_close = None
            new_rows = {}
            for d in fetch_dates:
                closes = client.equities_close_by_date(d.strftime("%Y-%m-%d"))
                if len(closes) == 0:
                    continue  # 休場日
                closes = closes[closes.index.isin(prime)]
                if prev_close is not None and d.normalize() in {b.normalize() for b in batch}:
                    common = closes.index.intersection(prev_close.index)
                    diff = closes[common] - prev_close[common]
                    new_rows[pd.Timestamp(d.date())] = {
                        "adv": float((diff > 0).sum()),
                        "dec": float((diff < 0).sum()),
                    }
                prev_close = closes
            if new_rows:
                add = pd.DataFrame.from_dict(new_rows, orient="index")
                cache = pd.concat([cache, add]).sort_index()
                cache = cache[~cache.index.duplicated(keep="last")]
                out = cache.copy()
                out.insert(0, "date", pd.DatetimeIndex(out.index).strftime("%Y-%m-%d"))
                out.to_csv(path, index=False)

        if len(cache) == 0:
            raise FetchError("advance_decline: データ未取得（初回は数回の実行で積み増し）")
        ratio = advance_decline_ratio(cache["adv"], cache["dec"], window=25)
        if len(ratio) == 0:
            raise FetchError("advance_decline: 25日ぶんの蓄積待ち")
        series["advance_decline_25"] = IndicatorSeries("advance_decline_25", ratio, "jquants_v2")
    except FetchError as exc:
        errors["advance_decline_25"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        errors["advance_decline_25"] = f"advance_decline_25: {exc}"


def _provide_margin_pl(config: Config, series: dict, errors: dict) -> None:
    """#6 信用評価損益率（買い方）：松井『投資指標(店内)』を Playwright で取得し、
    日次値を CSV に蓄積（前営業日値・anchor 正規化のため最新値が主眼）。"""
    from datetime import datetime, timedelta

    try:
        from .fetchers.matsui import fetch_margin_pl_buy

        value = fetch_margin_pl_buy()
        as_of = pd.Timestamp((datetime.utcnow() + timedelta(hours=9)).date())
        path = _series_cache_path(config, "margin_pl_ratio")
        cached = _load_series_cache(path)
        merged = pd.concat([cached, pd.Series({as_of: float(value)})]).sort_index()
        merged = merged[~merged.index.duplicated(keep="last")]
        _save_series_cache(path, merged)
        series["margin_pl_ratio"] = IndicatorSeries("margin_pl_ratio", merged, "matsui")
    except FetchError as exc:
        errors["margin_pl_ratio"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        errors["margin_pl_ratio"] = f"margin_pl_ratio: {exc}"


def _provide_new_high_low(config: Config, client, series: dict, errors: dict) -> None:
    """#3 新高値 − 新安値（東証全体・ネット）：全銘柄 AdjC の52週(252営業日)高安から
    新高値/新安値銘柄数を数えネット値を算出。全銘柄終値を gzip CSV に増分キャッシュし
    （web/public/data/series/stock_closes.csv.gz）、1実行あたり一定日数ずつ積み増す。"""
    from datetime import datetime, timedelta
    from pathlib import Path

    try:
        engine_root = Path(__file__).resolve().parents[1]
        base = (engine_root / config.output.get("latest_path", "../web/public/data/latest.json")).resolve().parent / "series"
        base.mkdir(parents=True, exist_ok=True)
        closes_path = base / "stock_closes.csv.gz"

        if closes_path.exists():
            cache = pd.read_csv(closes_path, compression="gzip")
            cache["date"] = pd.to_datetime(cache["date"])
        else:
            cache = pd.DataFrame(columns=["date", "code", "adjc"])

        jst_today = (datetime.utcnow() + timedelta(hours=9)).date()
        # 52週窓のネット系列を lookback ぶん得るには概ね 2*lookback 営業日が必要
        window_days = int(config.lookback_days * 2 * 1.5) + 30
        start = jst_today - timedelta(days=window_days)
        target = pd.bdate_range(start=start, end=jst_today)
        have = set(pd.to_datetime(cache["date"]).dt.normalize().unique()) if len(cache) else set()
        missing = [d for d in target if d.normalize() not in have]
        max_new = int(os.environ.get("JQUANTS_NHL_MAX_FETCH", "30"))
        new_frames = []
        for d in missing[-max_new:]:
            closes = client.equities_close_by_date(d.strftime("%Y-%m-%d"))
            if len(closes) == 0:
                continue
            new_frames.append(pd.DataFrame({
                "date": pd.Timestamp(d.date()), "code": closes.index.astype(str),
                "adjc": closes.values.round(2),
            }))
        if new_frames:
            cache = pd.concat([cache] + new_frames, ignore_index=True)
            cache = cache[pd.to_datetime(cache["date"]) >= pd.Timestamp(start)]
            cache = cache.drop_duplicates(subset=["date", "code"], keep="last")
            cache.to_csv(closes_path, index=False, compression="gzip")

        if len(cache) == 0:
            raise FetchError("new_high_low: 終値キャッシュ空（初回は数回の実行で積み増し）")

        piv = cache.pivot_table(index="date", columns="code", values="adjc").sort_index()
        win = 252
        roll_max = piv.rolling(win, min_periods=win).max()
        roll_min = piv.rolling(win, min_periods=win).min()
        new_high = (piv >= roll_max) & roll_max.notna()
        new_low = (piv <= roll_min) & roll_min.notna()
        net = (new_high.sum(axis=1) - new_low.sum(axis=1))[roll_max.notna().any(axis=1)]
        if len(net) == 0:
            raise FetchError("new_high_low: 52週窓の蓄積待ち（初回は数回の実行で充填）")
        series["new_high_low"] = IndicatorSeries("new_high_low", net.astype(float), "jquants_v2")
    except FetchError as exc:
        errors["new_high_low"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        errors["new_high_low"] = f"new_high_low: {exc}"


def _provide_real(config: Config) -> dict[str, IndicatorSeries]:
    from .fetchers.jquants import JQuantsClient

    series: dict[str, IndicatorSeries] = {}
    errors: dict[str, str] = {}

    # ---- #1 モメンタム（指数価格から計算）----
    try:
        close = _nikkei_close_real(config)
        # TOPIX(現状 約4000)。異常値・誤指数の検知のためレンジ検証（広めの安全域）。
        close = validate_series(close, indicator_id="topix_close", min_value=300, max_value=20000,
                                min_points=130)
        dev = momentum_125dma(close)
        series["momentum_125dma"] = IndicatorSeries("momentum_125dma", dev, "jquants_or_stooq")
    except FetchError as exc:
        errors["momentum_125dma"] = str(exc)

    # ---- #4 日経VI（stooq N145.JP。J-Quants非配信のため）----
    _provide_nikkei_vi(config, series, errors)

    # ---- #5 P/Cレシオ・#7 空売り比率（J-Quants v2 一次データ）----
    if JQuantsClient.is_configured():
        client = JQuantsClient(base_url=config.sources.get("jquants", {}).get("base_url"))
        _provide_put_call(config, client, series, errors)
        _provide_short_ratio(config, client, series, errors)
        _provide_safe_haven(config, client, series, errors)
        _provide_advance_decline(config, client, series, errors)
        _provide_new_high_low(config, client, series, errors)
    else:
        for k in ("put_call_ratio", "short_selling_ratio", "safe_haven",
                  "advance_decline_25", "new_high_low"):
            errors[k] = "要確認: J-Quants APIキー（JQUANTS_API_KEY）未設定"

    # ---- #6 信用評価損益率（松井・Playwright。J-Quants 非依存）----
    _provide_margin_pl(config, series, errors)

    if errors:
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
