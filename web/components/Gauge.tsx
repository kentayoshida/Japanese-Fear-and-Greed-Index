"use client";

// ヒーロー半円ゲージ（速度計型ダイヤル）。design-tokens.css / cnn-design-brief §2.1。
// 半円180°。左端=0（極度の恐怖）→右端=100（極度の貪欲）。
// アークは赤→橙→黄→黄緑→緑の連続グラデーション。境界に白い区切り。針が現在値を指す。
// 中央に特大スコア＋バンドラベル（オーバーレイ div で .fg-score を使用）。

import { ZONES, zoneForScore } from "@/lib/fgi";

const CX = 200;
const CY = 192;
const R = 150; // アーク中心線半径
const TRACK = 22;
const R_OUT = R + TRACK / 2;
const R_IN = R - TRACK / 2;
const NEEDLE_LEN = 78;
const NEEDLE_HALF = 8;

// 値(0..100) → 角度(度)。0=180°(左), 100=0°(右)。
function valueToAngle(v: number): number {
  const clamped = Math.max(0, Math.min(100, v));
  return 180 - (clamped / 100) * 180;
}

function polar(cx: number, cy: number, r: number, angleDeg: number) {
  const a = (angleDeg * Math.PI) / 180;
  return { x: cx + r * Math.cos(a), y: cy - r * Math.sin(a) };
}

export default function Gauge({ score }: { score: number | null }) {
  const hasScore = score !== null && !Number.isNaN(score);
  const value = hasScore ? (score as number) : 50;
  const zone = zoneForScore(value);
  // 針は「上向き」を基準に描き、CSS transform で回転（更新時に滑らかに遷移）。
  // 回転角θ(SVG時計回り) = value*1.8 − 90（v=50→0°, v=100→+90°(右), v=0→−90°(左)）。
  const needleRot = value * 1.8 - 90;

  const arcStart = polar(CX, CY, R, 180); // 左端(0)
  const arcEnd = polar(CX, CY, R, 0); // 右端(100)

  return (
    <div className="gauge">
      <svg viewBox="-46 0 492 236" role="img"
           aria-label={`現在のスコア ${hasScore ? Math.round(value) : "—"}（${zone.labelJa}）`}>
        <defs>
          <linearGradient id="fgArc" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#c0392b" />
            <stop offset="25%" stopColor="#e67e22" />
            <stop offset="50%" stopColor="#e6b800" />
            <stop offset="75%" stopColor="#7cb342" />
            <stop offset="100%" stopColor="#1a9850" />
          </linearGradient>
        </defs>

        {/* 連続グラデーションのアーク */}
        <path
          d={`M ${arcStart.x.toFixed(2)} ${arcStart.y.toFixed(2)} A ${R} ${R} 0 0 1 ${arcEnd.x.toFixed(2)} ${arcEnd.y.toFixed(2)}`}
          fill="none"
          stroke="url(#fgArc)"
          strokeWidth={TRACK}
        />

        {/* 境界の白い区切り（25 / 45 / 55 / 75） */}
        {[25, 45, 55, 75].map((t) => {
          const a = valueToAngle(t);
          const p1 = polar(CX, CY, R_IN, a);
          const p2 = polar(CX, CY, R_OUT, a);
          return <line key={t} x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y} stroke="#ffffff" strokeWidth={2.5} />;
        })}

        {/* ゾーン名ラベル（各ゾーン中央の外側） */}
        {ZONES.map((z) => {
          const mid = (z.min + z.max) / 2;
          const a = valueToAngle(mid);
          const isExtreme = z.min === 0 || z.max === 100;
          const lab = polar(CX, CY, R_OUT + (isExtreme ? 18 : 16), a);
          return (
            <text key={z.key} x={lab.x} y={lab.y} fontSize={isExtreme ? 8 : 9.5} fontWeight={700}
                  fill={z.color} textAnchor="middle" dominantBaseline="middle">
              {z.labelJa}
            </text>
          );
        })}

        {/* 針（上向き基準を回転） */}
        {hasScore && (
          <g className="needle" style={{ transform: `rotate(${needleRot}deg)`, transformOrigin: `${CX}px ${CY}px` }}>
            <polygon
              points={`${CX - NEEDLE_HALF},${CY} ${CX},${CY - NEEDLE_LEN} ${CX + NEEDLE_HALF},${CY}`}
              fill="var(--fg-gauge-needle-color)"
            />
            <circle cx={CX} cy={CY} r={14} fill="var(--fg-gauge-needle-color)" />
            <circle cx={CX} cy={CY} r={6} fill="#ffffff" />
          </g>
        )}
      </svg>

      {/* 中央スコア＋バンドラベル（オーバーレイ） */}
      <div className="gauge__readout">
        <div className="fg-score gauge__score">{hasScore ? Math.round(value) : "—"}</div>
        <div className="gauge__band" style={{ color: hasScore ? zone.color : "var(--fg-text-muted)" }}>
          {hasScore ? zone.labelJa : "データなし"}
        </div>
      </div>
    </div>
  );
}
