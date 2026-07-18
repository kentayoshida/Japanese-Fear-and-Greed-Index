import datetime as dt

import pandas as pd
import pytest

from fgi.fetchers.base import FetchError
from fgi.fetchers.matsui import _extract_basis_date, _parse_pl


def test_parse_pl_negative():
    assert _parse_pl("-3.856") == pytest.approx(-3.856)


def test_parse_pl_with_percent_and_spaces():
    assert _parse_pl("  -12.4% ") == pytest.approx(-12.4)


def test_parse_pl_positive():
    assert _parse_pl("2.13") == pytest.approx(2.13)


def test_parse_pl_empty_raises():
    with pytest.raises(FetchError):
        _parse_pl("")
    with pytest.raises(FetchError):
        _parse_pl(None)


def test_parse_pl_out_of_range_raises():
    # 信用評価損益率として非現実的な値は弾く（誤セル抽出の検知）
    with pytest.raises(FetchError):
        _parse_pl("999")


def test_parse_pl_no_number_raises():
    with pytest.raises(FetchError):
        _parse_pl("—")


# ---- 基準日の抽出（松井は評価損益率を翌営業日公開するため、ページの基準日でキーする）----

TODAY = dt.date(2026, 7, 21)  # 火（7/20 海の日の翌営業日）を基準に判定


def test_basis_date_full_ymd_slash():
    assert _extract_basis_date("信用残速報（2026/7/16 時点）", TODAY) == pd.Timestamp("2026-07-16")


def test_basis_date_full_ymd_kanji():
    assert _extract_basis_date("基準日：2026年7月16日", TODAY) == pd.Timestamp("2026-07-16")


def test_basis_date_month_day_only_infers_year():
    # 年なし表記は今年を当てはめる（未来でない直近日）
    assert _extract_basis_date("信用残速報（7/16）", TODAY) == pd.Timestamp("2026-07-16")


def test_basis_date_month_day_kanji():
    assert _extract_basis_date("7月16日時点", TODAY) == pd.Timestamp("2026-07-16")


def test_basis_date_picks_most_recent_valid():
    # 複数日付があれば、未来でなく直近の最も新しい妥当日を採る
    text = "前回 7/9 / 今回 7/16（速報）"
    assert _extract_basis_date(text, TODAY) == pd.Timestamp("2026-07-16")


def test_basis_date_ignores_future_dates():
    # 未来日（今日より後）は採らない
    assert _extract_basis_date("次回更新 7/22 予定 / 基準 7/16", TODAY) == pd.Timestamp("2026-07-16")


def test_basis_date_year_boundary_infers_prev_year():
    # 年始に「12/30」表記なら前年を当てる
    jan = dt.date(2026, 1, 5)
    assert _extract_basis_date("信用残速報（12/30）", jan) == pd.Timestamp("2025-12-30")


def test_basis_date_none_when_absent():
    assert _extract_basis_date("評価損益率 -7.302%", TODAY) is None
    assert _extract_basis_date("", TODAY) is None
    assert _extract_basis_date(None, TODAY) is None


def test_basis_date_none_when_too_old():
    # 直近数週間を超える古い日付しかなければ採らない（誤抽出防止）
    assert _extract_basis_date("2026/1/6", TODAY) is None


# ---- 曜日付き基準日（松井の実表示 "7/16(木)" 形式）----

def test_basis_date_weekday_md_form():
    # 松井ページ実表示：信用取引指標(松井証券店内) の右に "7/16(木)"
    assert _extract_basis_date("信用取引指標(松井証券店内)\n7/16(木)", TODAY,
                               require_weekday=True) == pd.Timestamp("2026-07-16")


def test_basis_date_weekday_fullwidth_paren():
    assert _extract_basis_date("7/16（木）", TODAY, require_weekday=True) == pd.Timestamp("2026-07-16")


def test_basis_date_weekday_ymd_form():
    assert _extract_basis_date("2026/7/16(木)", TODAY, require_weekday=True) == pd.Timestamp("2026-07-16")


def test_basis_date_weekday_ignores_plain_numbers_on_page():
    # ページ全体を走査しても、曜日サフィックスの無い数値（比率・倍率等）は拾わない
    body = ("売り(%) 74.1 82.0\n買い(%) 74.8 82.6\n信用取引指標(松井証券店内) 7/16(木)\n"
            "売り残 240.10 -24.253\n買い残 5,209.74 -7.302\n※倍率 21.698倍")
    assert _extract_basis_date(body, TODAY, require_weekday=True) == pd.Timestamp("2026-07-16")


def test_basis_date_weekday_none_when_no_suffix():
    # 曜日サフィックスが無ければ require_weekday では拾わない
    assert _extract_basis_date("7/16 時点", TODAY, require_weekday=True) is None
