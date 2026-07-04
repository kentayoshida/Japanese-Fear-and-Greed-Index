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

from .config import Config, Variant
from .fetchers.base import FetchError, IndicatorSeries, validate_series
from .fetchers.derive import momentum_125dma


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
        from_date = (datetime.utcnow() - timedelta(days=900)).strftime("%Y-%m-%d")
        return client.index_close(code=equity.get("code", "0000"), from_date=from_date)
    if src == "nikkei_csv":
        url = equity.get("csv_url")
        if not url:
            raise FetchError("equity_close(nikkei_csv): csv_url 未設定")
        # 日経公式の日次CSV（VIと同じ構造・パーサ。終値列を検出）。
        return _nikkei_official_ohlc_csv(url, equity.get("encoding", "cp932"))
    if src == "stooq":
        return _stooq_close(equity.get("symbol", "^nkx"))
    raise FetchError(f"equity_close: 未対応 source={src}")


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
        from_date = (datetime.utcnow() + timedelta(hours=9)
                     - timedelta(days=int(config.lookback_days * 1.6) + 40)).strftime("%Y-%m-%d")
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
    start = jst_today - timedelta(days=int(config.lookback_days * 3) + 60)
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
    return merged


def _provide_margin_pl(config: Config, client, series: dict, errors: dict,
                       scrape_latest: bool = True) -> None:
    """#6 信用評価損益率（買い方）。仕様 §2 の三層構成：
      tier-1: 松井『投資指標(店内)』を Playwright で取得（正・最新営業日のみ）
      tier-2: 週次信用買い残 × 指数の在庫平均コスト MTM 近似（過去日を日次補完）
      tier-3: 重複日で tier-2 を tier-1 にオフセット較正し、観測日は実測で上書き
    松井が取れなくても MTM で継続、MTM が組めなくても松井のみで継続する。
    #6 は市場全体の指標のため全版共通。scrape_latest=False の版はキャッシュを再利用し
    松井への再アクセスを避ける（ToS：取得は日次1回に限る）。"""
    from datetime import datetime, timedelta

    from .fetchers.derive import margin_pl_mtm

    # --- tier-1: 松井（正）。取得できたら observed 系列(margin_pl_ratio.csv)に蓄積 ---
    matsui_path = _series_cache_path(config, "margin_pl_ratio")
    matsui = _load_series_cache(matsui_path)
    if scrape_latest:
        try:
            from .fetchers.matsui import fetch_margin_pl_buy

            value = fetch_margin_pl_buy()
            as_of = pd.Timestamp((datetime.utcnow() + timedelta(hours=9)).date())
            matsui = pd.concat([matsui, pd.Series({as_of: float(value)})]).sort_index()
            matsui = matsui[~matsui.index.duplicated(keep="last")]
            _save_series_cache(matsui_path, matsui)
        except Exception as exc:  # noqa: BLE001  松井不通でも tier-2 で継続
            errors.setdefault("margin_pl_ratio_matsui", f"matsui: {exc}")

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

    # --- tier-3: 較正して合成（観測日は実測で上書き）---
    final = None
    if mtm is not None and len(mtm):
        cal = mtm
        if len(matsui):
            common = mtm.index.intersection(matsui.index)
            if len(common):
                offset = float((matsui.reindex(common) - mtm.reindex(common)).median())
                cal = mtm + offset
        if len(matsui):
            final = pd.concat([cal, matsui]).sort_index()
            final = final[~final.index.duplicated(keep="last")]  # matsui(後勝ち)で上書き
        else:
            final = cal
    elif len(matsui):
        final = matsui  # MTM 不可なら松井のみ（従来動作）

    if final is None or len(final) == 0:
        errors["margin_pl_ratio"] = "margin_pl_ratio: 松井・MTM いずれも取得できず"
        return
    src = "matsui+mtm" if (mtm is not None and len(mtm)) else "matsui"
    series["margin_pl_ratio"] = IndicatorSeries("margin_pl_ratio", final, src)


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
        # 52週高安。日本市場は年間約245営業日のため窓は245（米国基準の252だと1年貯めても
        # 到達せず計算不能になる）。min_periods は約40週分あれば52週高安を近似計算し、
        # 期間が貯まるほど本来の52週窓に近づく（キャッシュ増分に対して堅牢）。
        win = 245
        minp = 200
        roll_max = piv.rolling(win, min_periods=minp).max()
        roll_min = piv.rolling(win, min_periods=minp).min()
        new_high = (piv >= roll_max) & roll_max.notna()
        new_low = (piv <= roll_min) & roll_min.notna()
        net = (new_high.sum(axis=1) - new_low.sum(axis=1))[roll_max.notna().any(axis=1)]
        if len(net) == 0:
            raise FetchError("new_high_low: 52週高安の蓄積待ち（約40週分の全銘柄終値が必要）")
        series["new_high_low"] = IndicatorSeries("new_high_low", net.astype(float), "jquants_v2")
    except FetchError as exc:
        errors["new_high_low"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        errors["new_high_low"] = f"new_high_low: {exc}"


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
        _provide_put_call(config, client, series, errors)
        _provide_short_ratio(config, client, series, errors)
        _provide_safe_haven(config, client, variant, series, errors)
        _provide_advance_decline(config, client, series, errors)
        _provide_new_high_low(config, client, series, errors)
    else:
        for k in ("put_call_ratio", "short_selling_ratio", "safe_haven",
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
