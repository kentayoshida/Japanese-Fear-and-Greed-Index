"use client";

// ヒーロー半円ゲージ（速度計型ダイヤル）。仕様 §6.5。
// 半円180°。左端=0（極度の恐怖）→右端=100（極度の貪欲）。
// アーチを5ゾーンに色分けし、針(needle)が現在値を指す。

import { ZONES, zoneForScore } from "@/lib/fgi";

const CX = 200;
const CY = 200;
const R_OUTER = 170;
const R_INNER = 120;
const NEEDLE_LEN = 150;

// 値(0..100) → 角度(度)。0=180°(左), 100=0°(右)。
function valueToAngle(v: number): number {
  const clamped = Math.max(0, Math.min(100, v));
  return 180 - (clamped / 100) * 180;
}

function polar(cx: number, cy: number, r: number, angleDeg: number) {
  const a = (angleDeg * Math.PI) / 180;
  return { x: cx + r * Math.cos(a), y: cy - r * Math.sin(a) };
}

// ドーナツ扇形（ring sector）のパス。startVal→endVal を rInner/rOuter で塗る。
function ringSectorPath(startVal: number, endVal: number): string {
  const a0 = valueToAngle(startVal);
  const a1 = valueToAngle(endVal);
  const oStart = polar(CX, CY, R_OUTER, a0);
  const oEnd = polar(CX, CY, R_OUTER, a1);
  const iEnd = polar(CX, CY, R_INNER, a1);
  const iStart = polar(CX, CY, R_INNER, a0);
  // a0 > a1（左→右で角度は減少）。大円弧フラグは常に0（各ゾーンは180°未満）。
  const largeArc = 0;
  // 外周は反時計回り（角度減少方向）に sweep=1
  return [
    `M ${oStart.x.toFixed(2)} ${oStart.y.toFixed(2)}`,
    `A ${R_OUTER} ${R_OUTER} 0 ${largeArc} 1 ${oEnd.x.toFixed(2)} ${oEnd.y.toFixed(2)}`,
    `L ${iEnd.x.toFixed(2)} ${iEnd.y.toFixed(2)}`,
    `A ${R_INNER} ${R_INNER} 0 ${largeArc} 0 ${iStart.x.toFixed(2)} ${iStart.y.toFixed(2)}`,
    "Z",
  ].join(" ");
}

export default function Gauge({ score }: { score: number | null }) {
  const hasScore = score !== null && !Number.isNaN(score);
  const value = hasScore ? (score as number) : 50;
  const zone = zoneForScore(value);
  const needleAngle = valueToAngle(value);
  const tip = polar(CX, CY, NEEDLE_LEN, needleAngle);
  const baseL = polar(CX, CY, 14, needleAngle + 90);
  const baseR = polar(CX, CY, 14, needleAngle - 90);

  return (
    <div className="gauge">
      <svg viewBox="-20 0 440 250" role="img" aria-label={`現在のスコア ${hasScore ? Math.round(value) : "—"}（${zone.labelJa}）`}>
        {/* 5ゾーンのアーチ */}
        {ZONES.map((z) => (
          <path key={z.key} d={ringSectorPath(z.min, z.max)} fill={z.color} stroke="#ffffff" strokeWidth={2} />
        ))}

        {/* 境界の小目盛り（25 / 45 / 55 / 75） */}
        {[25, 45, 55, 75].map((t) => {
          const a = valueToAngle(t);
          const p1 = polar(CX, CY, R_OUTER + 2, a);
          const p2 = polar(CX, CY, R_OUTER + 9, a);
          return <line key={t} x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y} stroke="#c7ccd3" strokeWidth={1.5} />;
        })}

        {/* ゾーン名ラベル（本家CNN風。各ゾーン中央の角度に配置） */}
        {ZONES.map((z) => {
          const mid = (z.min + z.max) / 2;
          const a = valueToAngle(mid);
          const lab = polar(CX, CY, R_OUTER + 20, a);
          return (
            <text
              key={z.key}
              x={lab.x}
              y={lab.y}
              fontSize={10}
              fontWeight={700}
              fill={z.color}
              textAnchor="middle"
              dominantBaseline="middle"
            >
              {z.labelJa}
            </text>
          );
        })}

        {/* 針 */}
        {hasScore && (
          <g className="needle" style={{ transformOrigin: `${CX}px ${CY}px` }}>
            <polygon
              points={`${baseL.x.toFixed(2)},${baseL.y.toFixed(2)} ${tip.x.toFixed(2)},${tip.y.toFixed(2)} ${baseR.x.toFixed(2)},${baseR.y.toFixed(2)}`}
              fill="#1a1d21"
            />
            <circle cx={CX} cy={CY} r={16} fill="#1a1d21" />
            <circle cx={CX} cy={CY} r={7} fill="#ffffff" />
          </g>
        )}

        {/* 中央のスコアとレーティング（針の基部より上に配置して重なりを避ける） */}
        <text x={CX} y={CY - 58} textAnchor="middle" fontSize={64} fontWeight={800} fill="#1a1d21" style={{ fontVariantNumeric: "tabular-nums" }}>
          {hasScore ? Math.round(value) : "—"}
        </text>
        <text x={CX} y={CY - 28} textAnchor="middle" fontSize={19} fontWeight={700} fill={zone.color}>
          {hasScore ? zone.labelJa : "データなし"}
        </text>
      </svg>
    </div>
  );
}
