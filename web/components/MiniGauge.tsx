"use client";

// 時点比較用の小型半円ゲージ（CNN 本家の signature 要素）。仕様 §6.5。
// 半円180°・5ゾーン色・針。数値とゾーン色を併記する。

import { ZONES, zoneForScore } from "@/lib/fgi";

const CX = 60;
const CY = 58;
const R_OUTER = 50;
const R_INNER = 34;

function valueToAngle(v: number): number {
  const c = Math.max(0, Math.min(100, v));
  return 180 - (c / 100) * 180;
}
function polar(r: number, a: number) {
  const rad = (a * Math.PI) / 180;
  return { x: CX + r * Math.cos(rad), y: CY - r * Math.sin(rad) };
}
function sector(v0: number, v1: number): string {
  const a0 = valueToAngle(v0);
  const a1 = valueToAngle(v1);
  const oS = polar(R_OUTER, a0);
  const oE = polar(R_OUTER, a1);
  const iE = polar(R_INNER, a1);
  const iS = polar(R_INNER, a0);
  return [
    `M ${oS.x.toFixed(1)} ${oS.y.toFixed(1)}`,
    `A ${R_OUTER} ${R_OUTER} 0 0 1 ${oE.x.toFixed(1)} ${oE.y.toFixed(1)}`,
    `L ${iE.x.toFixed(1)} ${iE.y.toFixed(1)}`,
    `A ${R_INNER} ${R_INNER} 0 0 0 ${iS.x.toFixed(1)} ${iS.y.toFixed(1)}`,
    "Z",
  ].join(" ");
}

export default function MiniGauge({ score }: { score: number | null }) {
  const has = score !== null && !Number.isNaN(score);
  const v = has ? (score as number) : 50;
  const zone = zoneForScore(v);
  const a = valueToAngle(v);
  const tip = polar(R_INNER + 8, a);

  return (
    <svg viewBox="0 0 120 74" width="100%" role="img" aria-label={`スコア ${has ? Math.round(v) : "—"}`}>
      {ZONES.map((z) => (
        <path key={z.key} d={sector(z.min, z.max)} fill={z.color} opacity={has ? 1 : 0.25} />
      ))}
      {has && (
        <>
          <line x1={CX} y1={CY} x2={tip.x} y2={tip.y} stroke="#f5f6f8" strokeWidth={2.5} strokeLinecap="round" />
          <circle cx={CX} cy={CY} r={4} fill="#f5f6f8" />
        </>
      )}
      <text x={CX} y={CY - 12} textAnchor="middle" fontSize={20} fontWeight={800} fill="#f5f6f8" style={{ fontVariantNumeric: "tabular-nums" }}>
        {has ? Math.round(v) : "—"}
      </text>
    </svg>
  );
}
