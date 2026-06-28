"""パイプライン：生値系列 → point-in-time 正規化 → 加重合成 → JSON。

入力は {indicator_id: IndicatorSeries} の dict（生値・公表日インデックス）。
各日付について、その日までに入手可能だった値だけで正規化し合成する（§3.4）。
"""

from __future__ import annotations

import pandas as pd

from .compose import ComponentScore, compose
from .config import Config
from .fetchers.base import IndicatorSeries
from .normalize import normalize_indicator


def _component_for_date(
    config: Config, ind, ser: IndicatorSeries | None, date: pd.Timestamp
) -> ComponentScore:
    """1指標・1日付の正規化済みコンポーネントを返す。取得不能なら stale。"""
    if ser is None:
        return ComponentScore(
            id=ind.id, label_ja=ind.label_ja, dimension=ind.dimension,
            raw=None, score=None, inverted=ind.inverted, stale=True,
        )

    window = ser.as_of(date).dropna()
    if len(window) == 0:
        return ComponentScore(
            id=ind.id, label_ja=ind.label_ja, dimension=ind.dimension,
            raw=None, score=None, inverted=ind.inverted, stale=True,
        )

    history = list(window.values)
    raw = float(window.iloc[-1])
    try:
        score = normalize_indicator(
            method=ind.method,
            history=history,
            lookback=config.lookback_days,
            inverted=ind.inverted,
            anchors=ind.anchors,
        )
    except Exception:
        return ComponentScore(
            id=ind.id, label_ja=ind.label_ja, dimension=ind.dimension,
            raw=raw, score=None, inverted=ind.inverted, stale=True,
        )

    return ComponentScore(
        id=ind.id, label_ja=ind.label_ja, dimension=ind.dimension,
        raw=raw, score=score, inverted=ind.inverted, stale=False,
    )


def components_for_date(
    config: Config, raw_series: dict[str, IndicatorSeries], date: pd.Timestamp
) -> list[ComponentScore]:
    return [
        _component_for_date(config, ind, raw_series.get(ind.id), date)
        for ind in config.indicators
    ]


def build_latest(
    config: Config, raw_series: dict[str, IndicatorSeries], as_of: pd.Timestamp
) -> dict:
    comps = components_for_date(config, raw_series, as_of)
    return compose(config, comps, as_of.strftime("%Y-%m-%d"))


def build_history(
    config: Config, raw_series: dict[str, IndicatorSeries], dates: list[pd.Timestamp]
) -> list[dict]:
    """各日付の合成スコア時系列を返す（history.json 用）。

    coverage が 0 の日（全指標欠損）はスコア None になるため出力から除外する。
    """
    out: list[dict] = []
    for d in dates:
        comps = components_for_date(config, raw_series, d)
        result = compose(config, comps, d.strftime("%Y-%m-%d"))
        if result["score"] is None:
            continue
        out.append(
            {
                "date": result["as_of"],
                "score": result["score"],
                "band": result["band"],
                "coverage": result["coverage"],
            }
        )
    return out


def union_business_dates(
    raw_series: dict[str, IndicatorSeries], start: pd.Timestamp | None = None
) -> list[pd.Timestamp]:
    """全指標の公表日の和集合（昇順）。history のサンプリング日付に使う。"""
    idx = pd.DatetimeIndex([])
    for ser in raw_series.values():
        idx = idx.union(ser.series.index)
    if start is not None:
        idx = idx[idx >= start]
    return list(idx.sort_values())
