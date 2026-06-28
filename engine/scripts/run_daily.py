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

from fgi.config import load_config  # noqa: E402
from fgi.pipeline import build_history, build_latest, union_business_dates  # noqa: E402
from fgi.providers import provide  # noqa: E402


def _resolve_out_path(engine_root: Path, rel: str) -> Path:
    p = (engine_root / rel).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def main() -> int:
    ap = argparse.ArgumentParser(description="日本版 Fear & Greed Index 日次ランナー")
    ap.add_argument("--mode", choices=["real", "demo"], default="real")
    ap.add_argument("--config", default=None, help="config.yaml パス（省略時は既定）")
    ap.add_argument("--history-start", default=None, help="history 開始日 YYYY-MM-DD（省略時は全期間）")
    args = ap.parse_args()

    config = load_config(args.config)
    raw_series, errors = provide(config, mode=args.mode)

    if not raw_series:
        print("ERROR: 取得できた指標が1つもありません。出力を中止します。", file=sys.stderr)
        for k, v in errors.items():
            print(f"  - {k}: {v}", file=sys.stderr)
        return 1

    # 評価基準日 = 取得できた全系列の最大公表日
    as_of = max(s.latest_date() for s in raw_series.values())

    latest = build_latest(config, raw_series, as_of)
    latest["generated_at"] = datetime.now(timezone.utc).isoformat()
    latest["mode"] = args.mode
    if args.mode == "demo":
        latest["sample"] = True  # 合成データであることを明示
    if errors:
        latest["fetch_errors"] = errors  # 取得不能だった指標と理由（透明性）

    start = pd.Timestamp(args.history_start) if args.history_start else None
    dates = union_business_dates(raw_series, start=start)
    history = build_history(config, raw_series, dates)

    latest_path = _resolve_out_path(ENGINE_ROOT, config.output["latest_path"])
    history_path = _resolve_out_path(ENGINE_ROOT, config.output["history_path"])

    latest_path.write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")
    history_path.write_text(json.dumps(history, ensure_ascii=False), encoding="utf-8")

    print(f"[{args.mode}] as_of={latest['as_of']} score={latest['score']} "
          f"band={latest['band']} coverage={latest['coverage']}/{latest['n_indicators']}")
    print(f"  latest : {latest_path}")
    print(f"  history: {history_path} ({len(history)} rows)")
    if errors:
        print("  未取得（stale 扱い）:")
        for k, v in errors.items():
            print(f"    - {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
