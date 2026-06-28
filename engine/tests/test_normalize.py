import numpy as np

from fgi.normalize import anchor_map, normalize_indicator, percentile_rank


def test_percentile_rank_monotone():
    # 単調増加列：最大値はほぼ100付近、最小値は0付近
    vals = list(range(100))
    assert percentile_rank(vals, lookback=100) > 99
    assert percentile_rank(vals[::-1] + [vals[-1]], lookback=100) > 99  # 末尾が最大


def test_percentile_rank_midpoint():
    vals = [10, 20, 30, 40, 50]
    # 末尾(50)は最大なので mid-rank = (4 + 0.5)/5 = 0.9 → 90
    assert abs(percentile_rank(vals, lookback=5) - 90.0) < 1e-6


def test_percentile_rank_lookback_window():
    # lookback で窓を絞る：直近3個 [3,4,5] の末尾5は最大
    vals = [100, 100, 100, 3, 4, 5]
    assert abs(percentile_rank(vals, lookback=3) - (2 + 0.5) / 3 * 100) < 1e-6


def test_percentile_rank_handles_nan():
    vals = [1.0, np.nan, 2.0, 3.0]
    # NaN を除外して [1,2,3]、末尾3は最大
    assert percentile_rank(vals, lookback=10) > 80


def test_anchor_map_interpolation():
    anchors = [[70, 0], [100, 50], [130, 100]]
    assert anchor_map(100, anchors) == 50
    assert anchor_map(85, anchors) == 25      # 70→100 の中点
    assert anchor_map(115, anchors) == 75     # 100→130 の中点


def test_anchor_map_clips():
    anchors = [[70, 0], [100, 50], [130, 100]]
    assert anchor_map(50, anchors) == 0       # 下限クリップ
    assert anchor_map(200, anchors) == 100    # 上限クリップ


def test_anchor_margin_pl():
    anchors = [[-30, 0], [-20, 20], [-10, 50], [0, 100]]
    assert anchor_map(-20, anchors) == 20
    assert anchor_map(-25, anchors) == 10     # -30→-20 の中点
    assert anchor_map(-35, anchors) == 0      # クラッシュ帯クリップ
    assert anchor_map(5, anchors) == 100


def test_normalize_inverted():
    # 反転：percentile=90 → 100-90=10（高VIは恐怖）
    vals = [10, 20, 30, 40, 50]
    s = normalize_indicator(method="percentile", history=vals, lookback=5, inverted=True)
    assert abs(s - 10.0) < 1e-6
