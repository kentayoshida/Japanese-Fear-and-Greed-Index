"use client";

// ヒストリカル時系列チャート。仕様 §6.5。
// 合成スコアの折れ線＋背景に5ゾーンの色帯。期間切替（1M/3M/6M/1Y/MAX）。

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

function CustomTooltip({ active, payload }: any) {
  if (!active || !payload || !payload.length) return null;
  const p = payload[0].payload as HistoryPoint;
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip__date">{p.date}</div>
      <div className="chart-tooltip__score" style={{ color: colorForScore(p.score) }}>
        {p.score.toFixed(1)}
      </div>
    </div>
  );
}

export default function HistoryChart({ history }: { history: HistoryPoint[] }) {
  const [range, setRange] = useState("1y");
  const cfg = RANGES.find((r) => r.key === range)!;
  const data = cfg.days ? history.slice(-cfg.days) : history;

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

      <div className="history__chart">
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 8, left: 4 }}>
            {/* 背景のゾーン色帯 */}
            {ZONES.map((z) => (
              <ReferenceArea
                key={z.key}
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
              domain={[0, 100]}
              ticks={[0, 25, 45, 55, 75, 100]}
              tick={{ fill: "#6b7280", fontSize: 11 }}
              tickLine={false}
              axisLine={{ stroke: "#e2e5ea" }}
              width={32}
            />
            <Tooltip content={<CustomTooltip />} />
            <Line
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
