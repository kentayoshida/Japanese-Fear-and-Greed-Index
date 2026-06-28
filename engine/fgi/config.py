"""config.yaml の読み込みと型付きアクセス。

定量パラメータ（指標採否・正規化方式・lookback・加重・アンカー）は
すべてこのコンフィグに集約する（仕様 §6）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


@dataclass(frozen=True)
class Band:
    name: str
    label_ja: str
    min: float
    max: float


@dataclass(frozen=True)
class Dimension:
    id: str
    weight: float
    label_ja: str


@dataclass(frozen=True)
class Indicator:
    id: str
    label_ja: str
    dimension: str
    method: str  # "percentile" | "anchor"
    inverted: bool = False
    anchors: list[list[float]] | None = None
    description_ja: str = ""


@dataclass(frozen=True)
class Config:
    lookback_days: int
    bands: list[Band]
    dimensions: dict[str, Dimension]
    indicators: list[Indicator]
    output: dict[str, str]
    sources: dict[str, Any] = field(default_factory=dict)

    def indicator(self, indicator_id: str) -> Indicator:
        for ind in self.indicators:
            if ind.id == indicator_id:
                return ind
        raise KeyError(f"unknown indicator: {indicator_id}")


def load_config(path: str | Path | None = None) -> Config:
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    with open(cfg_path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    bands = [Band(**b) for b in raw["bands"]]
    dimensions = {
        dim_id: Dimension(id=dim_id, weight=float(d["weight"]), label_ja=d.get("label_ja", dim_id))
        for dim_id, d in raw["dimensions"].items()
    }
    indicators = [
        Indicator(
            id=i["id"],
            label_ja=i.get("label_ja", i["id"]),
            dimension=i["dimension"],
            method=i["method"],
            inverted=bool(i.get("inverted", False)),
            anchors=i.get("anchors"),
            description_ja=i.get("description_ja", ""),
        )
        for i in raw["indicators"]
    ]

    # 整合性チェック：指標の dimension が dimensions に存在するか
    for ind in indicators:
        if ind.dimension not in dimensions:
            raise ValueError(
                f"indicator '{ind.id}' references unknown dimension '{ind.dimension}'"
            )
        if ind.method not in ("percentile", "anchor"):
            raise ValueError(f"indicator '{ind.id}' has invalid method '{ind.method}'")
        if ind.method == "anchor" and not ind.anchors:
            raise ValueError(f"indicator '{ind.id}' uses method=anchor but has no anchors")

    return Config(
        lookback_days=int(raw["lookback_days"]),
        bands=bands,
        dimensions=dimensions,
        indicators=indicators,
        output=raw.get("output", {}),
        sources=raw.get("sources", {}),
    )
