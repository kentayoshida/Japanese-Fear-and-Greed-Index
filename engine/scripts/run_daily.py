#!/usr/bin/env python3
"""日次ランナー：生値取得 → 正規化 → 加重合成 → latest.json / history.json。

使い方:
  python scripts/run_daily.py --mode real    # 本番（実ソース／J-Quants）
  python scripts/run_daily.py --mode demo     # 合成データでフロント表示確認

GitHub Actions の日次 cron から --mode real で呼ぶ。JST 引け後＋データ遅延を
見て実行し、生成した JSON をコミットする（仕様 §1-C / §6）。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# fgi パッケージを import 可能に
ENGINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE_ROOT))

from fgi.config import load_config, variant_config  # noqa: E402
from fgi.pipeline import (  # noqa: E402
    build_history,
    build_latest,
    build_raw_series,
    union_business_dates,
)
from fgi.providers import provide_variants  # noqa: E402


def _resolve_out_path(engine_root: Path, rel: str) -> Path:
    p = (engine_root / rel).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _variant_path(base: Path, key: str) -> Path:
    """latest.json → latest.<key>.json のように版キーを差し込む。"""
    return base.with_name(f"{base.stem}.{key}{base.suffix}")


def main() -> int:
    ap = argparse.ArgumentParser(description="日本版 Fear & Greed Index 日次ランナー")
    ap.add_argument("--mode", choices=["real", "demo"], default="real")
    ap.add_argument("--config", default=None, help="config.yaml パス（省略時は既定）")
    ap.add_argument("--history-start", default=None, help="history 開始日 YYYY-MM-DD（省略時は全期間）")
    args = ap.parse_args()

    config = load_config(args.config)
    results = provide_variants(config, mode=args.mode)

    latest_base = _resolve_out_path(ENGINE_ROOT, config.output["latest_path"])
    history_base = _resolve_out_path(ENGINE_ROOT, config.output["history_path"])
    start = pd.Timestamp(args.history_start) if args.history_start else None

    manifest_variants: list[dict] = []
    produced = 0
    for v in config.variants:
        raw_series, errors = results.get(v.key, ({}, {}))
        if not raw_series:
            print(f"[{v.key}] 取得できた指標が1つもありません。この版はスキップします。",
                  file=sys.stderr)
            for k, msg in errors.items():
                print(f"    - {k}: {msg}", file=sys.stderr)
            continue

        # 指数オーバーレイ用の株価指数終値（指標ではないので pipeline から切り離す）
        equity = raw_series.pop("_equity_close", None)

        vcfg = variant_config(config, v)
        as_of = max(s.latest_date() for s in raw_series.values())

        latest = build_latest(vcfg, raw_series, as_of)
        latest["generated_at"] = datetime.now(timezone.utc).isoformat()
        latest["mode"] = args.mode
        latest["variant"] = v.key
        latest["variant_label"] = v.label_ja
        # チャートに重ねる指数の名称・最新値
        latest["index_label"] = v.equity.get("label_ja", v.key)
        if equity is not None:
            ew = equity.as_of(as_of).dropna()
            if len(ew):
                latest["index_value"] = round(float(ew.iloc[-1]), 2)
        if args.mode == "demo":
            latest["sample"] = True  # 合成データであることを明示
        if errors:
            latest["fetch_errors"] = errors  # 取得不能だった指標と理由（透明性）

        dates = union_business_dates(raw_series, start=start)
        history = build_history(vcfg, raw_series, dates, index_series=equity)

        # 指標カードの生値チャート（直近252営業日ぶんの生値・CNN型）
        chart_dates = dates[-252:] if len(dates) > 252 else dates
        series_map = build_raw_series(vcfg, raw_series, chart_dates)
        for comp in latest["components"]:
            comp["series"] = series_map.get(comp["id"], [])

        # 版別ファイル
        vlatest = _variant_path(latest_base, v.key)
        vhistory = _variant_path(history_base, v.key)
        vlatest.write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")
        vhistory.write_text(json.dumps(history, ensure_ascii=False), encoding="utf-8")
        # 既定版は latest.json / history.json も兼ねる（後方互換）
        if v.default:
            latest_base.write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")
            history_base.write_text(json.dumps(history, ensure_ascii=False), encoding="utf-8")

        manifest_variants.append({"key": v.key, "label_ja": v.label_ja, "default": v.default})
        produced += 1

        print(f"[{args.mode}:{v.key}] as_of={latest['as_of']} score={latest['score']} "
              f"band={latest['band']} coverage={latest['coverage']}/{latest['n_indicators']}")
        print(f"  latest : {vlatest}")
        print(f"  history: {vhistory} ({len(history)} rows)")
        if errors:
            print("  未取得（stale 扱い）:")
            for k, msg in errors.items():
                print(f"    - {k}: {msg}")

    if produced == 0:
        print("ERROR: どの版も出力できませんでした。", file=sys.stderr)
        return 1

    # 版一覧マニフェスト（フロントのタブ生成用）
    manifest_path = latest_base.with_name("variants.json")
    manifest_path.write_text(
        json.dumps({"variants": manifest_variants,
                    "generated_at": datetime.now(timezone.utc).isoformat()},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  manifest: {manifest_path} ({produced} 版)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
