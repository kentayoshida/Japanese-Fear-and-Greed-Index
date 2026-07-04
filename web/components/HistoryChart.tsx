"use client";

// ヒストリカル時系列チャート（本家CNN Timeline 風）。
// 既定は F&G 合成スコアのみの青ライン。「指数を重ねる」トグルONで版の株価指数を
// 右→左の二軸で重ねて表示する。

import { useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { HistoryPoint } from "@/lib/fgi";

const RANGES: { key: string; label: string; days: number | null }[] = [
  { key: "1m", label: "1M", days: 21 },
  { key: "3m", label: "3M", days: 63 },
  { key: "6m", label: "6M", days: 126 },
  { key: "1y", label: "1Y", days: 252 },
  { key: "max", label: "MAX", days: null },
];

const LINE_COLOR = "#1a6ba5"; // 本家CNN系の青（F&Gスコア）
const INDEX_COLOR = "#d98a2b"; // 指数ライン（本家の移動平均線に近いオレンジ）
const AXIS_COLOR = "#a2937d"; // 本家CNN系の淡いタン系（軸の数字・月ラベル）

function monthTick(d: string): string {
  return d.length >= 7 ? d.slice(0, 7).replace("-", "/") : d;
}

function makeTooltip(showIndex: boolean, indexLabel: string) {
  return function CustomTooltip({ active, payload }: any) {
    if (!active || !payload || !payload.length) return null;
    const p = payload[0].payload as HistoryPoint;
    return (
      <div className="chart-tooltip">
        <div className="chart-tooltip__date">{p.date}</div>
        <div className="chart-tooltip__score" style={{ color: LINE_COLOR }}>
          {p.score.toFixed(1)}
        </div>
        {showIndex && typeof p.index === "number" && (
          <div className="chart-tooltip__index" style={{ color: INDEX_COLOR }}>
            {indexLabel} {p.index.toLocaleString(undefined, { maximumFractionDigits: 2 })}
          </div>
        )}
        {typeof p.coverage === "number" && (
          <div className="chart-tooltip__cov">採用指標 {p.coverage}/8</div>
        )}
      </div>
    );
  };
}

export default function HistoryChart({
  history,
  indexLabel = "指数",
}: {
  history: HistoryPoint[];
  indexLabel?: string;
}) {
  const [range, setRange] = useState("1y");
  const [showIndex, setShowIndex] = useState(false);
  const cfg = RANGES.find((r) => r.key === range)!;
  const data = cfg.days ? history.slice(-cfg.days) : history;
  const hasIndex = data.some((d) => typeof d.index === "number");
  const overlay = showIndex && hasIndex;

  return (
    <div className="history">
      <div className="history__header">
        <h2 className="section-title">ヒストリカル推移</h2>
        <div className="history__controls">
          {hasIndex && (
            <label className="index-toggle">
              <input
                type="checkbox"
                checked={showIndex}
                onChange={(e) => setShowIndex(e.target.checked)}
              />
              指数を重ねる
            </label>
          )}
          <div className="range-toggle" role="tablist" aria-label="期間切替">
            {RANGES.map((r) => (
              <button
                key={r.key}
                role="tab"
                aria-selected={r.key === range}
                className={`range-btn ${r.key === range ? "is-active" : ""}`}
                onClick={() => setRange(r.key)}
              >
                {r.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {overlay && (
        <div className="chart-legend">
          <span className="chart-legend__item">
            <span className="chart-legend__swatch" style={{ background: LINE_COLOR }} />
            F&amp;G スコア
          </span>
          <span className="chart-legend__item">
            <span className="chart-legend__swatch" style={{ background: INDEX_COLOR }} />
            {indexLabel}
          </span>
        </div>
      )}

      <div className="history__chart tlchart">
        {!overlay && (
          <>
            <span className="tlchart__ann tlchart__ann--greed">▲ 極度の貪欲</span>
            <span className="tlchart__ann tlchart__ann--fear">▼ 極度の恐怖</span>
          </>
        )}
        <ResponsiveContainer width="100%" height={320}>
          <LineChart data={data} margin={{ top: 10, right: 8, bottom: 6, left: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#ece8e1" />
            <XAxis
              dataKey="date"
              tickFormatter={monthTick}
              minTickGap={70}
              tick={{ fill: AXIS_COLOR, fontSize: 11 }}
              tickLine={false}
              axisLine={{ stroke: "#e0dcd4" }}
            />
            <YAxis
              yAxisId="score"
              orientation="right"
              domain={[0, 100]}
              ticks={[0, 25, 50, 75, 100]}
              tick={{ fill: AXIS_COLOR, fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              width={34}
            />
            {overlay && (
              <YAxis
                yAxisId="idx"
                orientation="left"
                domain={["auto", "auto"]}
                tick={{ fill: INDEX_COLOR, fontSize: 11 }}
                tickFormatter={(v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                tickLine={false}
                axisLine={false}
                width={44}
              />
            )}
            <Tooltip content={makeTooltip(overlay, indexLabel)} />
            {overlay && (
              <Line
                yAxisId="idx"
                type="monotone"
                dataKey="index"
                stroke={INDEX_COLOR}
                strokeWidth={1.5}
                strokeOpacity={0.9}
                dot={false}
                isAnimationActive={false}
                connectNulls
              />
            )}
            <Line
              yAxisId="score"
              type="monotone"
              dataKey="score"
              stroke={LINE_COLOR}
              strokeWidth={1.7}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {data.some((d) => typeof d.coverage === "number" && d.coverage < 8) && (
        <p className="chart-note">
          ※ 全8指標がそろう前の期間は、その時点で入手できた少数の指標で算出しています
          （各点の採用指標数はツールチップに表示）。指標が蓄積するほど本来の合成に近づきます。
        </p>
      )}
    </div>
  );
}
