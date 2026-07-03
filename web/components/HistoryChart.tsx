"use client";

// ヒストリカル時系列チャート。仕様 §6.5。
// 合成スコア（左軸）の折れ線＋背景に5ゾーンの色帯。加えて版の株価指数（右軸）を
// 重ねて描画し、スコアと実際の指数水準の関係を読み取れるようにする。期間切替。

import { useState } from "react";
import {
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { HistoryPoint, ZONES, colorForScore } from "@/lib/fgi";

const RANGES: { key: string; label: string; days: number | null }[] = [
  { key: "1m", label: "1M", days: 21 },
  { key: "3m", label: "3M", days: 63 },
  { key: "6m", label: "6M", days: 126 },
  { key: "1y", label: "1Y", days: 252 },
  { key: "max", label: "MAX", days: null },
];

const INDEX_COLOR = "#3b6fb0"; // 指数ラインの色（スコアの濃墨と区別できる青）

function makeTooltip(indexLabel: string) {
  return function CustomTooltip({ active, payload }: any) {
    if (!active || !payload || !payload.length) return null;
    const p = payload[0].payload as HistoryPoint;
    return (
      <div className="chart-tooltip">
        <div className="chart-tooltip__date">{p.date}</div>
        <div className="chart-tooltip__score" style={{ color: colorForScore(p.score) }}>
          {p.score.toFixed(1)}
        </div>
        {typeof p.index === "number" && (
          <div className="chart-tooltip__index">
            {indexLabel} {p.index.toLocaleString(undefined, { maximumFractionDigits: 2 })}
          </div>
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
  const cfg = RANGES.find((r) => r.key === range)!;
  const data = cfg.days ? history.slice(-cfg.days) : history;
  const hasIndex = data.some((d) => typeof d.index === "number");

  return (
    <div className="history">
      <div className="history__header">
        <h2 className="section-title">ヒストリカル推移</h2>
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

      {hasIndex && (
        <div className="chart-legend">
          <span className="chart-legend__item">
            <span className="chart-legend__swatch" style={{ background: "#1a1d21" }} />
            F&amp;G スコア
          </span>
          <span className="chart-legend__item">
            <span className="chart-legend__swatch" style={{ background: INDEX_COLOR }} />
            {indexLabel}
          </span>
        </div>
      )}

      <div className="history__chart">
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 8, left: 4 }}>
            {/* 背景のゾーン色帯（スコア軸に対して） */}
            {ZONES.map((z) => (
              <ReferenceArea
                key={z.key}
                yAxisId="score"
                y1={z.min}
                y2={z.max}
                fill={z.color}
                fillOpacity={0.16}
                ifOverflow="extendDomain"
              />
            ))}
            <XAxis
              dataKey="date"
              tick={{ fill: "#6b7280", fontSize: 11 }}
              minTickGap={40}
              tickLine={false}
              axisLine={{ stroke: "#e2e5ea" }}
            />
            <YAxis
              yAxisId="score"
              domain={[0, 100]}
              ticks={[0, 25, 45, 55, 75, 100]}
              tick={{ fill: "#6b7280", fontSize: 11 }}
              tickLine={false}
              axisLine={{ stroke: "#e2e5ea" }}
              width={32}
            />
            {hasIndex && (
              <YAxis
                yAxisId="idx"
                orientation="right"
                domain={["auto", "auto"]}
                tick={{ fill: INDEX_COLOR, fontSize: 11 }}
                tickFormatter={(v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                tickLine={false}
                axisLine={{ stroke: "#e2e5ea" }}
                width={48}
              />
            )}
            <Tooltip content={makeTooltip(indexLabel)} />
            {/* 指数ライン（背面） */}
            {hasIndex && (
              <Line
                yAxisId="idx"
                type="monotone"
                dataKey="index"
                stroke={INDEX_COLOR}
                strokeWidth={1.5}
                strokeOpacity={0.85}
                dot={false}
                isAnimationActive={false}
                connectNulls
              />
            )}
            {/* スコアライン（前面） */}
            <Line
              yAxisId="score"
              type="monotone"
              dataKey="score"
              stroke="#1a1d21"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
