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
    """採用できた指標のみで、**次元レベルで**再正規化した重みを返す（合計=1）。仕様 §4.1b。

    手順：
      1. 採用指標を次元ごとに束ねる。少なくとも1指標が採用された次元を「採用次元」とする。
      2. 採用次元の重みを合計1.0に再正規化（各次元重み ÷ 採用次元重み合計）。
      3. 各次元の重みを、その次元で採用された指標に均等配分。

    これにより、2指標次元（例 ブレッドス／ヘッジ）の片方だけ欠損しても、その次元の
    重みは縮まず残った1指標に集約される（欠損を中立値で埋めない §3.4 と一貫）。
    available_ids が空なら空 dict を返す。
    """
    id_to_dim = {ind.id: ind.dimension for ind in config.indicators}
    by_dim: dict[str, list[str]] = defaultdict(list)
    for ind_id in available_ids:
        dim = id_to_dim.get(ind_id)
        if dim is not None:
            by_dim[dim].append(ind_id)
    if not by_dim:
        return {}

    dim_total = sum(config.dimensions[d].weight for d in by_dim)
    if dim_total <= 0:
        return {}

    weights: dict[str, float] = {}
    for dim, ids in by_dim.items():
        dim_w = config.dimensions[dim].weight / dim_total  # 採用次元で再正規化
        per = dim_w / len(ids)                              # 次元内は採用指標で均等
        for ind_id in ids:
            weights[ind_id] = per
    return weights
