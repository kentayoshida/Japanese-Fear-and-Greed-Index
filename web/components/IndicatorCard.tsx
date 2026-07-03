"use client";

// 指標内訳カード（cnn-design-brief §2.3）。縦積み。
// eyebrow(カテゴリ) / H3(タイトル) / ミニ時系列(正規化スコア) / 両端ラベル(恐怖⇄貪欲) /
// 現在値・生値・重み・基準日・取得日時 / 日本語の短い説明。

import { Line, LineChart, ReferenceArea, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { Component, ZONES, leanForComponent, colorForScore } from "@/lib/fgi";

const DIMENSION_LABELS: Record<string, string> = {
  momentum: "モメンタム",
  breadth: "ブレッドス",
  volatility: "ボラティリティ",
  hedge_positioning: "ヘッジ / ポジショニング",
  leverage: "レバレッジ / 個人心理",
  safe_haven: "安全資産選好",
};

// 指標ごとの一言説明（データに description が無い場合のフォールバック）。
const DESCRIPTIONS: Record<string, string> = {
  momentum_125dma: "株価指数と125日移動平均の乖離。上方乖離は強気。",
  advance_decline_25: "値上がり÷値下がり銘柄数の25日累積。市場の幅。",
  new_high_low: "新高値−新安値のネット銘柄数。株価の地力。",
  nikkei_vi: "日経平均の予想変動率。高いほど不安（反転）。",
  put_call_ratio: "プット÷コール出来高。高いほどヘッジ需要（反転）。",
  short_selling_ratio: "売買代金に占める空売り比率。高いほど弱気（反転）。",
  margin_pl_ratio: "信用買いの含み損益率。低いほど個人の恐怖。",
  safe_haven: "株式と債券の20日リターン差。株式優位なら強気。",
};

function formatFetched(iso?: string): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleString("ja-JP", {
    year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

function MiniSpark({ data }: { data: { d: string; s: number | null }[] }) {
  const valid = data.filter((p) => typeof p.s === "number");
  if (valid.length < 2) {
    return <div className="spark spark--empty">データ蓄積中…</div>;
  }
  return (
    <div className="spark">
      <ResponsiveContainer width="100%" height={60}>
        <LineChart data={data} margin={{ top: 3, right: 2, bottom: 0, left: 2 }}>
          {ZONES.map((z) => (
            <ReferenceArea key={z.key} y1={z.min} y2={z.max} fill={z.color}
                           fillOpacity={0.12} ifOverflow="extendDomain" />
          ))}
          <XAxis dataKey="d" hide />
          <YAxis domain={[0, 100]} hide />
          <Line type="monotone" dataKey="s" stroke="#1a1d21" strokeWidth={1.5}
                dot={false} isAnimationActive={false} connectNulls />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function IndicatorCard({
  c,
  generatedAt,
}: {
  c: Component;
  generatedAt?: string;
}) {
  const lean = leanForComponent(c);
  const fetched = formatFetched(generatedAt);
  const spark = c.spark ?? [];

  return (
    <article className={`indicator-card ${c.stale ? "is-stale" : ""}`}>
      <div className="indicator-card__top">
        <div>
          <div className="fg-eyebrow">{DIMENSION_LABELS[c.dimension] ?? c.dimension}</div>
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

      <div className="indicator-card__chartrow">
        <div className="indicator-card__ends" aria-hidden="true">
          <span>貪欲</span>
          <span>恐怖</span>
        </div>
        <MiniSpark data={spark} />
      </div>

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
        {c.data_date && <span className="indicator-card__asof">基準日 {c.data_date}</span>}
        {fetched && <span className="indicator-card__fetched">取得 {fetched}</span>}
      </div>

      <p className="indicator-card__desc">{c.description || DESCRIPTIONS[c.id] || ""}</p>
    </article>
  );
}
