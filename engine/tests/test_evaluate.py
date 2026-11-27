"""逆張り評価（fgi.evaluate）と、評価用データ取得まわりの単体テスト。"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from fgi import evaluate as ev


def _idx(n, start="2025-01-06"):
    return pd.bdate_range(start=start, periods=n)


# ---------------------------------------------------------------- 将来リターン
def test_forward_returns_use_next_day_close_no_lookahead():
    close = pd.Series([100, 110, 121, 133.1, 146.41], index=_idx(5))
    f = ev.forward_returns(close, horizons=(1, 2), lag=1)
    # 日0のシグナル → 日1の終値(110)で建て、1日後=日2(121)
    assert abs(f.loc[close.index[0], 1] - (121 / 110 - 1)) < 1e-12
    assert abs(f.loc[close.index[0], 2] - (133.1 / 110 - 1)) < 1e-12
    # 末尾は将来が無いので NaN（先読みしない）
    assert math.isnan(f.loc[close.index[-1], 1])
    assert math.isnan(f.loc[close.index[-2], 1])


def test_price_cutoff_drops_returns_that_need_holdout_prices():
    idx = _idx(10)
    df = pd.DataFrame({"score": [10.0] * 10, "coverage": 8,
                       "index": np.linspace(100, 109, 10)}, index=idx)
    p = ev.EvalParams(horizons=(2,), min_coverage=8)
    cutoff = idx[6]
    res = ev.evaluate_period(df, p, start=idx[0], end=cutoff, price_cutoff=cutoff)
    # 日 t の 2日後リターンは日 t+3 の価格に依存。t+3 < cutoff(=日6) を満たすのは t ≤ 2
    assert res["contrarian"]["long"]["days"]["2"]["n"] == 3


# ---------------------------------------------------------------- ゾーン・イベント
def test_zone_events_dedupe_with_cooldown():
    s = pd.Series([50, 20, 22, 60, 21, 60, 60, 60, 60, 60, 60, 19], index=_idx(12), dtype=float)
    e = ev.zone_events(s, "long", 25, cooldown=5)
    # 日1で突入。日4は直前5日内(日1,2)にゾーン内があるので除外。日11は直前5日がゾーン外 → 突入
    assert list(e) == [s.index[1], s.index[11]]


def test_day_and_event_stats_hit_rates():
    idx = _idx(6)
    fwd = pd.DataFrame({20: [0.05, -0.02, 0.01, np.nan, 0.03, -0.01]}, index=idx)
    mask = pd.Series([True, True, False, True, False, False], index=idx)
    d = ev.day_stats(fwd, mask, "long")["20"]
    assert d["n"] == 2 and d["hit"] == 0.5
    assert abs(d["mean"] - 0.015) < 1e-9
    s = ev.event_stats(fwd, pd.DatetimeIndex([idx[1], idx[5]]), "short")["20"]
    assert s["n"] == 2 and s["hit"] == 1.0  # Short は下落が勝ち


def test_t_stat():
    assert ev.t_stat([1.0]) is None
    assert ev.t_stat([1.0, 1.0]) is None  # 分散ゼロ
    t = ev.t_stat([1.0, 2.0, 3.0])
    assert abs(t - 2.0 / (1.0 / math.sqrt(3))) < 1e-9


# ---------------------------------------------------------------- 売買ルール
def test_positions_state_machine():
    s = pd.Series([50, 20, 40, 55, 80, 60, 45, 30, np.nan, 20], index=_idx(10), dtype=float)
    pos = ev.positions(s, 25, 75, 50)
    #            50 20 40 55 80  60  45 30 NaN 20
    assert list(pos) == [0, 1, 1, 0, -1, -1, 0, 0, 0, 1]
    assert list(ev.positions(s, 25, 75, 50, allow_short=False)) == [0, 1, 1, 0, 0, 0, 0, 0, 0, 1]


def test_backtest_applies_one_day_lag():
    idx = _idx(6)
    close = pd.Series([100, 100, 110, 121, 121, 121], index=idx, dtype=float)
    score = pd.Series([20, 60, 60, 60, 60, 60], index=idx, dtype=float)
    # 日0 Long 判定 → 日1 終値で建玉 → 日2 のリターン(+10%)を得る。日1で 60 → 手仕舞い判定、
    # 日2 終値で手仕舞い → 日3 のリターンは得ない
    bt = ev.backtest(score, close, 25, 75, 50, lag=1)
    assert abs(bt["strategy"]["total"] - 0.10) < 1e-9
    assert bt["trades"] == 1


# ---------------------------------------------------------------- ① ② 補助
def test_coincident_and_stability():
    idx = _idx(5)
    close = pd.Series([100, 95, 96, 92, 100], index=idx, dtype=float)  # −5%, +1%, −4.2%, +8.7%
    score = pd.Series([50, 30, 35, 50, 40], index=idx, dtype=float)
    c = ev.coincident(score, close)
    assert c["stress_days"] == 2
    assert c["stress_fear_share"] == 0.5        # 日1=30(恐怖) / 日3=50(非恐怖)
    st = ev.stability(score, close)
    # ±3%超: 日1(下落・スコア下落=同方向) 日3(下落・スコア上昇=逆行) 日4(上昇・スコア下落=逆行)
    assert st["big_move_days"] == 3
    assert abs(st["opposite_share"] - 2 / 3) < 1e-3


def test_saturation_shares():
    s = pd.Series([1, 2, 50, 99, 60], dtype=float)
    r = ev.saturation(s)
    assert r["low_lt5"] == 0.4 and r["high_gt95"] == 0.2


def test_evaluate_variant_runs_on_synthetic_components():
    n = 400
    idx = _idx(n, "2024-01-04")
    rng = np.random.default_rng(0)
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, n))), index=idx)
    score = pd.Series(np.clip(50 + 30 * np.sin(np.arange(n) / 15), 0, 100), index=idx)
    df = pd.DataFrame({"score": score, "coverage": 8, "index": close,
                       "nikkei_vi_raw": 20.0, "nikkei_vi_score": score.values}, index=idx)
    res = ev.evaluate_variant(df, ev.EvalParams(), "2024-01-04", str(idx[350].date()))
    assert res["calibration"]["n_days"] == 350
    assert res["holdout"]["n_days"] == 50
    assert res["full"]["contrarian"]["long"]["events"]["20"]["n"] > 0
    assert "nikkei_vi" in res["full"]["indicators"]
    assert len(res["full"]["sensitivity"]["grid"]) == 9


# ---------------------------------------------------------------- データ取得まわり
def test_new_high_low_from_closes_full_window():
    idx = _idx(5)
    piv = pd.DataFrame({"A": [1, 2, 3, 4, 5], "B": [5, 4, 3, 2, 1], "C": [1, 3, 2, 3, 2]},
                       index=idx, dtype=float)
    from fgi.fetchers.derive import new_high_low_from_closes

    net = new_high_low_from_closes(piv, win=3)
    # 窓3が埋まる日2以降。日2: A新高・B新安・C(2)は高安どちらでもない → 0
    assert list(net.index) == list(idx[2:])
    assert net.loc[idx[2]] == 0
    # 日3: A新高, B新安, C=3 は窓[3,2,3]の最高値 → 新高 → +1
    assert net.loc[idx[3]] == 1


def test_adv_dec_from_closes_universe_filter():
    from fgi.fetchers.derive import adv_dec_from_closes

    prev = pd.Series({"1": 100.0, "2": 50.0, "3": 10.0, "4": 7.0})
    cur = pd.Series({"1": 101.0, "2": 49.0, "3": 10.0, "5": 3.0})
    assert adv_dec_from_closes(prev, cur) == (1.0, 1.0)            # 3 は変わらず、4/5 は片側のみ
    assert adv_dec_from_closes(prev, cur, universe={"2", "3"}) == (0.0, 1.0)


def test_stitch_with_proxy_scales_and_keeps_primary():
    from fgi.fetchers.derive import stitch_with_proxy

    idx = _idx(10)
    proxy = pd.Series(np.arange(10, 20, dtype=float), index=idx)        # 10..19
    primary = pd.Series(np.arange(15, 20, dtype=float) * 2, index=idx[5:])  # 30..38（比率2）
    primary.iloc[-1] = 999.0                                                # 公式値を優先すること
    out = stitch_with_proxy(primary, proxy)
    assert out.index.min() == idx[0]
    assert abs(out.loc[idx[0]] - 20.0) < 1e-9      # 10 × 2
    assert out.loc[idx[-1]] == 999.0
    # 重なりが無ければ primary のまま
    assert stitch_with_proxy(primary, proxy.iloc[:3]).equals(primary)


def test_fetch_start_respects_data_start():
    from dataclasses import replace
    from datetime import date

    from fgi.config import load_config
    from fgi.providers import _fetch_start

    cfg = load_config()
    assert cfg.data_start == "2022-11-01"
    assert _fetch_start(cfg, 10, warmup_days=0) == date(2022, 11, 1)
    assert _fetch_start(cfg, 10, warmup_days=30) == date(2022, 10, 2)
    no_ds = replace(cfg, data_start=None)
    assert _fetch_start(no_ds, 10) > date(2026, 1, 1)


def test_breadth_needed_dates():
    from fgi.providers import _breadth_needed_dates

    cal = _idx(10)
    need = _breadth_needed_dates(cal, missing_ad=[cal[5]], missing_nhl=[cal[9]], win=3)
    assert need == {cal[4], cal[5], cal[7], cal[8], cal[9]}
    # 窓が埋まらない日（先頭付近）は要求しない
    assert _breadth_needed_dates(cal, [cal[0]], [cal[1]], win=3) == set()


class _FakeClient:
    """全銘柄終値を決定論的に返すモック。"""

    def __init__(self, cal):
        self.cal = cal
        self.calls = 0

    def index_close(self, code="0000", from_date=None, to_date=None):
        s = pd.Series(1.0, index=self.cal)
        return s[s.index >= pd.Timestamp(from_date)] if from_date else s

    def equities_close_by_date(self, date):
        self.calls += 1
        i = list(self.cal).index(pd.Timestamp(date))
        # 銘柄 A は単調増加、B は単調減少、C は横ばい
        return pd.Series({"A": 100.0 + i, "B": 500.0 - i, "C": 50.0})

    def listed_codes_by_market(self, market_name=None):
        return {"A", "B", "C"}


def test_provide_breadth_backfills_and_trims(tmp_path, monkeypatch):
    from dataclasses import replace

    from fgi import providers
    from fgi.config import load_config

    cal = pd.bdate_range("2025-01-01", periods=320)
    cfg = load_config()
    cfg = replace(cfg, data_start=str(cal[260].date()),
                  output={**cfg.output, "latest_path": str(tmp_path / "latest.json")})
    monkeypatch.setattr(providers, "_jst_today", lambda: cal[-1].date())
    monkeypatch.setattr(providers, "_fetch_start",
                        lambda c, days_back, warmup_days=0: cal[260].date())
    providers._TRADING_DAYS_MEMO.clear()
    monkeypatch.setenv("JQUANTS_BREADTH_MAX_FETCH", "1000")
    client = _FakeClient(cal)
    series, errors = {}, {}
    providers._provide_breadth(cfg, client, series, errors)
    assert "new_high_low" in series and "advance_decline_25" in series, errors
    nhl = series["new_high_low"].series
    # A は常に新高値、B は常に新安値、C は横ばい（最高値=最安値=当日 → 両方に数える）→ 0
    assert (nhl == 0).all()
    assert nhl.index.min() == cal[260]
    ad = pd.read_csv(tmp_path / "series" / "advance_decline.csv")
    assert (ad["adv"] == 1).all() and (ad["dec"] == 1).all()
    # 終値キャッシュは直近 260 営業日に縮む
    cache = pd.read_csv(tmp_path / "series" / "stock_closes.csv.gz", compression="gzip")
    assert cache["date"].nunique() <= providers.BREADTH_KEEP_DAYS
    # 2回目はすべて計算済み → 追加取得なし
    calls = client.calls
    providers._provide_breadth(cfg, client, {}, {})
    assert client.calls == calls


def test_build_history_component_rows():
    from fgi.config import load_config
    from fgi.fetchers.base import IndicatorSeries
    from fgi.pipeline import build_history

    cfg = load_config()
    idx = _idx(30)
    ser = {"nikkei_vi": IndicatorSeries("nikkei_vi", pd.Series(np.arange(30.0) + 10, index=idx), "t")}
    rows: list = []
    hist = build_history(cfg, ser, list(idx[-3:]), component_rows=rows)
    assert len(rows) == len(hist) == 3
    assert rows[-1]["nikkei_vi_raw"] == 39.0
    assert rows[-1]["coverage"] == 1
    assert rows[-1]["option_skew_score"] is None  # 未取得の指標は None
