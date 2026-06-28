"""加重（Weighting）。仕様 §4。

既定：次元バケット均等加重（§4.1）。
  1. 各次元に均等加重（config の dimensions[].weight）。
  2. 次元内に複数指標がある場合は、その次元の重みを指標間で均等配分。

ブレッドスのように次元内に2指標ある場合の二重計上を避けるのが目的。
合成時には「当日採用できた指標」だけで重みを再正規化する（§3.4 / §5）。
"""

from __future__ import annotations

from collections import defaultdict

from .config import Config


def base_weights(config: Config) -> dict[str, float]:
    """全指標の基準重み（次元重み ÷ 次元内指標数）を返す。合計は概ね1。

    欠損を考慮しない「フル稼働時」の重み。実際の合成では available_weights を使う。
    """
    by_dim: dict[str, list[str]] = defaultdict(list)
    for ind in config.indicators:
        by_dim[ind.dimension].append(ind.id)

    weights: dict[str, float] = {}
    for ind in config.indicators:
        dim = config.dimensions[ind.dimension]
        n_in_dim = len(by_dim[ind.dimension])
        weights[ind.id] = dim.weight / n_in_dim

    # 次元重みは相対比のみ意味を持つため合計1へ正規化（config の丸め誤差を吸収）。
    total = sum(weights.values())
    if total > 0:
        weights = {k: v / total for k, v in weights.items()}
    return weights


def available_weights(config: Config, available_ids: list[str]) -> dict[str, float]:
    """採用できた指標のみで再正規化した重みを返す（合計=1）。

    欠損指標を 50（中立）で埋めるのではなく、重みを採用指標に按分する（§3.4）。
    available_ids が空なら空 dict を返す。
    """
    base = base_weights(config)
    present = {i: base[i] for i in available_ids if i in base}
    total = sum(present.values())
    if total <= 0:
        return {}
    return {i: w / total for i, w in present.items()}
