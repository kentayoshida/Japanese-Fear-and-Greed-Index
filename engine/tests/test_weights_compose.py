import pandas as pd

from fgi.compose import ComponentScore, band_for_score, compose
from fgi.config import load_config
from fgi.weights import available_weights, base_weights


def _cfg():
    return load_config()


def test_base_weights_sum_to_one():
    cfg = _cfg()
    w = base_weights(cfg)
    assert abs(sum(w.values()) - 1.0) < 1e-6


def test_breadth_and_hedge_split_1_12():
    # 6次元・各1/6。breadth(2指標) と hedge_positioning(2指標) は各 1/12。
    cfg = _cfg()
    w = base_weights(cfg)
    assert abs(w["advance_decline_25"] - 1 / 12) < 1e-4
    assert abs(w["new_high_low"] - 1 / 12) < 1e-4
    assert abs(w["put_call_ratio"] - 1 / 12) < 1e-4
    assert abs(w["short_selling_ratio"] - 1 / 12) < 1e-4
    # 単独次元は 1/6
    assert abs(w["momentum_125dma"] - 1 / 6) < 1e-4
    assert abs(w["nikkei_vi"] - 1 / 6) < 1e-4
    assert abs(w["margin_pl_ratio"] - 1 / 6) < 1e-4
    assert abs(w["safe_haven"] - 1 / 6) < 1e-4


def test_available_weights_renormalize():
    cfg = _cfg()
    # 半分だけ採用 → 合計1に再正規化
    ids = ["momentum_125dma", "nikkei_vi"]
    w = available_weights(cfg, ids)
    assert abs(sum(w.values()) - 1.0) < 1e-6
    # 両方とも単独次元(1/6)なので採用後は等分
    assert abs(w["momentum_125dma"] - 0.5) < 1e-6


def test_partial_dimension_drop_keeps_dimension_weight():
    # §4.1b: ヘッジ次元(2指標)の片方 #5 が欠損しても、次元重みは縮まず #7 に集約。
    cfg = _cfg()
    all_ids = [i.id for i in cfg.indicators]
    ids = [i for i in all_ids if i != "put_call_ratio"]  # #5 のみ欠損
    w = available_weights(cfg, ids)
    assert abs(sum(w.values()) - 1.0) < 1e-9
    # 全次元が残る（hedge_positioning は #7 のみ採用）→ 6次元均等 = 各1/6
    # 単独次元 #1 は 1/6、hedge の #7 も次元を独占するので 1/6
    assert abs(w["short_selling_ratio"] - 1 / 6) < 1e-9
    assert abs(w["momentum_125dma"] - 1 / 6) < 1e-9
    # breadth は2指標残るので各 1/12
    assert abs(w["advance_decline_25"] - 1 / 12) < 1e-9


def test_dimension_drop_renormalizes_to_five():
    # §4.1b: #6(leverage 単独)が欠損 → 5次元。単独 1/5、2指標次元 各1/10。
    cfg = _cfg()
    ids = [i.id for i in cfg.indicators if i.id != "margin_pl_ratio"]
    w = available_weights(cfg, ids)
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert abs(w["momentum_125dma"] - 1 / 5) < 1e-9
    assert abs(w["advance_decline_25"] - 1 / 10) < 1e-9
    assert abs(w["put_call_ratio"] - 1 / 10) < 1e-9


def test_band_boundaries():
    cfg = _cfg()
    assert band_for_score(cfg, 0)[0] == "Extreme Fear"
    assert band_for_score(cfg, 24.9)[0] == "Extreme Fear"
    assert band_for_score(cfg, 25)[0] == "Fear"
    assert band_for_score(cfg, 50)[0] == "Neutral"
    assert band_for_score(cfg, 60)[0] == "Greed"
    assert band_for_score(cfg, 80)[0] == "Extreme Greed"
    assert band_for_score(cfg, 100)[0] == "Extreme Greed"


def test_compose_coverage_and_score():
    cfg = _cfg()
    comps = []
    for ind in cfg.indicators:
        # 半分を stale にする
        stale = ind.id in {"put_call_ratio", "short_selling_ratio", "margin_pl_ratio", "safe_haven"}
        comps.append(
            ComponentScore(
                id=ind.id, label_ja=ind.label_ja, dimension=ind.dimension,
                raw=1.0, score=None if stale else 60.0, inverted=ind.inverted, stale=stale,
            )
        )
    out = compose(cfg, comps, "2026-06-26")
    assert out["coverage"] == 4
    assert out["score"] == 60.0  # 採用指標が全て60なら合成も60
    assert out["band"] == "Greed"
    # 採用指標の重みは合計1
    used = [c for c in out["components"] if not c["stale"]]
    assert abs(sum(c["weight"] for c in used) - 1.0) < 1e-6
    # stale 指標は weight 0
    for c in out["components"]:
        if c["stale"]:
            assert c["weight"] == 0.0
