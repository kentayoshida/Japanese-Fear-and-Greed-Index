"""fetcher 共通の基盤。

IndicatorSeries は「ある指標の生値を、実公表日（point-in-time）で
インデックスした時系列」。pipeline はこの系列を使って、各日付時点で
入手可能だった値のみから正規化スコアを計算する（未来情報の混入を防ぐ）。
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


class FetchError(RuntimeError):
    """データ取得・検証に失敗したことを表す。当該指標は当日合成から除外する。"""


@dataclass
class IndicatorSeries:
    indicator_id: str
    series: pd.Series  # index=日付(DatetimeIndex, 公表日基準), value=生値(float)
    source: str        # 取得元の識別子（メタデータ／監査用）

    def __post_init__(self) -> None:
        if not isinstance(self.series.index, pd.DatetimeIndex):
            self.series.index = pd.to_datetime(self.series.index)
        self.series = self.series.sort_index()
        # 重複日付は最後の値を採用
        self.series = self.series[~self.series.index.duplicated(keep="last")]

    def as_of(self, date: pd.Timestamp) -> pd.Series:
        """指定日「まで」に公表済みの値だけを返す（point-in-time 厳守 §3.4）。"""
        return self.series.loc[self.series.index <= date]

    def latest_date(self) -> pd.Timestamp:
        return self.series.index.max()


def validate_series(
    s: pd.Series,
    *,
    indicator_id: str,
    min_value: float | None = None,
    max_value: float | None = None,
    min_points: int = 1,
) -> pd.Series:
    """取得系列の型・レンジ・データ点数を検証する（§8 データ品質最優先）。"""
    s = pd.to_numeric(s, errors="coerce").dropna()
    if len(s) < min_points:
        raise FetchError(
            f"{indicator_id}: insufficient data points ({len(s)} < {min_points})"
        )
    if min_value is not None and (s < min_value).any():
        bad = s[s < min_value]
        raise FetchError(f"{indicator_id}: values below {min_value}: {bad.tail(3).to_dict()}")
    if max_value is not None and (s > max_value).any():
        bad = s[s > max_value]
        raise FetchError(f"{indicator_id}: values above {max_value}: {bad.tail(3).to_dict()}")
    return s
