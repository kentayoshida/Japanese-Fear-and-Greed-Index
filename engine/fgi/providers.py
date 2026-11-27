"""データプロバイダ：各指標の生値系列（IndicatorSeries）を組み立てる。

2モード：
  - real : 実ソースから取得（GitHub Actions 上で実行）。取得不能な指標は
           FetchError を送出し、呼び出し側で stale 扱い（中立値で埋めない §8）。
  - demo : 決定論的な合成データ。フロント表示と E2E 動作確認用。

実ソースの結線状況（2026-06 時点）：
  #1 momentum_125dma   : 指数価格（J-Quants 指数四本値 / stooq）から計算。←Phase1で結線可
  #2 advance_decline_25: J-Quants 全銘柄終値（共通キャッシュ）からプライムの値上がり/値下がりを集計。
  #3 new_high_low      : 同じ全銘柄終値の52週(245営業日)高安から算出。
  #4 nikkei_vi         : JPX/大阪取引所 公式。←要ソース確認（公式CSV/Excel）
  #5 option_skew       : J-Quants 日経225オプション四本値の IV（5%OTMプット−コール, 5日平均）。
  #6 margin_pl_ratio   : 松井証券「投資指標（店内）」日次。←要ToS確認
  #7 short_selling     : J-Quants 業種別空売り比率（市場全体に合算・5日平均）。
  #8 safe_haven        : 指数価格 + 10年JGBトータルリターン。←債券系列ソース要確認

未結線の指標は FetchError("要確認: ...") を送出する。実装者が各ソースを
確認・結線したら、その指標の provider を実データに差し替えること。
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

from .config import Config, Variant
from .fetchers.base import FetchError, IndicatorSeries, validate_series
from .fetchers.derive import momentum_125dma


def _jst_today():
    from datetime import datetime, timedelta, timezone

    return (datetime.now(timezone.utc) + timedelta(hours=9)).date()


def _fetch_start(config: Config, days_back: int, warmup_days: int = 0):
    """取得開始日（date）。従来の「今日から days_back 日前」と、config.data_start から
    warmup_days 日前の、早い方。data_start 未設定なら従来どおり。"""
    from datetime import date, timedelta

    base = _jst_today() - timedelta(days=int(days_back))
    if config.data_start:
        ds = date.fromisoformat(config.data_start) - timedelta(days=int(warmup_days))
        return min(base, ds)
    return base


_TRADING_DAYS_MEMO: dict[str, pd.DatetimeIndex] = {}


def _trading_days(client, start) -> pd.DatetimeIndex:
    """start 以降の東証営業日（TOPIX 終値のある日）。取得失敗時は平日で代用。

    休場日を「未取得」と誤認して毎回再取得し続けるのを防ぐ（増分キャッシュの枠を浪費しない）。
    1回の実行内ではメモ化して API 呼び出しを1回に抑える。
    """
    key = pd.Timestamp(start).strftime("%Y-%m-%d")
    if key in _TRADING_DAYS_MEMO:
        return _TRADING_DAYS_MEMO[key]
    try:
        s = client.index_close(code="0000", from_date=key)
        days = pd.DatetimeIndex(pd.to_datetime(s.index).normalize().unique()).sort_values()
        if len(days) == 0:
            raise ValueError("empty calendar")
    except Exception:  # noqa: BLE001
        days = pd.bdate_range(start=key, end=_jst_today())
    _TRADING_DAYS_MEMO[key] = days
    return days


def _equity_close(config: Config, equity: dict) -> pd.Series:
    """版の株式指数終値系列を取得する（#1 モメンタム・#8 株式レッグ用）。

    source=jquants は指数四本値（code 指定, 例 0000=TOPIX）、source=stooq は
    日次CSV（symbol 指定, 例 ^nkx=日経225）。J-Quants は日経225を配信しないため
    日経225版は stooq を使う（Ken 決定A）。
    """
    from datetime import datetime, timedelta

    src = equity.get("source", "jquants")
    if src == "jquants":
        from .fetchers.jquants import JQuantsClient

        if not JQuantsClient.is_configured():
            raise FetchError("equity_close(jquants): APIキー未設定")
        client = JQuantsClient(base_url=config.sources.get("jquants", {}).get("base_url"))
        # 125日線＋252日パーセンタイルの助走ぶん、data_start より約200日前から取得
        from_date = _fetch_start(config, 900, warmup_days=200).strftime("%Y-%m-%d")
        return client.index_close(code=equity.get("code", "0000"), from_date=from_date)
    if src == "nikkei_csv":
        url = equity.get("csv_url")
        if not url:
            raise FetchError("equity_close(nikkei_csv): csv_url 未設定")
        # 日経公式の日次CSV（VIと同じ構造・パーサ。終値列を検出）。
        s = _nikkei_official_ohlc_csv(url, equity.get("encoding", "cp932"))
        return _extend_with_proxy(config, equity, s)
    if src == "stooq":
        return _stooq_close(equity.get("symbol", "^nkx"))
    raise FetchError(f"equity_close: 未対応 source={src}")


def _extend_with_proxy(config: Config, equity: dict, s: pd.Series) -> pd.Series:
    """公式CSVの初日が取得開始日より新しければ、連動ETF（backfill_proxy_code）の調整後終値で
    過去を補う（stitch_with_proxy）。ETFの取得に失敗しても公式CSVだけで続行する。"""
    from .fetchers.derive import stitch_with_proxy
    from .fetchers.jquants import JQuantsClient

    code = equity.get("backfill_proxy_code")
    if not code or not config.data_start or not len(s) or not JQuantsClient.is_configured():
        return s
    need = pd.Timestamp(_fetch_start(config, 900, warmup_days=200))
    if s.index.min() <= need:
        return s
    try:
        client = JQuantsClient(base_url=config.sources.get("jquants", {}).get("base_url"))
        proxy = client.equity_adj_close(str(code), from_date=need.strftime("%Y-%m-%d"))
        out = stitch_with_proxy(s, proxy)
        print(f"[equity] 公式CSV初日 {s.index.min().date()} より前を ETF {code} で補完 "
              f"→ 初日 {out.index.min().date()}")
        return out
    except Exception as exc:  # noqa: BLE001
        print(f"[equity] ETF {code} による補完に失敗（公式CSVのみで続行）: {exc}")
        return s


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
            # 125日移動平均＋252日パーセンタイルに十分な履歴（data_start の約200日前から）
            from_date = _fetch_start(config, 900, warmup_days=200).strftime("%Y-%m-%d")
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


def _provide_option_skew(config: Config, client, series: dict, errors: dict) -> None:
    """#5 オプション・スキュー：日次のオプション四本値から raw(put_iv−call_iv) を算出し、
    CSV（option_skew_raw.csv）に増分キャッシュ。指標値は raw の5営業日単純平均。

    オプション四本値は日付単位（1日約1万行）でしかレンジ取得できないため、
    過去ぶんは1回の実行で一定数だけ取得して積み増す（レート制限・時間を考慮）。
    正規化（252営業日）には過去 252+5 営業日ぶんの raw が要る。初回の充填は
    JQUANTS_OPTION_MAX_FETCH（既定40）を大きくして手動実行すると早く終わる。
    IV の提供は 2016-07-19 以降のみ。
    """
    from datetime import date

    from .fetchers.derive import option_skew_daily, smooth_option_skew

    iv_start = date(2016, 7, 19)
    try:
        path = _series_cache_path(config, "option_skew_raw")
        cached = _load_series_cache(path)
        start = max(iv_start, _fetch_start(config, int(config.lookback_days * 1.6) + 20))
        target = _trading_days(client, start)
        have = {d.normalize() for d in cached.index}
        missing = [d for d in target if d.normalize() not in have]
        max_new = int(os.environ.get("JQUANTS_OPTION_MAX_FETCH")
                      or os.environ.get("JQUANTS_PC_MAX_FETCH") or "40")
        new: dict[pd.Timestamp, float] = {}
        for d in missing[-max_new:]:  # 直近の未取得日から積み増す
            try:
                chain = client.index_option_chain(d.strftime("%Y-%m-%d"))
            except Exception:  # noqa: BLE001  休場日などはスキップ
                continue
            r = option_skew_daily(chain)
            if r is not None:
                new[pd.Timestamp(d.date())] = float(r[2])
        merged = cached
        if new:
            merged = pd.concat([cached, pd.Series(new)]).sort_index()
            merged = merged[~merged.index.duplicated(keep="last")]
            _save_series_cache(path, merged)
        print(f"[option_skew] 今回取得 {len(new)} 日 / 残り未取得 "
              f"{max(len(missing) - min(len(missing), max_new), 0)} 日（{start} 以降）")
        smoothed = smooth_option_skew(merged, window=5)
        if len(smoothed) == 0:
            raise FetchError("option_skew: データ未取得（キャッシュ不足・初回は数回の実行で積み増し）")
        series["option_skew"] = IndicatorSeries("option_skew", smoothed, "jquants_v2")
    except FetchError as exc:
        errors["option_skew"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        errors["option_skew"] = f"option_skew: {exc}"


def _provide_short_ratio(config: Config, client, series: dict, errors: dict) -> None:
    """#7 空売り比率：業種別レンジを集計して市場全体比率を作り、5営業日平均を指標値にする。"""
    from datetime import datetime, timedelta

    from .fetchers.derive import rolling_mean, short_selling_market_ratio

    try:
        start = _fetch_start(config, int(config.lookback_days * 1.6) + 10,
                             warmup_days=10).strftime("%Y-%m-%d")
        df = client.short_ratio_market_df(start)
        ratio = short_selling_market_ratio(df)
        ratio = validate_series(ratio, indicator_id="short_selling_ratio",
                                min_value=0, max_value=100, min_points=20)
        # 単日値は暴落日に投げ売りで分母が膨らみ逆転するため、5営業日平均で採点する。
        smoothed = rolling_mean(ratio, window=5)
        series["short_selling_ratio"] = IndicatorSeries(
            "short_selling_ratio", smoothed, "jquants_v2", daily=ratio)
    except FetchError as exc:
        errors["short_selling_ratio"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        errors["short_selling_ratio"] = f"short_selling_ratio: {exc}"


def _stooq_close(symbol: str) -> pd.Series:
    """stooq の日次CSVから終値系列を取得する（CIのオープンネットワークで実行）。"""
    import requests
    from io import StringIO

    url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
    try:
        resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0 (fgi)"})
        resp.raise_for_status()
        df = pd.read_csv(StringIO(resp.text))
    except FetchError:
        raise
    except Exception as exc:  # noqa: BLE001  HTTPError 等も FetchError に正規化
        raise FetchError(f"stooq({symbol}): {exc}") from exc
    if "Close" not in df.columns or "Date" not in df.columns:
        raise FetchError(f"stooq({symbol}): unexpected columns {list(df.columns)}")
    return pd.Series(
        pd.to_numeric(df["Close"], errors="coerce").values, index=pd.to_datetime(df["Date"])
    ).dropna().sort_index()


def _nikkei_official_ohlc_csv(url: str, encoding: str = "cp932") -> pd.Series:
    """日経公式の日次CSV（Shift_JIS）を取得して終値系列を返す（日経VI/日経225 共通）。

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
        s = _nikkei_official_ohlc_csv(url, cfg.get("encoding", "cp932"))
        s = validate_series(s, indicator_id="nikkei_vi", min_value=5, max_value=200, min_points=60)
        series["nikkei_vi"] = IndicatorSeries("nikkei_vi", s, "nikkei_official")
    except FetchError as exc:
        errors["nikkei_vi"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        errors["nikkei_vi"] = f"nikkei_vi(official): {exc}"


def _provide_safe_haven(config: Config, client, variant: Variant, series: dict, errors: dict) -> None:
    """#8 セーフヘイブン：株式(版の指数) − 債券(国債ETF調整後終値) の20日リターン差。

    株式レッグは版ごと（TOPIX は J-Quants、日経225 は stooq）、債券レッグは全版共通。
    """
    from datetime import datetime, timedelta

    from .fetchers.derive import safe_haven

    try:
        jq = config.sources.get("jquants", {})
        bond_code = jq.get("bond_etf_code", "2510")
        from_date = _fetch_start(config, int(config.lookback_days * 1.6) + 40,
                                 warmup_days=40).strftime("%Y-%m-%d")
        eq = _equity_close(config, variant.equity)                     # 版の株式指数
        bond = client.equity_adj_close(bond_code, from_date=from_date)  # 国債ETF 調整後終値
        sh = safe_haven(eq, bond, window=20)
        if len(sh) == 0:
            raise FetchError("safe_haven: 系列が空（株式/債券の重なり日数不足）")
        series["safe_haven"] = IndicatorSeries("safe_haven", sh, "jquants_v2")
    except FetchError as exc:
        errors["safe_haven"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        errors["safe_haven"] = f"safe_haven: {exc}"


def _weekly_margin_long_cache(config: Config, client) -> pd.Series:
    """#6案A素材：市場全体の週次信用買い残（LongVol 合算）を金曜ベースで増分キャッシュ。

    /markets/margin-interest は date（原則金曜）指定で全銘柄を返すため、1週=1呼び出し。
    1実行あたり max_new 週ぶんだけ過去に遡って積み増す（初回は数回で充填）。
    祝日で記録日が金曜からずれる週は前営業日を数日戻って試す。
    """
    from datetime import datetime, timedelta

    path = _series_cache_path(config, "weekly_margin_long")
    cached = _load_series_cache(path)
    jst_today = (datetime.utcnow() + timedelta(hours=9)).date()
    # MTM の建値推定に十分な履歴（正規化窓 lookback + 助走）を金曜系列で確保
    start = _fetch_start(config, int(config.lookback_days * 3) + 60, warmup_days=365)
    fridays = pd.date_range(start=start, end=jst_today, freq="W-FRI")
    have = {d.normalize() for d in cached.index}
    missing = [d for d in fridays if d.normalize() not in have]
    max_new = int(os.environ.get("JQUANTS_WM_MAX_FETCH", "12"))
    new: dict[pd.Timestamp, float] = {}
    for fri in missing[-max_new:]:  # 直近の未取得週から積み増す
        for back in range(0, 4):  # 金→木→水→火（祝日ずれ吸収）
            day = fri - pd.Timedelta(days=back)
            try:
                total = client.weekly_margin_long_total(day.strftime("%Y-%m-%d"))
            except Exception:  # noqa: BLE001
                total = None
            if total:
                new[pd.Timestamp(fri.date())] = float(total)
                break
    merged = cached
    if new:
        merged = pd.concat([cached, pd.Series(new)]).sort_index()
        merged = merged[~merged.index.duplicated(keep="last")]
        _save_series_cache(path, merged)
    print(f"[weekly_margin] 今回取得 {len(new)} 週 / 残り未取得 "
          f"{max(len(missing) - min(len(missing), max_new), 0)} 週（{start} 以降）")
    return merged


def _load_margin_pl_history() -> pd.Series:
    """#6 信用評価損益率（買い方）の**確定日次履歴**（松井「店内信用評価損益率の推移」由来・
    正のデータ）。engine/fgi/data/margin_pl_history.csv を読む。tier-3 の較正アンカーおよび
    観測上書きに使う。より新しいライブ実測が同一日を上書きできるが、通常は一致する。"""
    from pathlib import Path

    p = Path(__file__).resolve().parent / "data" / "margin_pl_history.csv"
    if not p.exists():
        return pd.Series(dtype="float64")
    df = pd.read_csv(p)
    s = pd.Series(pd.to_numeric(df["value"], errors="coerce").values,
                  index=pd.to_datetime(df["date"]))
    return s.dropna().sort_index()


def _merge_observed(history: pd.Series, live: pd.Series) -> pd.Series:
    """#6 観測系列の合成：確定日次履歴（history・正）＋ 松井ライブ実測（live）。
    履歴が収録する日付は **履歴を正として優先**し、ライブは履歴に無い日付
    （通常は履歴期間より新しい日）だけを補う。これにより、旧ロジックで日付がズレた
    ライブ点があっても、確定履歴の範囲内では正しい値が表示される。"""
    if not len(history):
        return live
    if not len(live):
        return history
    # history を正として優先し、history に無い日付のみ live で補う（順序非依存）。
    return history.combine_first(live).sort_index()


def _provide_margin_pl(config: Config, client, series: dict, errors: dict,
                       scrape_latest: bool = True) -> None:
    """#6 信用評価損益率（買い方）。仕様 §2 の三層構成：
      tier-1: 松井『投資指標(店内)』を Playwright で取得（正・最新営業日のみ）
      tier-2: 週次信用買い残 × 指数の在庫平均コスト MTM 近似（過去日を日次補完）
      tier-3: 重複日で tier-2 を tier-1 にオフセット較正し、観測日は実測で上書き
    松井が取れなくても MTM で継続、MTM が組めなくても松井のみで継続する。
    #6 は市場全体の指標のため全版共通。scrape_latest=False の版はキャッシュを再利用し
    松井への再アクセスを避ける（ToS：取得は日次1回に限る）。"""
    from .fetchers.derive import margin_pl_mtm

    # --- tier-1: 松井（正）。取得できたら observed 系列(margin_pl_ratio.csv)に蓄積 ---
    matsui_path = _series_cache_path(config, "margin_pl_ratio")
    matsui = _load_series_cache(matsui_path)
    if scrape_latest:
        try:
            from .fetchers.matsui import fetch_margin_pl_buy

            value, basis = fetch_margin_pl_buy()
            # 松井は評価損益率を「翌営業日公開」（祝日で更に遅延）するため、実行日ではなく
            # ページ表示の基準日でキーする（データ本来の日付に付与＝自己修復型）。
            # 基準日を読めなかった場合は日付を推測せず、その回の格納は見送る（捏造しない）。
            if basis is None:
                errors.setdefault(
                    "margin_pl_ratio_matsui",
                    "matsui: 基準日を読み取れず（値の格納を見送り。tier-2 で継続）",
                )
            else:
                as_of = pd.Timestamp(pd.Timestamp(basis).date())
                new_pt = pd.Series({as_of: float(value)})
                # 同一基準日は新しい実測で上書き（combine_first で順序非依存）。
                matsui = new_pt.combine_first(matsui).sort_index()
                _save_series_cache(matsui_path, matsui)
        except Exception as exc:  # noqa: BLE001  松井不通でも tier-2 で継続
            errors.setdefault("margin_pl_ratio_matsui", f"matsui: {exc}")

    # --- 観測系列 = 確定日次履歴（松井チャート由来・正）＋ 松井ライブ実測（最新・上書き）---
    history = _load_margin_pl_history()
    observed = _merge_observed(history, matsui)

    # --- tier-2: 週次買い残 × 指数の MTM 近似（J-Quants 未設定時はスキップ）---
    mtm = None
    if client is not None:
        try:
            weekly = _weekly_margin_long_cache(config, client)
            if len(weekly) >= 2:
                idx = _nikkei_close_real(config)
                mtm = margin_pl_mtm(weekly, idx)
        except Exception as exc:  # noqa: BLE001
            errors.setdefault("margin_pl_ratio_mtm", f"mtm: {exc}")

    # --- tier-3: 較正して合成（観測日は観測=正で上書き、他日は較正MTMで補完）---
    final = None
    if mtm is not None and len(mtm):
        cal = mtm
        if len(observed):
            common = mtm.index.intersection(observed.index)
            if len(common):
                offset = float((observed.reindex(common) - mtm.reindex(common)).median())
                cal = mtm + offset
        if len(observed):
            # observed(正)を優先し、観測が無い日は較正MTMで補完（combine_first で順序非依存）。
            final = observed.combine_first(cal).sort_index()
        else:
            final = cal
    elif len(observed):
        final = observed  # MTM 不可なら観測(履歴＋松井ライブ)のみ

    if final is None or len(final) == 0:
        errors["margin_pl_ratio"] = "margin_pl_ratio: 松井・履歴・MTM いずれも取得できず"
        return
    src = "matsui+mtm" if (mtm is not None and len(mtm)) else "matsui"
    if len(history):
        src += "+hist"
    series["margin_pl_ratio"] = IndicatorSeries("margin_pl_ratio", final, src)


BREADTH_NHL_WIN = 245      # 52週 ≒ 245営業日（日本市場）
BREADTH_KEEP_DAYS = 260    # 終値キャッシュに常時残す直近営業日数（52週窓＋余裕）


def _breadth_needed_dates(cal: pd.DatetimeIndex, missing_ad, missing_nhl,
                          win: int = BREADTH_NHL_WIN) -> set:
    """派生値が欠けている日を計算するのに必要な終値の日付集合（営業日カレンダー上）。

    騰落(#2)は当日と前営業日、新高安(#3)は当日を含む直近 win 営業日の終値が要る。
    """
    pos = {d: i for i, d in enumerate(cal)}
    need: set = set()
    for d in missing_ad:
        i = pos.get(d)
        if i is None or i == 0:
            continue
        need.update((cal[i - 1], cal[i]))
    for d in missing_nhl:
        i = pos.get(d)
        if i is None or i < win - 1:
            continue
        need.update(cal[i - win + 1: i + 1])
    return need


def _provide_breadth(config: Config, client, series: dict, errors: dict) -> None:
    """#2 騰落レシオ・#3 新高値−新安値：全銘柄の日次終値（共通キャッシュ）から両方を算出。

    - 派生値は小さな CSV に恒久保存：advance_decline.csv（date, adv, dec）/ new_high_low.csv
      （date, net）。過去日の再計算に終値を持ち続ける必要がない。
    - 欠けている派生値の計算に必要な終値だけを取得（直近の日から、1回 JQUANTS_BREADTH_MAX_FETCH 日）。
    - 終値キャッシュは「直近 260 営業日」と「まだ計算待ちの日に必要な日」だけを残して縮める。
    - 騰落の母集団は現在のプライム銘柄（過去日の生存者バイアスあり）。新高安は全上場銘柄。
    """
    from pathlib import Path

    from .fetchers.derive import adv_dec_from_closes, advance_decline_ratio, new_high_low_from_closes

    try:
        engine_root = Path(__file__).resolve().parents[1]
        base = (engine_root / config.output.get("latest_path", "../web/public/data/latest.json")).resolve().parent / "series"
        base.mkdir(parents=True, exist_ok=True)
        closes_path = base / "stock_closes.csv.gz"
        ad_path = _series_cache_path(config, "advance_decline")
        nhl_path = _series_cache_path(config, "new_high_low")

        # --- キャッシュ読込 ---
        if closes_path.exists():
            cache = pd.read_csv(closes_path, compression="gzip", dtype={"code": str})
            cache["date"] = pd.to_datetime(cache["date"])
        else:
            cache = pd.DataFrame(columns=["date", "code", "adjc"])
        if ad_path.exists():
            adf = pd.read_csv(ad_path)
            adf["date"] = pd.to_datetime(adf["date"])
            ad = adf.set_index("date")[["adv", "dec"]].sort_index()
        else:
            ad = pd.DataFrame(columns=["adv", "dec"], dtype="float64")
        nhl = _load_series_cache(nhl_path)

        # --- 対象日と必要な終値 ---
        target_start = pd.Timestamp(_fetch_start(config, int(config.lookback_days * 1.6) + 40))
        # 52週窓のため、終値は対象初日の約400暦日前から要る
        cal = _trading_days(client, (target_start - pd.Timedelta(days=400)).date())
        target = [d for d in cal if d >= target_start]
        have_ad = {d.normalize() for d in ad.index}
        have_nhl = {d.normalize() for d in nhl.index}
        missing_ad = [d for d in target if d not in have_ad]
        missing_nhl = [d for d in target if d not in have_nhl]
        need = _breadth_needed_dates(cal, missing_ad, missing_nhl)
        have_close = set(pd.to_datetime(cache["date"]).dt.normalize().unique()) if len(cache) else set()
        to_fetch = sorted(d for d in need if d not in have_close)
        max_new = int(os.environ.get("JQUANTS_BREADTH_MAX_FETCH")
                      or os.environ.get("JQUANTS_NHL_MAX_FETCH") or "30")
        batch = to_fetch[-max_new:]  # 直近の日から（日次の最新値を常に優先）
        frames = []
        for d in batch:
            closes = client.equities_close_by_date(d.strftime("%Y-%m-%d"))
            if len(closes) == 0:
                continue
            frames.append(pd.DataFrame({
                "date": pd.Timestamp(d.date()), "code": closes.index.astype(str),
                "adjc": closes.values.round(2),
            }))
        if frames:
            cache = pd.concat([cache] + frames, ignore_index=True)
            cache = cache.drop_duplicates(subset=["date", "code"], keep="last")
        print(f"[breadth] 終値 今回取得 {len(frames)} 日 / 残り未取得 "
              f"{max(len(to_fetch) - len(batch), 0)} 日（{target_start.date()} 以降の派生値用）")

        piv = (cache.pivot_table(index="date", columns="code", values="adjc").sort_index()
               if len(cache) else pd.DataFrame())
        pdates = set(piv.index)

        # --- #2 騰落：前営業日と当日の終値がそろった欠損日を計算 ---
        pos = {d: i for i, d in enumerate(cal)}
        ad_new = {}
        universe = None
        for d in missing_ad:
            i = pos.get(d)
            if i is None or i == 0 or d not in pdates or cal[i - 1] not in pdates:
                continue
            if universe is None:
                universe = client.listed_codes_by_market("プライム")
            adv, dec = adv_dec_from_closes(piv.loc[cal[i - 1]], piv.loc[d], universe)
            ad_new[pd.Timestamp(d)] = {"adv": adv, "dec": dec}
        if ad_new:
            ad = pd.concat([ad, pd.DataFrame.from_dict(ad_new, orient="index")]).sort_index()
            ad = ad[~ad.index.duplicated(keep="last")]
            out = ad.copy()
            out.insert(0, "date", pd.DatetimeIndex(out.index).strftime("%Y-%m-%d"))
            out.to_csv(ad_path, index=False)

        # --- #3 新高安：52週窓の終値がすべてそろった欠損日を計算 ---
        nhl_new = {}
        if len(piv):
            calc = [d for d in missing_nhl
                    if pos.get(d) is not None and pos[d] >= BREADTH_NHL_WIN - 1
                    and all(x in pdates for x in cal[pos[d] - BREADTH_NHL_WIN + 1: pos[d] + 1])]
            if calc:
                net = new_high_low_from_closes(piv, win=BREADTH_NHL_WIN)
                for d in calc:
                    if d in net.index:
                        nhl_new[pd.Timestamp(d)] = float(net.loc[d])
        if nhl_new:
            nhl = pd.concat([nhl, pd.Series(nhl_new)]).sort_index()
            nhl = nhl[~nhl.index.duplicated(keep="last")]
            _save_series_cache(nhl_path, nhl)

        # --- 終値キャッシュの縮小（直近 260 営業日 ＋ まだ計算待ちの日に必要な日）---
        if len(cache):
            still_ad = [d for d in missing_ad if pd.Timestamp(d) not in ad_new]
            still_nhl = [d for d in missing_nhl if pd.Timestamp(d) not in nhl_new]
            keep = set(cal[-BREADTH_KEEP_DAYS:]) | _breadth_needed_dates(cal, still_ad, still_nhl)
            dn = pd.to_datetime(cache["date"]).dt.normalize()
            cache = cache[dn.isin(keep)]
            cache.to_csv(closes_path, index=False, compression="gzip")

        # --- 指標系列 ---
        if len(ad):
            ratio = advance_decline_ratio(ad["adv"], ad["dec"], window=25)
            if len(ratio):
                series["advance_decline_25"] = IndicatorSeries("advance_decline_25", ratio, "jquants_v2")
            else:
                errors["advance_decline_25"] = "advance_decline: 25日ぶんの蓄積待ち"
        else:
            errors["advance_decline_25"] = "advance_decline: データ未取得（初回は数回の実行で積み増し）"
        if len(nhl):
            series["new_high_low"] = IndicatorSeries("new_high_low", nhl.astype(float), "jquants_v2")
        else:
            errors["new_high_low"] = "new_high_low: 52週高安の蓄積待ち（245営業日分の全銘柄終値が必要）"
    except Exception as exc:  # noqa: BLE001
        errors.setdefault("advance_decline_25", f"breadth: {exc}")
        errors.setdefault("new_high_low", f"breadth: {exc}")


def _provide_real(config: Config, variant: Variant,
                  scrape_matsui: bool = True) -> tuple[dict[str, IndicatorSeries], dict[str, str]]:
    """1つの版（variant）の生値系列を組み立てる。

    版ごとに変わるのは #1 モメンタム・#8 セーフヘイブンの株式レッグのみ。
    市場全体系（#2〜#7）は全版共通で、CSV キャッシュを介するため2版目以降は
    追加のAPI取得がほぼ発生しない（松井は scrape_matsui で1回に限定）。
    """
    from .fetchers.jquants import JQuantsClient

    series: dict[str, IndicatorSeries] = {}
    errors: dict[str, str] = {}

    # ---- #1 モメンタム（版の株式指数から計算）----
    try:
        close = _equity_close(config, variant.equity)
        eqmin = float(variant.equity.get("min", 300))
        eqmax = float(variant.equity.get("max", 20000))
        close = validate_series(close, indicator_id=f"{variant.key}_equity_close",
                                min_value=eqmin, max_value=eqmax, min_points=130)
        dev = momentum_125dma(close)
        series["momentum_125dma"] = IndicatorSeries(
            "momentum_125dma", dev, variant.equity.get("source", "jquants"))
        # 指数そのものの終値系列も持ち回る（チャートのオーバーレイ用。指標ではない）。
        series["_equity_close"] = IndicatorSeries(
            "_equity_close", close, variant.equity.get("source", "jquants"))
    except FetchError as exc:
        errors["momentum_125dma"] = str(exc)
    except Exception as exc:  # noqa: BLE001  株式指数の取得失敗で全体を落とさない
        errors["momentum_125dma"] = f"momentum_125dma: {exc}"

    # ---- #4 日経VI（日経公式CSV。全版共通）----
    _provide_nikkei_vi(config, series, errors)

    # ---- #2/#3/#5/#7/#8（J-Quants v2 一次データ）----
    client = None
    if JQuantsClient.is_configured():
        client = JQuantsClient(base_url=config.sources.get("jquants", {}).get("base_url"))
        _provide_option_skew(config, client, series, errors)
        _provide_short_ratio(config, client, series, errors)
        _provide_safe_haven(config, client, variant, series, errors)
        _provide_breadth(config, client, series, errors)
    else:
        for k in ("option_skew", "short_selling_ratio", "safe_haven",
                  "advance_decline_25", "new_high_low"):
            errors[k] = "要確認: J-Quants APIキー（JQUANTS_API_KEY）未設定"

    # ---- #6 信用評価損益率（松井 tier-1 + 週次買い残 MTM tier-2。全版共通）----
    _provide_margin_pl(config, client, series, errors, scrape_latest=scrape_matsui)

    return series, errors


def provide_variants(
    config: Config, mode: str = "real"
) -> dict[str, tuple[dict[str, IndicatorSeries], dict[str, str]]]:
    """全版の (生値系列, errors) を版キーごとに返す。

    real は版を順に処理し、松井スクレイプは最初の版のみ実行（残りはキャッシュ再利用）。
    demo は合成データを全版に複製する（版差は指数レッグのみで合成では区別しないため）。
    """
    if mode == "demo":
        return {v.key: (_provide_demo(config), {}) for v in config.variants}
    if mode == "real":
        out: dict[str, tuple[dict[str, IndicatorSeries], dict[str, str]]] = {}
        for i, v in enumerate(config.variants):
            # 1つの版が丸ごと失敗しても他版の出力を止めない（版ごとに隔離）。
            try:
                out[v.key] = _provide_real(config, v, scrape_matsui=(i == 0))
            except Exception as exc:  # noqa: BLE001
                out[v.key] = ({}, {"_variant": f"{v.key}: {exc}"})
        return out
    raise ValueError(f"unknown provider mode: {mode}")


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
        "option_skew":         (6.0, 0.4, (0.0, 15.0), -1.0),
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
    # チャートのオーバーレイ用に合成の株価指数（mood と緩く相関する乱歩）を持たせる。
    idx = 2800.0 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, n_days)) + 0.02 * mood)
    series["_equity_close"] = IndicatorSeries("_equity_close", pd.Series(idx, index=dates), "demo")
    return series


# =============================================================================
# 公開エントリ
# =============================================================================
def provide(config: Config, mode: str = "real") -> tuple[dict[str, IndicatorSeries], dict[str, str]]:
    """既定版の生値系列を返す（後方互換）。全版は provide_variants を使う。

    返り値: (raw_series, errors)。errors は取得失敗した指標 id → 理由。
    """
    results = provide_variants(config, mode)
    default = config.default_variant()
    return results[default.key]
