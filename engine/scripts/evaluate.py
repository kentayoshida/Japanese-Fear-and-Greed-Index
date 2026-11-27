#!/usr/bin/env python3
"""逆張り有用性の評価レポートを生成する（API キー不要・オフラインで再現可能）。

入力 : web/public/data/history_components.<variant>.csv（run_daily.py が出力）
出力 : docs/evaluation/report.md（人が読む）/ docs/evaluation/metrics.json（機械可読）

主軸は ③ 逆張り：スコア < --long で Long、> --short で Short する目安として機能するか。
期間は「調整用（--start〜--holdout-start の前日）」「検証用（--holdout-start〜）」「全期間」。
調整用の将来リターンは検証期間の価格を使わない（検証期間を凍結するため）。

例: cd engine && python scripts/evaluate.py
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ENGINE_ROOT.parent
sys.path.insert(0, str(ENGINE_ROOT))

from fgi.evaluate import EvalParams, evaluate_variant, load_components  # noqa: E402

DATA_DIR = REPO_ROOT / "web" / "public" / "data"
OUT_DIR = REPO_ROOT / "docs" / "evaluation"

IND_JA = {
    "momentum_125dma": "#1 モメンタム",
    "advance_decline_25": "#2 騰落レシオ",
    "new_high_low": "#3 新高値−新安値",
    "nikkei_vi": "#4 日経VI",
    "option_skew": "#5 オプション・スキュー",
    "margin_pl_ratio": "#6 信用評価損益率",
    "short_selling_ratio": "#7 空売り比率",
    "safe_haven": "#8 セーフヘイブン",
}


def _pct(x, nd=1):
    return "—" if x is None else f"{x * 100:+.{nd}f}%"


def _rate(x):
    return "—" if x is None else f"{x * 100:.0f}%"


def _num(x, nd=2):
    return "—" if x is None else f"{x:.{nd}f}"


def _contrarian_table(per: dict, horizons) -> list[str]:
    c = per["contrarian"]
    lines = ["| ゾーン | 集計 | " + " | ".join(f"{h}日後" for h in horizons) + " |",
             "| --- | --- | " + " | ".join("---" for _ in horizons) + " |"]
    for side, label in (("long", "Long（<閾値）"), ("short", "Short（>閾値）")):
        ev = c[side]["events"]
        dy = c[side]["days"]
        lines.append(f"| {label} | 突入イベント 件数 / 勝率 / 平均 / t | " + " | ".join(
            (f"{ev[str(h)]['n']} / {_rate(ev[str(h)].get('hit'))} / {_pct(ev[str(h)].get('mean'))}"
             f" / {_num(ev[str(h)].get('t'))}") if ev[str(h)]["n"] else "0"
            for h in horizons) + " |")
        lines.append(f"| {label} | 全該当日 日数 / 勝率 / 平均（超過） | " + " | ".join(
            (f"{dy[str(h)]['n']} / {_rate(dy[str(h)].get('hit'))} / {_pct(dy[str(h)].get('mean'))}"
             f"（{_pct(dy[str(h)].get('excess'))}）") if dy[str(h)]["n"] else "0"
            for h in horizons) + " |")
    nd = c["neutral_days"]
    lines.append("| 中立域 | 全該当日 日数 / 上昇率 / 平均 | " + " | ".join(
        (f"{nd[str(h)]['n']} / {_rate(nd[str(h)].get('hit'))} / {_pct(nd[str(h)].get('mean'))}")
        if nd[str(h)]["n"] else "0" for h in horizons) + " |")
    return lines


def _backtest_table(per: dict) -> list[str]:
    lines = ["| ルール | 累積 | 年率 | シャープ | 最大DD | 保有率 | 建玉回数 |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for key, label in (("long_short", "Long＋Short"), ("long_only", "Long のみ")):
        b = per["backtest"][key]
        s = b["strategy"]
        lines.append(f"| {label} | {_pct(s.get('total'))} | {_pct(s.get('cagr'))} | "
                     f"{_num(s.get('sharpe'))} | {_pct(s.get('max_dd'))} | {_rate(b.get('exposure'))} | "
                     f"{b.get('trades')} |")
    bh = per["backtest"]["long_short"]["buy_hold"]
    lines.append(f"| 参考：買い持ち | {_pct(bh.get('total'))} | {_pct(bh.get('cagr'))} | "
                 f"{_num(bh.get('sharpe'))} | {_pct(bh.get('max_dd'))} | 100% | — |")
    return lines


def _period_section(name: str, per: dict, p: EvalParams) -> list[str]:
    if not per or per.get("n_days", 0) == 0:
        return [f"### {name}", "", "対象日なし（採用指標数の条件を満たす日がない）。", ""]
    out = [f"### {name}（{per['range'][0]} 〜 {per['range'][1]}・{per['n_days']} 日）", ""]
    out.append(f"スコア < {p.long_th:g} の日の割合 {_rate(per['band_share']['lt25'])}、"
               f"> {p.short_th:g} の日の割合 {_rate(per['band_share']['gt75'])}。")
    out += ["", "**③ 逆張り：将来リターン**（翌日終値で建てた場合。Long の勝率は上昇、Short の勝率は下落の割合）", ""]
    out += _contrarian_table(per, p.horizons)
    out += ["", f"**③ 売買ルール**（< {p.long_th:g} で Long、> {p.short_th:g} で Short、"
            f"{p.exit_level:g} 回復で手仕舞い・翌日終値約定）", ""]
    out += _backtest_table(per)
    co, st = per["coincident"], per["stability"]
    out += ["", "**補助 ① 同時整合性・② 安定性**", "",
            "| 項目 | 値 |", "| --- | --- |",
            f"| 急落日（−3%以下）に恐怖側（<45）だった割合 | {_rate(co['stress_fear_share'])}（{co['stress_days']} 日） |",
            f"| 急騰日（+3%以上）に強欲側（>55）だった割合 | {_rate(co['rally_greed_share'])}（{co['rally_days']} 日） |",
            f"| 60日高値からの下落率との順位相関 | {_num(co['spearman_dd60'])} |",
            f"| 20日リターンとの順位相関 | {_num(co['spearman_ret20'])} |",
            f"| スコア日次変化の標準偏差 | {_num(st['daily_change_std'])} |",
            f"| ±3%超の日にスコアが相場と逆行した割合 | {_rate(st['opposite_share'])}（{st['big_move_days']} 日） |",
            f"| 張り付き（<5 / >95）の日の割合 | {_rate(per['saturation'].get('low_lt5'))} / {_rate(per['saturation'].get('high_gt95'))} |",
            ""]
    return out


def _indicator_section(per: dict, p: EvalParams) -> list[str]:
    ind = per.get("indicators", {})
    h = per.get("sensitivity", {}).get("horizon", 20)
    out = [f"**指標別診断**（指標単体のスコアで同じ閾値を当てた場合・{h}日後）", "",
           "| 指標 | Long突入 件数/勝率/平均 | Short突入 件数/勝率/平均 | 急落日の恐怖判定 | 20日リターン相関 | 張り付き <5 / >95 | 日次変化σ |",
           "| --- | --- | --- | --- | --- | --- | --- |"]
    for iid, v in ind.items():
        if not v.get("n"):
            out.append(f"| {IND_JA.get(iid, iid)} | データなし | | | | | |")
            continue
        le, se = v["long_events"], v["short_events"]
        out.append(
            f"| {IND_JA.get(iid, iid)} | "
            f"{le['n']} / {_rate(le.get('hit'))} / {_pct(le.get('mean'))} | "
            f"{se['n']} / {_rate(se.get('hit'))} / {_pct(se.get('mean'))} | "
            f"{_rate(v['stress_fear_share'])} | {_num(v['spearman_ret20'])} | "
            f"{_rate(v['saturation'].get('low_lt5'))} / {_rate(v['saturation'].get('high_gt95'))} | "
            f"{_num(v['daily_change_std'])} |")
    cm = per.get("indicator_corr")
    if cm:
        ids = list(cm.keys())
        out += ["", "**指標間の順位相関**（高いほど同じ情報を重複して持つ）", "",
                "| | " + " | ".join(f"#{list(IND_JA).index(i) + 1}" if i in IND_JA else i for i in ids) + " |",
                "| --- | " + " | ".join("---" for _ in ids) + " |"]
        for r in ids:
            out.append(f"| {IND_JA.get(r, r)} | " + " | ".join(_num(cm[r][c]) for c in ids) + " |")
    out.append("")
    return out


def _sensitivity_section(per: dict) -> list[str]:
    s = per.get("sensitivity")
    if not s:
        return []
    out = [f"**閾値の感度（参考・調整には使わない）**：突入イベントの {s['horizon']}日後", "",
           "| Long閾値 | Short閾値 | Long 件数/勝率/平均 | Short 件数/勝率/平均 | ルール累積 | シャープ |",
           "| --- | --- | --- | --- | --- | --- |"]
    for g in s["grid"]:
        le, se = g["long_events"], g["short_events"]
        out.append(f"| {g['long_th']:g} | {g['short_th']:g} | "
                   f"{le['n']} / {_rate(le.get('hit'))} / {_pct(le.get('mean'))} | "
                   f"{se['n']} / {_rate(se.get('hit'))} / {_pct(se.get('mean'))} | "
                   f"{_pct(g['bt_total'])} | {_num(g['bt_sharpe'])} |")
    out.append("")
    return out


def render(results: dict, p: EvalParams, args) -> str:
    lines = ["# 逆張り有用性の評価レポート", "",
             f"生成: {results['generated_at']}　/　入力: `web/public/data/history_components.<版>.csv`", "",
             "## 前提", "",
             f"- **主軸は ③ 逆張り**：スコア < {p.long_th:g} で Long、> {p.short_th:g} で Short する目安として機能するか。",
             "- 日 t のスコアは翌朝 6:00 JST 公開のため **翌営業日の終値で約定**（将来リターン = close(t+1+h)/close(t+1)−1）。",
             f"- 評価対象は採用指標数 {p.min_coverage} 以上の日のみ。開始 {args.start}。",
             f"- **調整用**は {args.holdout_start} より前（将来リターンも {args.holdout_start} 以降の価格は使わない）、"
             f"**検証用**は {args.holdout_start} 以降。検証用は調整に使わない。",
             f"- 「突入イベント」はゾーンに入った初日（直前 {p.cooldown} 日はゾーン外）。重なりのない標本に近く、t 値の目安に使う。"
             "「全該当日」は重複を含むため件数が水増しされる。",
             "- 既知の限界：#2 騰落の母集団は現在のプライム銘柄（過去日に生存者バイアス）。#6 の過去分は週次信用残の推計（tier-2）が中心。"
             "日経225 版の公式 CSV より前は連動 ETF(1321) で補完。",
             ""]
    for key, r in results["variants"].items():
        cov = r["coverage"]
        lines += [f"## {key} 版", "",
                  f"採用指標数：最大 {cov.get('max')}、最大に達した初日 {cov.get('first_full_date')}。"
                  f"月別の最小値：{', '.join(f'{k}:{v}' for k, v in list(cov.get('min_by_month', {}).items()))}", ""]
        lines += _period_section("調整用", r["calibration"], p)
        lines += _period_section("検証用", r["holdout"], p)
        lines += _period_section("全期間", r["full"], p)
        if r["full"].get("n_days"):
            lines += _indicator_section(r["full"], p)
            lines += _sensitivity_section(r["full"])
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="逆張り有用性の評価レポート")
    ap.add_argument("--variant", default="all", help="版キー（all で variants.json の全版）")
    ap.add_argument("--data-dir", default=str(DATA_DIR))
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--start", default="2024-01-04")
    ap.add_argument("--holdout-start", default="2026-11-01")
    ap.add_argument("--min-coverage", type=int, default=8)
    ap.add_argument("--long", type=float, default=25.0)
    ap.add_argument("--short", type=float, default=75.0)
    ap.add_argument("--exit", type=float, default=50.0)
    ap.add_argument("--horizons", default="5,20,60")
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    if args.variant == "all":
        manifest = json.loads((data_dir / "variants.json").read_text(encoding="utf-8"))
        keys = [v["key"] for v in manifest["variants"]]
    else:
        keys = [args.variant]

    results = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
               "params": {}, "variants": {}}
    p = None
    for key in keys:
        path = data_dir / f"history_components.{key}.csv"
        if not path.exists():
            print(f"[skip] {path} がありません（run_daily.py 実行後に生成されます）", file=sys.stderr)
            continue
        df = load_components(path)
        p = EvalParams(long_th=args.long, short_th=args.short, exit_level=args.exit,
                       horizons=tuple(int(h) for h in args.horizons.split(",")),
                       min_coverage=args.min_coverage)
        results["variants"][key] = evaluate_variant(df, p, args.start, args.holdout_start)
    if p is None:
        print("ERROR: 評価できる版がありません。", file=sys.stderr)
        return 1
    results["params"] = {k: (list(v) if isinstance(v, tuple) else v)
                         for k, v in p.__dict__.items() if k != "indicator_ids"}
    results["params"].update({"start": args.start, "holdout_start": args.holdout_start})

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "metrics.json").write_text(json.dumps(results, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    (out_dir / "report.md").write_text(render(results, p, args), encoding="utf-8")
    print(f"report : {out_dir / 'report.md'}")
    print(f"metrics: {out_dir / 'metrics.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
