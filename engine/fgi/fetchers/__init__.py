"""指標ごとのデータ取得モジュール（仕様 §6）。

各 fetcher は疎結合で、ソースが落ちても他が動くように独立して実装する。
取得値はレンジ・型・鮮度を検証し、異常時はその指標を当日合成から除外
（stale=True）する。欠損を中立値(50)で埋めない（§8）。

各 fetcher は `fetch(config) -> IndicatorSeries` を実装する。
IndicatorSeries は「実公表日（point-in-time）でインデックスした生値の時系列」。
"""

from .base import IndicatorSeries, FetchError

__all__ = ["IndicatorSeries", "FetchError"]
