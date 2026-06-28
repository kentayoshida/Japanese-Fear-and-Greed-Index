"use client";

// 指標内訳カード。仕様 §6.5。
// 各指標に小型ゲージ（横バー）＋現在値＋ラベル（Fear/Greed どちら寄りか）。

import { Component, ZONES, leanForComponent, colorForScore } from "@/lib/fgi";

const DIMENSION_LABELS: Record<string, string> = {
  momentum: "モメンタム",
  breadth: "ブレッドス",
  volatility: "ボラティリティ",
  hedge_positioning: "ヘッジ / ポジショニング",
  leverage: "レバレッジ / 個人心理",
  safe_haven: "安全資産選好",
};

// 指標ごとの一言説明（日本語オリジナル）。
const DESCRIPTIONS: Record<string, string> = {
  momentum_125dma: "日経平均と125日移動平均の乖離。上方乖離は強気。",
  advance_decline_25: "値上がり÷値下がり銘柄数の25日累積。市場の幅。",
  new_high_low: "新高値−新安値のネット銘柄数。株価の地力。",
  nikkei_vi: "日経平均の予想変動率。高いほど不安（反転）。",
  put_call_ratio: "プット÷コール出来高。高いほどヘッジ需要（反転）。",
  short_selling_ratio: "売買代金に占める空売り比率。高いほど弱気（反転）。",
  margin_pl_ratio: "信用買いの含み損益率。低いほど個人の恐怖。",
  safe_haven: "株式と債券の20日リターン差。株式優位なら強気。",
};

function MiniBar({ score }: { score: number | null }) {
  return (
    <div className="minibar">
      <div className="minibar__track">
        {ZONES.map((z) => (
          <div
            key={z.key}
            className="minibar__zone"
            style={{ left: `${z.min}%`, width: `${z.max - z.min}%`, background: z.color, opacity: 0.35 }}
          />
        ))}
        {score !== null && (
          <div className="minibar__marker" style={{ left: `${Math.max(0, Math.min(100, score))}%` }} />
        )}
      </div>
    </div>
  );
}

export default function IndicatorCard({ c }: { c: Component }) {
  const lean = leanForComponent(c);
  return (
    <div className={`indicator-card ${c.stale ? "is-stale" : ""}`}>
      <div className="indicator-card__top">
        <div>
          <div className="indicator-card__dim">{DIMENSION_LABELS[c.dimension] ?? c.dimension}</div>
          <h3 className="indicator-card__label">{c.label}</h3>
        </div>
        <div className="indicator-card__score">
          {c.score !== null ? (
            <span style={{ color: colorForScore(c.score) }}>{Math.round(c.score)}</span>
          ) : (
            <span className="muted">—</span>
          )}
        </div>
      </div>

      <MiniBar score={c.score} />

      <div className="indicator-card__meta">
        {c.stale ? (
          <span className="badge badge--stale">データ未取得（合成から除外）</span>
        ) : (
          lean && (
            <span className="badge" style={{ color: lean.color, borderColor: lean.color }}>
              {lean.text}寄り
            </span>
          )
        )}
        <span className="indicator-card__raw">
          生値: {c.raw !== null ? c.raw.toLocaleString(undefined, { maximumFractionDigits: 2 }) : "—"}
        </span>
        <span className="indicator-card__weight">重み {(c.weight * 100).toFixed(1)}%</span>
      </div>

      <p className="indicator-card__desc">{DESCRIPTIONS[c.id] ?? ""}</p>
    </div>
  );
}
