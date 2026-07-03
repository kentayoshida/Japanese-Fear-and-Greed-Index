"use client";

// 時点比較（本家CNNの右側リスト）。前営業日／1週間前／1か月前／1年前 を
// 「ラベル＋状態（左）＋点線＋スコア円（右）」の縦リストで表示。

import { HistoryPoint, labelForScore, colorForScore, lookupAtOffset } from "@/lib/fgi";

type Item = { label: string; offset: number };

// 営業日換算の概算オフセット（5営業日=1週間, 21=1か月, 252=1年）。
const ITEMS: Item[] = [
  { label: "前営業日", offset: 1 },
  { label: "1週間前", offset: 5 },
  { label: "1か月前", offset: 21 },
  { label: "1年前", offset: 252 },
];

export default function ComparisonStrip({ history }: { history: HistoryPoint[] }) {
  return (
    <div className="compare-list">
      {ITEMS.map((it) => {
        const pt = lookupAtOffset(history, it.offset);
        const color = pt ? colorForScore(pt.score) : "#9aa0a6";
        return (
          <div className="compare-row" key={it.label}>
            <div className="compare-row__text">
              <div className="compare-row__label">{it.label}</div>
              <div className="compare-row__state" style={{ color }}>
                {pt ? labelForScore(pt.score) : "データなし"}
              </div>
            </div>
            <div className="compare-row__dots" aria-hidden="true" />
            <div
              className="compare-row__circle"
              style={{
                borderColor: color,
                background: `color-mix(in srgb, ${color} 18%, white)`,
              }}
            >
              {pt ? Math.round(pt.score) : "—"}
            </div>
          </div>
        );
      })}
    </div>
  );
}
