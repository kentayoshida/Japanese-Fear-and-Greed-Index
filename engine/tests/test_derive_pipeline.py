import numpy as np
import pandas as pd

from fgi.config import load_config
from fgi.fetchers.base import IndicatorSeries
from fgi.fetchers.derive import (
    advance_decline_ratio,
    margin_pl_mtm,
    momentum_125dma,
    new_high_low_net,
    put_call_ratio,
    safe_haven,
)
from fgi.pipeline import build_history, build_latest, union_business_dates


def _dates(n):
    return pd.bdate_range("2024-01-01", periods=n)


def test_momentum_125dma_sign():
    d = _dates(200)
    # 直近を急騰させると上方乖離（正）になる
    close = pd.Series(np.linspace(100, 110, 200), index=d)
    close.iloc[-1] = 130
    dev = momentum_125dma(close)
    assert dev.iloc[-1] > 0
    assert len(dev) == 200 - 125 + 1  # min_periods=125: 先頭124点が落ちる


def test_advance_decline_ratio():
    d = _dates(30)
    adv = pd.Series([60] * 30, index=d)
    dec = pd.Series([40] * 30, index=d)
    r = advance_decline_ratio(adv, dec, window=25)
    assert abs(r.iloc[-1] - 150.0) < 1e-6  # 60/40*100


def test_new_high_low_net():
    d = _dates(5)
    nh = pd.Series([100, 90, 80, 70, 60], index=d)
    nl = pd.Series([10, 20, 30, 40, 50], index=d)
    net = new_high_low_net(nh, nl)
    assert net.iloc[0] == 90
    assert net.iloc[-1] == 10


def test_put_call_ratio_v2_columns():
    # v2 カラム: Vo(出来高), PCDiv(1=Put,2=Call)
    df = pd.DataFrame(
        {
            "Date": ["2026-06-25", "2026-06-25", "2026-06-25", "2026-06-25"],
            "PCDiv": ["1", "1", "2", "2"],
            "Vo": [300, 300, 200, 200],
        }
    )
    r = put_call_ratio(df)
    assert abs(r.iloc[-1] - (600 / 400)) < 1e-6


def test_short_selling_market_ratio():
    from fgi.fetchers.derive import short_selling_market_ratio

    # 2業種・1日。空売り比率 = (規制あり+規制なし) / (実売り+空売り計) * 100
    df = pd.DataFrame(
        {
            "Date": ["2026-06-25", "2026-06-25"],
            "S33": ["0050", "1050"],
            "SellExShortVa": [600.0, 400.0],   # 実売り合計 1000
            "ShrtWithResVa": [300.0, 100.0],   # 規制あり 400
            "ShrtNoResVa": [100.0, 100.0],     # 規制なし 200
        }
    )
    r = short_selling_market_ratio(df)
    # short=600, total=1600 → 37.5%
    assert abs(r.iloc[-1] - 37.5) < 1e-6


def test_safe_haven_equity_outperform():
    d = _dates(40)
    eq = pd.Series(np.linspace(100, 120, 40), index=d)   # 株式上昇
    bd = pd.Series(np.linspace(100, 101, 40), index=d)   # 債券ほぼ横ばい
    sh = safe_haven(eq, bd, window=20)
    assert sh.iloc[-1] > 0  # 株式優位


def test_margin_pl_mtm_rising_index_positive():
    # 建値一定の週次残高 + 上昇する指数 → 含み益（正）で MTM される。
    weeks = pd.date_range("2024-01-05", periods=6, freq="W-FRI")
    weekly_long = pd.Series([1000.0] * 6, index=weeks)  # 残高一定＝建値は初週水準に固定
    d = pd.bdate_range("2024-01-01", periods=60)
    idx = pd.Series(np.linspace(100.0, 120.0, 60), index=d)  # +20% 上昇
    pl = margin_pl_mtm(weekly_long, idx)
    assert pl.iloc[-1] > 0  # 指数上昇 → 買い方は含み益
    # 建値は初週(≈100)付近、最終指数120 → おおむね +20% 近辺
    assert 10.0 < pl.iloc[-1] < 30.0


