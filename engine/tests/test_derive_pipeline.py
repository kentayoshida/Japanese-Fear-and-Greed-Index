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
