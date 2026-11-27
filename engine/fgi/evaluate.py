"""逆張り有用性の評価（純関数群）。

主軸は ③ 逆張り：スコア < long_th で Long、> short_th で Short する目安として機能するか。
補助として ① 同時整合性・② 安定性・指標別診断を出す。

約定の前提（先読み防止）：日 t のスコアは翌朝 6:00 JST に公開されるため、
t+1 の終値で建てる（lag=1）。将来リターン = close(t+1+h) / close(t+1) − 1。
入力は run_daily.py が出力する history_components.<variant>.csv（date, score, coverage,
index, <id>_raw, <id>_score）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

STRESS_RET = -0.03   # 急落日：日次騰落率 −3% 以下
RALLY_RET = 0.03     # 急騰日：+3% 以上
FEAR_LINE = 45.0     # これ未満を「恐怖側」とみなす（バンド境界）
GREED_LINE = 55.0    # これ超を「強欲側」とみなす


@dataclass
class EvalParams:
    long_th: float = 25.0
    short_th: float = 75.0
    exit_level: float = 50.0
    horizons: tuple[int, ...] = (5, 20, 60)
    lag: int = 1
    cooldown: int = 5          # ゾーン突入イベント：直前 cooldown 日がゾーン外
    min_coverage: int = 8
    sens_long: tuple[float, ...] = (20.0, 25.0, 30.0)
    sens_short: tuple[float, ...] = (70.0, 75.0, 80.0)
    indicator_ids: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- 基本量
def load_components(path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return df[~df.index.duplicated(keep="last")]


def indicator_ids_from(df: pd.DataFrame) -> list[str]:
    return [c[: -len("_score")] for c in df.columns
            if c.endswith("_score") and c != "score"]


def forward_returns(close: pd.Series, horizons, lag: int = 1) -> pd.DataFrame:
    """各日 t について close(t+lag+h)/close(t+lag) − 1（営業日の位置でずらす）。"""
    c = pd.to_numeric(close, errors="coerce")
    entry = c.shift(-lag)
    out = {h: c.shift(-(lag + h)) / entry - 1.0 for h in horizons}
    return pd.DataFrame(out, index=c.index)


def forward_exit_dates(index: pd.DatetimeIndex, horizons, lag: int = 1) -> pd.DataFrame:
    """forward_returns の各値が依存する最終日（検証期間の価格を使わないための切り捨てに使う）。"""
    s = pd.Series(index, index=index)
    return pd.DataFrame({h: s.shift(-(lag + h)) for h in horizons}, index=index)


def t_stat(x) -> float | None:
    a = pd.Series(x, dtype="float64").dropna()
    n = len(a)
    if n < 2:
        return None
    sd = float(a.std(ddof=1))
    if sd == 0 or math.isnan(sd):
        return None
    return float(a.mean() / (sd / math.sqrt(n)))


def _r(x, nd=4):
    if x is None:
        return None
    try:
        if isinstance(x, float) and math.isnan(x):
            return None
        return round(float(x), nd)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- ③ 逆張り
def zone_mask(score: pd.Series, side: str, th: float) -> pd.Series:
    s = pd.to_numeric(score, errors="coerce")
    return (s < th) if side == "long" else (s > th)


def zone_events(score: pd.Series, side: str, th: float, cooldown: int = 5) -> pd.DatetimeIndex:
    """ゾーン突入日：当日ゾーン内で、直前 cooldown 日はいずれもゾーン外（独立標本に近づける）。"""
    m = zone_mask(score, side, th).fillna(False).astype(bool)
    prev_any = m.shift(1, fill_value=False).rolling(cooldown, min_periods=1).max().astype(bool)
    return m.index[m & ~prev_any]


def day_stats(fwd: pd.DataFrame, mask: pd.Series, side: str) -> dict:
    """ゾーン内の各日の将来リターン統計（日次・重複あり）と、全日平均に対する超過。"""
    out = {}
    for h in fwd.columns:
        allr = fwd[h].dropna()
        z = fwd.loc[mask.reindex(fwd.index).fillna(False).astype(bool), h].dropna()
        base = float(allr.mean()) if len(allr) else float("nan")
        if len(z) == 0:
            out[str(h)] = {"n": 0}
            continue
        hit = (z > 0).mean() if side == "long" else (z < 0).mean()
        out[str(h)] = {
            "n": int(len(z)), "mean": _r(z.mean()), "median": _r(z.median()),
            "hit": _r(hit, 3), "base_mean": _r(base), "excess": _r(z.mean() - base),
        }
    return out


def event_stats(fwd: pd.DataFrame, events: pd.DatetimeIndex, side: str) -> dict:
    """ゾーン突入イベントごとの将来リターン統計（件数・勝率・平均・t値）。"""
    out = {}
    for h in fwd.columns:
        z = fwd[h].reindex(events).dropna()
        if len(z) == 0:
            out[str(h)] = {"n": 0}
            continue
        hit = (z > 0).mean() if side == "long" else (z < 0).mean()
        out[str(h)] = {"n": int(len(z)), "mean": _r(z.mean()), "hit": _r(hit, 3),
                       "t": _r(t_stat(z), 2)}
    return out


def positions(score: pd.Series, long_th: float, short_th: float, exit_level: float,
              allow_short: bool = True) -> pd.Series:
    """スコアからポジション（+1/0/−1）を日ごとに決める。

    Long は score < long_th で建て、score ≥ exit_level で手仕舞い。
    Short は score > short_th で建て、score ≤ exit_level で手仕舞い。同日に手仕舞い後の新規も可。
    スコア欠損日はフラット。
    """
    pos = []
    cur = 0
    for v in pd.to_numeric(score, errors="coerce").values:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            cur = 0
            pos.append(cur)
            continue
        if cur == 1 and v >= exit_level:
            cur = 0
        elif cur == -1 and v <= exit_level:
            cur = 0
        if cur == 0:
            if v < long_th:
                cur = 1
            elif allow_short and v > short_th:
                cur = -1
        pos.append(cur)
    return pd.Series(pos, index=score.index, dtype="int64")


def backtest(score: pd.Series, close: pd.Series, long_th: float, short_th: float,
             exit_level: float, lag: int = 1, allow_short: bool = True) -> dict:
    """売買ルールの成績。日 t のポジションは t+lag の終値で建て、t+lag+1 以降の日次リターンを得る。"""
    c = pd.to_numeric(close, errors="coerce")
    r = c.pct_change()
    pos = positions(score, long_th, short_th, exit_level, allow_short)
    strat = (pos.shift(lag + 1) * r).dropna()
    bh = r.reindex(strat.index).dropna()
    entries = int(((pos != 0) & (pos != pos.shift(1, fill_value=0))).sum())
    return {
        "strategy": _perf(strat),
        "buy_hold": _perf(bh),
        "exposure": _r(float((pos.shift(lag + 1).reindex(strat.index) != 0).mean())
                       if len(strat) else None, 3),
        "long_share": _r(float((pos == 1).mean()) if len(pos) else None, 3),
        "short_share": _r(float((pos == -1).mean()) if len(pos) else None, 3),
        "trades": entries,
    }


def _perf(r: pd.Series) -> dict:
    r = pd.Series(r, dtype="float64").dropna()
    if len(r) == 0:
        return {"n_days": 0}
    eq = (1 + r).cumprod()
    total = float(eq.iloc[-1] - 1)
    years = len(r) / 252.0
    cagr = float(eq.iloc[-1] ** (1 / years) - 1) if years > 0 and eq.iloc[-1] > 0 else None
    sd = float(r.std(ddof=1)) if len(r) > 1 else float("nan")
    sharpe = float(r.mean() / sd * math.sqrt(252)) if sd and not math.isnan(sd) and sd > 0 else None
    mdd = float((eq / eq.cummax() - 1).min())
    return {"n_days": int(len(r)), "total": _r(total), "cagr": _r(cagr), "sharpe": _r(sharpe, 2),
            "max_dd": _r(mdd)}


# --------------------------------------------------------------------------- ① ②
def spearman(a: pd.Series, b: pd.Series) -> float | None:
    d = pd.concat([pd.to_numeric(a, errors="coerce"), pd.to_numeric(b, errors="coerce")],
                  axis=1).dropna()
    if len(d) < 3:
        return None
    ra, rb = d.iloc[:, 0].rank(), d.iloc[:, 1].rank()
    v = ra.corr(rb)
    return None if pd.isna(v) else float(v)


def coincident(score: pd.Series, close: pd.Series) -> dict:
    """① 同時整合性：急落日に恐怖側か／急騰日に強欲側か、下落率・20日リターンとの順位相関。"""
    c = pd.to_numeric(close, errors="coerce")
    r1 = c.pct_change()
    s = pd.to_numeric(score, errors="coerce")
    stress = r1 <= STRESS_RET
    rally = r1 >= RALLY_RET
    dd60 = c / c.rolling(60, min_periods=20).max() - 1
    ret20 = c / c.shift(20) - 1
    return {
        "stress_days": int(stress.sum()),
        "stress_fear_share": _r((s[stress] < FEAR_LINE).mean() if stress.any() else None, 3),
        "rally_days": int(rally.sum()),
        "rally_greed_share": _r((s[rally] > GREED_LINE).mean() if rally.any() else None, 3),
        "spearman_dd60": _r(spearman(s, dd60), 3),
        "spearman_ret20": _r(spearman(s, ret20), 3),
    }


def stability(score: pd.Series, close: pd.Series) -> dict:
    """② 安定性：日次変化の大きさと、大きく動いた日にスコアが相場と逆向きに動いた割合。"""
    s = pd.to_numeric(score, errors="coerce")
    ds = s.diff()
    r1 = pd.to_numeric(close, errors="coerce").pct_change()
    big = r1.abs() >= abs(STRESS_RET)
    opp = (np.sign(ds[big]) * np.sign(r1[big])) < 0
    return {
        "daily_change_std": _r(ds.std(), 2),
        "big_move_days": int(big.sum()),
        "opposite_share": _r(opp.mean() if big.any() else None, 3),
    }


def saturation(score: pd.Series) -> dict:
    s = pd.to_numeric(score, errors="coerce").dropna()
    if len(s) == 0:
        return {"n": 0}
    return {"n": int(len(s)), "low_lt5": _r((s < 5).mean(), 3), "high_gt95": _r((s > 95).mean(), 3)}


# --------------------------------------------------------------------------- 期間ごとの評価
def evaluate_period(df: pd.DataFrame, p: EvalParams, start=None, end=None,
                    price_cutoff=None) -> dict:
    """期間 [start, end) の評価。price_cutoff 以降の価格に依存する将来リターンは使わない
    （検証期間の値動きで調整用期間を評価しないため）。"""
    close = df["index"]
    fwd = forward_returns(close, p.horizons, p.lag)
    if price_cutoff is not None:
        ex = forward_exit_dates(df.index, p.horizons, p.lag)
        for h in p.horizons:
            fwd.loc[~(ex[h] < pd.Timestamp(price_cutoff)), h] = np.nan
    sel = pd.Series(True, index=df.index)
    if start is not None:
        sel &= df.index >= pd.Timestamp(start)
    if end is not None:
        sel &= df.index < pd.Timestamp(end)
    sel &= df["coverage"] >= p.min_coverage
    d = df[sel]
    f = fwd[sel]
    if len(d) == 0:
        return {"n_days": 0}
    score = d["score"]

    res: dict = {
        "n_days": int(len(d)),
        "range": [d.index.min().strftime("%Y-%m-%d"), d.index.max().strftime("%Y-%m-%d")],
        "band_share": {"lt25": _r((score < p.long_th).mean(), 3),
                       "gt75": _r((score > p.short_th).mean(), 3)},
    }
    # ③ 逆張り（主軸）
    res["contrarian"] = {
        "long": {"days": day_stats(f, zone_mask(score, "long", p.long_th), "long"),
                 "events": event_stats(f, zone_events(score, "long", p.long_th, p.cooldown), "long"),
                 "event_dates": [x.strftime("%Y-%m-%d")
                                 for x in zone_events(score, "long", p.long_th, p.cooldown)]},
        "short": {"days": day_stats(f, zone_mask(score, "short", p.short_th), "short"),
                  "events": event_stats(f, zone_events(score, "short", p.short_th, p.cooldown), "short"),
                  "event_dates": [x.strftime("%Y-%m-%d")
                                  for x in zone_events(score, "short", p.short_th, p.cooldown)]},
        "neutral_days": day_stats(f, (score >= p.long_th) & (score <= p.short_th), "long"),
    }
    # 売買ルール（期間内の価格のみ。cutoff 以降は切る）
    dclose = close[sel]
    res["backtest"] = {
        "long_short": backtest(score, dclose, p.long_th, p.short_th, p.exit_level, p.lag, True),
        "long_only": backtest(score, dclose, p.long_th, p.short_th, p.exit_level, p.lag, False),
    }
    # 感度（参考）
    sens = []
    h_ref = 20 if 20 in p.horizons else p.horizons[0]
    for lt in p.sens_long:
        for st in p.sens_short:
            le = event_stats(f[[h_ref]], zone_events(score, "long", lt, p.cooldown), "long")[str(h_ref)]
            se = event_stats(f[[h_ref]], zone_events(score, "short", st, p.cooldown), "short")[str(h_ref)]
            bt = backtest(score, dclose, lt, st, p.exit_level, p.lag, True)["strategy"]
            sens.append({"long_th": lt, "short_th": st, "long_events": le, "short_events": se,
                         "bt_total": bt.get("total"), "bt_sharpe": bt.get("sharpe")})
    res["sensitivity"] = {"horizon": h_ref, "grid": sens}
    # ① ②
    res["coincident"] = coincident(score, dclose)
    res["stability"] = stability(score, dclose)
    res["saturation"] = saturation(score)

    # 指標別診断
    ind = {}
    ret20 = dclose / dclose.shift(20) - 1
    for iid in p.indicator_ids:
        col = f"{iid}_score"
        if col not in d.columns:
            continue
        sc = pd.to_numeric(d[col], errors="coerce")
        if sc.notna().sum() == 0:
            ind[iid] = {"n": 0}
            continue
        ev_l = zone_events(sc, "long", p.long_th, p.cooldown)
        ev_s = zone_events(sc, "short", p.short_th, p.cooldown)
        ind[iid] = {
            "n": int(sc.notna().sum()),
            "saturation": saturation(sc),
            "daily_change_std": _r(sc.diff().std(), 2),
            "stress_fear_share": coincident(sc, dclose)["stress_fear_share"],
            "spearman_ret20": _r(spearman(sc, ret20), 3),
            "long_days": day_stats(f[[h_ref]], zone_mask(sc, "long", p.long_th), "long")[str(h_ref)],
            "short_days": day_stats(f[[h_ref]], zone_mask(sc, "short", p.short_th), "short")[str(h_ref)],
            "long_events": event_stats(f[[h_ref]], ev_l, "long")[str(h_ref)],
            "short_events": event_stats(f[[h_ref]], ev_s, "short")[str(h_ref)],
        }
    res["indicators"] = ind
    cols = [f"{i}_score" for i in p.indicator_ids if f"{i}_score" in d.columns]
    if cols:
        cm = d[cols].apply(pd.to_numeric, errors="coerce").rank().corr()
        cm.index = [c[:-6] for c in cm.index]
        cm.columns = [c[:-6] for c in cm.columns]
        res["indicator_corr"] = {r: {c: _r(cm.loc[r, c], 2) for c in cm.columns} for r in cm.index}
    return res


def coverage_summary(df: pd.DataFrame, start=None) -> dict:
    d = df if start is None else df[df.index >= pd.Timestamp(start)]
    if len(d) == 0:
        return {}
    by_month = d["coverage"].groupby(d.index.to_period("M")).min()
    first_full = d.index[d["coverage"] >= d["coverage"].max()]
    return {
        "max": int(d["coverage"].max()),
        "first_full_date": first_full.min().strftime("%Y-%m-%d") if len(first_full) else None,
        "min_by_month": {str(k): int(v) for k, v in by_month.items()},
    }


def evaluate_variant(df: pd.DataFrame, p: EvalParams, start: str, holdout_start: str) -> dict:
    if not p.indicator_ids:
        p.indicator_ids = indicator_ids_from(df)
    return {
        "coverage": coverage_summary(df, start),
        "calibration": evaluate_period(df, p, start=start, end=holdout_start,
                                       price_cutoff=holdout_start),
        "holdout": evaluate_period(df, p, start=holdout_start),
        "full": evaluate_period(df, p, start=start),
    }
