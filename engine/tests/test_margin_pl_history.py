"""#6 確定日次履歴（松井チャート由来・正のデータ）の読み込みと観測合成の優先度テスト。"""

import pandas as pd

from fgi.providers import _load_margin_pl_history, _merge_observed


def test_history_loads_expected_shape():
    s = _load_margin_pl_history()
    assert len(s) > 0
    # % 単位の常識的レンジ（信用評価損益率）
    assert s.min() > -40 and s.max() < 10
    assert s.index.is_monotonic_increasing
    # アンカー：終点（2026-07-10）は確定値 -5.0%
    assert float(s.loc["2026-07-10"]) == -5.0
    # 始点は 2026-02-02
    assert s.index.min() == pd.Timestamp("2026-02-02")


def test_history_is_authoritative_within_its_range():
    # 履歴（正）が収録する日付は、旧ロジックでズレたライブ点があっても履歴が優先。
    hist = pd.Series({pd.Timestamp("2026-07-10"): -5.0, pd.Timestamp("2026-07-09"): -6.17})
    live = pd.Series({pd.Timestamp("2026-07-10"): -3.423})  # 旧ロジックのズレた点（同一日）
    merged = _merge_observed(hist, live)
    assert float(merged.loc["2026-07-10"]) == -5.0  # 履歴が正
    assert float(merged.loc["2026-07-09"]) == -6.17


def test_live_supplies_dates_beyond_history():
    # 履歴に無い新しい日付はライブ実測が補う。
    hist = pd.Series({pd.Timestamp("2026-07-10"): -5.0})
    live = pd.Series({pd.Timestamp("2026-07-16"): -7.302})  # 履歴期間より新しい日
    merged = _merge_observed(hist, live)
    assert float(merged.loc["2026-07-10"]) == -5.0
    assert float(merged.loc["2026-07-16"]) == -7.302


def test_merge_empty_history_returns_live():
    live = pd.Series({pd.Timestamp("2026-07-10"): -7.302})
    out = _merge_observed(pd.Series(dtype="float64"), live)
    assert out.equals(live)


def test_merge_empty_live_returns_history():
    hist = pd.Series({pd.Timestamp("2026-07-10"): -5.0})
    out = _merge_observed(hist, pd.Series(dtype="float64"))
    assert float(out.loc["2026-07-10"]) == -5.0
