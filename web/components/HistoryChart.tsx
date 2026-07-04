"use client";

// ヒストリカル時系列チャート（本家CNN Timeline 風）。
// F&G 合成スコアのみを1本の青ラインで描画（株価指数は重ねない）。
// 白背景＋淡い破線グリッド＋右側の目盛り、上下に「極度の貪欲／極度の恐怖」の目印。

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

const LINE_COLOR = "#1a6ba5"; // 本家CNN系の青
const AXIS_COLOR = "#a2937d"; // 本家CNN系の淡いタン系（軸の数字・月ラベル）

function monthTick(d: string): string {
  // "2026-01-15" → "2026/01"
  return d.length >= 7 ? d.slice(0, 7).replace("-", "/") : d;
}

function CustomTooltip({ active, payload }: any) {
  if (!active || !payload || !payload.length) return null;
  const p = payload[0].payload as HistoryPoint;
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip__date">{p.date}</div>
      <div className="chart-tooltip__score" style={{ color: LINE_COLOR }}>
        {p.score.toFixed(1)}
      </div>
      {typeof p.coverage === "number" && (
        <div className="chart-tooltip__cov">採用指標 {p.coverage}/8</div>
      )}
    </div>
  );
}

// indexLabel は互換のため受け取るが、このバージョンでは使用しない。
export default function HistoryChart({
  history,
}: {
  history: HistoryPoint[];
  indexLabel?: string;
}) {
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

      <div className="history__chart tlchart">
        <span className="tlchart__ann tlchart__ann--greed">▲ 極度の貪欲</span>
        <span className="tlchart__ann tlchart__ann--fear">▼ 極度の恐怖</span>
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
              orientation="right"
              domain={[0, 100]}
              ticks={[0, 25, 50, 75, 100]}
              tick={{ fill: AXIS_COLOR, fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              width={34}
            />
            <Tooltip content={<CustomTooltip />} />
            <Line
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
