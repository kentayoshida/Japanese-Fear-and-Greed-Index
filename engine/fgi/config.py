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
class Variant:
    """出力版。株式指数レッグ(#1,#8)だけが版ごとに変わる。"""
    key: str
    label_ja: str
    equity: dict[str, Any]
    default: bool = False


@dataclass(frozen=True)
class Config:
    lookback_days: int
    bands: list[Band]
    dimensions: dict[str, Dimension]
    indicators: list[Indicator]
    output: dict[str, str]
    sources: dict[str, Any] = field(default_factory=dict)
    variants: list[Variant] = field(default_factory=list)

    def indicator(self, indicator_id: str) -> Indicator:
        for ind in self.indicators:
            if ind.id == indicator_id:
                return ind
        raise KeyError(f"unknown indicator: {indicator_id}")

    def default_variant(self) -> Variant:
        for v in self.variants:
            if v.default:
                return v
        return self.variants[0]


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

    sources = raw.get("sources", {})

    # 版（variants）。未指定なら sources.jquants の指数を使う単一の topix 版を既定生成。
    raw_variants = raw.get("variants")
    if raw_variants:
        variants = [
            Variant(
                key=v["key"],
                label_ja=v.get("label_ja", v["key"]),
                equity=dict(v.get("equity", {})),
                default=bool(v.get("default", False)),
            )
            for v in raw_variants
        ]
    else:
        code = sources.get("jquants", {}).get("equity_index_code", "0000")
        variants = [Variant(key="topix", label_ja="TOPIX", default=True,
                            equity={"source": "jquants", "code": code, "label_ja": "TOPIX",
                                    "min": 300, "max": 20000})]
    if not any(v.default for v in variants):
        variants = [Variant(**{**v.__dict__, "default": (i == 0)})
                    for i, v in enumerate(variants)]

    return Config(
        lookback_days=int(raw["lookback_days"]),
        bands=bands,
        dimensions=dimensions,
        indicators=indicators,
        output=raw.get("output", {}),
        sources=sources,
        variants=variants,
    )


def variant_config(config: Config, variant: Variant) -> Config:
    """版に応じて #1/#8 のラベル・説明を株式指数名で差し替えた Config を返す。

    正規化方式・lookback・加重・アンカーは全版共通。ラベルだけを版仕様にする。
    """
    from dataclasses import replace

    eq_label = variant.equity.get("label_ja", variant.key)
    new_inds: list[Indicator] = []
    for ind in config.indicators:
        if ind.id == "momentum_125dma":
            new_inds.append(replace(
                ind,
                label_ja=f"{eq_label} vs 125日線乖離率",
                description_ja=f"{eq_label} が125日移動平均からどれだけ上方/下方に乖離しているか。上方乖離は強気。",
            ))
        elif ind.id == "safe_haven":
            new_inds.append(replace(
                ind,
                label_ja=f"セーフヘイブン需要（{eq_label} − 債券 20日リターン差）",
                description_ja=f"{eq_label}と10年JGBトータルリターンの20日リターン差。株式優位なら強気。",
            ))
        else:
            new_inds.append(ind)
    return replace(config, indicators=new_inds)
