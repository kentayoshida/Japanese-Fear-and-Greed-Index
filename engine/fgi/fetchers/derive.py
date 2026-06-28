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


def put_call_ratio(option_df: pd.DataFrame) -> pd.Series:
    """#5 日経225オプション Put/Call レシオ（出来高ベース）。

    option_df は J-Quants 日経225オプション四本値（全ストライク・日次）。
    期待カラム: 'Date', 'PutCallDivision'(1=Put?/2=Call? は API 仕様で確認), 'Volume'。
    日付ごとに put 出来高合計 ÷ call 出来高合計。

    ※ PutCallDivision の値の意味は契約後 API ドキュメントで確認し調整すること。
    """
    df = option_df.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce").fillna(0.0)
    # 暫定マッピング（要確認）: PutCallDivision 1=Put, 2=Call
    puts = df[df["PutCallDivision"].astype(str) == "1"].groupby("Date")["Volume"].sum()
    calls = df[df["PutCallDivision"].astype(str) == "2"].groupby("Date")["Volume"].sum()
    ratio = (puts / calls.replace(0, pd.NA)).dropna()
    ratio.name = "put_call_ratio"
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
