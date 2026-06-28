"""正規化（0〜100 への変換）。仕様 §3。

2方式をサポートする（指標ごとに config で選択）：
  - percentile : 直近 lookback 営業日のローリング・パーセンタイル順位
  - anchor     : 固定アンカーによる区分線形マッピング（境界外はクリップ）

方向の処理（§3.3）：inverted=True の指標は正規化後に score = 100 - score。
信用評価損益率のように「低い=Fear」をアンカーで吸収する指標は inverted=False。
"""

from __future__ import annotations

import math
from typing import Sequence

import pandas as pd


def percentile_rank(series: Sequence[float], lookback: int) -> float:
    """series の最後の値が、直近 lookback 個の窓内で占めるパーセンタイル順位 (0〜100)。

    分布を仮定せず外れ値に頑健（仕様 §3.1）。NaN は窓から除外する。
    窓内に有効値が1個しかない場合は中立 (50.0) を返す。
    """
    s = pd.Series(series, dtype="float64").dropna()
    if len(s) == 0:
        raise ValueError("percentile_rank: empty series after dropping NaN")

    window = s.iloc[-lookback:] if lookback > 0 else s
    current = window.iloc[-1]
    n = len(window)
    if n <= 1:
        return 50.0

    # mid-rank 方式（同値は 0.5 カウント）。CDF 的なパーセンタイル順位。
    less = (window < current).sum()
    equal = (window == current).sum()
    rank = (less + 0.5 * equal) / n
    return float(round(rank * 100.0, 6))


def anchor_map(value: float, anchors: Sequence[Sequence[float]]) -> float:
    """固定アンカー [[x, score], ...] による区分線形マッピング (§3.2)。

    anchors は x 昇順を想定（昇順でなければ内部でソート）。境界外はクリップ。
    """
    if value is None or (isinstance(value, float) and math.isnan(value)):
        raise ValueError("anchor_map: value is NaN/None")

    pts = sorted(([float(x), float(y)] for x, y in anchors), key=lambda p: p[0])
    if len(pts) < 2:
        raise ValueError("anchor_map: need at least 2 anchors")

    # 境界外クリップ
    if value <= pts[0][0]:
        return float(pts[0][1])
    if value >= pts[-1][0]:
        return float(pts[-1][1])

    # 区分線形補間
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= value <= x1:
            if x1 == x0:
                return float(y1)
            t = (value - x0) / (x1 - x0)
            return float(round(y0 + t * (y1 - y0), 6))

    # 到達しないはずだが安全側
    return float(pts[-1][1])


def normalize_indicator(
    *,
    method: str,
    history: Sequence[float],
    lookback: int,
    inverted: bool = False,
    anchors: Sequence[Sequence[float]] | None = None,
) -> float:
    """1指標の生値系列（point-in-time、古い→新しい）を 0〜100 スコアへ変換。

    history の最後の要素が「評価対象日の生値」。percentile は窓全体を、
    anchor は最後の値のみを使う。
    """
    if method == "percentile":
        score = percentile_rank(history, lookback)
    elif method == "anchor":
        if not anchors:
            raise ValueError("normalize_indicator: method=anchor requires anchors")
        current = pd.Series(history, dtype="float64").dropna().iloc[-1]
        score = anchor_map(float(current), anchors)
    else:
        raise ValueError(f"unknown normalization method: {method}")

    if inverted:
        score = 100.0 - score
    return float(round(score, 4))
