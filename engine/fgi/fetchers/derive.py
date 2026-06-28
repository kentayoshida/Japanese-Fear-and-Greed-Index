"""生データから指標の生値系列を計算する純関数群（ネットワーク I/O を含まない）。

ここを純関数に分離することで point-in-time のロジックを単体テストできる。
"""

from __future__ import annotations

import pandas as pd


def momentum_125dma(close: pd.Series, window: int = 125) -> pd.Series:
    """#1 日経225 と 125日移動平均の乖離率（％）。

    乖離率 = (終値 − MA125) / MA125 × 100。上方乖離（正）= Greed。
    """
    close = pd.to_numeric(close, errors="coerce").sort_index()
    ma = close.rolling(window=window, min_periods=window).mean()
    dev = (close - ma) / ma * 100.0
    return dev.dropna()


def advance_decline_ratio(advances: pd.Series, declines: pd.Series, window: int = 25) -> pd.Series:
    """#2 騰落レシオ（25日）。= 直近window日の値上がり銘柄数合計 ÷ 値下がり銘柄数合計 × 100。"""
    adv = pd.to_numeric(advances, errors="coerce").sort_index()
    dec = pd.to_numeric(declines, errors="coerce").sort_index()
    adv_sum = adv.rolling(window=window, min_periods=window).sum()
    dec_sum = dec.rolling(window=window, min_periods=window).sum()
    ratio = adv_sum / dec_sum.replace(0, pd.NA) * 100.0
    return ratio.dropna()


def new_high_low_net(new_highs: pd.Series, new_lows: pd.Series) -> pd.Series:
    """#3 新高値 − 新安値（ネット銘柄数）。正 = 株価の地力が強い = Greed。"""
    nh = pd.to_numeric(new_highs, errors="coerce").sort_index()
    nl = pd.to_numeric(new_lows, errors="coerce").sort_index()
    net = (nh - nl).dropna()
    return net


def put_call_ratio(
    option_df: pd.DataFrame,
    *,
    date_col: str = "Date",
    volume_col: str = "Vo",
    putcall_col: str = "PCDiv",
    put_value: str = "1",
    call_value: str = "2",
) -> pd.Series:
    """#5 日経225オプション Put/Call レシオ（出来高ベース）。

    option_df は J-Quants v2 /derivatives/bars/daily/options/225（全ストライク・日次）。
    v2 カラム: 'Date', 'Vo'(出来高), 'PCDiv'(プット/コール区分)。
    日付ごとに put 出来高合計 ÷ call 出来高合計。

    ※ PCDiv の値（1=Put / 2=Call）は J-Quants 仕様準拠。万一逆なら put_value/call_value で調整。
    """
    df = option_df.copy()
    df[date_col] = pd.to_datetime(df[date_col])
    df[volume_col] = pd.to_numeric(df[volume_col], errors="coerce").fillna(0.0)
    pcd = df[putcall_col].astype(str)
    puts = df[pcd == put_value].groupby(date_col)[volume_col].sum()
    calls = df[pcd == call_value].groupby(date_col)[volume_col].sum()
    ratio = (puts / calls.replace(0, pd.NA)).dropna()
    ratio.name = "put_call_ratio"
    return ratio.sort_index()


def short_selling_market_ratio(
    df: pd.DataFrame,
    *,
    date_col: str = "Date",
    sell_ex_short: str = "SellExShortVa",
    short_with_res: str = "ShrtWithResVa",
    short_no_res: str = "ShrtNoResVa",
) -> pd.Series:
    """#7 市場全体の空売り比率（％）。J-Quants /markets/short-ratio の業種別金額から算出。

    空売り比率 = (規制あり空売り + 規制なし空売り) ÷ (実売り + 空売り合計) × 100。
    日付ごとに全業種（33業種 + ETF/REIT=9999）を合算して市場全体値とする。
    """
    d = df.copy()
    d[date_col] = pd.to_datetime(d[date_col])
    for c in (sell_ex_short, short_with_res, short_no_res):
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0.0)
    g = d.groupby(date_col)[[sell_ex_short, short_with_res, short_no_res]].sum()
    short = g[short_with_res] + g[short_no_res]
    total = g[sell_ex_short] + short
    ratio = (short / total.replace(0, pd.NA) * 100.0).dropna()
    ratio.name = "short_selling_ratio"
    return ratio.sort_index()


def safe_haven(nikkei_close: pd.Series, bond_total_return: pd.Series, window: int = 20) -> pd.Series:
    """#8 セーフヘイブン需要 = 株式20日リターン − 債券(トータルリターン)20日リターン（％）。

    正 = 株式優位 = リスク選好 = Greed。bond_total_return は10年JGBトータルリターン
    指数（または債券ETFの調整後終値）を想定。両系列を共通営業日に揃えて計算。
    """
    eq = pd.to_numeric(nikkei_close, errors="coerce").sort_index()
    bd = pd.to_numeric(bond_total_return, errors="coerce").sort_index()
    df = pd.concat({"eq": eq, "bd": bd}, axis=1).dropna()
    eq_ret = df["eq"].pct_change(window) * 100.0
    bd_ret = df["bd"].pct_change(window) * 100.0
    diff = (eq_ret - bd_ret).dropna()
    diff.name = "safe_haven"
    return diff