def test_margin_pl_mtm_weighted_entry_on_additions():
    # 高値圏で買い増すと平均建値が上がり、同一指数でも含み損益が下がる。
    weeks = pd.date_range("2024-01-05", periods=4, freq="W-FRI")
    d = pd.bdate_range("2024-01-01", periods=40)
    idx = pd.Series(np.linspace(100.0, 130.0, 40), index=d)
    flat = pd.Series([1000.0, 1000.0, 1000.0, 1000.0], index=weeks)  # 買い増しなし
    added = pd.Series([1000.0, 1000.0, 2000.0, 3000.0], index=weeks)  # 高値で買い増し
    pl_flat = margin_pl_mtm(flat, idx).iloc[-1]
    pl_added = margin_pl_mtm(added, idx).iloc[-1]
    assert pl_added < pl_flat  # 高値買い増しで建値上昇 → 含み損益は縮小


def test_point_in_time_no_lookahead():
    # 公表日より後の値を使わないこと（as_of）
    d = _dates(10)
    ser = IndicatorSeries("x", pd.Series(range(10), index=d, dtype="float64"), "test")
    sub = ser.as_of(d[4])
    assert len(sub) == 5
    assert sub.iloc[-1] == 4


def test_pipeline_latest_and_history():
    cfg = load_config()
    d = _dates(300)
    rng = np.random.default_rng(42)
    raw = {}
    # 全指標にランダムウォーク的な系列を与える
    for ind in cfg.indicators:
        vals = np.cumsum(rng.normal(0, 1, len(d))) + 50
        raw[ind.id] = IndicatorSeries(ind.id, pd.Series(vals, index=d), "synthetic")

    latest = build_latest(cfg, raw, d[-1])
    assert latest["coverage"] == len(cfg.indicators)
    assert 0 <= latest["score"] <= 100
    assert len(latest["components"]) == len(cfg.indicators)

    dates = union_business_dates(raw, start=d[260])
    hist = build_history(cfg, raw, dates)
    assert len(hist) > 0
    for row in hist:
        assert 0 <= row["score"] <= 100
        assert row["coverage"] == len(cfg.indicators)


# ---- #5 オプション・スキュー ------------------------------------------------
def _chain(date="2026-11-20", under=50000.0, sqd_near="2026-11-27", sqd_next="2026-12-11",
           extra_rows=()):
    """期近(11月限, SQ=sqd_near)・次限月(12月限)の合成チェーン。"""
    rows = []
    for cm, sqd, put_base, call_base in (("2026-11", sqd_near, 30.0, 22.0),
                                         ("2026-12", sqd_next, 28.0, 24.0)):
        for k in range(45000, 55500, 500):
            rows.append(dict(Date=date, EmMrgnTrgDiv="002", UnderPx=under, SQD=sqd, CM=cm,
                             PCDiv="1", Strike=float(k), IV=put_base + (50000 - k) / 1000.0))
            rows.append(dict(Date=date, EmMrgnTrgDiv="002", UnderPx=under, SQD=sqd, CM=cm,
                             PCDiv="2", Strike=float(k), IV=call_base + (k - 50000) / 5000.0))
    rows.extend(extra_rows)
    return pd.DataFrame(rows)


def test_option_skew_daily_picks_front_month_5pct_otm():
    from fgi.fetchers.derive import option_skew_daily

    put_iv, call_iv, raw = option_skew_daily(_chain())
    # 期近(11月限): put 47500 → 30+2.5=32.5 / call 52500 → 22+0.5=22.5
    assert abs(put_iv - 32.5) < 1e-9
    assert abs(call_iv - 22.5) < 1e-9
    assert abs(raw - 10.0) < 1e-9


def test_option_skew_daily_rolls_to_next_month_when_sq_within_7_days():
    from fgi.fetchers.derive import option_skew_daily

    # 当日2026-11-20 に対し SQ=11-26（6暦日）→ 次の限月(12月限)に乗り換え
    put_iv, call_iv, raw = option_skew_daily(_chain(sqd_near="2026-11-26"))
    assert abs(put_iv - (28.0 + 2.5)) < 1e-9
    assert abs(call_iv - (24.0 + 0.5)) < 1e-9
    # ちょうど7暦日（11-27）は期近のまま
    assert abs(option_skew_daily(_chain(sqd_near="2026-11-27"))[2] - 10.0) < 1e-9


