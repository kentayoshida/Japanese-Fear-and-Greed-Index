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
            description_ja=ind.description_ja,
        )

    window = ser.as_of(date).dropna()
    if len(window) == 0:
        return ComponentScore(
            id=ind.id, label_ja=ind.label_ja, dimension=ind.dimension,
            raw=None, score=None, inverted=ind.inverted, stale=True,
            description_ja=ind.description_ja,
        )

    history = list(window.values)
    raw = float(window.iloc[-1])
    data_date = pd.Timestamp(window.index[-1]).strftime("%Y-%m-%d")  # この指標の基準日
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
            description_ja=ind.description_ja, data_date=data_date,
        )

    return ComponentScore(
        id=ind.id, label_ja=ind.label_ja, dimension=ind.dimension,
        raw=raw, score=score, inverted=ind.inverted, stale=False,
        description_ja=ind.description_ja, data_date=data_date,
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
    config: Config,
    raw_series: dict[str, IndicatorSeries],
    dates: list[pd.Timestamp],
    index_series: IndicatorSeries | None = None,
) -> list[dict]:
    """各日付の合成スコア時系列を返す（history.json 用）。

    coverage が 0 の日（全指標欠損）はスコア None になるため出力から除外する。
    index_series（版の株価指数）を渡すと、その日時点(point-in-time)の指数終値を
    `index` として各行に添える（チャートのオーバーレイ用）。
    """
    out: list[dict] = []
    for d in dates:
        comps = components_for_date(config, raw_series, d)
        result = compose(config, comps, d.strftime("%Y-%m-%d"))
        if result["score"] is None:
            continue
        row = {
            "date": result["as_of"],
            "score": result["score"],
            "band": result["band"],
            "coverage": result["coverage"],
        }
        if index_series is not None:
            iw = index_series.as_of(d).dropna()
            if len(iw):
                row["index"] = round(float(iw.iloc[-1]), 2)
        out.append(row)
    return out


def build_sparks(
    config: Config, raw_series: dict[str, IndicatorSeries], dates: list[pd.Timestamp]
) -> dict[str, list]:
    """各指標の正規化スコアを dates 上で point-in-time 算出（カードのミニ時系列用）。

    返り値: {indicator_id: [{"d": "YYYY-MM-DD", "s": score|None}, ...]}
    """
    from .normalize import normalize_indicator

    out: dict[str, list] = {}
    for ind in config.indicators:
        ser = raw_series.get(ind.id)
        pts: list = []
        if ser is not None:
            for d in dates:
                w = ser.as_of(d).dropna()
                s = None
                if len(w):
                    try:
                        s = normalize_indicator(
                            method=ind.method, history=list(w.values),
                            lookback=config.lookback_days, inverted=ind.inverted,
                            anchors=ind.anchors,
                        )
                    except Exception:  # noqa: BLE001
                        s = None
                pts.append({"d": pd.Timestamp(d).strftime("%Y-%m-%d"),
                            "s": None if s is None else round(float(s), 1)})
        out[ind.id] = pts
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
