"""合成・出力（Composition）。仕様 §5。

合成スコア = Σ(指標スコア × 重み)。0〜100。採用指標のみで重みを再正規化する。
欠損（取得失敗・stale）の指標は当日合成から除外し coverage に記録する。
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import Config
from .weights import available_weights


@dataclass
class ComponentScore:
    """1指標の正規化済みスコアとメタ情報。"""

    id: str
    label_ja: str
    dimension: str
    raw: float | None
    score: float | None   # 0〜100。stale/欠損時は None
    inverted: bool
    stale: bool = False


def band_for_score(config: Config, score: float) -> tuple[str, str]:
    """スコアfrom判定バンド名 (英, 日) を返す。境界は [min, max) で評価し最後だけ閉区間。"""
    bands = config.bands
    for i, b in enumerate(bands):
        is_last = i == len(bands) - 1
        if (b.min <= score < b.max) or (is_last and score == b.max):
            return b.name, b.label_ja
    # 範囲外（理論上0〜100に収まるが安全側）
    if score < bands[0].min:
        return bands[0].name, bands[0].label_ja
    return bands[-1].name, bands[-1].label_ja


def compose(config: Config, components: list[ComponentScore], as_of: str) -> dict:
    """採用指標を加重合成して latest.json 形式の dict を返す（§5.2）。"""
    available = [c for c in components if c.score is not None and not c.stale]
    available_ids = [c.id for c in available]
    weights = available_weights(config, available_ids)

    score = sum(c.score * weights[c.id] for c in available) if available else None
    band_name, band_label = band_for_score(config, score) if score is not None else ("", "")

    components_out = []
    for c in components:
        components_out.append(
            {
                "id": c.id,
                "label": c.label_ja,
                "dimension": c.dimension,
                "raw": None if c.raw is None else round(float(c.raw), 6),
                "score": None if c.score is None else round(float(c.score), 4),
                "weight": round(weights.get(c.id, 0.0), 6),
                "inverted": c.inverted,
                "stale": c.stale or c.score is None,
            }
        )

    return {
        "as_of": as_of,
        "score": None if score is None else round(float(score), 1),
        "band": band_name,
        "band_label_ja": band_label,
        "coverage": len(available),
        "n_indicators": len(config.indicators),
        "lookback_days": config.lookback_days,
        "components": components_out,
        "history_ref": "history.json",
        "disclaimer": "本指標は情報提供目的の自作指標であり、投資助言ではありません。",
    }