def test_option_skew_daily_excludes_emergency_margin_rows_and_zero_iv():
    from fgi.fetchers.derive import option_skew_daily

    # 緊急取引証拠金区分 "001" の行（極端な IV）は無視される
    bogus = [dict(Date="2026-11-20", EmMrgnTrgDiv="001", UnderPx=50000.0, SQD="2026-11-27",
                  CM="2026-11", PCDiv="1", Strike=47500.0, IV=99.0)]
    assert abs(option_skew_daily(_chain(extra_rows=bogus))[2] - 10.0) < 1e-9
    # IV=0 の最近傍行は飛ばして IV>0 の次点を採る
    df = _chain()
    df.loc[(df.CM == "2026-11") & (df.PCDiv == "2") & (df.Strike == 52500.0), "IV"] = 0.0
    _, call_iv, _ = option_skew_daily(df)
    assert call_iv > 0 and abs(call_iv - 22.5) > 1e-6  # 52500 ではなく 52000/53000 側


def test_option_skew_daily_returns_none_when_unavailable():
    from fgi.fetchers.derive import option_skew_daily

    df = _chain()
    assert option_skew_daily(df[df.PCDiv == "1"]) is None  # コール無し
    assert option_skew_daily(_chain(sqd_near="2026-11-20", sqd_next="2026-11-25")) is None  # 限月なし


def test_smooth_option_skew_5day_mean():
    from fgi.fetchers.derive import smooth_option_skew

    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 11.0], index=_dates(6))
    sm = smooth_option_skew(s, window=5)
    assert len(sm) == 2  # 5本そろった日のみ
    assert abs(sm.iloc[0] - 3.0) < 1e-9
    assert abs(sm.iloc[1] - 5.0) < 1e-9


# ---- #7 空売り比率の5日平均 -------------------------------------------------
def test_rolling_mean_matches_spec_values():
    """実装指示 #7 の回帰値：11-24 の5日平均 40.69、11-20 は 41.87（本番の単日値から）。"""
    from fgi.fetchers.derive import rolling_mean

    daily = pd.Series(
        [43.3218, 42.1443, 41.6149, 43.6934, 43.4256, 38.4885, 36.2262],
        index=pd.to_datetime(["2026-11-13", "2026-11-16", "2026-11-17", "2026-11-18",
                              "2026-11-19", "2026-11-20", "2026-11-24"]),
    )
    sm = rolling_mean(daily, window=5)
    assert round(sm.loc["2026-11-24"], 2) == 40.69
    assert round(sm.loc["2026-11-20"], 2) == 41.87
    assert len(sm) == 3  # 5本そろう 11-19 以降のみ


def test_pipeline_emits_raw_daily_for_smoothed_indicator():
    """daily を持つ指標は raw=5日平均、raw_daily=当日単日値として出力される。"""
    from fgi.config import load_config
    from fgi.fetchers.base import IndicatorSeries
    from fgi.fetchers.derive import rolling_mean
    from fgi.pipeline import build_latest

    cfg = load_config()
    d = _dates(30)
    daily = pd.Series([40.0 + (i % 7) for i in range(30)], index=d)
    ser = IndicatorSeries("short_selling_ratio", rolling_mean(daily, 5), "test", daily=daily)
    out = build_latest(cfg, {"short_selling_ratio": ser}, d[-1])
    c = next(c for c in out["components"] if c["id"] == "short_selling_ratio")
    assert abs(c["raw"] - daily.iloc[-5:].mean()) < 1e-6
    assert abs(c["raw_daily"] - daily.iloc[-1]) < 1e-6
    # daily を持たない指標は raw_daily=None
    other = next(c for c in out["components"] if c["id"] == "nikkei_vi")
    assert other["raw_daily"] is None
