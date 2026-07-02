import pytest

from fgi.fetchers.base import FetchError
from fgi.fetchers.matsui import _parse_pl


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
