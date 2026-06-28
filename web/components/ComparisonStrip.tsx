"use client";

// 時点比較ストリップ（本家の signature 要素）。仕様 §6.5。
// 前営業日 / 1週間前 / 1か月前 / 1年前 のスコアを「数値＋ゾーン色」で横並び表示。

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
    <div className="compare-strip">
      {ITEMS.map((it) => {
        const pt = lookupAtOffset(history, it.offset);
        return (
          <div className="compare-item" key={it.label}>
            <div className="compare-label">{it.label}</div>
            {pt ? (
              <>
                <div className="compare-dot" style={{ background: colorForScore(pt.score) }}>
                  {Math.round(pt.score)}
                </div>
                <div className="compare-zone" style={{ color: colorForScore(pt.score) }}>
                  {labelForScore(pt.score)}
                </div>
              </>
            ) : (
              <>
                <div className="compare-dot compare-dot--empty">—</div>
                <div className="compare-zone compare-zone--empty">データなし</div>
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}
