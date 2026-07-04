"use client";

// ヒーロー半円ゲージ（本家CNN流）。design-tokens.css / cnn-design-brief §2.1。
// グレー地の5ゾーン。針が指すゾーンだけを色付き（淡色地＋色枠）にする。
// 弧に沿って回転したゾーン名、内側に 0/25/50/75/100 目盛りと点、下部中央の
// 白円内に大きなスコア。針は上向き基準を CSS transform で回転。

import { ZONES, zoneForScore, zoneLabel } from "@/lib/fgi";
import { useLang } from "@/lib/i18n";

const CX = 200;
const CY = 196;
const R_OUT = 172;
const R_IN = 108;
const R_MID = (R_OUT + R_IN) / 2;
const NEEDLE_LEN = R_IN - 4;
const HUB = 46;

function valueToAngle(v: number): number {
  const c = Math.max(0, Math.min(100, v));
  return 180 - (c / 100) * 180;
}
function polar(cx: number, cy: number, r: number, deg: number) {
  const a = (deg * Math.PI) / 180;
  return { x: cx + r * Math.cos(a), y: cy - r * Math.sin(a) };
}

// value 区間 [s,e] のリング扇形パス。
function ringSectorPath(s: number, e: number): string {
  const a0 = valueToAngle(s);
  const a1 = valueToAngle(e);
  const oS = polar(CX, CY, R_OUT, a0);
  const oE = polar(CX, CY, R_OUT, a1);
  const iE = polar(CX, CY, R_IN, a1);
  const iS = polar(CX, CY, R_IN, a0);
  return [
    `M ${oS.x.toFixed(2)} ${oS.y.toFixed(2)}`,
    `A ${R_OUT} ${R_OUT} 0 0 1 ${oE.x.toFixed(2)} ${oE.y.toFixed(2)}`,
    `L ${iE.x.toFixed(2)} ${iE.y.toFixed(2)}`,
    `A ${R_IN} ${R_IN} 0 0 0 ${iS.x.toFixed(2)} ${iS.y.toFixed(2)}`,
    "Z",
  ].join(" ");
}

export default function Gauge({ score }: { score: number | null }) {
  const { lang } = useLang();
  const hasScore = score !== null && !Number.isNaN(score);
  const value = hasScore ? (score as number) : 50;
  const activeZone = zoneForScore(value);
  const needleRot = value * 1.8 - 90; // 上向き基準の回転角

  return (
    <div className="gauge">
      <svg viewBox="-6 0 412 236" role="img"
           aria-label={`Score ${hasScore ? Math.round(value) : "—"} (${zoneLabel(activeZone, lang)})`}>
        {/* 5ゾーン（既定グレー、アクティブのみ色付き） */}
        {ZONES.map((z) => {
          const isActive = hasScore && z.key === activeZone.key;
          return (
            <path
              key={z.key}
              d={ringSectorPath(z.min, z.max)}
              fill={isActive ? `color-mix(in srgb, ${z.color} 22%, white)` : "#eceef1"}
              stroke={isActive ? z.color : "#ffffff"}
              strokeWidth={isActive ? 2 : 3}
            />
          );
        })}

        {/* ゾーン名（弧に沿って回転） */}
        {ZONES.map((z) => {
          const mid = (z.min + z.max) / 2;
          const a = valueToAngle(mid);
          const p = polar(CX, CY, R_MID, a);
          const rot = 90 - a;
          const isActive = hasScore && z.key === activeZone.key;
          return (
            <text
              key={z.key}
              x={p.x}
              y={p.y}
              fontSize={z.min === 0 || z.max === 100 ? 9.5 : 11}
              fontWeight={700}
              letterSpacing="0.02em"
              fill={isActive ? z.color : "#8a929b"}
              textAnchor="middle"
              dominantBaseline="middle"
              transform={`rotate(${rot} ${p.x.toFixed(2)} ${p.y.toFixed(2)})`}
            >
              {zoneLabel(z, lang)}
            </text>
          );
        })}

        {/* 内側の細かい目盛り点（5刻み） */}
        {Array.from({ length: 21 }, (_, i) => i * 5).map((t) => {
          const p = polar(CX, CY, R_IN - 8, valueToAngle(t));
          return <circle key={t} cx={p.x} cy={p.y} r={1.1} fill="#c7ccd1" />;
        })}

        {/* 数値目盛り 0 / 25 / 50 / 75 / 100 */}
        {[0, 25, 50, 75, 100].map((t) => {
          const p = polar(CX, CY, R_IN - 20, valueToAngle(t));
          return (
            <text key={t} x={p.x} y={p.y} fontSize={12} fill="#5a6570"
                  textAnchor="middle" dominantBaseline="middle" fontVariant="tabular-nums">
              {t}
            </text>
          );
        })}

        {/* 針（上向き基準を回転） */}
        {hasScore && (
          <g className="needle" style={{ transform: `rotate(${needleRot}deg)`, transformOrigin: `${CX}px ${CY}px` }}>
            <polygon
              points={`${CX - 9},${CY} ${CX},${CY - NEEDLE_LEN} ${CX + 9},${CY}`}
              fill="var(--fg-gauge-needle-color)"
            />
          </g>
        )}

        {/* 下部中央の白円（スコアを収める） */}
        <circle cx={CX} cy={CY} r={HUB} fill="#ffffff" stroke="#e0e0e0" strokeWidth={1.5} />
      </svg>

      {/* スコア（白円の中央にオーバーレイ） */}
      <div className="gauge__readout">
        <div className="fg-score gauge__score">{hasScore ? Math.round(value) : "—"}</div>
      </div>
    </div>
  );
}
